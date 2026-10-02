"""Shortcut recorder: click, press the new combination, done. Esc cancels.

On macOS the physical key is read from the native key code, so recording works with any
input source (e.g. Khmer). Elsewhere, and in tests, the Qt key is used.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFocusEvent, QGuiApplication, QKeyEvent
from PySide6.QtWidgets import QPushButton, QWidget

from clipflow.models.hotkey import KEY_NAMES, MAC_KEY_NAMES, PUNCTUATION_KEYS, Hotkey

_QT_KEY_NAMES: dict[int, str] = {
    **{int(getattr(Qt.Key, f"Key_{c}")): c for c in KEY_NAMES if len(c) == 1 and c.isalnum()},
    **{int(getattr(Qt.Key, f"Key_F{n}")): f"F{n}" for n in range(1, 21)},
    int(Qt.Key.Key_Space): "Space",
    **{ord(c): c for c in PUNCTUATION_KEYS},
}
_MODIFIER_KEYS = {
    Qt.Key.Key_Control,
    Qt.Key.Key_Meta,
    Qt.Key.Key_Alt,
    Qt.Key.Key_Shift,
    Qt.Key.Key_AltGr,
    Qt.Key.Key_CapsLock,
}


def modifiers_from_qt(modifiers: Qt.KeyboardModifier) -> frozenset[str]:
    """Qt's modifier flags in our names. On macOS Qt reports ⌘ as Control and ⌃ as Meta."""
    mac = sys.platform == "darwin"
    mapping = {
        Qt.KeyboardModifier.ControlModifier: "cmd" if mac else "ctrl",
        Qt.KeyboardModifier.MetaModifier: "ctrl" if mac else "cmd",
        Qt.KeyboardModifier.AltModifier: "option",
        Qt.KeyboardModifier.ShiftModifier: "shift",
    }
    return frozenset(name for flag, name in mapping.items() if modifiers & flag)


def key_name(event: QKeyEvent) -> str | None:
    if QGuiApplication.platformName() == "cocoa":
        name = MAC_KEY_NAMES.get(event.nativeVirtualKey())
        if name is not None:
            return name
    return _QT_KEY_NAMES.get(int(event.key()))


class HotkeyEdit(QPushButton):
    """Shows the current shortcut; click to record a new one."""

    recorded = Signal(object)  # Hotkey

    def __init__(self, hotkey: Hotkey, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("hotkeyEdit")
        self.setAutoDefault(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("Global shortcut")
        self.setAccessibleDescription("Activate, then press the new shortcut. Escape cancels.")
        self.setMinimumWidth(150)
        self._hotkey = hotkey
        self._recording = False
        self.clicked.connect(self.start_recording)
        self._render()

    @property
    def hotkey(self) -> Hotkey:
        return self._hotkey

    @property
    def recording(self) -> bool:
        return self._recording

    def set_hotkey(self, hotkey: Hotkey) -> None:
        self._hotkey = hotkey
        self._recording = False
        self._render()

    def start_recording(self) -> None:
        self._recording = True
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self._render()

    def cancel_recording(self) -> None:
        self._recording = False
        self._render()

    def _render(self, held: frozenset[str] = frozenset()) -> None:
        if self._recording:
            prefix = Hotkey("", held).display() if held else ""
            self.setText(f"{prefix}… press keys" if prefix else "Press shortcut…")
        else:
            self.setText(self._hotkey.display())

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._recording:
            if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.start_recording()
                return
            super().keyPressEvent(event)
            return
        if event.key() == Qt.Key.Key_Escape and not event.modifiers():
            self.cancel_recording()
            return
        modifiers = modifiers_from_qt(event.modifiers())
        if event.key() in _MODIFIER_KEYS:
            self._render(modifiers)  # show modifiers as they're held
            return
        name = key_name(event)
        if name is None:
            self.setText("Unsupported key — try again")
            return
        self._hotkey = Hotkey(name, modifiers)
        self._recording = False
        self._render()
        self.recorded.emit(self._hotkey)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if self._recording and event.key() in _MODIFIER_KEYS:
            self._render(modifiers_from_qt(event.modifiers()))
            return
        super().keyReleaseEvent(event)

    def focusOutEvent(self, event: QFocusEvent) -> None:
        if self._recording:
            self.cancel_recording()
        super().focusOutEvent(event)
