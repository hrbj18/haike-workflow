"""Offline safety checks; never accesses real cookies or the network."""
import importlib.util
import argparse
import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import time

import pytest

SPEC = importlib.util.spec_from_file_location("single_download", Path(__file__).resolve().parents[1] / "scripts/download_douyin_mediacrawler.py")
download = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(download)


def test_cookie_paths_are_independent_of_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert download.cookie_path(None) == download.WORKSPACE / "www.douyin.com_cookies.txt"
    assert download.cookie_path(str(tmp_path / "chosen.txt")) == tmp_path / "chosen.txt"


def test_cookie_filter_keeps_httponly_and_rejects_expired_foreign(tmp_path):
    path = tmp_path / "synthetic.txt"
    future = int(time.time()) + 3600
    path.write_text("# Netscape HTTP Cookie File\n" +
                    f"#HttpOnly_.douyin.com\tTRUE\t/\tTRUE\t{future}\tsynthetic\tfake\n" +
                    ".douyin.com\tTRUE\t/\tTRUE\t1\told\tfake\n" +
                    f".evildouyin.com\tTRUE\t/\tTRUE\t{future}\tforeign\tfake\n", encoding="utf-8")
    values = download.read_cookies(path)
    assert [c["name"] for c in values] == ["synthetic"]
    assert values[0]["httpOnly"] is True


@pytest.mark.parametrize("value", ["https://evil.example/", "https://douyin.com.evil.example/", "http://www.douyin.com/video/123", "https://user:pass@www.douyin.com/", "https://www.douyin.com:444/"])
def test_untrusted_url_is_rejected(value):
    with pytest.raises(ValueError):
        download.input_url(value)


def test_share_text_and_id_are_accepted():
    assert download.input_url("复制打开抖音 https://v.douyin.com/example/ 看作品") == "https://v.douyin.com/example/"
    assert download.input_url("7688649786064424233") == "7688649786064424233"


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "nan", "inf", "524288001", True])
def test_byte_limit_is_a_positive_bounded_integer(value):
    with pytest.raises(argparse.ArgumentTypeError):
        download.max_bytes_argument(value)


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "86400.1", True])
def test_duration_limit_is_positive_finite_and_bounded(value):
    with pytest.raises(argparse.ArgumentTypeError):
        download.max_seconds_argument(value)


@pytest.mark.parametrize("detail,expected", [
    ({"video": {"duration": 60000}}, 60),
    ({"video": {"duration_ms": "59999"}}, 59.999),
    ({"duration_ms": 12000}, 12),
    ({"video_duration_ms": 15500}, 15.5),
    ({"duration_seconds": 42.5}, 42.5),
    ({"video": {"duration_seconds": 10}}, 10),
    ({"duration": 42}, None),
    ({"video": {"duration": float("nan")}}, None),
    ({"video": {"duration": True}}, None),
    ({}, None),
])
def test_detail_duration_only_uses_known_units(detail, expected):
    assert download.detail_duration_seconds(detail) == expected


def test_current_upstream_extractor_is_preferred_and_returns_first_explicit_video(monkeypatch):
    selected = "https://cdn.example/video.mp4?fixture-signature=private"
    called = []
    detail = {"video": {"play_addr_h264": {"url_list": [
        "https://cdn.example/music.mp3", selected,
    ]}}}

    def extract(value):
        called.append(value)
        return ["https://cdn.example/music.mp3", "https://cdn.example/cover.jpg", selected]

    monkeypatch.setitem(sys.modules, "media_platform.douyin.media", SimpleNamespace(extract_video_urls=extract))
    monkeypatch.setitem(sys.modules, "store.douyin", SimpleNamespace(
        _extract_video_download_url=lambda _: pytest.fail("legacy extractor must not run")))
    assert download.upstream_video_url(detail) == selected
    assert called == [detail]


def test_older_upstream_private_extractor_remains_compatible(monkeypatch):
    selected = "https://cdn.example/video.mp4"
    detail = {"video": {"play_addr": {"url_list": [selected]}}}
    monkeypatch.setitem(sys.modules, "media_platform.douyin.media", None)
    monkeypatch.setitem(sys.modules, "store.douyin", SimpleNamespace(_extract_video_download_url=lambda _: selected))
    assert download.upstream_video_url(detail) == selected


@pytest.mark.parametrize("result", [[], "https://cdn.example/video.mp4", [None],
                                        ["https://cdn.example/unrelated.mp4"]])
def test_current_extractor_empty_or_invalid_result_does_not_fall_back_to_music(monkeypatch, result):
    detail = {"video": {"play_addr": {"url_list": ["https://cdn.example/video.mp4"]}}}
    monkeypatch.setitem(sys.modules, "media_platform.douyin.media", SimpleNamespace(extract_video_urls=lambda _: result))
    monkeypatch.setitem(sys.modules, "store.douyin", SimpleNamespace(
        _extract_video_download_url=lambda _: pytest.fail("empty video must not use legacy music fallback")))
    assert download.upstream_video_url(detail) == ""


@pytest.mark.parametrize("detail", [{}, {"video": {"duration": 8000}},
    {"images": [{"url_list": ["https://cdn.example/image.jpg"]}],
     "video": {"play_addr": {"url_list": ["https://cdn.example/video.mp4"]}}}])
def test_missing_video_stream_and_image_albums_never_invoke_extractor(monkeypatch, detail):
    monkeypatch.setitem(sys.modules, "media_platform.douyin.media", SimpleNamespace(
        extract_video_urls=lambda _: pytest.fail("no explicit video stream")))
    assert download.upstream_video_url(detail) == ""


def _resolver_fixture(monkeypatch, tmp_path, detail):
    root = tmp_path / "copy"
    (root / "third_party" / "MediaCrawler").mkdir(parents=True)
    monkeypatch.setattr(download, "ROOT", root)
    monkeypatch.chdir(tmp_path)
    closed, extracted = [], []

    class Page:
        async def goto(self, *_args, **_kwargs):
            pass

        async def evaluate(self, *_args):
            return "fixture-UA"

    class Context:
        async def add_cookies(self, _cookies):
            pass

        async def new_page(self):
            return Page()

    class Browser:
        async def new_context(self, **_kwargs):
            return Context()

        async def close(self):
            closed.append(True)

    class Chromium:
        async def launch(self, **_kwargs):
            return Browser()

    @asynccontextmanager
    async def playwright():
        yield SimpleNamespace(chromium=Chromium())

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def update_cookies(self, _context):
            pass

        async def get_video_by_id(self, _ident):
            video = {"play_addr": {"url_list": ["https://cdn.example/PRIVATE_SIGNED_URL"]},
                     **detail.get("video", {})}
            return {"aweme_id": "7688649786064424233", "desc": "fixture", **detail, "video": video}

    def extract(_detail):
        extracted.append(True)
        return "https://cdn.example/PRIVATE_SIGNED_URL"

    monkeypatch.setitem(sys.modules, "playwright.async_api", SimpleNamespace(async_playwright=playwright))
    monkeypatch.setitem(sys.modules, "media_platform.douyin.client", SimpleNamespace(DouYinClient=Client))
    monkeypatch.setitem(sys.modules, "media_platform.douyin.help", SimpleNamespace(
        parse_video_info_from_url=lambda _url: SimpleNamespace(url_type="video", aweme_id="7688649786064424233")))
    monkeypatch.setitem(sys.modules, "media_platform.douyin.media", None)
    monkeypatch.setitem(sys.modules, "store.douyin", SimpleNamespace(_extract_video_download_url=extract))
    monkeypatch.setattr("logging.disable", lambda *_args: None)
    return closed, extracted


def test_resolve_checks_real_detail_before_returning_original_three_tuple(tmp_path, monkeypatch):
    closed, extracted = _resolver_fixture(monkeypatch, tmp_path, {"video": {"duration": 60000}})
    args = SimpleNamespace(url="7688649786064424233", max_seconds=60)
    result = asyncio.run(download.resolve(args, []))
    assert result == ("7688649786064424233", "fixture", "https://cdn.example/PRIVATE_SIGNED_URL")
    assert args.resolved_duration_seconds == 60
    assert closed == [True] and extracted == [True]


def test_resolve_accepts_fresh_upstream_without_removed_private_helper(tmp_path, monkeypatch):
    closed, old_extracted = _resolver_fixture(monkeypatch, tmp_path, {"video": {"duration": 5000}})
    extracted = []

    def extract(detail):
        extracted.append(detail)
        return ["https://cdn.example/PRIVATE_SIGNED_URL"]

    monkeypatch.setitem(sys.modules, "media_platform.douyin.media", SimpleNamespace(extract_video_urls=extract))
    monkeypatch.setitem(sys.modules, "store.douyin", SimpleNamespace())
    args = SimpleNamespace(url="7688649786064424233", max_seconds=60)
    result = asyncio.run(download.resolve(args, []))
    assert result == ("7688649786064424233", "fixture", "https://cdn.example/PRIVATE_SIGNED_URL")
    assert len(extracted) == 1 and old_extracted == [] and closed == [True]


@pytest.mark.parametrize("detail", [{"video": {"duration": 60001}}, {}])
def test_resolve_rejects_long_or_unknown_duration_before_media_download(tmp_path, monkeypatch, detail):
    closed, extracted = _resolver_fixture(monkeypatch, tmp_path, detail)
    with pytest.raises(ValueError):
        asyncio.run(download.resolve(SimpleNamespace(url="7688649786064424233", max_seconds=60), []))
    assert closed == [True] and extracted == []


def test_default_duration_remains_unrestricted_and_old_resolve_contract_works(tmp_path, monkeypatch):
    closed, extracted = _resolver_fixture(monkeypatch, tmp_path, {})
    result = asyncio.run(download.resolve(SimpleNamespace(url="7688649786064424233"), []))
    assert len(result) == 3 and closed == [True] and extracted == [True]


def test_main_passes_explicit_hard_byte_budget_without_new_downloader(tmp_path, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(download, "selected_cookies", lambda _args: ([], "fixture"))

    async def resolve(args, _cookies):
        args.resolved_duration_seconds = 58.5
        return "7688649786064424233", "fixture title", "https://cdn.example/PRIVATE_SIGNED_URL"

    monkeypatch.setattr(download, "resolve", resolve)
    from douyin_intelligence import materials

    def downloader(url, destination, config):
        calls.append(config)
        destination.write_bytes(b"fixture mp4")

    monkeypatch.setattr(materials, "download_video", downloader)
    monkeypatch.setattr(sys, "argv", ["download", "7688649786064424233", "--output-dir", str(tmp_path),
                                     "--max-bytes", "52428800", "--max-seconds", "60"])
    assert download.main() == 0
    assert calls[0]["materials"]["max_video_bytes"] == 50 * 1024 * 1024
    receipt = json.loads(next(tmp_path.rglob("download.json")).read_text(encoding="utf-8"))
    assert receipt["duration_seconds"] == 58.5
    assert "PRIVATE_SIGNED_URL" not in capsys.readouterr().out


def test_explicit_duration_cap_cannot_be_silently_skipped_by_old_resolver(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(download, "selected_cookies", lambda _args: ([], "fixture"))

    async def resolve(_args, _cookies):
        return "7688649786064424233", "fixture", "https://cdn.example/PRIVATE_SIGNED_URL"

    monkeypatch.setattr(download, "resolve", resolve)
    monkeypatch.setattr(sys, "argv", ["download", "7688649786064424233", "--output-dir", str(tmp_path), "--max-seconds", "60"])
    assert download.main() == 1
    assert not list(tmp_path.iterdir())
    assert json.loads(capsys.readouterr().err)["stage"] == "mediacrawler_resolve"
