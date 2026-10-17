"""N1 replacement inputs fail before cloud calls; media stays draft scoped."""
import io
import json
import wave

import pytest
from PIL import Image

from backlot.studio import Studio
from backlot.studio_n1 import TEMPLATE_ID, settings
from backlot.work_catalog import WorkError


@pytest.fixture
def studio(tmp_path):
    return Studio(tmp_path / "projects")


def draft(studio, n1=None):
    return studio.save_draft({"template_id": TEMPLATE_ID, "title": "本期用户标题", "text": "本期讲解。",
                              "input": {"soundMode": "audio", "n1": n1 or {}}})


def image(studio, d):
    buffer = io.BytesIO()
    Image.new("RGB", (640, 480), "navy").save(buffer, format="PNG")
    return studio.save_asset(d["id"], "来源.png", "image", buffer.getvalue())


def test_default_is_current_title_and_incomplete_scenes_can_be_saved(studio):
    d = draft(studio)
    result = settings(d)
    assert result["titleLines"] == ["本期用户标题", "", ""]
    assert result["scenes"] == []
    saved = studio.save_draft({**d, "input": {**d["input"], "n1": {"scenes": [{"kind": "material", "start": 0, "end": 3}]}}})
    assert saved["revision"] == 2
    with pytest.raises(WorkError, match="项目内图片或视频"):
        settings(saved)


@pytest.mark.parametrize("n1", [
    {"titleLines": ["不合规"]}, {"titleLines": ["长" * 17, "", ""]},
    {"brand": ""}, {"api_key": "should-never-save-as-layout"},
    {"scenes": [{"kind": "data", "start": 0, "end": 3, "dataTitle": "数据", "rows": ["长" * 18]}]},
    {"scenes": [{"kind": "presenter", "start": True, "end": 3}]},
    {"scenes": [{"kind": "presenter", "start": 0, "end": float("nan")}]},
    {"scenes": [{"kind": "presenter", "start": 0, "end": 4}, {"kind": "presenter", "start": 3, "end": 6}]},
])
def test_bad_n1_rejected_before_any_gateway(studio, monkeypatch, n1):
    from backlot.studio_avatar import quote
    d = draft(studio, n1)
    def forbidden(*args): raise AssertionError("invalid layout must not access cloud or upload")
    monkeypatch.setattr(studio, "client", forbidden)
    with pytest.raises(WorkError): quote(studio, d)


def test_other_templates_reject_n1_fields_and_n1_cannot_route_to_ai(studio):
    with pytest.raises(WorkError, match="不支持的字段"):
        studio.save_draft({"template_id": "avatar-safe-circle-v1", "input": {"n1": {}}})
    d = draft(studio)
    for values in ({"ai": {"enabled": True}}, {"motion": {"style": "other"}}):
        with pytest.raises(WorkError, match="手工画面"):
            settings({**d, "input": {**d["input"], **values}})


def test_scene_ownership_duration_and_highlight_are_checked(studio):
    d = draft(studio)
    a = image(studio, d)
    scene = {"kind": "screenshot", "start": 3, "end": 6, "assetId": a["id"], "asset": a,
             "highlights": [{"x": .1, "y": .5, "width": .8, "start": .2, "duration": .4}]}
    d = {**d, "input": {**d["input"], "n1": {"scenes": [scene]}}}
    assert settings(d, 6, studio)["scenes"][0]["assetId"] == a["id"]
    with pytest.raises(WorkError, match="超出实际配音"):
        settings(d, 5, studio)
    other = draft(studio)
    with pytest.raises(WorkError, match="不属于此项目"):
        settings({**d, "id": other["id"]}, 6, studio)
    for patch in ({"fit": "cover"}, {"highlights": [{"x": .8, "y": .5, "width": .8}]},
                  {"highlights": [{"x": .1, "y": .5, "width": .8, "start": 2.9, "duration": .4}]}):
        with pytest.raises(WorkError):
            settings({**d, "input": {**d["input"], "n1": {"scenes": [{**scene, **patch}]}}}, 6, studio)


def test_n1_props_copy_scoped_asset_with_screenshot_dimensions(studio):
    from backlot.studio_composition import n1_props
    d = draft(studio)
    a = image(studio, d)
    d = {**d, "input": {**d["input"], "n1": {"scenes": [{"kind": "screenshot", "start": 0, "end": 3, "assetId": a["id"]}]}}}
    folder = studio.projects_root / d["id"] / "renders" / "test-n1"
    (folder / "public").mkdir(parents=True)
    props = n1_props(folder, d, 3, [])
    s = props["scenes"][0]
    assert (s["assetWidth"], s["assetHeight"], s["mediaKind"], s["src"]) == (640, 480, "image", "n1-0.png")
    assert (folder / "public" / s["src"]).read_bytes() == studio.asset(a["id"]).read_bytes()
    assert props["avatarSrc"] == "avatar.mp4" and props["audioSrc"] == "narration.wav"
    assert json.loads((folder / "n1-sources.json").read_text())["sources"][0]["asset_id"] == a["id"]


def test_asset_video_is_not_looped_or_stretched(studio, monkeypatch):
    d = draft(studio)
    source = studio.projects_root / d["id"] / "source.mp4"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"not-used-by-mock")
    monkeypatch.setattr(studio, "asset", lambda *args: source)
    monkeypatch.setattr("backlot.studio_render.media_probe", lambda path: {"duration": 3})
    scene = {"kind": "material", "start": 0, "end": 3, "offset": 1, "assetId": "a" * 32}
    with pytest.raises(WorkError, match="时长不足"):
        settings({**d, "input": {**d["input"], "n1": {"scenes": [scene]}}}, 5, studio)


def test_atelier_stages_public_layout_but_never_other_json(tmp_path):
    from tools.video.video_compose import VideoCompose
    source = tmp_path / "template"
    source.mkdir()
    (source / "index.tsx").write_text("import layout from './layout.json'", encoding="utf-8")
    (source / "layout.json").write_text('{"width":1080}', encoding="utf-8")
    for name in ("props.json", "client-config.json", "gateway-state.json"):
        (source / name).write_text('{"private":"fixture"}', encoding="utf-8")
    composer = tmp_path / "composer"
    composer.mkdir()
    entry = VideoCompose()._stage_atelier_project(source / "index.tsx", composer)
    assert entry.is_file() and (entry.parent / "layout.json").is_file()
    assert not any((entry.parent / name).exists() for name in ("props.json", "client-config.json", "gateway-state.json"))


def development_request(studio):
    from backlot.studio_avatar import key_identity
    d = draft(studio)
    d["input"]["subtitles"] = False
    project = studio.projects_root / d["id"]
    output = project / "renders" / "sample"
    output.mkdir(parents=True)
    (output / "avatar-source.mp4").write_bytes(b"existing-local-avatar")
    audio = project / "silent.wav"
    with wave.open(str(audio), "wb") as stream:
        stream.setparams((1, 2, 24000, 72000, "NONE", "not compressed"))
        stream.writeframes(bytes(72000 * 2))
    return project, {"id": "private-layout-sample", "draft": d, "render_id": "sample", "quotes": {},
                     "prepared": {"audio_path": str(audio), "duration": 3}, "key_identity": key_identity(studio),
                     "development_sample": {"silent": True, "label": "版式与动效演示", "captions": [{"text": "手工字幕演示", "startMs": 0, "endMs": 3000}]}}


def test_development_sample_never_creates_client_or_asr_and_labels_manual_cues(studio, monkeypatch):
    from backlot.studio_avatar import run_avatar
    project, request = development_request(studio)
    def forbidden(*args): raise AssertionError("development samples cannot contact providers")
    monkeypatch.setattr(Studio, "client", forbidden)
    monkeypatch.setattr("backlot.studio_avatar.media_probe", lambda path: {"duration": 3, "audio": True, "video": {"width": 448}})
    observed = []
    def compose(folder, d, video, audio, duration, cues):
        observed.extend(cues)
        result = folder / "avatar-preview.mp4"
        result.write_bytes(b"rendered-layout-sample")
        return result
    monkeypatch.setattr("backlot.studio_composition.compose_avatar", compose)
    result = run_avatar(project, request)
    assert result["status"] == "completed"
    assert observed == [{"text": "手工字幕演示", "startMs": 0, "endMs": 3000, "timestampMs": None, "confidence": None}]
    qa = json.loads((project / "renders/sample/qa.json").read_text(encoding="utf-8"))
    assert qa["caption_timing"] == "illustrative_manual"
    assert qa["provider_jobs"] == [] and qa["development_sample"]["cloud_calls"] == 0


def test_development_sample_checks_actual_silence_and_existing_video(studio, monkeypatch):
    from backlot.studio_avatar import development_captions
    project, request = development_request(studio)
    output = project / "renders/sample"
    monkeypatch.setattr("backlot.studio_avatar.media_probe", lambda path: {"duration": 3, "audio": True, "video": True})
    assert len(development_captions(request, project, output)) == 1
    audio = project / "silent.wav"
    data = bytearray(audio.read_bytes())
    data[-1] = 1
    audio.write_bytes(data)
    with pytest.raises(WorkError, match="全零音轨"):
        development_captions(request, project, output)
    (output / "avatar-source.mp4").unlink()
    with pytest.raises(WorkError, match="已有的人物"):
        development_captions(request, project, output)


def test_development_sample_cannot_enter_public_draft_quote_or_generate(studio, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backlot.studio_api import router
    d = draft(studio)
    app = FastAPI()
    app.state.studio = studio
    app.include_router(router)
    client = TestClient(app)
    def forbidden(*args): raise AssertionError("public development flag must be rejected before provider access")
    monkeypatch.setattr(studio, "client", forbidden)
    flag = {"silent": True, "label": "版式与动效演示", "captions": []}
    assert client.post("/api/studio/drafts", json={**d, "development_sample": flag}).status_code == 422
    assert client.post("/api/studio/drafts", json={**d, "input": {**d["input"], "development_sample": flag}}).status_code == 422
    for action in ("quote", "generate"):
        assert client.post(f"/api/studio/drafts/{d['id']}/{action}", json={"revision": d["revision"], "development_sample": flag}).status_code == 422
