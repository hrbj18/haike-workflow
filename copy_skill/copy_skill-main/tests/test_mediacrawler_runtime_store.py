import asyncio
from types import SimpleNamespace

import pytest

from douyin_intelligence.mediacrawler_runtime_store import install_duration_bridge


def fixture_store():
    rows = []
    class Store:
        async def store_content(self, content_item):
            rows.append(content_item)
        async def store_comment(self, value):
            return value
    class Factory:
        create_store = staticmethod(Store)
    async def update(item):
        await asyncio.sleep(0)
        if item.get("fail"):
            raise ValueError("fixture failure")
        await module.DouyinStoreFactory.create_store().store_content({"aweme_id": item["aweme_id"], "title": "fixture"})
    module = SimpleNamespace(update_douyin_aweme=update, DouyinStoreFactory=Factory)
    return module, rows


def test_explicit_milliseconds_survive_current_upstream_whitelist_without_source_mutation():
    module, rows = fixture_store()
    assert install_duration_bridge(module) is True
    raw = {"aweme_id": "one", "video": {"duration": 25400}}
    asyncio.run(module.update_douyin_aweme(raw))
    assert rows == [{"aweme_id": "one", "title": "fixture", "duration_ms": 25400}]
    assert raw == {"aweme_id": "one", "video": {"duration": 25400}}
    assert install_duration_bridge(module) is False


def test_parallel_items_keep_their_own_duration():
    module, rows = fixture_store()
    install_duration_bridge(module)
    async def run():
        await asyncio.gather(module.update_douyin_aweme({"aweme_id": "a", "video": {"duration": 6000}}),
                             module.update_douyin_aweme({"aweme_id": "b", "video": {"duration": 18000}}))
    asyncio.run(run())
    assert {row["aweme_id"]: row["duration_ms"] for row in rows} == {"a": 6000, "b": 18000}


@pytest.mark.parametrize("video", [{}, {"duration": None}, {"duration": True}, {"duration": "nan"}, {"duration": -1}])
def test_unknown_or_invalid_duration_is_not_invented(video):
    module, rows = fixture_store()
    install_duration_bridge(module)
    asyncio.run(module.update_douyin_aweme({"aweme_id": "one", "video": video, "duration": 25}))
    assert "duration_ms" not in rows[0]


def test_failed_update_does_not_leak_context_and_other_store_methods_work():
    module, rows = fixture_store()
    install_duration_bridge(module)
    async def run():
        with pytest.raises(ValueError):
            await module.update_douyin_aweme({"aweme_id": "one", "video": {"duration": 9000}, "fail": True})
        store = module.DouyinStoreFactory.create_store()
        await store.store_content({"aweme_id": "one"})
        assert await store.store_comment("untouched") == "untouched"
    asyncio.run(run())
    assert rows == [{"aweme_id": "one"}]


def test_status_distinguishes_runtime_bridge_from_a_source_patch(tmp_path):
    from douyin_intelligence.mediacrawler_patch import TARGET_RELPATH, duration_patch_status
    path = tmp_path / TARGET_RELPATH
    path.parent.mkdir(parents=True)
    path.write_text("class DouyinStoreFactory:\n    pass\nasync def update_douyin_aweme(item):\n    extract_video_urls(item)\n", encoding="utf-8")
    result = duration_patch_status({"_project_root": str(tmp_path)})
    assert result["status"] == "runtime_bridge_ready"
    assert result["patched"] is False and result["runtime_bridge"] is True
