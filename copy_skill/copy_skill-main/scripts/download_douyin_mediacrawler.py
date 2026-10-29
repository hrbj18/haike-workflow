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
import math
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent.parent
HOSTS = {"douyin.com", "www.douyin.com", "v.douyin.com", "www.iesdouyin.com"}
MAX_VIDEO_BYTES = 524288000


def max_bytes_argument(value: str) -> int:
    try:
        if isinstance(value, (bool, float)):
            raise ValueError()
        result = int(value)
        if not 1 <= result <= MAX_VIDEO_BYTES:
            raise ValueError()
        return result
    except (ValueError, TypeError, OverflowError):
        raise argparse.ArgumentTypeError(f"max-bytes must be an integer from 1 to {MAX_VIDEO_BYTES}") from None


def max_seconds_argument(value: str) -> float:
    try:
        if isinstance(value, bool):
            raise ValueError()
        result = float(value)
        if not math.isfinite(result) or not 0 < result <= 86400:
            raise ValueError()
        return result
    except (ValueError, TypeError, OverflowError):
        raise argparse.ArgumentTypeError("max-seconds must be finite and greater than 0, up to 86400") from None


def detail_duration_seconds(detail: dict) -> float | None:
    """Read fields with known units; do not guess an ambiguous raw duration."""
    video = detail.get("video") if isinstance(detail.get("video"), dict) else {}
    fields = ((video.get("duration_ms"), 1000), (video.get("duration"), 1000),
              (detail.get("duration_ms"), 1000), (detail.get("video_duration_ms"), 1000),
              (video.get("duration_seconds"), 1), (detail.get("duration_seconds"), 1),
              (detail.get("video_duration_seconds"), 1))
    for raw, scale in fields:
        if isinstance(raw, bool):
            continue
        try:
            value = float(raw) / scale
        except (ValueError, TypeError, OverflowError):
            continue
        if math.isfinite(value) and value > 0:
            return value
    return None


def check_duration(duration: float | None, maximum: float | None) -> None:
    if maximum is None:
        return
    if duration is None or not math.isfinite(duration) or duration <= 0:
        raise ValueError("No reliable video duration metadata for the requested limit")
    if duration > maximum:
        raise ValueError("Video duration exceeds the requested limit")


def upstream_video_url(detail: dict) -> str:
    """Support both upstream extractor APIs, accepting only explicit video URLs."""
    video = detail.get("video")
    if not isinstance(video, dict) or detail.get("images"):
        return ""
    addresses = [video.get(key) for key in
                 ("play_addr_h264", "play_addr_256", "play_addr", "download_addr")]
    addresses.extend(item.get("play_addr") for item in (video.get("bit_rate") or [])
                     if isinstance(item, dict))
    video_urls = {url for address in addresses if isinstance(address, dict)
                  for url in (address.get("url_list") or []) if isinstance(url, str)}
    if not video_urls:
        return ""
    try:
        from media_platform.douyin.media import extract_video_urls
    except ImportError:
        from store.douyin import _extract_video_download_url
        candidates = [_extract_video_download_url(detail)]
    else:
        candidates = extract_video_urls(detail)
        if not isinstance(candidates, (list, tuple)):
            return ""
    for url in candidates:
        if not isinstance(url, str) or url not in video_urls:
            continue
        parsed = urlparse(url)
        path = parsed.path.lower()
        if (parsed.scheme in {"http", "https"} and parsed.hostname
                and not parsed.username and not parsed.password
                and not path.endswith((".mp3", ".m4a", ".aac", ".wav", ".jpg", ".jpeg", ".png", ".webp"))
                and "ies-music" not in path and "/music/" not in path):
            return url
    return ""


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


def selected_cookies(args):
    if args.cookies:
        return read_cookies(cookie_path(args.cookies)), "explicit"
    sys.path.insert(0, str(ROOT / "src"))
    from douyin_intelligence.download_credentials_adapter import account_record, selected_account_id
    account_id = selected_account_id(args.account_id)
    if account_id is not None:
        record = account_record(account_id)
        args.download_user_agent = record.get("user_agent", "")
        return record["cookies"], "download_account"
    return read_cookies(cookie_path(None)), "workspace_default"


async def resolve(args, cookies):
    crawler = ROOT / "third_party" / "MediaCrawler"
    os.chdir(crawler)  # upstream signing JS is opened relative to its root
    sys.path.insert(0, str(crawler))
    from playwright.async_api import async_playwright
    from media_platform.douyin.client import DouYinClient
    from media_platform.douyin.help import parse_video_info_from_url
    import logging
    logging.disable(logging.CRITICAL)  # upstream errors may contain raw response/URL data
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True, timeout=30000)
        try:
            user_agent = getattr(args, "download_user_agent", "")
            context = await browser.new_context(**({"user_agent": user_agent} if user_agent else {}))
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
            duration = detail_duration_seconds(detail)
            check_duration(duration, getattr(args, "max_seconds", None))
            # Preserve resolve's existing three-item return contract.
            args.resolved_duration_seconds = duration
            media = upstream_video_url(detail)
            if not media:
                raise ValueError("No video stream in detail")
            return info.aweme_id, str(detail.get("desc", "")), media
        finally:
            await browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", type=input_url, help="Douyin share text, HTTPS URL or video ID")
    parser.add_argument("--cookies", help="Netscape Cookie file; default: workspace root")
    parser.add_argument("--account-id", type=int, help="Verified workspace download account; default: selected account")
    parser.add_argument("--output-dir", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--max-bytes", type=max_bytes_argument, default=MAX_VIDEO_BYTES,
                        help="Hard video download cap in bytes; default: 500 MiB")
    parser.add_argument("--max-seconds", type=max_seconds_argument,
                        help="Reject videos beyond this metadata duration; default: no duration limit")
    parser.add_argument("--check", action="store_true", help="Offline input/Cookie validation only")
    args = parser.parse_args()
    args.output_dir = args.output_dir.expanduser().resolve()
    stage = "cookies"
    try:
        cookies, cookie_source = selected_cookies(args)
        if args.check:
            print(json.dumps({"status": "input_ok", "cookie_source": cookie_source, "cookie_count": len(cookies)}, ensure_ascii=False))
            return 0
        stage = "mediacrawler_resolve"
        video_id, title, media = asyncio.run(asyncio.wait_for(resolve(args, cookies), timeout=120))
        check_duration(getattr(args, "resolved_duration_seconds", None), args.max_seconds)
        stage = "project_download"
        sys.path.insert(0, str(ROOT / "src"))
        from douyin_intelligence.materials import download_video
        # Unique task directory avoids the downloader's existing-file cache and overwrites.
        from uuid import uuid4
        folder = args.output_dir / f"douyin-{video_id}-{time.strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}"
        folder.mkdir(parents=True, exist_ok=False)
        destination = folder / f"{video_id}.mp4"
        download_video(media, destination, {"materials": {"max_video_bytes": args.max_bytes,
                       "download_timeout_seconds": 60, "download_retries": 1}})
        digest = hashlib.sha256()
        with destination.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        receipt = {"status": "downloaded", "backend": "MediaCrawler + materials.download_video",
                   "video_id": video_id, "title": title, "source_url": f"https://www.douyin.com/video/{video_id}",
                   "file": str(destination), "bytes": destination.stat().st_size,
                   "sha256": digest.hexdigest(), "cookie_source": cookie_source}
        if getattr(args, "resolved_duration_seconds", None) is not None:
            receipt["duration_seconds"] = args.resolved_duration_seconds
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
