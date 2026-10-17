"""File ASR transport contracts use fake HTTP, temporary files and no paid calls."""
import json

import pytest
import requests

from backlot import bailian_asr
from lib import bailian_speech as api


class Response:
    def __init__(self, data, status=200, content=None):
        self.data, self.status_code = data, status
        self.ok = status < 400
        self.content = content

    def json(self):
        return self.data


TRANSCRIPT = {"transcripts":[{"text":"你好，机器人🤖", "sentences":[
    {"begin_time":120,"end_time":900,"text":"你好", "words":[
        {"begin_time":120,"end_time":400,"text":"你"}, {"begin_time":400,"end_time":900,"text":"好"}]},
    {"begin_time":1000,"end_time":1600,"text":"机器人🤖", "words":[
        {"begin_time":1000,"end_time":1300,"text":"机器人"}, {"begin_time":1300,"end_time":1600,"text":"🤖"}]}]}]}


class Cloud:
    upload_host = "https://fixture.oss-cn-beijing.aliyuncs.com"
    result_url = "https://fixture.oss-cn-beijing.aliyuncs.com/transcript.json"

    def __init__(self):
        self.submits, self.queries, self.downloads = [], [], []
        self.upload_count = 0
        self.submission = Response({"output":{"task_id":"accepted-task"}, "request_id":"fixture-request"})
        self.poll = []
        self.download_failures = []
        self.transcript = TRANSCRIPT

    def post(self, url, **kwargs):
        if url == self.upload_host:
            self.upload_count += 1
            self.upload_key = kwargs["data"]["key"]
            return Response({})
        assert url.endswith("/services/audio/asr/transcription")
        self.submits.append(kwargs)
        if isinstance(self.submission, Exception):
            raise self.submission
        return self.submission

    def get(self, url, **kwargs):
        if url.endswith("/uploads"):
            return Response({"data":{"upload_host":self.upload_host,"upload_dir":"fixture",
                "oss_access_key_id":"fake-upload-id","signature":"fake-upload-signature","policy":"fake-policy"}})
        if "/tasks/" in url:
            self.queries.append(url)
            value = self.poll.pop(0) if self.poll else Response({"output":{"task_status":"SUCCEEDED",
                "results":[{"subtask_status":"SUCCEEDED","transcription_url":self.result_url}]},
                "usage":{"input_tokens":10,"output_tokens":3}})
            if isinstance(value, Exception):
                raise value
            return value
        assert url == self.result_url
        self.downloads.append(url)
        if self.download_failures:
            raise self.download_failures.pop(0)
        return Response({},content=json.dumps(self.transcript,ensure_ascii=False).encode("utf-8"))


@pytest.fixture
def cloud(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY","offline-fixture-key")
    monkeypatch.setenv("DASHSCOPE_WORKSPACE_ID","")
    monkeypatch.setenv("BAILIAN_ASR_STORAGE","temporary")
    fixture = Cloud()
    monkeypatch.setattr(requests,"post",fixture.post)
    monkeypatch.setattr(requests,"get",fixture.get)
    fixture.audio = tmp_path / "source.wav"
    fixture.audio.write_bytes(b"offline transport fixture; no inference")
    fixture.root = tmp_path
    return fixture


def transcribe(cloud, **kwargs):
    return bailian_asr.transcribe_file(cloud.audio,artifact_dir=cloud.root,poll_seconds=0,**kwargs)


@pytest.mark.parametrize("status,code,kind", [
    (401,"InvalidApiKey","invalid_key"),(400,"Arrearage","insufficient_balance"),
    (400,"isv.OUT_OF_SERVICE","insufficient_balance"),(403,"Model.AccessDenied","other"),
])
def test_definitive_submit_rejection_is_classified_before_any_accepted_task(cloud,status,code,kind):
    cloud.submission = Response({"code":code,"message":"offline-fixture-key must stay hidden"},status)
    with pytest.raises(api.BailianSpeechError) as caught:
        transcribe(cloud)
    error = caught.value
    assert error.failure_kind == kind and error.provider_code == code
    assert error.definitive is True and error.accepted is False and error.task_id is None
    assert len(cloud.submits) == 1 and cloud.queries == []
    assert "offline-fixture-key" not in str(error)


@pytest.mark.parametrize("submission", [
    Response({"output":{},"request_id":"missing-task-id"}),
    Response({"code":"InternalError"},503),
    requests.Timeout("submission timed out"),requests.ConnectionError("connection lost"),
])
def test_uncertain_submission_never_resubmits_or_becomes_fallback_permission(cloud,submission):
    cloud.submission = submission
    for _ in range(2):
        with pytest.raises(api.BailianAmbiguous) as caught:
            transcribe(cloud)
        assert caught.value.definitive is False and caught.value.failure_kind == "other"
        assert caught.value.accepted is False
    assert len(cloud.submits) == 1 and cloud.upload_count == 1
    assert cloud.queries == []


@pytest.mark.parametrize("failure,kind,code,http_status", [
    (Response({"code":"InvalidApiKey"},401),"invalid_key","InvalidApiKey",401),
    (Response({"code":"Arrearage"},400),"insufficient_balance","Arrearage",400),
    (requests.Timeout("poll timeout"),"other",None,None),
    (requests.ConnectionError("poll disconnected"),"other",None,None),
    (Response({"code":"InternalError"},500),"other","InternalError",500),
])
def test_accepted_task_poll_failure_preserves_identity_and_forbids_fallback(cloud,failure,kind,code,http_status):
    cloud.poll = [failure]
    with pytest.raises(api.BailianSpeechError) as caught:
        transcribe(cloud)
    error = caught.value
    assert error.accepted is True and error.task_id == "accepted-task"
    assert error.definitive is False
    assert error.failure_kind == kind and error.provider_code == code and error.http_status == http_status
    text,rows,_metadata = transcribe(cloud)
    assert text == "你好，机器人🤖" and rows
    assert len(cloud.submits) == 1 and cloud.upload_count == 1
    assert len(cloud.queries) == 2 and cloud.queries[0] == cloud.queries[1]


def test_preflight_failure_during_resume_knows_previously_accepted_task(cloud,monkeypatch):
    cloud.poll = [requests.Timeout("poll timeout")]
    with pytest.raises(api.BailianSpeechError):
        transcribe(cloud)
    monkeypatch.delenv("DASHSCOPE_API_KEY")
    with pytest.raises(api.BailianSpeechError) as caught:
        transcribe(cloud)
    assert caught.value.accepted is True and caught.value.task_id == "accepted-task"
    assert caught.value.definitive is False
    assert len(cloud.submits) == 1


def test_terminal_cloud_balance_failure_is_still_an_accepted_operation(cloud):
    cloud.poll = [Response({"output":{"task_status":"FAILED","code":"Arrearage","message":"account needs funding"}})]
    with pytest.raises(api.BailianSpeechError) as caught:
        transcribe(cloud)
    assert caught.value.failure_kind == "insufficient_balance"
    assert caught.value.provider_code == "Arrearage"
    assert caught.value.accepted is True and caught.value.definitive is False
    assert caught.value.task_id == "accepted-task"


def test_result_download_failure_resumes_only_saved_result_without_submit_or_poll(cloud):
    cloud.download_failures = [requests.ConnectionError("download disconnected")]
    with pytest.raises(api.BailianSpeechError) as caught:
        transcribe(cloud)
    assert caught.value.accepted is True and caught.value.definitive is False
    assert caught.value.task_id == "accepted-task"
    assert transcribe(cloud)[0] == "你好，机器人🤖"
    assert len(cloud.submits) == 1 and len(cloud.queries) == 1 and len(cloud.downloads) == 2


def test_each_sentence_retains_only_its_own_real_word_clock_and_legacy_flat_metadata(cloud):
    _text,rows,metadata = transcribe(cloud)
    assert rows[0]["words"] == [{"start":.12,"end":.4,"text":"你"},{"start":.4,"end":.9,"text":"好"}]
    assert rows[1]["words"] == [{"start":1.0,"end":1.3,"text":"机器人"},{"start":1.3,"end":1.6,"text":"🤖"}]
    assert metadata["words"] == rows[0]["words"] + rows[1]["words"]
    assert metadata["timestamp_unit"] == "seconds"
    assert cloud.submits[0]["json"]["input"] == {"file_urls":["oss://" + cloud.upload_key]}
    assert isinstance(cloud.submits[0]["json"]["parameters"],dict)


def test_missing_word_time_is_rejected_instead_of_inventing_zero_timestamp(cloud):
    cloud.transcript = {"transcripts":[{"text":"测试","sentences":[{"begin_time":100,"end_time":900,
        "text":"测试","words":[{"end_time":900,"text":"测试"}]}]}]}
    with pytest.raises(api.BailianSpeechError) as caught:
        transcribe(cloud)
    assert caught.value.accepted is True and caught.value.definitive is False
    assert len(cloud.submits) == 1
