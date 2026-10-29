"""Warm the dedicated project Chrome (CDP 9223) with a Netscape cookie export.

Reads a Netscape HTTP cookie file, injects every .douyin.com / www.douyin.com
cookie into the running dedicated Chrome via Playwright CDP, reloads douyin.com
and verifies the login state. Does NOT print any cookie values.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# CDP discovery must never go through a system proxy.
os.environ["NO_PROXY"] = "localhost,127.0.0.1"
os.environ["no_proxy"] = "localhost,127.0.0.1"

COOKIE_FILE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("www.douyin.com_cookies.txt")
CDP_URL = "http://127.0.0.1:9223"


def parse_netscape(path: Path) -> list[dict]:
    cookies: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _flag, cpath, secure, expires, name, value = parts[:7]
        domain = domain.strip()
        if "douyin.com" not in domain:
            continue
        try:
            exp = int(expires)
        except ValueError:
            exp = -1
        cookies.append(
            {
                "name": name,
                "value": value,
                "domain": domain,
                "path": cpath or "/",
                "secure": secure.upper() == "TRUE",
                "expires": exp if exp > 0 else -1,
            }
        )
    return cookies


async def ensure_chrome() -> None:
    """Launch the dedicated Chrome (same flags as copy_skill) if 9223 is down."""
    import socket
    import subprocess
    import time

    def cdp_ready(port: int) -> bool:
        with socket.socket() as s:
            s.settimeout(1.0)
            return s.connect_ex(("127.0.0.1", port)) == 0

    if cdp_ready(9223):
        print("[warm] dedicated Chrome already running on 9223")
        return
    chrome = Path(r"C:/Program Files/Google/Chrome/Application/chrome.exe")
    profile = Path(__file__).resolve().parents[1] / "third_party/MediaCrawler/browser_data/cdp_dy_user_data_dir"
    if not chrome.is_file():
        raise FileNotFoundError(str(chrome))
    profile.mkdir(parents=True, exist_ok=True)
    chrome_cmd = [
        str(chrome),
        "--remote-debugging-port=9223",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--remote-allow-origins=http://127.0.0.1:9223",
        "https://www.douyin.com/jingxuan",
    ]
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    try:  # break away from any sandbox job object so Chrome outlives this command
        subprocess.Popen(chrome_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=flags | 0x01000000)  # CREATE_BREAKAWAY_FROM_JOB
        print("[warm] chrome launched with breakaway-from-job")
    except OSError:
        subprocess.Popen(chrome_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=flags)
        print("[warm] chrome launched (no breakaway)")
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if cdp_ready(9223):
            print("[warm] dedicated Chrome started on 9223")
            return
        time.sleep(0.4)
    raise TimeoutError("Chrome CDP port 9223 not ready in 25s")


async def main() -> int:
    from playwright.async_api import async_playwright

    await ensure_chrome()
    cookies = parse_netscape(COOKIE_FILE)
    key_names = {"sessionid", "sessionid_ss", "sid_guard", "sid_tt", "uid_tt"}
    have_keys = {c["name"] for c in cookies} & key_names
    print(f"[warm] parsed {len(cookies)} douyin cookies; session keys present: {sorted(have_keys)}")
    if not have_keys:
        print("[warm] FAIL: no session cookies found in export")
        return 2

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL, timeout=15000)
        context = browser.contexts[0]
        await context.add_cookies(cookies)
        print(f"[warm] injected {len(cookies)} cookies into context")

        page = None
        for pg in context.pages:
            if "douyin.com" in (pg.url or ""):
                page = pg
                break
        if page is None:
            page = await context.new_page()
        await page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=45000)
        await page.reload(wait_until="domcontentloaded")

        ok = False
        for attempt in range(8):  # poll up to ~40s for douyin to accept the session
            await asyncio.sleep(5)
            title = ""
            try:
                title = await page.title()
            except Exception:  # noqa: BLE001
                pass
            has_login_ls = None
            try:
                has_login_ls = await page.evaluate("() => window.localStorage.getItem('HasUserLogin')")
            except Exception:  # noqa: BLE001
                pass
            state = await context.cookies("https://www.douyin.com")
            cookie_map = {c["name"]: c["value"] for c in state}
            login_status = cookie_map.get("LOGIN_STATUS")
            ok = (has_login_ls == "1") or (login_status == "1")
            print(f"[warm] poll{attempt + 1}: title={title[:40]!r} HasUserLogin={has_login_ls!r} LOGIN_STATUS={login_status!r}")
            if ok:
                break

        print("[warm] RESULT:", "LOGGED_IN" if ok else "NOT_LOGGED_IN")
        # keep the dedicated Chrome running; only detach this CDP client
        return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
