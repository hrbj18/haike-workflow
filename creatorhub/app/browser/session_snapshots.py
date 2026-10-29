"""Best-effort checkpoints for short-lived Kuaishou and Channels sessions."""
from __future__ import annotations

import asyncio
import copy
import inspect
import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit
from weakref import WeakKeyDictionary, WeakSet

from .identity import Identity


def _platform_host(platform: str, host: str, *, cookie: bool = False) -> bool:
    host = str(host or "").lstrip(".").lower()
    if platform == "kuaishou":
        return host == "kuaishou.com" or host.endswith(".kuaishou.com")
    if platform == "shipinhao":
        return (cookie and host == "weixin.qq.com") or (
            host == "channels.weixin.qq.com"
            or host.endswith(".channels.weixin.qq.com"))
    return False


def platform_session_state(identity: Identity, state: dict) -> dict:
    """Copy only this platform's state; preserve cookie expiry and attributes."""
    if not isinstance(state, dict):
        return {"cookies": [], "origins": []}
    cookies = [copy.deepcopy(cookie) for cookie in state.get("cookies", [])
               if isinstance(cookie, dict)
               and cookie.get("name")
               and _platform_host(identity.platform, cookie.get("domain"), cookie=True)]
    origins = []
    for origin in state.get("origins", []):
        if not isinstance(origin, dict):
            continue
        try:
            parsed = urlsplit(str(origin.get("origin") or ""))
        except ValueError:
            continue
        if parsed.scheme == "https" and _platform_host(identity.platform, parsed.hostname):
            origins.append(copy.deepcopy(origin))
    result = {"cookies": cookies, "origins": origins}
    if "sessionStorage" in state:
        result["sessionStorage"] = []
        for entry in state.get("sessionStorage") or []:
            if not isinstance(entry, dict):
                continue
            try:
                parsed = urlsplit(str(entry.get("origin") or ""))
            except ValueError:
                continue
            if (parsed.scheme != "https" or parsed.username or parsed.password
                    or parsed.path or parsed.query or parsed.fragment
                    or not _platform_host(identity.platform, parsed.hostname)):
                continue
            items = [copy.deepcopy(item) for item in entry.get("items", [])
                     if isinstance(item, dict) and isinstance(item.get("name"), str)
                     and isinstance(item.get("value"), str)]
            result["sessionStorage"].append({"origin": parsed.geturl(), "items": items})
    return result


async def _tab_session_storage(identity: Identity, context) -> list | None:
    """Capture only owned HTTPS frames, without navigating or opening a page."""
    pages = getattr(context, "pages", None)
    if not isinstance(pages, (tuple, list)):
        return None  # Keep older browser adapters' storage-state format intact.
    by_origin = {}
    for page in pages:
        for frame in getattr(page, "frames", ()):
            if getattr(frame, "url", None) in getattr(page, "_creatorhub_local_seed_urls", ()):
                # A locally fulfilled bootstrap is not a live platform
                # observation, even while another tab is being checkpointed.
                continue
            try:
                parsed = urlsplit(frame.url)
            except (TypeError, ValueError):
                continue
            if parsed.scheme != "https" or not _platform_host(identity.platform, parsed.hostname):
                continue
            entry = await frame.evaluate("""() => ({origin: location.origin,
                items: Object.entries(sessionStorage).map(([name, value]) => ({name, value}))})""")
            if isinstance(entry, dict) and entry.get("origin") == (
                    f"{parsed.scheme}://{parsed.netloc}"):
                # Newer tabs take precedence. Empty state is meaningful and
                # must not accidentally resurrect an older tab's saved values.
                by_origin[entry["origin"]] = entry
    return list(by_origin.values()) if by_origin else None


def _bridge_state(identity: Identity) -> dict | None:
    newest = None
    for raw in identity.bridge_states:
        try:
            state = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if isinstance(state, dict):
            newest = platform_session_state(identity, state)
    return newest


def _cookie_generation(cookies: list) -> set:
    # Internal comparison only. A different token set must not inherit tab auth
    # observed before that rotation, even if no platform page is currently open.
    return {(c.get("name"), str(c.get("domain", "")).lstrip(".").lower(),
             c.get("path", "/"), c.get("value")) for c in cookies}


async def capture_platform_session_state(identity: Identity, context,
                                         previous_state: dict | None = None) -> dict:
    """Capture without saving, including anonymous logins awaiting DB commit."""
    capture = context.storage_state
    try:
        supports_idb = "indexed_db" in inspect.signature(capture).parameters
    except (TypeError, ValueError):
        supports_idb = False
    raw = await asyncio.wait_for(
        capture(indexed_db=True) if supports_idb else capture(), timeout=5)
    state = platform_session_state(identity, raw)
    observed = await asyncio.wait_for(_tab_session_storage(identity, context), timeout=5)
    previous = previous_state if previous_state is not None else _bridge_state(identity)
    tab_storage = {}
    if (previous and _cookie_generation(previous.get("cookies", []))
            == _cookie_generation(state["cookies"])):
        tab_storage = {entry["origin"]: copy.deepcopy(entry)
                       for entry in previous.get("sessionStorage", [])}
    if observed is not None:
        observed = platform_session_state(identity, {"sessionStorage": observed})["sessionStorage"]
        tab_storage.update((entry["origin"], entry) for entry in observed)
    if tab_storage or observed is not None:
        state["sessionStorage"] = list(tab_storage.values())
    return state


async def _seed_new_tab(page, context, state: dict) -> bool:
    """Seed once in local HTML, leaving no script to replay on clear/reload.

    CDP bypasses service workers and the temporary route blocks every request
    except our locally fulfilled document. A failed setup never navigates.
    Only a newly created, untouched about:blank page may enter this function.
    """
    if getattr(page, "url", None) != "about:blank":
        return False
    entries = [entry for entry in state.get("sessionStorage", []) if entry["items"]]
    if not entries:
        return False
    session = None
    routed = False
    seed_url = ""
    token = uuid.uuid4().hex
    seed_urls = set()
    page._creatorhub_local_seed_urls = seed_urls

    async def local_only(route):
        if route.request.url == seed_url and route.request.resource_type == "document":
            await route.fulfill(status=200, content_type="text/html", body=(
                '<!doctype html><meta name="creatorhub-local-session" content="' + token + '">'))
        else:
            await route.abort()

    try:
        session = await context.new_cdp_session(page)
        await session.send("Network.setBypassServiceWorker", {"bypass": True})
        await page.route("**/*", local_only)
        routed = True
        for entry in entries:
            seed_url = entry["origin"] + "/.well-known/creatorhub-local-session/" + token
            seed_urls.add(seed_url)
            await page.goto(seed_url, wait_until="domcontentloaded", timeout=3000)
            actual = await page.evaluate("""() => ({url: location.href,
                token: document.querySelector('meta[name="creatorhub-local-session"]')?.content})""")
            if actual != {"url": seed_url, "token": token}:
                return False
            await page.evaluate("""items => {
                if (sessionStorage.length === 0)
                    for (const item of items) sessionStorage.setItem(item.name, item.value);
            }""", entry["items"])
        return True
    except Exception:
        return False
    finally:
        # Return the untouched new tab in the same blank state callers expect.
        # Its per-origin session namespace survives this local navigation. This
        # also avoids a retained seed document overriding a later business tab.
        # Independent bounded finalizers also run if an earlier finalizer is
        # cancelled. CancelledError propagates after cleanup, never into work.
        try:
            if getattr(page, "url", None) in seed_urls:
                try:
                    await asyncio.wait_for(page.goto(
                        "about:blank", wait_until="domcontentloaded", timeout=2000), timeout=2.5)
                except Exception:
                    pass  # Exact seed URLs remain excluded from checkpoints.
        finally:
            try:
                if routed:
                    try:
                        await asyncio.wait_for(page.unroute("**/*", local_only), timeout=1)
                    except Exception:
                        pass
            finally:
                try:
                    if session is not None:
                        try:
                            await asyncio.wait_for(session.send(
                                "Network.setBypassServiceWorker", {"bypass": False}), timeout=1)
                        except Exception:
                            pass
                finally:
                    if session is not None:
                        try:
                            await asyncio.wait_for(session.detach(), timeout=1)
                        except Exception:
                            pass


async def restore_platform_session_storage(context, identity: Identity,
                                            state_provider=None) -> bool:
    """Prepare each owned new tab once, including direct context.new_page calls."""
    if (identity.platform not in {"kuaishou", "shipinhao"} or identity.account_id is None
            or getattr(context, "_creatorhub_tab_restore", False)):
        return False
    original = getattr(context, "new_page", None)
    if not callable(original):
        return False

    async def prepare(page):
        state = state_provider() if callable(state_provider) else None
        if state is None:
            state = _bridge_state(identity)
        if not state or not any(entry["items"] for entry in state.get("sessionStorage", [])):
            return
        saved = {(c.get("name"), str(c.get("domain", "")).lstrip("."), c.get("path", "/")):
                 c.get("value") for c in state.get("cookies", [])}
        live = await context.cookies()
        if any(saved[key] != cookie.get("value") for cookie in live
               if (key := (cookie.get("name"), str(cookie.get("domain", "")).lstrip("."),
                           cookie.get("path", "/"))) in saved):
            return
        await _seed_new_tab(page, context, state)

    async def new_page(*args, **kwargs):
        page = await original(*args, **kwargs)
        try:
            await prepare(page)
        except asyncio.CancelledError:
            # This new page has not been handed to any caller or user. Do not
            # leave it behind if preparation was cancelled part way through.
            try:
                await asyncio.wait_for(page.close(), timeout=3)
            except Exception:
                pass
            finally:
                raise
        except Exception:
            # Optional recovery must not leak values or strand an owned page.
            pass
        return page

    context.new_page = new_page
    context._creatorhub_tab_restore = True
    for page in list(getattr(context, "pages", ())):
        if getattr(page, "url", None) == "about:blank":
            try:
                await prepare(page)
            except Exception:
                pass
    return True


@dataclass
class _TrackedSession:
    identity: Identity
    context: object
    closed: bool = False
    task: asyncio.Task | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class SessionSnapshots:
    """Checkpoint live contexts without extending or resetting platform sessions.

    ``callback(identity, state)`` may be synchronous or asynchronous. It must
    store the supplied dict for that account only, without changing account
    status. Empty state and failures never invoke the callback. No exception
    text is logged because browser errors may contain authentication values.
    """

    def __init__(self, callback: Callable | None, interval_seconds: float = 30):
        self.callback = callback
        self.interval_seconds = max(0.01, float(interval_seconds))
        self._sessions: dict[int, _TrackedSession] = {}
        self._closed_contexts: WeakSet = WeakSet()
        self._latest_states: dict[tuple, dict] = {}
        self._paused: WeakKeyDictionary = WeakKeyDictionary()

    async def pause(self, context) -> None:
        self._paused[context] = self._paused.get(context, 0) + 1
        session = self._sessions.get(id(context))
        if session is not None:
            # Drain a capture already in flight before the caller clears auth.
            async with session.lock:
                pass

    def resume(self, context) -> None:
        count = self._paused.get(context, 0)
        if count <= 1:
            self._paused.pop(context, None)
        else:
            self._paused[context] = count - 1

    def is_paused(self, context) -> bool:
        return bool(self._paused.get(context, 0))

    def _eligible(self, identity: Identity) -> bool:
        return bool(callable(self.callback) and identity.account_id is not None
                    and identity.platform in {"kuaishou", "shipinhao"})

    @staticmethod
    def _identity_key(identity: Identity) -> tuple:
        return (identity.account_id, identity.platform,
                os.path.normcase(str(Path(identity.profile_dir).resolve())))

    def latest_state(self, identity: Identity) -> dict | None:
        """Return this account/profile's last saved state for a cold hand-off."""
        if not self._eligible(identity):
            return None
        state = self._latest_states.get(self._identity_key(identity))
        return copy.deepcopy(state) if state is not None else None

    def remember(self, identity: Identity, state: dict) -> bool:
        """Remember a business-confirmed login without committing it to a DB."""
        if not self._eligible(identity):
            return False
        state = platform_session_state(identity, state)
        if not state["cookies"]:
            return False
        self._latest_states[self._identity_key(identity)] = copy.deepcopy(state)
        return True

    def track(self, identity: Identity, context) -> None:
        if not self._eligible(identity):
            return
        key = id(context)
        if key in self._sessions:
            return
        self._closed_contexts.discard(context)
        session = _TrackedSession(identity, context)
        self._sessions[key] = session

        def closed(*_args):
            session.closed = True
            self._closed_contexts.add(context)
            self._sessions.pop(key, None)
            if session.task is not None:
                session.task.cancel()

        try:
            context.on("close", closed)
        except Exception:
            self._sessions.pop(key, None)
            return
        session.task = asyncio.create_task(self._periodic(session))

    async def _periodic(self, session: _TrackedSession) -> None:
        try:
            while not session.closed:
                await asyncio.sleep(self.interval_seconds)
                await self.snapshot(session.identity, session.context)
        except asyncio.CancelledError:
            pass

    async def snapshot(self, identity: Identity, context) -> bool:
        if (not self._eligible(identity) or context in self._closed_contexts
                or self._paused.get(context, 0)):
            return False
        session = self._sessions.get(id(context))
        if session is not None and (session.closed or session.identity.key != identity.key):
            return False
        lock = session.lock if session is not None else asyncio.Lock()
        async with lock:
            try:
                if context in self._closed_contexts or self._paused.get(context, 0):
                    return False
                state = await capture_platform_session_state(
                    identity, context, self.latest_state(identity))
                if context in self._closed_contexts or self._paused.get(context, 0):
                    return False
                state = platform_session_state(identity, state)
                # No cookies means no usable browser authentication snapshot.
                # Never replace a saved session with an empty/closed profile.
                if not state["cookies"]:
                    return False
                result = self.callback(identity, state)
                if inspect.isawaitable(result):
                    result = await asyncio.wait_for(result, timeout=5)
                if result is False:
                    return False
                self.remember(identity, state)
                return True
            except Exception:
                return False

    async def snapshot_context(self, context) -> bool:
        session = self._sessions.get(id(context))
        if session is None:
            return False
        return await self.snapshot(session.identity, context)

    async def shutdown(self) -> None:
        sessions = list(self._sessions.values())
        for session in sessions:
            await self.snapshot(session.identity, session.context)
            if session.task is not None:
                session.task.cancel()
        if sessions:
            await asyncio.gather(*(session.task for session in sessions
                                   if session.task is not None), return_exceptions=True)
        self._sessions.clear()
        self._latest_states.clear()
        self._paused.clear()
