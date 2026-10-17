"""Opt-in real offscreen headed Chromium; local documents and temp profile only."""
import copy
import json
import os
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

import pytest
from patchright.async_api import async_playwright

from app.browser.identity import Identity
from app.browser.manager import BrowserManager


ORIGIN = "https://channels.weixin.qq.com"
pytestmark = pytest.mark.local_cdp


@unittest.skipUnless(os.environ.get("CREATORHUB_SESSION_NATIVE_TEST") == "1",
                     "explicit opt-in for isolated offscreen headed Chromium regression")
class NativeSessionStorageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="creatorhub-native-session-")
        self.saved = []
        self.manager = BrowserManager(
            "synthetic-fixture-UA", self.scratch.name,
            session_state_callback=lambda identity, state: self.saved.append(copy.deepcopy(state)))
        self.manager._pw = await async_playwright().start()
        chrome = [Path(os.environ.get(key, "")) / "Google/Chrome/Application/chrome.exe"
                  for key in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
        if any(path.is_file() for path in chrome):
            self.manager._browser_channel = "chrome"
        self.identity = Identity(
            account_id=971, platform="shipinhao", identity_mode="native",
            profile_dir=str(Path(self.scratch.name) / "synthetic-profile"))

    async def asyncTearDown(self):
        try:
            await self.manager.stop()
        finally:
            self.scratch.cleanup()

    async def document(self, route):
        # Every synthetic app request is fulfilled locally, including the
        # deliberately unrelated origin. No platform HTTP request is sent.
        await route.fulfill(status=200, content_type="text/html", body=(
            "<!doctype html><title>Isolated session regression</title><p>fixture</p>"))

    async def test_real_cold_profile_tab_restore_preserves_native_storage_and_clear(self):
        context = await self.manager.context_for(self.identity)
        await context.route("**/*", self.document)
        page = await context.new_page()
        await page.goto(ORIGIN + "/synthetic-fixture")
        await context.add_cookies([{
            "name": "_finder_auth", "value": "synthetic-session-only",
            "domain": ".weixin.qq.com", "path": "/", "expires": -1,
            "httpOnly": True, "secure": True,
        }])
        await page.evaluate("""async () => {
            sessionStorage.setItem('fixture_tab_auth', 'fresh-tab-fixture');
            localStorage.setItem('fixture_native_local', 'native-newer-fixture');
            await new Promise((resolve, reject) => {
                const request = indexedDB.open('fixture-native-db', 1);
                request.onupgradeneeded = () => request.result.createObjectStore('items');
                request.onerror = () => reject(request.error);
                request.onsuccess = () => {
                    const db = request.result;
                    const transaction = db.transaction('items', 'readwrite');
                    transaction.objectStore('items').put('native-idb-fixture', 'fixture');
                    transaction.oncomplete = () => { db.close(); resolve(); };
                    transaction.onerror = () => reject(transaction.error);
                };
            });
        }""")
        self.assertTrue(await self.manager.snapshot_session(self.identity, context))
        # Closing the short health tab must not erase the last observed SS on
        # a later no-frame checkpoint or final native profile flush.
        await page.close()
        self.assertTrue(await self.manager.snapshot_session(self.identity, context))
        await self.manager.close_context(self.identity.key)
        checkpoint = copy.deepcopy(self.saved[-1])
        self.assertEqual(checkpoint["sessionStorage"], [{"origin": ORIGIN, "items": [
            {"name": "fixture_tab_auth", "value": "fresh-tab-fixture"},
        ]}])
        self.assertTrue(checkpoint["origins"][0].get("indexedDB"))
        self.assertEqual(checkpoint["cookies"][0]["expires"], -1)

        # Simulate the cold DB path: no in-memory latest snapshot may help.
        await self.manager._session_snapshots.shutdown()
        checkpoint["origins"][0]["localStorage"] = [
            {"name": "fixture_native_local", "value": "stale-db-must-not-win"}]
        identity = replace(self.identity, bridge_states=(json.dumps(checkpoint),))
        cold = await self.manager.context_for(identity)
        await cold.route("**/*", self.document)
        # Direct context.new_page is the same path used by interactive and
        # publisher callers; it is covered, not merely manager.new_page.
        restored = await cold.new_page()
        await restored.goto(ORIGIN + "/synthetic-fixture")
        self.assertEqual(await restored.evaluate("sessionStorage.getItem('fixture_tab_auth')"),
                         "fresh-tab-fixture")
        self.assertEqual(await restored.evaluate("localStorage.getItem('fixture_native_local')"),
                         "native-newer-fixture")
        idb = await restored.evaluate("""async () => await new Promise((resolve, reject) => {
            const request = indexedDB.open('fixture-native-db', 1);
            request.onerror = () => reject(request.error);
            request.onsuccess = () => {
                const db = request.result;
                const read = db.transaction('items').objectStore('items').get('fixture');
                read.onsuccess = () => { db.close(); resolve(read.result); };
                read.onerror = () => reject(read.error);
            };
        })""")
        self.assertEqual(idb, "native-idb-fixture")

        await restored.evaluate("sessionStorage.setItem('fixture_tab_auth', 'new-live-tab')")
        await restored.reload()
        self.assertEqual(await restored.evaluate("sessionStorage.getItem('fixture_tab_auth')"), "new-live-tab")
        await restored.evaluate("sessionStorage.clear()")
        await restored.reload()
        self.assertEqual(await restored.evaluate("sessionStorage.length"), 0,
                         "No permanent init script may resurrect cleared auth")
        await restored.goto("https://unrelated.invalid/synthetic-fixture")
        self.assertEqual(await restored.evaluate("sessionStorage.length"), 0)
