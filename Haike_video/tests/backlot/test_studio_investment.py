"""Template6 contracts use only local fixtures and fake providers."""
import json

import pytest

from backlot.studio import Studio
from backlot.studio_investment import TEMPLATE_ID, render_props, semantic_events, settings
from backlot.work_catalog import WorkError


@pytest.fixture
def studio(tmp_path):
    return Studio(tmp_path / "projects")


def draft(studio, investment=None):
    return studio.save_draft({"template_id": TEMPLATE_ID, "title": "本期招商标题", "text": "今天开门，今天收现金。",
                              "input": {"soundMode": "audio", "investment": investment or {}}})


def test_registry_and_saved_input_are_scoped_without_sample_copy(studio):
    d = draft(studio)
    assert settings(d)["headline"] == "本期招商标题"
    assert settings(d)["emphasis"] == []
    assert settings(d)["opening"] is True and settings(d)["closing"] is True
    assert studio.template(TEMPLATE_ID)["width"] == 1080
    assert studio.draft(d["id"])["input"]["investment"] == {}
    with pytest.raises(WorkError, match="不支持的字段"):
        studio.save_draft({"template_id": "avatar-safe-circle-v1", "input": {"investment": {}}})


@pytest.mark.parametrize("config", [{"opening": 1}, {"closing": "no"}, {"brand": ""}, {"headline": "字" * 33},
    {"brand": "项目\n名称"}, {"headline": "一\n二\n三"}, {"cta": "一\n\n二"},
    {"key": "never-save-a-key"}, {"emphasis": [{"match": "词", "text": "字" * 19}]},
    {"emphasis": [{"match": "词", "kind": "external"}]}, {"emphasis": ["收现金", "收 现金"]}])
def test_invalid_settings_fail_before_gateway(studio, monkeypatch, config):
    from backlot.studio_avatar import quote
    d = draft(studio, config)
    def forbidden(*args): pytest.fail("invalid template settings accessed a provider")
    monkeypatch.setattr(studio, "client", forbidden)
    with pytest.raises(WorkError): quote(studio, d)


def test_split_asr_cues_match_semantics_and_unmatched_is_never_scheduled(studio):
    d = draft(studio, {"opening": False, "closing": True, "emphasis": [
        {"match": "今天收现金", "text": "今天收现金", "kind": "card", "detail": "不编造账期"},
        {"match": "未被说出的承诺", "text": "不得出现"}]})
    cues = [{"text": "今天开门，今天", "startMs": 0, "endMs": 1800},
            {"text": "收现金。", "startMs": 1800, "endMs": 3000}]
    props, receipt = render_props(d, 4, cues)
    event = props["events"][0]
    assert (event["fromCue"], event["toCue"], event["asrStart"], event["asrEnd"]) == (0, 1, 0, 3)
    assert event["end"] == 3.35
    assert receipt["unmatched"] == [{"emphasis_index": 1, "match": "未被说出的承诺"}]
    assert props["investment"]["opening"] is False and props["investment"]["closing"] is True
    assert props["captions"] == cues and props["avatarSrc"] == "avatar.mp4"
    assert studio.draft(d["id"])["input"]["investment"] == d["input"]["investment"]


def test_caption_off_still_requests_real_clock_for_semantic_cards(studio):
    from backlot.studio_network_materials import needs_clock
    d = draft(studio, {"emphasis": ["收现金"]})
    d["input"]["subtitles"] = False
    cues = [{"text": "收现金", "startMs": 600, "endMs": 2000}]
    props, _ = render_props(d, 3, cues)
    assert needs_clock(d) and props["captions"] == []
    assert props["events"][0]["start"] == .6


def test_chinese_tens_match_real_asr_digits_without_changing_caption_or_large_units(studio):
    from backlot.studio_investment import normalized
    d = draft(studio, {"emphasis": [{"match": "十四个月", "text": "拖了14个月"}]})
    cues = [{"text": "等一笔拖了14个月的结算款", "startMs": 5000, "endMs": 8000}]
    props, receipt = render_props(d, 10, cues)
    assert not receipt["unmatched"]
    assert props["events"][0]["asrStart"] == 5 and props["events"][0]["asrEnd"] == 8
    assert props["captions"] == cues
    assert normalized("三十个平方") == normalized("30个平方")
    assert normalized("一千万") == "一千万"
    assert normalized("三点十四") == "三点十四"
    assert normalized("一二三四") == "一二三四"


def test_clock_and_same_cue_card_overflow_rejected(studio):
    config = settings(draft(studio, {"emphasis": ["一", "二", "三", "四"]}))
    with pytest.raises(WorkError, match="最多展示3条"):
        semantic_events(config, [{"text": "一二三四", "startMs": 0, "endMs": 2000}], 3)
    for cue in ({"text": "一", "startMs": float("nan"), "endMs": 2000},
                {"text": "字" * 29, "startMs": 0, "endMs": 2000}):
        with pytest.raises(WorkError): semantic_events(config, [cue], 3)


def test_batch_configuration_keeps_investment_and_does_not_change_other_templates(studio):
    from backlot.codex_batch import CodexBatch
    from backlot.studio_avatar_defaults import SUPPORTED
    assert TEMPLATE_ID in {item["id"] for item in SUPPORTED}
    # _input has no filesystem/network dependency; exercise input propagation.
    batch = object.__new__(CodexBatch)
    item = {"audio_path": "source.wav", "investment": {"brand": "本期项目", "opening": False}}
    expected = batch._input(item, {"id": "portrait"}, {"id": "audio"})
    assert expected["investment"] == item["investment"]
    assert expected["investment"] is not item["investment"]


def test_layout_limits_and_staged_json_are_public_constants():
    from pathlib import Path
    source = Path(__file__).resolve().parents[2] / "templates/avatar-investment-a-v6"
    geometry = json.loads((source / "layout.json").read_text(encoding="utf-8"))
    assert geometry["canvas"] == {"width": 1080, "height": 1920, "fps": 30}
    assert geometry["caption"]["maxCharsPerLine"] == 14
    assert geometry["caption"]["maxLines"] == 2
    assert geometry["emphasis"]["cardTop"] + geometry["emphasis"]["cardHeight"] < geometry["caption"]["top"]
