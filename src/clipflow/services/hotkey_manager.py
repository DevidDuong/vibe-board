"""Owns the app's single global shortcut: validation, conflicts, and safe switching.

Switching registers the new combination *before* releasing the old one, so a failed change
always leaves the previous working shortcut active. Qt-free and platform-neutral.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from clipflow.models.hotkey import Hotkey, validation_problem
from clipflow.platform.hotkey import GlobalHotkeyBackend, HotkeyError, HotkeyRegistration

logger = logging.getLogger(__name__)


class HotkeyManager:
    def __init__(self, backend: GlobalHotkeyBackend, on_pressed: Callable[[], None]) -> None:
        self._backend = backend
        self._on_pressed = on_pressed
        self._registration: HotkeyRegistration | None = None
        self.active: Hotkey | None = None

    def problem(self, hotkey: Hotkey) -> str | None:
        """Why ``hotkey`` can't be used, or None. Checks rules and macOS's own shortcuts.

        Other apps' global shortcuts can't be detected by any public macOS API.
        """
        problem = validation_problem(hotkey)
        if problem is None and hotkey != self.active:
            problem = self._backend.system_conflict(hotkey)
        return problem

    def activate(self, hotkey: Hotkey | None) -> None:
        """Make ``hotkey`` the global shortcut (None turns it off). Raises ``HotkeyError``;
        on failure the previous shortcut stays registered."""
        if hotkey == self.active:
            return
        if hotkey is None:
            self.stop()
            return
        problem = self.problem(hotkey)
        if problem:
            raise HotkeyError(problem)
        registration = self._backend.register(hotkey, self._on_pressed)  # may raise
        previous = self._registration
        self._registration, self.active = registration, hotkey
        if previous is not None:
            previous.unregister()
        logger.info("Global shortcut active (%s)", hotkey.display())

    def stop(self) -> None:
        if self._registration is not None:
            self._registration.unregister()
            logger.info("Global shortcut turned off")
        self._registration, self.active = None, None
