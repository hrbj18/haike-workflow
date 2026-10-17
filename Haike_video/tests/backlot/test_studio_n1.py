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


@pytest.fixture
def local_agent_storyboard(studio):
    from types import SimpleNamespace
    from backlot.studio import atomic_private
    from backlot import studio_agent_materials as agent
    from backlot.studio_network_materials import MaterialSearchError
    from backlot.studio_storyboard import produce
    from backlot.work_catalog import sha
    atomic_private(studio.private / 'studio-ai/relay.json', {'analysis_mode': 'agent'})
    d = draft(studio)
    d = studio.save_draft({**d, 'input': {**d['input'], 'network_materials_enabled': False, 'ai': {'enabled': True}}})
    a = image(studio, d)
    cues = [{'text': '第一句。', 'startMs': 0, 'endMs': 1400}, {'text': '第二句。', 'startMs': 1600, 'endMs': 3200}]
    folder = agent.directory(studio, d)
    def forbidden(*args): pytest.fail('local Agent N1 must not search or invoke another model')
    with pytest.raises(MaterialSearchError):
        produce(studio, d, folder, cues, 3.2, forbidden, audio_sha256='a' * 64)
    context = agent.context(studio, d)
    assert context['audio_sha256'] == 'a' * 64
    scenes = [{'from_cue': i, 'to_cue': i, 'script_start': i * 4, 'script_end': (i + 1) * 4,
               'label': '已审本地图片', 'asset_id': a['id'], 'query': '', 'illustration_prompt': '',
               'reason': 'Agent已观察本机授权图片，配合本句展示'} for i in range(2)]
    agent.apply(studio, d, {'draft_revision': d['revision'], 'clock_sha256': context['clock_sha256'], 'scenes': scenes,
        'materials': [{'asset_id': a['id'], 'sha256': sha(studio.asset(a['id'], d['id'])), 'source': 'user',
                       'rights_confirmed': True, 'observed_frames': [0], 'reason': '已观察640×480的蓝色图片'}]})
    plan = produce(studio, d, folder, cues, 3.2, forbidden, audio_sha256='a' * 64)
    return SimpleNamespace(studio=studio, draft=d, asset=a, cues=cues, folder=folder, plan=plan)


def test_n1_local_agent_assets_enter_real_clock_bound_render_props(local_agent_storyboard):
    from copy import deepcopy
    from backlot.studio_composition import n1_props
    from backlot.work_catalog import sha
    case = local_agent_storyboard
    before = deepcopy(case.draft)
    assert settings(case.draft, studio=case.studio)['scenes'] == []
    assert case.plan['status'] == 'ready' and case.plan['analysis_mode'] == 'agent'
    (case.folder / 'public').mkdir(exist_ok=True)
    props = n1_props(case.folder, case.draft, 3.2, case.cues, case.plan)
    assert [(s['start'], s['end']) for s in props['scenes']] == [(0, 1.6), (1.6, 3.2)]
    assert props['duration'] == 3.2 and props['captions'] == case.cues
    source = case.studio.asset(case.asset['id'], case.draft['id'])
    for scene in props['scenes']:
        assert scene['mediaKind'] == 'image' and (scene['assetWidth'], scene['assetHeight']) == (640, 480)
        assert (case.folder / 'public' / scene['src']).read_bytes() == source.read_bytes()
    receipt = json.loads((case.folder / 'n1-sources.json').read_text(encoding='utf-8'))
    assert all(s['asset_id'] == case.asset['id'] and s['sha256'] == sha(source) for s in receipt['sources'])
    assert case.studio.draft(case.draft['id']) == before


def test_n1_verified_agent_plan_keeps_frozen_route_after_settings_change(local_agent_storyboard):
    from copy import deepcopy
    from backlot.studio import atomic_private
    from backlot.studio_composition import n1_props
    case = local_agent_storyboard
    before = deepcopy(case.draft)
    atomic_private(case.studio.private / 'studio-ai/relay.json', {'analysis_mode': 'relay'})
    with pytest.raises(WorkError, match='手工画面'):
        settings(case.draft, studio=case.studio)
    (case.folder / 'public').mkdir(exist_ok=True)
    props = n1_props(case.folder, case.draft, 3.2, case.cues, case.plan)
    assert [s['assetId'] for s in props['scenes']] == [case.asset['id']] * 2
    assert [(s['start'], s['end']) for s in props['scenes']] == [(0, 1.6), (1.6, 3.2)]
    assert case.draft == before and case.studio.draft(case.draft['id']) == before


@pytest.mark.parametrize('change', ['sha', 'clock', 'tail', 'pending', 'relay', 'disabled', 'no_studio', 'motion', 'network_only_user'])
def test_n1_local_agent_cannot_bypass_original_media_clock_or_policy(local_agent_storyboard, change):
    from copy import deepcopy
    from backlot.studio_n1 import storyboard_settings
    case = local_agent_storyboard
    d, plan, studio = deepcopy(case.draft), deepcopy(case.plan), case.studio
    if change == 'sha': plan['scenes'][0]['asset_sha256'] = 'f' * 64
    elif change == 'clock': plan['scenes'][1]['start'] = 1.7
    elif change == 'tail': plan['scenes'][-1]['end'] = 3.1
    elif change == 'pending': plan['status'] = 'searching'
    elif change == 'relay': plan['analysis_mode'] = 'relay'
    elif change == 'disabled': d['input']['ai']['enabled'] = False
    elif change == 'no_studio': studio = None
    elif change == 'motion': d['input']['motion'] = {'style': 'other'}
    else: d['input']['network_materials_enabled'] = True
    with pytest.raises(WorkError):
        storyboard_settings(d, plan, 3.2, studio)


def test_n1_local_ai_still_rejects_relay_mode_or_missing_studio(studio):
    from backlot.studio import atomic_private
    d = draft(studio)
    d['input'].update(network_materials_enabled=False, ai={'enabled': True})
    with pytest.raises(WorkError): settings(d)
    atomic_private(studio.private / 'studio-ai/relay.json', {'analysis_mode': 'relay'})
    with pytest.raises(WorkError): settings(d, studio=studio)


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
