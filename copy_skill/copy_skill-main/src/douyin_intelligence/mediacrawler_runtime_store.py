"""Preserve explicit clip duration through upstream's runtime store whitelist."""
from __future__ import annotations

from contextvars import ContextVar
import math


def install_duration_bridge(store_module):
    """Wrap the owned subprocess's store without editing third-party sources."""
    if getattr(store_module, "_copy_skill_duration_bridge", False):
        return False
    current = ContextVar("copy_skill_aweme_duration", default=None)
    original_update = store_module.update_douyin_aweme
    original_create = store_module.DouyinStoreFactory.create_store

    class DurationStore:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def __getattr__(self, name):
            return getattr(self.wrapped, name)

        async def store_content(self, content_item):
            item = dict(content_item)
            observed = current.get()
            if (observed is not None and str(item.get("aweme_id") or "") == observed[0]
                    and "duration_ms" not in item):
                item["duration_ms"] = observed[1]
            return await self.wrapped.store_content(content_item=item)

    async def update(aweme_item):
        value = (aweme_item.get("video") or {}).get("duration") if isinstance(aweme_item.get("video"), dict) else None
        duration = None
        if not isinstance(value, bool):
            try:
                number = float(value)
                if math.isfinite(number) and 0 < number <= 86400000:
                    duration = int(number) if number.is_integer() else number
            except (TypeError, ValueError, OverflowError):
                pass
        observed = (str(aweme_item.get("aweme_id") or ""), duration) if duration is not None else None
        token = current.set(observed)
        try:
            return await original_update(aweme_item)
        finally:
            current.reset(token)

    store_module.update_douyin_aweme = update
    store_module.DouyinStoreFactory.create_store = staticmethod(lambda: DurationStore(original_create()))
    store_module._copy_skill_duration_bridge = True
    return True
