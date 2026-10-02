"""Platform-neutral interface for a system-wide "open the window" shortcut.

A backend only registers a key combination and calls back when it is pressed. It never
reads, posts, or simulates keyboard input, and never needs to see other keystrokes.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from clipflow.models.hotkey import Hotkey


class HotkeyError(Exception):
    """A shortcut can't be registered. The message is shown to the user."""


class HotkeyRegistration(Protocol):
    def unregister(self) -> None: ...


class GlobalHotkeyBackend(Protocol):
    def system_conflict(self, hotkey: Hotkey) -> str | None:
        """Name the OS feature already using ``hotkey``, or None."""
        ...

    def register(self, hotkey: Hotkey, callback: Callable[[], None]) -> HotkeyRegistration:
        """Register ``hotkey`` system-wide. Raises ``HotkeyError`` on failure."""
        ...


class UnsupportedHotkeyBackend:
    """Used where no native backend exists (e.g. future Windows builds until implemented)."""

    def system_conflict(self, hotkey: Hotkey) -> str | None:
        return None

    def register(self, hotkey: Hotkey, callback: Callable[[], None]) -> HotkeyRegistration:
        raise HotkeyError("Global shortcuts aren't supported on this platform yet.")


def create_hotkey_backend() -> GlobalHotkeyBackend:
    import sys

    if sys.platform == "darwin":
        from clipflow.platform.macos_hotkey import CarbonHotkeyBackend

        return CarbonHotkeyBackend()
    return UnsupportedHotkeyBackend()
