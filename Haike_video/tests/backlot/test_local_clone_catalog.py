from backlot import audio_center


def test_new_clones_are_visible_by_id_without_reviving_presets(monkeypatch):
    voices = [
        {"id": "approved", "name": "雅雅", "voice_type": "cloned"},
        {"id": "mine", "name": "同事", "voice_type": "cloned", "available": True},
        {"id": "mine2", "name": "同事", "voice_type": "cloned", "available": False},
        {"id": "preset", "name": "Qwen Serena", "voice_type": "preset"},
    ]
    monkeypatch.setattr(audio_center, "_local_profiles", lambda: voices)
    for source in ("_doubao_profiles", "_tencent_profiles", "_bailian_profiles"):
        monkeypatch.setattr(audio_center, source, lambda state: [])
    assert [p["id"] for p in audio_center._catalog_profiles({"test": True})] == ["approved", "mine", "mine2"]
    assert audio_center._select_default(audio_center._catalog_profiles({"test": True}), "mine")["id"] == "mine"
