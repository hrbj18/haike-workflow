"""Offline safety checks; never accesses real cookies or the network."""
import importlib.util
from pathlib import Path
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
