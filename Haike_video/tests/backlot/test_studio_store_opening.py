"""Isolated opening-film contracts; no provider calls, real media or claimed reviews."""
from copy import deepcopy
import struct
import wave

import pytest

from backlot import studio_store_opening as opening
from backlot.production_queue import ProductionQueue
from backlot.production_queue_worker import ProductionQueueWorker
from backlot.studio import atomic_private
from backlot.work_catalog import WorkError, sha


@pytest.fixture
def sample(tmp_path, monkeypatch):
    template = tmp_path / "runtime/templates/store-opening-v1"
    template.mkdir(parents=True)
    (template / "index.tsx").write_text("export const isolatedFixture=true;", encoding="utf-8")
    monkeypatch.setattr(opening, "TEMPLATE", template)
    monkeypatch.setattr(opening, "runtime", lambda: {str(template / "index.tsx"): sha(template / "index.tsx")})
    queue = ProductionQueue(tmp_path / "q.sqlite3", projects_root=tmp_path / "projects")
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    paths = {name: inputs / name for name in ["master.wav", "audio-receipt.json", "asr.json", "asset-review.json", "a.mp4", "b.mp4", "avatar.mp4"]}
    for name in ["a.mp4", "b.mp4", "avatar.mp4"]:
        paths[name].write_bytes(("isolated-video-fixture-" + name).encode())
    with wave.open(str(paths["master.wav"]), "wb") as stream:
        stream.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
        stream.writeframes(b"\0" * (6 * 48000 * 4))
    captions = [{"text": "我是店长", "startMs": 0, "endMs": 1000}, {"text": "新塘未来汇开业了", "startMs": 1500, "endMs": 5500}]
    props = {"style": 22, "durationFrames": 180, "audio": "master.wav", "location": "新塘未来汇 · 海客AI社区服务站",
             "captions": captions, "chapters": [{"from": 0, "title": "开业现场", "sub": "来店体验"}],
             "shots": [{"id": "door", "lane": "main", "src": "a.mp4", "from": 0, "frames": 90, "offset": 1, "fit": "contain"},
                       {"id": "crowd", "lane": "main", "src": "b.mp4", "from": 90, "frames": 90, "offset": 2, "fit": "contain"}],
             "avatarSegments": [{"src": "avatar.mp4", "from": 0, "frames": 30}]}
    audio = {"approved_audio": {"path": "isolated-source", "sha256": "a" * 64, "user_approved": True},
             "master_audio_sha256": sha(paths["master.wav"]), "audio_sha256": sha(paths["master.wav"]),
             "authorization": {"user_approved_audio": True, "publication": False, "high_quality_avatar": True,
                               "portrait_sha256": "b" * 64, "workflow_id": "2112180419025260546"},
             "avatar_review": [{"src": "avatar.mp4", "from": 0, "frames": 30, "source_sha256": sha(paths["avatar.mp4"]),
                                "source_text": "我是店长", "reason": "店长介绍", "asr_cue_indices": [0]}]}
    asr = {"audio_sha256": "a" * 64, "text": "我是店长。新塘未来汇开业了。", "approved_script_sha256": "c" * 64, "cues": captions}
    review = {"version": "store-opening-asset-review-v1", "review_method": "isolated fixtures only", "reviewed_by": "test-fixture", "shots": [
        {"id": s["id"], "src": s["src"], "source_sha256": sha(paths[s["src"]]), "source_start_seconds": s["offset"],
         "source_end_seconds": s["offset"] + s["frames"] / 30, "observed_frames": [s["offset"] + .1], "clean": True,
         "relevant": True, "description": "isolated fixture, not a real visual review", "category": "门店聚客"} for s in props["shots"]]}
    for name, value in [("audio-receipt.json", audio), ("asr.json", asr), ("asset-review.json", review)]:
        atomic_private(paths[name], value)
    monkeypatch.setattr(opening, "media_probe", lambda p: {"duration": 8, "video": {"width": 1920, "height": 1080, "codec_name": "h264"}, "audio": None})
    return {"queue": queue, "props": props, "paths": paths, "audio": audio, "asr": asr, "review": review, "template": template}


def prepare(sample):
    return opening.prepare(sample["queue"], sample["props"], sample["paths"], "隔离新店开业")


def test_originals_are_copied_once_and_queue_submission_is_idempotent(sample):
    before = {name: sha(path) for name, path in sample["paths"].items()}
    request = prepare(sample)
    assert prepare(sample) == request
    assert request["contract"] == "store-opening-v1" and request["publication"] is False
    project = opening.validate(sample["queue"], request)
    for name, expected in before.items():
        assert sha(project / "assets/store-manager" / name) == expected == sha(sample["paths"][name])
    assert opening.submit(sample["queue"], request)["job_id"] == opening.submit(sample["queue"], request)["job_id"]


@pytest.mark.parametrize("mutation", ["gap", "overlap", "same_source_split", "too_long", "subtitle_overlap", "subtitle_end", "subtitle_width", "avatar_outside", "avatar_overlap", "avatar_too_long", "traversal", "location"])
def test_invalid_edit_contracts_are_rejected_before_copy(sample, mutation):
    props = sample["props"]
    if mutation == "gap": props["shots"][1]["from"] += 1
    elif mutation == "overlap": props["shots"][1]["from"] -= 1
    elif mutation == "same_source_split": props["shots"][1]["src"] = "a.mp4"
    elif mutation == "too_long": props["shots"][0]["frames"] = 121
    elif mutation == "subtitle_overlap": props["captions"][1]["startMs"] = 900
    elif mutation == "subtitle_end": props["captions"][1]["endMs"] = 6002
    elif mutation == "subtitle_width": props["captions"][1]["text"] = "字" * 22
    elif mutation == "avatar_outside": props["avatarSegments"][0]["from"] = 179
    elif mutation == "avatar_overlap": props["avatarSegments"].append(deepcopy(props["avatarSegments"][0]))
    elif mutation == "avatar_too_long": props["avatarSegments"][0]["frames"] = 241
    elif mutation == "traversal": props["shots"][0]["src"] = "../a.mp4"
    else: props["location"] = "旧门店地址"
    with pytest.raises(WorkError):
        prepare(sample)
    assert not list(sample["queue"].projects_root.glob("studio-*"))


@pytest.mark.parametrize("mutation", ["missing_review", "wrong_sha", "wrong_range", "unseen", "not_clean", "not_relevant", "avatar_not_manager", "avatar_cue", "avatar_clock", "wrong_master", "wrong_asr", "captions_not_asr", "unauthorized"])
def test_evidence_must_bind_current_source_and_exact_window(sample, mutation):
    review, audio, asr = sample["review"], sample["audio"], sample["asr"]
    if mutation == "missing_review": review["shots"].pop()
    elif mutation == "wrong_sha": review["shots"][0]["source_sha256"] = "f" * 64
    elif mutation == "wrong_range": review["shots"][0]["source_start_seconds"] += .2
    elif mutation == "unseen": review["shots"][0]["observed_frames"] = []
    elif mutation == "not_clean": review["shots"][0]["clean"] = False
    elif mutation == "not_relevant": review["shots"][0]["relevant"] = False
    elif mutation == "avatar_not_manager": audio["avatar_review"][0]["source_text"] = "欢迎到店"
    elif mutation == "avatar_cue": audio["avatar_review"][0]["asr_cue_indices"] = [1]
    elif mutation == "avatar_clock":
        sample["props"]["avatarSegments"][0]["from"] = 60
        audio["avatar_review"][0]["from"] = 60
    elif mutation == "wrong_master": audio["master_audio_sha256"] = "d" * 64
    elif mutation == "wrong_asr": asr["audio_sha256"] = "d" * 64
    elif mutation == "captions_not_asr": asr["cues"] = deepcopy(asr["cues"]); asr["cues"][0]["endMs"] = 950
    else: audio["authorization"]["high_quality_avatar"] = False
    for name, value in [("audio-receipt.json", audio), ("asr.json", asr), ("asset-review.json", review)]:
        atomic_private(sample["paths"][name], value)
    with pytest.raises(WorkError):
        prepare(sample)


def test_optional_detail_gaps_are_allowed_but_overlaps_are_not(sample):
    props = deepcopy(sample["props"])
    props["shots"].append({"id": "detail", "lane": "detail", "src": "a.mp4", "from": 50, "frames": 50, "offset": 0, "fit": "contain"})
    opening.validate_props(props)
    props["shots"].append({"id": "detail2", "lane": "detail", "src": "b.mp4", "from": 90, "frames": 50, "offset": 1, "fit": "contain"})
    with pytest.raises(WorkError, match="重叠"):
        opening.validate_props(props)


def test_low_resolution_or_out_of_source_interval_is_rejected(sample, monkeypatch):
    monkeypatch.setattr(opening, "media_probe", lambda p: {"duration": 8, "video": {"width": 540, "height": 960}})
    with pytest.raises(WorkError, match="720p"):
        prepare(sample)
    monkeypatch.setattr(opening, "media_probe", lambda p: {"duration": 3, "video": {"width": 1920, "height": 1080}})
    with pytest.raises(WorkError, match="原片长度"):
        prepare(sample)


def test_explicit_crop_position_accepts_audited_percentages_without_css_injection(sample):
    props = sample["props"]
    props["shots"][0]["objectPosition"] = "38.5% 100%"
    opening.validate_props(props)
    props["shots"][0]["objectPosition"] = "101% 50%"
    with pytest.raises(WorkError, match="裁切位置"):
        opening.validate_props(props)
    props["shots"][0]["objectPosition"] = "50% 50%; filter:blur(5px)"
    with pytest.raises(WorkError, match="裁切位置"):
        opening.validate_props(props)


def test_frozen_source_and_runtime_tampering_are_detected(sample):
    request = prepare(sample)
    (sample["template"] / "index.tsx").write_text("changed implementation", encoding="utf-8")
    with pytest.raises(WorkError, match="实现已变化"):
        opening.validate(sample["queue"], request)
    (sample["template"] / "index.tsx").write_text("export const isolatedFixture=true;", encoding="utf-8")
    project = opening.validate(sample["queue"], request)
    (project / "assets/store-manager/a.mp4").write_bytes(b"changed source")
    with pytest.raises(WorkError, match="冻结素材内容已变化"):
        opening.validate(sample["queue"], request)


def test_refreeze_checks_original_assets_but_creates_new_runtime_identity(sample):
    request = prepare(sample)
    (sample["template"] / "index.tsx").write_text("reviewed changed implementation", encoding="utf-8")
    project = opening.validate(sample["queue"], request, check_runtime=False)
    sources = {name: project / "assets/store-manager" / name for name in request["origins"]}
    fresh = opening.prepare(sample["queue"], request["props"], sources, request["title"])
    assert fresh["project_id"] != request["project_id"] and fresh["runtime"] != request["runtime"]
    assert opening.validate(sample["queue"], fresh)
    assert all(fresh["origins"][name]["sha256"] == value["sha256"] for name, value in request["origins"].items())


def test_worker_dispatches_new_contract_without_changing_legacy_path(sample, monkeypatch):
    expected = {"status": "completed", "result": {"isolated": True}}
    monkeypatch.setattr(opening, "run", lambda queue, job: expected)
    worker = ProductionQueueWorker(sample["queue"], sample["queue"].projects_root)
    assert worker._run_investment_recompose({"frozen_request": {"contract": "store-opening-v1"}}) == expected


def add_font_fixtures(sample):
    """Minimal sfnt table-directory fixtures, never presented as renderable fonts."""
    data = bytearray(2048)
    struct.pack_into(">4sHHHH", data, 0, b"\x00\x01\x00\x00", 4, 64, 2, 0)
    for index, tag in enumerate([b"head", b"name", b"cmap", b"maxp"]):
        struct.pack_into(">4sIII", data, 12 + index * 16, tag, 0, 256 + index * 256, 64)
    sample["props"]["fontAssets"] = deepcopy(opening.FONT_ASSETS)
    for filename in opening.FONT_ASSETS.values():
        path = sample["paths"]["master.wav"].parent / filename
        path.write_bytes(data)
        sample["paths"][filename] = path
    return sample


def test_optional_fonts_are_frozen_copied_and_detected_if_modified(sample):
    add_font_fixtures(sample)
    request = prepare(sample)
    assert request["contract"] == "store-opening-v1"
    assert set(request["origins"]) == set(sample["paths"])
    project = opening.validate(sample["queue"], request)
    for filename in opening.FONT_ASSETS.values():
        assert sha(project / "assets/store-manager" / filename) == request["origins"][filename]["sha256"]
    frozen_font = project / "assets/store-manager/display.ttf"
    data = bytearray(frozen_font.read_bytes())
    data[-1] ^= 1
    frozen_font.write_bytes(data)
    with pytest.raises(WorkError, match="冻结素材内容已变化"):
        opening.validate(sample["queue"], request)


@pytest.mark.parametrize("fonts", [None, {}, {"display": "display.ttf"},
    {"display": "../display.ttf", "body": "body.ttf", "latin": "latin.ttf"},
    {"display": "C:/display.ttf", "body": "body.ttf", "latin": "latin.ttf"},
    {"display": "display.ttf", "body": "display.ttf", "latin": "latin.ttf"},
    {"display": "display.ttf", "body": "body.ttf", "latin": "latin.ttf", "extra": "extra.ttf"},
    {"display": "display.ttf; color:red", "body": "body.ttf", "latin": "latin.ttf"}])
def test_font_declaration_rejects_partial_extra_or_unsafe_slots(sample, fonts):
    sample["props"]["fontAssets"] = fonts
    with pytest.raises(WorkError, match="字体槽"):
        prepare(sample)
    assert not list(sample["queue"].projects_root.glob("studio-*"))


@pytest.mark.parametrize("mutation", ["missing", "extra", "undeclared"])
def test_font_sources_must_match_the_declared_exact_set(sample, mutation):
    add_font_fixtures(sample)
    if mutation == "missing":
        sample["paths"].pop("latin.ttf")
    elif mutation == "extra":
        sample["paths"]["extra.ttf"] = sample["paths"]["latin.ttf"]
    else:
        sample["props"].pop("fontAssets")
    with pytest.raises(WorkError, match="素材槽不完整"):
        prepare(sample)


@pytest.mark.parametrize("mutation", ["bad_signature", "too_small", "too_large", "table_count", "out_of_bounds", "duplicate_table", "missing_required_table"])
def test_font_headers_and_table_bounds_are_checked_before_copy(sample, mutation):
    add_font_fixtures(sample)
    path = sample["paths"]["display.ttf"]
    data = bytearray(path.read_bytes())
    if mutation == "bad_signature":
        data[:4] = b"html"
    elif mutation == "too_small":
        data = data[:512]
    elif mutation == "too_large":
        with path.open("wb") as stream:
            stream.seek(32 * 1024 * 1024)
            stream.write(b"x")
    elif mutation == "table_count":
        struct.pack_into(">H", data, 4, 129)
    elif mutation == "out_of_bounds":
        struct.pack_into(">I", data, 12 + 8, len(data) + 1)
    elif mutation == "duplicate_table":
        data[12 + 16:12 + 20] = b"head"
    else:
        data[12:16] = b"fake"
    if mutation != "too_large":
        path.write_bytes(data)
    with pytest.raises(WorkError, match="字体"):
        prepare(sample)
    assert not list(sample["queue"].projects_root.glob("studio-*"))


def test_completed_legacy_request_still_validates_after_current_runtime_changes(sample, monkeypatch):
    request = prepare(sample)
    project = opening.validate(sample["queue"], request)
    folder = project / "renders" / request["render_id"]
    folder.mkdir(parents=True)
    output = folder / "avatar-preview.mp4"
    output.write_bytes(b"isolated completed legacy output, not a real video")
    atomic_private(folder / "quality.json", {"isolated_fixture": True})
    atomic_private(folder / "result.json", {"request_sha256": request["request_sha256"],
        "output_sha256": sha(output), "quality_sha256": sha(folder / "quality.json")})
    monkeypatch.setattr(opening, "runtime", lambda: {"current_source_revision": "changed"})
    assert "fontAssets" not in request["props"]
    assert opening.validate(sample["queue"], request) == project

