"""Single-video download using the installed MediaCrawler and project downloader.

Run with third_party/MediaCrawler/.venv/Scripts/python.exe on Windows.
Credentials and signed URLs stay in memory. No yt-dlp or shared browser profile.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent.parent
HOSTS = {"douyin.com", "www.douyin.com", "v.douyin.com", "www.iesdouyin.com"}


def input_url(value: str) -> str:
    value = value.strip()
    if re.fullmatch(r"\d{15,22}", value):
        return value
    match = re.search(r"https://[^\s<>\[\]\"）)]+", value)
    candidate = match.group(0) if match else value
    parsed = urlparse(candidate)
    if parsed.scheme != "https" or parsed.hostname not in HOSTS or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("Expected a Douyin HTTPS link or video ID")
    return candidate


def cookie_path(value: str | None) -> Path:
    return Path(value).expanduser().resolve() if value else WORKSPACE / "www.douyin.com_cookies.txt"


def read_cookies(path: Path) -> list[dict]:
    jar = http.cookiejar.MozillaCookieJar(str(path))
    jar.load(ignore_discard=True, ignore_expires=False)
    result = []
    for item in jar:
        domain = item.domain.lstrip(".")
        if domain != "douyin.com" and not domain.endswith(".douyin.com"):
            continue
        result.append({"name": item.name, "value": item.value, "domain": item.domain,
                       "path": item.path or "/", "secure": item.secure,
                       "httpOnly": item.has_nonstandard_attr("HTTPOnly"),
                       "expires": item.expires if item.expires else -1})
    if not result:
        raise ValueError("No unexpired Douyin cookies")
    return result


async def resolve(args, cookies):
    crawler = ROOT / "third_party" / "MediaCrawler"
    os.chdir(crawler)  # upstream signing JS is opened relative to its root
    sys.path.insert(0, str(crawler))
    from playwright.async_api import async_playwright
    from media_platform.douyin.client import DouYinClient
    from media_platform.douyin.help import parse_video_info_from_url
    from store.douyin import _extract_video_download_url
    import logging
    logging.disable(logging.CRITICAL)  # upstream errors may contain raw response/URL data
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True, timeout=30000)
        try:
            context = await browser.new_context()
            await context.add_cookies(cookies)
            page = await context.new_page()
            await page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=45000)
            client = DouYinClient(timeout=30, proxy=None, headers={
                "User-Agent": await page.evaluate("() => navigator.userAgent"),
                "Origin": "https://www.douyin.com/", "Referer": "https://www.douyin.com/",
                "Content-Type": "application/json;charset=UTF-8"},
                playwright_page=page, cookie_dict={})
            await client.update_cookies(context)
            info = parse_video_info_from_url(args.url)
            if info.url_type == "short":
                resolved = input_url(await client.resolve_short_url(args.url))
                info = parse_video_info_from_url(resolved)
            if not re.fullmatch(r"\d{15,22}", info.aweme_id or ""):
                raise ValueError("No video ID resolved")
            detail = await client.get_video_by_id(info.aweme_id)
            if str(detail.get("aweme_id", "")) != info.aweme_id or detail.get("images"):
                raise ValueError("No matching video detail or image album")
            media = _extract_video_download_url(detail)
            if not media:
                raise ValueError("No video stream in detail")
            return info.aweme_id, str(detail.get("desc", "")), media
        finally:
            await browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", type=input_url, help="Douyin share text, HTTPS URL or video ID")
    parser.add_argument("--cookies", help="Netscape Cookie file; default: workspace root")
    parser.add_argument("--output-dir", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--check", action="store_true", help="Offline input/Cookie validation only")
    args = parser.parse_args()
    args.output_dir = args.output_dir.expanduser().resolve()
    stage = "cookies"
    try:
        cookies = read_cookies(cookie_path(args.cookies))
        if args.check:
            print(json.dumps({"status": "input_ok", "cookie_source": "explicit" if args.cookies else "workspace_default", "cookie_count": len(cookies)}, ensure_ascii=False))
            return 0
        stage = "mediacrawler_resolve"
        video_id, title, media = asyncio.run(asyncio.wait_for(resolve(args, cookies), timeout=120))
        stage = "project_download"
        sys.path.insert(0, str(ROOT / "src"))
        from douyin_intelligence.materials import download_video
        # Unique task directory avoids the downloader's existing-file cache and overwrites.
        from uuid import uuid4
        folder = args.output_dir / f"douyin-{video_id}-{time.strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}"
        folder.mkdir(parents=True, exist_ok=False)
        destination = folder / f"{video_id}.mp4"
        download_video(media, destination, {"materials": {"max_video_bytes": 524288000,
                       "download_timeout_seconds": 60, "download_retries": 1}})
        digest = hashlib.sha256()
        with destination.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        receipt = {"status": "downloaded", "backend": "MediaCrawler + materials.download_video",
                   "video_id": video_id, "title": title, "source_url": f"https://www.douyin.com/video/{video_id}",
                   "file": str(destination), "bytes": destination.stat().st_size,
                   "sha256": digest.hexdigest(), "cookie_source": "explicit" if args.cookies else "workspace_default"}
        (folder / "download.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(receipt, ensure_ascii=False))
        return 0
    except Exception as exc:
        # Do not print exception messages or tracebacks: upstream exceptions can carry secrets.
        print(json.dumps({"status": "failed", "stage": stage, "error_type": type(exc).__name__}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
