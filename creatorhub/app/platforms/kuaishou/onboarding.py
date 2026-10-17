"""Dismiss only the known Kuaishou Joyride tour through its own controls."""
from __future__ import annotations


_PORTAL = "#react-joyride-portal"
_OVERLAY = _PORTAL + " .react-joyride__overlay"
# These labels were already handled by the publisher's onboarding cleanup.
# Prefer ending the tour over advancing it; never use a page-wide business button.
_BUTTONS = ("跳过引导", "跳过", "我知道了", "知道了", "下一步")


async def dismiss_known_tour(page) -> bool | None:
    """True: closed; None: no tour; False: still blocked or unobservable.

    Only normal, scoped button clicks are allowed. A known button alone is not
    success: the actual Joyride overlay must become hidden before proceeding.
    Six bounded steps also cover the publisher's historical four-step tour.
    """
    try:
        overlay = page.locator(_OVERLAY)
        if not await overlay.count() or not await overlay.first.is_visible():
            return None
        portal = page.locator(_PORTAL)
        for _ in range(6):
            clicked = False
            for label in _BUTTONS:
                button = portal.get_by_role("button", name=label, exact=True)
                if await button.count() != 1 or not await button.first.is_visible():
                    continue
                try:
                    await button.first.click(timeout=1500)
                except Exception:
                    continue
                print(f"[ks-guide] 已点击新手引导按钮「{label}」", flush=True)
                clicked = True
                break
            if not clicked:
                print("[ks-guide] 引导遮罩仍在，未找到唯一的已知引导按钮；停止后续点击", flush=True)
                return False
            try:
                await overlay.first.wait_for(state="hidden", timeout=1500)
                return True
            except Exception:
                # A next-step button may keep the same overlay alive. Inspect
                # the next step again; never force a click through that overlay.
                await page.wait_for_timeout(200)
        return not await overlay.count() or not await overlay.first.is_visible()
    except Exception:
        # An observation failure cannot establish that clicking underneath is safe.
        return False
