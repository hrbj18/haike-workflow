"""Strict Channels location clearance before the publish click."""
import asyncio

from app.platforms.channels.publish import _clear_location


class _Node:
    def __init__(self, state, role):
        self.state = state
        self.role = role

    @property
    def first(self):
        return self

    async def count(self):
        return 0 if self.role == "missing" else 1

    async def is_visible(self):
        if self.role == "choice":
            return self.state["menu_open"] and self.state["has_choice"]
        return self.role != "missing"

    async def inner_text(self):
        return self.state["label"]

    async def click(self, timeout=None):
        if self.role == "trigger":
            self.state["menu_open"] = True
        elif self.role == "choice":
            self.state["label"] = "不显示位置"
            self.state["menu_open"] = False

    def get_by_text(self, text, exact=False):
        assert text == "不显示位置" and exact
        return _Node(self.state, "choice")


class _Frame:
    def __init__(self, state):
        self.state = state

    def locator(self, selector):
        if selector == '.post-position-wrap .position-display':
            return _Node(self.state, "control")
        if selector == '.post-position-wrap .location-name':
            return _Node(self.state, "trigger")
        if selector == '.post-position-wrap':
            return _Node(self.state, "root")
        return _Node(self.state, "missing")


class _Page:
    def __init__(self, state):
        self.frames = [_Frame(state)]

    async def wait_for_timeout(self, delay):
        pass


def test_existing_hidden_location_passes_without_click():
    state = {"label": "不显示位置", "menu_open": False, "has_choice": True}
    assert asyncio.run(_clear_location(_Page(state))) == ""
    assert state["menu_open"] is False


def test_saved_city_is_cleared_and_read_back():
    state = {"label": "广州市", "menu_open": False, "has_choice": True}
    assert asyncio.run(_clear_location(_Page(state))) == ""
    assert state["label"] == "不显示位置"


def test_missing_option_blocks_publish():
    state = {"label": "广州市", "menu_open": False, "has_choice": False}
    assert "找不到可见" in asyncio.run(_clear_location(_Page(state)))
    assert state["label"] == "广州市"
