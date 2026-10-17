"""Network footage is opt-in, authenticated, resumable, and actually rendered."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from backlot.studio import Studio, atomic_private
from backlot.studio_network_materials import MaterialSearchError, enabled, needs_clock, preflight, public_result, write_result
from backlot.studio_storyboard import options, produce, resolve_scene, validate_plan
from backlot.work_catalog import WorkError, sha


@pytest.fixture
def case(tmp_path):
    studio = Studio(tmp_path / "projects")
    atomic_private(studio.private / "studio-ai/relay.json", {"analysis_mode": "relay", "api_key": "private-test-key", "base_url": "https://example.invalid"})
    draft = studio.save_draft({"template_id": "avatar-deepblue-n1-v1", "title": "联网画面测试", "text": "第一句。第二句。",
                               "input": {"network_materials_enabled": True, "soundMode": "audio", "subtitles": False}})
    image = io.BytesIO()
    Image.new("RGB", (640, 480), "navy").save(image, format="PNG")
    asset = studio.save_asset(draft["id"], "已核验素材.png", "image", image.getvalue())
    cues = [{"text": "第一句。", "startMs": 50, "endMs": 1400}, {"text": "第二句。", "startMs": 1700, "endMs": 3100}]
    raw = {"scenes": [{"from_cue": i, "to_cue": i, "script_start": i * 4, "script_end": (i + 1) * 4,
                       "label": f"第{i + 1}段画面", "asset_id": "", "query": "机器人 | robot", "illustration_prompt": "禁用的插画", "reason": "相关网络画面"}
                      for i in range(2)]}
    plan = {"scenes": validate_plan(raw, draft, cues, 3.2), "duration": 3.2}
    folder = studio.projects_root / draft["id"] / "renders/studio-1"
    return SimpleNamespace(studio=studio, draft=draft, asset=asset, cues=cues, plan=plan, folder=folder)


def test_new_flag_defaults_and_clock_requirements():
    old = {"input": {"subtitles": False}}
    assert enabled(old) is False and needs_clock(old) is False
    assert needs_clock({"input": {"subtitles": False, "network_materials_enabled": True}})
    with pytest.raises(WorkError, match="开关"):
        enabled({"input": {"network_materials_enabled": "true"}})


def test_network_flag_enables_existing_planner_but_never_images_or_skip(case):
    case.draft["input"]["ai"] = {"enabled": False, "allow_images": True, "skip_douyin": True}
    ai = options(case.studio, case.draft)
    assert ai["enabled"] is True and ai["allow_images"] is False and ai["skip_douyin"] is False
    assert ai["max_images"] == 0
    assert case.draft["input"]["ai"]["enabled"] is False


def test_explicit_off_blocks_all_automatic_sources_but_old_ai_keeps_behavior(case):
    calls = []
    sources = SimpleNamespace(**{name: (lambda scene, name=name: calls.append(name)) for name in ("douyin", "pexels", "illustration")})
    case.draft["input"].update(network_materials_enabled=False, ai={"enabled": True, "allow_images": False})
    ai = options(case.studio, case.draft)
    with pytest.raises(WorkError, match="联网素材已关闭"):
        resolve_scene(case.plan["scenes"][0], ai, sources)
    assert calls == []
    ai["materials"] = [{"id": "owned"}]
    assert resolve_scene({"asset_id": "owned"}, ai, sources)["id"] == "owned"
    del case.draft["input"]["network_materials_enabled"]
    with pytest.raises(WorkError, match="未找到"):
        resolve_scene(case.plan["scenes"][0], options(case.studio, case.draft), sources)
    assert calls == ["douyin", "pexels"]


def test_preflight_does_not_treat_saved_cookie_metadata_as_login(case, monkeypatch):
    monkeypatch.setattr("backlot.studio_storyboard.download_account", lambda studio: (3, None, {"status": "ready"}))
    calls = []
    def check(path, body, **kwargs):
        calls.append((path, body))
        return {"ok": False, "account": {"id": 3, "platform": "douyin", "download_status": "login_required"}}
    monkeypatch.setattr("backlot.network_materials.creator_call", check)
    with pytest.raises(MaterialSearchError, match="登录已失效") as error:
        preflight(case.studio)
    assert error.value.status == "login_required"
    assert calls == [("/api/download-sessions/3/check", {})]


@pytest.mark.parametrize("history_status", ["ready", "available"])
@pytest.mark.parametrize("live_status,ok", [("login_required", True), ("ready", False)])
def test_seven_hour_green_history_cannot_override_live_search_rejection(case, monkeypatch, history_status, live_status, ok):
    historical_at = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()
    monkeypatch.setattr("backlot.studio_storyboard.download_account", lambda studio: (3, None, {"status": "ready"}))
    calls = []
    def check(path, body, **kwargs):
        calls.append((path, body))
        return {"ok": ok, "account": {
            "id": 3, "platform": "douyin", "download_status": live_status,
            "download_check_status": history_status, "download_checked_at": historical_at,
            "publish_check_status": history_status, "publish_checked_at": historical_at,
            "search_status": "available", "search_checked_at": historical_at}}
    monkeypatch.setattr("backlot.network_materials.creator_call", check)
    with pytest.raises(MaterialSearchError) as error:
        preflight(case.studio)
    assert error.value.status == "login_required"
    assert calls == [("/api/download-sessions/3/check", {})]


@pytest.mark.parametrize("account_id,account,ok", [
    (None, {}, True), (True, {}, True),
    (3, {"id": 4, "platform": "douyin", "download_status": "ready"}, True),
    (3, {"id": 3, "platform": "kuaishou", "download_status": "ready"}, True),
    (3, {"id": 3, "platform": "douyin", "download_status": "ready"}, False),
    (3, {"id": 3, "platform": "douyin", "download_status": "network_error"}, False),
])
def test_preflight_fails_closed_for_unconfirmed_or_wrong_accounts(case, monkeypatch, account_id, account, ok):
    monkeypatch.setattr("backlot.studio_storyboard.download_account", lambda studio: (account_id, None, {}))
    monkeypatch.setattr("backlot.network_materials.creator_call", lambda *args, **kwargs: {"ok": ok, "account": account})
    with pytest.raises(MaterialSearchError): preflight(case.studio)


def test_preflight_checks_actual_selected_account_without_returning_credentials(case, monkeypatch):
    monkeypatch.setattr("backlot.studio_storyboard.download_account", lambda studio: (3, None, {"cookies": "never-public"}))
    monkeypatch.setattr("backlot.network_materials.creator_call", lambda *args, **kwargs: {
        "ok": True, "account": {"id": 3, "platform": "douyin", "download_status": "ready", "cookie": "never-public"}})
    result = preflight(case.studio)
    assert result["account_id"] == 3 and result["platform"] == "douyin"
    assert "never-public" not in json.dumps(result)


def test_switching_account_after_check_cannot_search_with_unchecked_cookie(case, monkeypatch):
    from backlot.studio_storyboard import Sources
    monkeypatch.setattr("backlot.studio_storyboard.configuration", lambda studio: {"douyin_commercial_authorized": True})
    monkeypatch.setattr("backlot.studio_storyboard.crawler_config", lambda *args: {"media_crawler": {"download_account_id": 4}})
    source = Sources(case.studio, case.draft, SimpleNamespace(folder=case.folder), None)
    source.checked_account_id = 3
    with pytest.raises(WorkError, match="账号选择已变化"):
        source.douyin(case.plan["scenes"][0])


def test_no_login_stops_before_planning_sources_and_records_clear_failure(case, monkeypatch):
    monkeypatch.setattr("backlot.studio_network_materials.preflight", lambda studio: (_ for _ in ()).throw(MaterialSearchError("请先登录", "login_required")))
    monkeypatch.setattr("backlot.studio_storyboard.make_plan", lambda *args: pytest.fail("no planner before login"))
    with pytest.raises(MaterialSearchError, match="请先登录"):
        produce(case.studio, case.draft, case.folder, case.cues, 3.2, None)
    receipt = public_result(case.folder, case.draft)
    assert receipt["status"] == "login_required" and receipt["used_count"] == 0
    assert not (case.folder / "storyboard.json").exists()


def test_quote_preflight_records_blocker_before_any_supplier_call(case, monkeypatch):
    from backlot.studio_avatar import quote
    monkeypatch.setattr("backlot.studio_network_materials.preflight", lambda studio: (_ for _ in ()).throw(MaterialSearchError("请先登录", "login_required")))
    monkeypatch.setattr(case.studio, "client", lambda: pytest.fail("no supplier before login"))
    with pytest.raises(MaterialSearchError, match="请先登录"): quote(case.studio, case.draft)
    assert public_result(case.folder, case.draft)["status"] == "login_required"


def test_quote_preflight_never_overwrites_an_already_rendered_receipt(case, monkeypatch):
    from backlot.studio_network_materials import validate_preflight
    write_result(case.folder, status="used", message="已采用", plan=ready_plan(case), used=True)
    original = (case.folder / "network-materials.json").read_bytes()
    monkeypatch.setattr("backlot.studio_network_materials.preflight", lambda studio: (_ for _ in ()).throw(MaterialSearchError("登录已失效", "login_required")))
    with pytest.raises(MaterialSearchError): validate_preflight(case.studio, case.draft)
    assert (case.folder / "network-materials.json").read_bytes() == original


def fake_sources(case, monkeypatch, *, no_match=False, fail_second=False):
    calls, checks, planning = [], [], []
    monkeypatch.setattr("backlot.studio_network_materials.preflight", lambda studio: checks.append("check"))
    def make_plan(*args):
        planning.append("plan")
        return deepcopy(case.plan)
    monkeypatch.setattr("backlot.studio_storyboard.make_plan", make_plan)
    class Sources:
        def __init__(self, *args): pass
        def douyin(self, scene): calls.append(("douyin", scene["id"])); return None
        def pexels(self, scene):
            calls.append(("pexels", scene["id"]))
            if no_match: return None
            if fail_second and scene["id"] == "scene-2" and len(checks) == 1:
                raise WorkError("本段素材检查暂时失败，请恢复原任务", "unavailable")
            return {**case.asset, "provenance": {"source": "pexels", "source_url": "https://www.pexels.com/video/robot-123/?token=secret"}}
        def illustration(self, scene): pytest.fail("network mode must not generate images")
    monkeypatch.setattr("backlot.studio_storyboard.Sources", Sources)
    return calls, checks, planning


def test_empty_results_are_visible_and_never_become_graphic_or_illustration(case, monkeypatch):
    calls, checks, planning = fake_sources(case, monkeypatch, no_match=True)
    with pytest.raises(MaterialSearchError, match="未找到适合"):
        produce(case.studio, case.draft, case.folder, case.cues, 3.2, None)
    result = public_result(case.folder, case.draft)
    assert result["status"] == "no_materials" and result["items"] == []
    assert checks == ["check"] and planning == ["plan"]
    assert calls == [("douyin", "scene-1"), ("pexels", "scene-1")]


def test_partial_success_resumes_only_missing_footage_then_ready_is_not_used(case, monkeypatch):
    calls, checks, planning = fake_sources(case, monkeypatch, fail_second=True)
    with pytest.raises(WorkError): produce(case.studio, case.draft, case.folder, case.cues, 3.2, None)
    partial = json.loads((case.folder / "storyboard.json").read_text(encoding="utf-8"))
    assert partial["scenes"][0]["asset"]["id"] == case.asset["id"]
    assert "asset" not in partial["scenes"][1]
    plan = produce(case.studio, case.draft, case.folder, case.cues, 3.2, None)
    assert plan["status"] == "ready" and planning == ["plan"] and len(checks) == 2
    assert calls.count(("douyin", "scene-1")) == 1
    result = public_result(case.folder, case.draft)
    assert result["status"] == "ready" and result["used_count"] == 0 and result["selected_count"] == 2
    assert result["items"][0]["source_url"] == "https://www.pexels.com/video/robot-123/"
    assert "secret" not in json.dumps(result) and str(case.folder) not in json.dumps(result)
    # Reusing a complete, hashed storyboard does not require a fresh network call.
    monkeypatch.setattr("backlot.studio_network_materials.preflight", lambda studio: pytest.fail("already verified footage"))
    assert produce(case.studio, case.draft, case.folder, case.cues, 3.2, None)["status"] == "ready"


def ready_plan(case):
    plan = deepcopy(case.plan)
    for scene in plan["scenes"]:
        scene.update(asset={**case.asset, "provenance": {"source": "pexels"}}, asset_sha256=sha(case.studio.asset(case.asset["id"], case.draft["id"])))
    plan["status"] = "ready"
    return plan


def test_n1_compiles_real_asr_bound_verified_assets_into_render_props(case):
    from backlot.studio_composition import n1_props
    plan = ready_plan(case)
    (case.folder / "public").mkdir(parents=True)
    props = n1_props(case.folder, case.draft, 3.2, case.cues, plan)
    assert [(s["kind"], s["start"], s["end"]) for s in props["scenes"]] == [("material", 0, 1.7), ("material", 1.7, 3.2)]
    assert props["captions"] == case.cues
    for scene in props["scenes"]:
        assert scene["mediaKind"] == "image"
        assert (case.folder / "public" / scene["src"]).read_bytes() == case.studio.asset(case.asset["id"]).read_bytes()
    assert "n1" not in case.draft["input"]
    assert len(json.loads((case.folder / "n1-sources.json").read_text(encoding="utf-8"))["sources"]) == 2


def test_network_enabled_cannot_render_a_presenter_only_fallback(case):
    from backlot.studio_composition import compose_avatar, n1_props
    with pytest.raises(WorkError, match="尚无已核验分镜"):
        compose_avatar(case.folder, case.draft, None, None, 3.2, [])
    with pytest.raises(WorkError, match="尚无已核验分镜"):
        n1_props(case.folder, case.draft, 3.2, [])


@pytest.mark.parametrize("patch", ["hash", "clock", "tail", "status", "provenance"])
def test_n1_rejects_unverified_modified_or_discontinuous_network_assets(case, patch):
    from backlot.studio_n1 import storyboard_settings
    plan = ready_plan(case)
    if patch == "hash": plan["scenes"][0]["asset_sha256"] = "incorrect"
    elif patch == "clock": plan["scenes"][1]["start"] = 1.8
    elif patch == "tail": plan["scenes"][-1]["end"] = 3.1
    elif patch == "status": plan["status"] = "searching"
    else: plan["scenes"][0]["asset"]["provenance"] = {"source": "ai-generated"}
    with pytest.raises(WorkError): storyboard_settings(case.draft, plan, 3.2, case.studio)


def test_receipts_distinguish_pending_disabled_and_used_and_whitelist_sources(case):
    assert public_result(case.folder, case.draft)["status"] == "pending"
    assert public_result(case.folder, {"input": {}})["status"] == "disabled"
    plan = ready_plan(case)
    plan["scenes"][0]["asset"]["provenance"].update(source_url="https://www.pexels.com/video/robot-123/?signature=secret", cookie="private")
    write_result(case.folder, status="used", message="已采用", plan=plan, used=True)
    result = public_result(case.folder, case.draft)
    assert result["used_count"] == 2 and result["sources"] == ["pexels"]
    assert all("asset_id" in item for item in result["items"])
    assert "secret" not in json.dumps(result) and "private" not in json.dumps(result)
    (case.folder / "network-materials.json").write_text("bad-json", encoding="utf-8")
    assert public_result(case.folder, case.draft)["status"] == "failed"


def test_avatar_run_requires_asr_even_with_hidden_subtitles_and_marks_actual_use(case, monkeypatch):
    from backlot.studio_avatar import key_identity, run_avatar
    fake_sources(case, monkeypatch)
    case.folder.mkdir(parents=True)
    (case.folder / "avatar-source.mp4").write_bytes(b"existing-avatar")
    audio = case.folder / "narration.wav"
    audio.write_bytes(b"existing-audio")
    request = {"id": "fake-network-quote", "draft": case.draft, "render_id": "studio-1", "quotes": {},
               "key_identity": key_identity(case.studio), "max_charge_micros": 100,
               "asr": {"provider": "gateway"}, "prepared": {"audio_path": str(audio), "duration": 3.2, "audio_file": "audio-1", "image_file": "image-1"}}
    models = []
    class Gateway:
        def quote(self, model, inputs, project): models.append(model); return {"id": "fake-quote", "max_charge_micros": "0"}
        def confirm(self, *args): return "fake-intent"
        def wait(self, *args, **kwargs): return {"id": "fake-asr", "status": "succeeded", "result": {"segments": [
            {"text": "第一句。", "start": .05, "end": 1.4}, {"text": "第二句。", "start": 1.7, "end": 3.1}]}}
    renders = []
    def compose(folder, draft, video, audio, duration, cues, storyboard=None):
        assert cues == [] and storyboard["status"] == "ready"
        renders.append(storyboard)
        out = folder / "avatar-preview.mp4"
        out.write_bytes(b"fake-render-with-network-assets")
        return out
    monkeypatch.setattr("backlot.studio_composition.compose_avatar", compose)
    result = run_avatar(case.folder.parents[1], request, Gateway())
    assert result["status"] == "completed" and len(renders) == 1
    assert models == ["haike/tencent-asr"]
    assert result["result"]["network_materials"]["status"] == "used"
    assert public_result(case.folder, case.draft)["used_count"] == 2
