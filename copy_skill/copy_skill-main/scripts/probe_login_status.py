"""Probe the dedicated Chrome (CDP 9223) for the douyin LOGIN_STATUS cookie."""
from __future__ import annotations

import asyncio
import os
import sys

os.environ["NO_PROXY"] = "localhost,127.0.0.1"
os.environ["no_proxy"] = "localhost,127.0.0.1"


async def main() -> int:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9223", timeout=15000)
        context = browser.contexts[0]
        page = None
        for pg in context.pages:
            if "douyin.com" in (pg.url or ""):
                page = pg
                break
        page = page or await context.new_page()
        if "douyin.com" not in (page.url or ""):
            await page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=45000)
        ok = False
        for i in range(10):
            all_cookies = await context.cookies()
            names = {c["name"] for c in all_cookies}
            ls = "LOGIN_STATUS" in names
            try:
                has_ls = await page.evaluate("() => window.localStorage.getItem('HasUserLogin')")
            except Exception:  # noqa: BLE001
                has_ls = None
            print(f"probe{i + 1}: LOGIN_STATUS_cookie={ls} HasUserLogin={has_ls!r}")
            if ls:
                ok = True
                break
            await asyncio.sleep(6)
        print("RESULT:", "PONG_READY" if ok else "PONG_NOT_READY")
        return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
