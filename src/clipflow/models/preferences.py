from __future__ import annotations

from dataclasses import dataclass, replace

from clipflow.models.hotkey import DEFAULT_HOTKEY, Hotkey

THEME_MODES = ("system", "light", "dark")
PREVIEW_LINES_MIN = 1
PREVIEW_LINES_MAX = 8


@dataclass(frozen=True, slots=True)
class UiPreferences:
    """Appearance and behavior preferences. Deliberately UI-only: nothing here can enable
    clipboard reading, recording, command execution, or launch at login."""

    theme: str = "system"  # system | light | dark
    preview_lines: int = 3  # command lines shown on each card
    hide_after_copy: bool = False  # dismiss the window shortly after a copy
    unified_title_bar: bool = True  # macOS: draw content under a transparent title bar
    hotkey_enabled: bool = True  # global shortcut that shows/hides the window
    hotkey: str = DEFAULT_HOTKEY.to_text()  # e.g. "ctrl+option+cmd+V"

    def validated(self) -> UiPreferences:
        try:
            hotkey = Hotkey.parse(self.hotkey).to_text()
        except ValueError:
            hotkey = DEFAULT_HOTKEY.to_text()
        return replace(
            self,
            theme=self.theme if self.theme in THEME_MODES else "system",
            preview_lines=min(max(self.preview_lines, PREVIEW_LINES_MIN), PREVIEW_LINES_MAX),
            hotkey=hotkey,
        )

    def global_hotkey(self) -> Hotkey | None:
        """The shortcut to register, or None when turned off."""
        return Hotkey.parse(self.validated().hotkey) if self.hotkey_enabled else None
