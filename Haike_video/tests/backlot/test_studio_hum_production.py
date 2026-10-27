"""Isolated reusable speech-clock contract checks; no provider or media claims."""
from copy import deepcopy
from array import array
import json
import math
from pathlib import Path
import struct
import wave

import pytest
from PIL import Image

from backlot import studio_hum_production as hum
from backlot.production_queue import ProductionQueue
from backlot.production_queue_worker import ProductionQueueWorker
from backlot.studio import atomic_private
from backlot.work_catalog import WorkError, sha


def pcm(path, seconds, rate=24000):
    # A nonzero signal proves the adapter is not accepting silent placeholders.
    sample = struct.pack("<h", 1000)
    with wave.open(str(path), "wb") as stream:
        stream.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        stream.writeframes(sample * round(seconds * rate))


@pytest.fixture
def sample(tmp_path, monkeypatch):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    template = tmp_path / "template"
    template.mkdir()
    (template / "index.tsx").write_text("export const isolated=true;", encoding="utf-8")
    monkeypatch.setattr(hum, "TEMPLATE", template)
    monkeypatch.setattr(hum, "runtime", lambda: {str(template / "index.tsx"): sha(template / "index.tsx")})
    monkeypatch.setattr(hum, "_validate_fonts", lambda *_: None)
    monkeypatch.setattr(hum, "media_probe", lambda path: {"duration": 200, "video": {"width": 1920, "height": 1080}, "audio": {"codec_name": "pcm_s16le"}})
    paths = {}
    for name in ("voice.wav", "music.wav", "click.wav", "display.ttf", "body.ttf"):
        paths[name] = inputs / name
        paths[name].write_bytes(b"isolated-unrendered-fixture-" + name.encode())
    pcm(paths["voice.wav"], 20)
    media, reviews = [], []
    for index in range(4):
        src, poster = f"video-{index}.mp4", f"poster-{index}.jpg"
        paths[src], paths[poster] = inputs / src, inputs / poster
        paths[src].write_bytes(f"isolated-video-{index}".encode())
        Image.new("RGB", (800, 640), "#E8E2D5").save(paths[poster])
        media.append({"id": f"m{index}", "src": src, "thumbnail": poster, "offset": 1, "fit": "contain", "label": "本地素材"})
        reviews.append({"id": f"m{index}", "source_sha256": sha(paths[src]), "thumbnail_sha256": sha(paths[poster]), "reviewed": True,
                        "description": "Isolated test fixture; not a real visual review", "source_start_seconds": 0, "source_end_seconds": 100, "observed_frames": [1, 3]})
    value = {"title": "隔离合同测试", "props": {"brand": "海客", "footer": "欢迎来店体验", "visualStyle": "hum", "media": media,
              "fontAssets": {"display": "display.ttf", "body": "body.ttf"}, "captions": [{"text": "这是实际时码占位测试", "startMs": 100, "endMs": 19000}]},
             "shotPlan": [{"id": "wall", "module": "wall", "theme": "paper", "title": "来看看现场", "subtitle": "今天的体验", "mediaId": "m0", "wallMediaIds": ["m0", "m1", "m2", "m3"], "weight": 1},
                          {"id": "focus", "module": "focus", "theme": "dark", "title": "亲手试一试", "mediaId": "m1", "weight": 1},
                          {"id": "end", "module": "statement", "theme": "paper", "title": "欢迎来店", "weight": .5}],
             "sources": {n: str(p) for n, p in paths.items()}, "audio": {"voice": "voice.wav", "music": "music.wav", "tailSeconds": .25},
             "provenance": {"voice": {"sha256": sha(paths["voice.wav"]), "source": "isolated test PCM; not published narration", "authorized": True},
                            "captions": {"voice_sha256": sha(paths["voice.wav"]), "method": "isolated unit fixture only"},
                            "audio": {"music.wav": {"sha256": sha(paths["music.wav"]), "source": "test fixture"}}, "media": reviews}}
    # An undeclared sound is rejected instead of silently ingested.
    value["sources"].pop("click.wav")
    return {"value": value, "paths": paths, "template": template, "queue": ProductionQueue(tmp_path / "queue.sqlite3", tmp_path / "projects")}


@pytest.mark.parametrize("seconds", [20, 35, 60])
def test_duration_is_full_voice_sample_clock_with_frame_aligned_tail(sample, seconds):
    value = sample["value"]
    pcm(sample["paths"]["voice.wav"], seconds)
    value["provenance"]["voice"]["sha256"] = sha(sample["paths"]["voice.wav"])
    value["provenance"]["captions"]["voice_sha256"] = sha(sample["paths"]["voice.wav"])
    checked = hum.preflight(value)
    props = checked["props"]
    assert props["durationFrames"] == seconds * 30 + 8
    assert props["width"] * 5 == props["height"] * 4
    assert checked["audio"]["voice_clock"]["samples"] == seconds * 24000
    assert sum(s["frames"] for s in props["scenes"]) == props["durationFrames"]
    assert all(a["from"] + a["frames"] == b["from"] for a, b in zip(props["scenes"], props["scenes"][1:]))


def test_scene_plan_compresses_to_legal_wall_window_and_rejects_too_short():
    plan = [{"module": "wall"}, {"module": "statement"}]
    scenes = hum.plan_scenes(plan, 138)
    select = scenes[0]["selection"]
    assert select["cursorFrom"] < select["selectFrom"] < select["expandFrom"] < select["holdFrom"]
    assert scenes[0]["frames"] - select["holdFrom"] >= 30
    assert scenes[1]["from"] == scenes[0]["frames"]
    with pytest.raises(WorkError, match="口播太短"):
        hum.plan_scenes(plan, 137)


def test_card_stack_preserves_distribution_window_and_odd_card_count(sample):
    value = sample['value']
    value['shotPlan'][0]['motion'] = 'card-stack'
    value['shotPlan'][0]['wallMediaIds'] = ['m0', 'm1', 'm2']
    value['props']['media'].pop()
    value['provenance']['media'].pop()
    value['sources'].pop('video-3.mp4')
    value['sources'].pop('poster-3.jpg')
    props = hum.preflight(value)['props']
    assert props['scenes'][0]['selection']['expandFrom'] == 142
    assert props['scenes'][0]['selection']['holdFrom'] == 160
    value['shotPlan'][0]['wallMediaIds'].append('m0')
    with pytest.raises(WorkError, match='素材墙须有'):
        hum.preflight(value)


def test_paper_reveal_is_bound_to_focus_and_unknown_motion_is_blocked(sample):
    value = sample['value']
    value['shotPlan'][1]['motion'] = 'paper-reveal'
    hum.preflight(value)
    value['shotPlan'][0]['motion'] = 'paper-reveal'
    with pytest.raises(WorkError, match='动效与场景模块'):
        hum.preflight(value)


def test_fractional_clock_uses_pcm_samples_not_rounded_seconds(sample):
    pcm(sample["paths"]["voice.wav"], 20.123)
    value = sample["value"]
    voice_sha = sha(sample["paths"]["voice.wav"])
    value["provenance"]["voice"]["sha256"] = voice_sha
    value["provenance"]["captions"]["voice_sha256"] = voice_sha
    checked = hum.preflight(value)
    assert checked["props"]["durationFrames"] == 612
    value["props"]["durationFrames"] = 600
    with pytest.raises(WorkError, match="不能手工覆盖"):
        hum.preflight(value)


@pytest.mark.parametrize("mutation,match", [
    ("short_media", "实际播放长度"), ("wrong_voice", "口播来源"), ("wrong_captions", "字幕缺少"),
    ("unreviewed", "未看帧"), ("source_speed", "未开放参数"), ("audio_duplicate", "未开放参数"),
    ("unsafe_path", "安全"), ("unused_input", "sources与声明"), ("caption_overrun", "字幕须绑定"),
    ("unknown_style", "视觉风格"), ("fixed_and_auto", "只能选择一种"), ("sfx_overrun", "音效长度"),
])
def test_source_and_timing_gates(sample, mutation, match, monkeypatch):
    value = sample["value"]
    if mutation == "short_media":
        value["provenance"]["media"][0]["source_end_seconds"] = 2
        value["provenance"]["media"][0]["observed_frames"] = [1]
    elif mutation == "wrong_voice": value["provenance"]["voice"]["sha256"] = "0" * 64
    elif mutation == "wrong_captions": value["provenance"]["captions"]["voice_sha256"] = "0" * 64
    elif mutation == "unreviewed": value["provenance"]["media"][0]["reviewed"] = False
    elif mutation == "source_speed": value["props"]["media"][0]["playbackRate"] = 2
    elif mutation == "audio_duplicate": value["props"]["media"][0]["muted"] = False
    elif mutation == "unsafe_path": value["props"]["media"][0]["src"] = "../source.mp4"
    elif mutation == "unused_input": value["sources"]["click.wav"] = str(sample["paths"]["click.wav"])
    elif mutation == "caption_overrun": value["props"]["captions"][0]["endMs"] = 20200
    elif mutation == "unknown_style": value["props"]["visualStyle"] = "unadapted"
    elif mutation == "fixed_and_auto": value["props"]["scenes"] = []
    elif mutation == "sfx_overrun":
        value["sources"]["click.wav"] = str(sample["paths"]["click.wav"])
        value["audio"]["sfx"] = [{"src": "click.wav", "atSeconds": 20}]
        monkeypatch.setattr(hum, "media_probe", lambda _: {"duration": 1, "audio": {"codec_name": "pcm_s16le"}})
        value["audio"].pop("music")
    with pytest.raises(WorkError, match=match):
        hum.preflight(value)


def add_presenter(sample):
    value, paths = sample["value"], sample["paths"]
    paths["presenter.mp4"] = paths["voice.wav"].parent / "presenter.mp4"
    paths["presenter.mp4"].write_bytes(b"isolated-unrendered-avatar")
    value["sources"]["presenter.mp4"] = str(paths["presenter.mp4"])
    value["props"]["presenterClips"] = [{"id": "p", "src": "presenter.mp4", "from": 120, "frames": 210, "offset": 2}]
    value["props"]["presenterModes"] = [{"clipId": "p", "from": 120, "frames": 90, "mode": "large"},
                                       {"clipId": "p", "from": 210, "frames": 60, "mode": "hidden"},
                                       {"clipId": "p", "from": 270, "frames": 60, "mode": "small"}]
    value["provenance"]["presenterClips"] = [{"id": "p", "source_sha256": sha(paths["presenter.mp4"]), "voice_sha256": sha(paths["voice.wav"]),
                     "reviewed": True, "globalFrom": 120, "sourceOffset": 2, "frames": 210}]
    return value


def test_large_hidden_small_share_continuous_global_source_clock(sample):
    value = add_presenter(sample)
    props = hum.preflight(value)["props"]
    clip = props["presenterClips"][0]
    modes = props["presenterModes"]
    assert [clip["offset"] + (m["from"] - clip["from"]) / 30 for m in modes] == [2, 5, 7]
    assert [m["mode"] for m in modes] == ["large", "hidden", "small"]
    value["props"]["presenterModes"][2]["from"] = 269
    with pytest.raises(WorkError, match="重叠"):
        hum.preflight(value)


def test_presenter_cannot_escape_same_voice_or_source_range(sample, monkeypatch):
    value = add_presenter(sample)
    value["provenance"]["presenterClips"][0]["voice_sha256"] = "0" * 64
    with pytest.raises(WorkError, match="人物片段须绑定"):
        hum.preflight(value)
    value["provenance"]["presenterClips"][0]["voice_sha256"] = sha(sample["paths"]["voice.wav"])
    original = hum.media_probe
    monkeypatch.setattr(hum, "media_probe", lambda path: {"duration": 8, "video": {"width": 1440, "height": 1800}} if Path(path).name == "presenter.mp4" else original(path))
    with pytest.raises(WorkError, match="人物原片长度不足"):
        hum.preflight(value)


def test_none_presenter_is_supported_without_any_fake_clip(sample):
    checked = hum.preflight(sample["value"])
    assert not checked["props"].get("presenterClips") and not checked["props"].get("presenterModes")


def test_freeze_idempotency_resume_and_source_tamper(sample):
    queue, value = sample["queue"], sample["value"]
    request = hum.prepare(queue, value)
    assert hum.prepare(queue, value) == request
    job = hum.submit(queue, request)
    assert hum.submit(queue, request)["job_id"] == job["job_id"]
    project = hum.validate(queue, request)
    assert read_json(project / "artifacts" / hum.REQUEST_FILE) == request
    assert not (project / "renders" / request["render_id"]).exists()
    frozen_voice = project / "assets" / hum.CONTRACT / "voice.wav"
    pcm(frozen_voice, 19)
    with pytest.raises(WorkError, match="冻结来源文件已改变"):
        hum.validate(queue, request)


def test_completed_output_recovers_without_current_runtime_but_binds_output(sample, monkeypatch):
    request = hum.prepare(sample["queue"], sample["value"])
    project = hum.validate(sample["queue"], request)
    folder = project / "renders" / request["render_id"]
    folder.mkdir(parents=True)
    (folder / hum.OUTPUT_FILE).write_bytes(b"isolated-completed-result-not-real-video")
    atomic_private(folder / "quality.json", {"visual_review": "pending", "fixture": True})
    atomic_private(folder / "result.json", {"request_sha256": request["request_sha256"], "output_sha256": sha(folder / hum.OUTPUT_FILE), "quality_sha256": sha(folder / "quality.json")})
    monkeypatch.setattr(hum, "runtime", lambda: {"changed": "runtime"})
    assert hum.validate(sample["queue"], request) == project
    (folder / hum.OUTPUT_FILE).write_bytes(b"tampered")
    with pytest.raises(WorkError, match="成片或质量记录"):
        hum.validate(sample["queue"], request)


def test_queue_worker_dispatches_new_contract_without_using_twenty_second_adapter(sample, monkeypatch):
    expected = {"status": "completed", "stage": "fixture", "result": {}}
    monkeypatch.setattr(hum, "run", lambda queue, job: expected)
    worker = ProductionQueueWorker(sample["queue"], sample["queue"].projects_root)
    assert worker._run_investment_recompose({"frozen_request": {"contract": hum.CONTRACT}}) is expected


def test_verified_motiongit_package_exposes_new_reusable_workflow_and_freezes_bound_assets(sample, monkeypatch):
    from backlot import studio_motiongit as motion
    from backlot import studio_motiongit_render as render
    monkeypatch.setattr(motion, 'STORE', sample['paths']['voice.wav'].parent.parent / 'motiongit')
    package = {'id': 'mg-hum-fixture', 'template_id': 'motiongit-promo-user', 'verification': 'verified', 'sha256': 'isolated-package',
               'workflows': {'project-wall': {'schema': {}, 'implementation': 'motiongit-narrated-pilot-v1'}}}
    motion._put_package(package)
    exposed = motion.public_package(motion._get('packages', package['id']))
    assert exposed['workflows']['hum-production']['implementation'] == hum.CONTRACT
    assert exposed['workflows']['project-wall']['implementation'] == 'motiongit-narrated-pilot-v1'
    parameters = {k: deepcopy(v) for k, v in sample['value'].items() if k not in {'title', 'sources'}}
    draft = motion.save_draft(package['id'], 'hum-production', parameters, title=sample['value']['title'], output_profile='4:5')
    for name, path in sample['value']['sources'].items():
        motion.save_asset(draft['id'], name, Path(path).read_bytes())
    assert motion.validate_draft(draft['id'])['valid']
    request = render.freeze(sample['queue'], draft['id'])
    assert request['contract'] == hum.CONTRACT
    assert render.recorded_request(sample['queue'], draft['id'], request['render_id']) == request
    submitted = render.submit(sample['queue'], request)
    assert sample['queue'].get(submitted['job_id'], include_private=True)['frozen_request']['contract'] == hum.CONTRACT
    motion.save_asset(draft['id'], 'voice.wav', b'changed-bound-voice')
    with pytest.raises(WorkError, match='素材或口播绑定已变更'):
        render.recorded_request(sample['queue'], draft['id'], request['render_id'])


def test_api_serves_completed_hum_sample_with_bounded_render_identity(sample, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backlot import studio_motiongit_api as api
    monkeypatch.setattr(api, '_queue', lambda _: sample['queue'])
    app = FastAPI()
    app.include_router(api.router)
    client = TestClient(app)
    project_id, render_id = 'studio-' + 'a' * 16, 'hum-production-v1-' + 'b' * 20
    folder = sample['queue'].projects_root / project_id / 'renders' / render_id
    folder.mkdir(parents=True)
    (folder / hum.OUTPUT_FILE).write_bytes(b'isolated-media-placeholder')
    url = f'/api/studio/motiongit/productions/{project_id}/{render_id}'
    result = client.get(url)
    assert result.status_code == 200 and result.json()['sample'].endswith('/hum-production.mp4')
    assert client.get(url + '/media/hum-production.mp4').content == b'isolated-media-placeholder'
    assert client.get(url.replace(render_id, 'hum-production-v1-../unsafe')).status_code == 404


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize('seconds', [20, 35, 60])
def test_real_ffmpeg_mix_keeps_exact_sample_clock_and_declared_sources(tmp_path, seconds):
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    from backlot.studio_investment_audio_v5 import measure_audio
    # This is a genuine local audio integration test, separate from the mocked
    # contract fixtures above. It does not represent real narration/avatar QA.
    resolve_ffmpeg_pair()
    paths = {name: tmp_path / name for name in ('voice.wav', 'music.wav', 'click.wav')}
    for name, duration, frequency in [('voice.wav', seconds, 220), ('music.wav', seconds + 1, 440), ('click.wav', .1, 880)]:
        rate = 24000
        content = array('h', (round(4000 * math.sin(2 * math.pi * frequency * n / rate)) for n in range(round(duration * rate))))
        with wave.open(str(paths[name]), 'wb') as stream:
            stream.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
            stream.writeframes(content.tobytes())
    clock = hum._clock(paths['voice.wav'])
    plan = hum._audio_plan({'voice': 'voice.wav', 'music': 'music.wav', 'sfx': [{'src': 'click.wav', 'atSeconds': 1.5}]}, paths, clock)
    output = tmp_path / 'master.wav'
    receipt = hum.mix_master(plan, paths, output)
    with wave.open(str(output), 'rb') as stream:
        assert stream.getnframes() == (seconds * 30 + 8) * 1600
        assert (stream.getframerate(), stream.getnchannels(), stream.getsampwidth()) == (48000, 2, 2)
    assert receipt['voice_sha256'] == sha(paths['voice.wav'])
    assert receipt['voice_clock']['samples'] == seconds * 24000
    assert not receipt['speech_stretched'] and not receipt['speech_reordered']
    assert measure_audio(output)['true_peak_dbtp'] <= -2.4
