"""Settings: appearance, UI behavior, and the global shortcut. There is intentionally no
recording, clipboard-reading, command-execution, or launch-at-login option."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from clipflow import APP_NAME
from clipflow.models.hotkey import DEFAULT_HOTKEY, Hotkey
from clipflow.models.preferences import PREVIEW_LINES_MAX, PREVIEW_LINES_MIN, UiPreferences
from clipflow.ui.hotkey_edit import HotkeyEdit
from clipflow.ui.theme import SPACE_2, SPACE_3, SPACE_4, SPACE_5
from clipflow.ui.widgets import make_button, plain_label

HotkeyChecker = Callable[[Hotkey], "str | None"]
SaveHandler = Callable[[UiPreferences], None]


class SettingsSaveError(Exception):
    """Raised by the save handler; the message is shown and the dialog stays open."""


THEME_LABELS = {"system": "Match System", "light": "Light", "dark": "Dark"}


def privacy_text(database: Path) -> str:
    return (
        f"{APP_NAME} never reads your clipboard and never runs commands. Copy writes the saved "
        "text to the clipboard only when you ask; you paste and run it yourself.\n\n"
        f"Commands are stored unencrypted on this Mac at:\n{database}"
    )


class SettingsDialog(QDialog):
    def __init__(
        self,
        preferences: UiPreferences,
        *,
        database: Path,
        unified_title_bar_supported: bool,
        save_handler: SaveHandler,
        hotkey_checker: HotkeyChecker,
        hotkey_supported: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._original = preferences
        self._unified_supported = unified_title_bar_supported
        self._save_handler = save_handler
        self._hotkey_checker = hotkey_checker
        self._hotkey_supported = hotkey_supported
        self.setWindowTitle("Settings")
        self.setMinimumWidth(460)

        heading = plain_label("Settings", wrap=False, name="heading")

        self.theme_combo = QComboBox()
        for value, label in THEME_LABELS.items():
            self.theme_combo.addItem(label, value)
        self.theme_combo.setCurrentIndex(max(self.theme_combo.findData(preferences.theme), 0))
        self.theme_combo.setAccessibleName("Theme")

        self.preview_combo = QComboBox()
        for lines in range(PREVIEW_LINES_MIN, PREVIEW_LINES_MAX + 1):
            self.preview_combo.addItem(f"{lines} line{'s' if lines != 1 else ''}", lines)
        self.preview_combo.setCurrentIndex(
            max(self.preview_combo.findData(preferences.preview_lines), 0)
        )
        self.preview_combo.setAccessibleName("Command preview lines")

        self.hide_after_copy = QCheckBox("Hide the window after copying a command")
        self.hide_after_copy.setChecked(preferences.hide_after_copy)

        self.unified_title_bar = QCheckBox("Blend the title bar into the window (macOS)")
        self.unified_title_bar.setChecked(
            preferences.unified_title_bar and unified_title_bar_supported
        )
        self.unified_title_bar.setEnabled(unified_title_bar_supported)
        self.unified_title_bar.setToolTip(
            "Turn off to use the standard macOS title bar."
            if unified_title_bar_supported
            else "Only available on macOS."
        )

        # Global shortcut
        current = preferences.validated()
        self.hotkey_enabled = QCheckBox(f"Show or hide {APP_NAME} from any app with")
        self.hotkey_enabled.setChecked(current.hotkey_enabled and hotkey_supported)
        self.hotkey_enabled.setEnabled(hotkey_supported)
        self.hotkey_edit = HotkeyEdit(Hotkey.parse(current.hotkey))
        self.hotkey_edit.setEnabled(hotkey_supported)
        self.reset_hotkey_button = make_button(
            "Reset to Default", tooltip=f"Use {DEFAULT_HOTKEY.display()}"
        )
        self.reset_hotkey_button.setEnabled(hotkey_supported)
        self.reset_hotkey_button.clicked.connect(self._reset_hotkey)
        self.hotkey_edit.recorded.connect(lambda _hotkey: self._check_hotkey())
        self.hotkey_enabled.toggled.connect(lambda _on: self._check_hotkey())
        hotkey_row = QHBoxLayout()
        hotkey_row.setSpacing(SPACE_2)
        hotkey_row.addWidget(self.hotkey_enabled)
        hotkey_row.addWidget(self.hotkey_edit)
        hotkey_row.addWidget(self.reset_hotkey_button)
        hotkey_row.addStretch(1)
        self.hotkey_status = plain_label(name="fieldHint")
        self.hotkey_status.setAccessibleName("Shortcut status")
        hotkey_hint = plain_label(
            "Click the shortcut, then press the new combination (Esc cancels). Use ⌘ or ⌃ "
            "plus at least one more modifier. Shortcuts used by other apps can't be detected, "
            "so if it doesn't respond, choose another."
            if hotkey_supported
            else "Global shortcuts aren't available on this platform yet.",
            name="muted",
        )

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setHorizontalSpacing(SPACE_4)
        form.setVerticalSpacing(SPACE_3)
        form.addRow(plain_label("Theme", wrap=False, name="fieldLabel"), self.theme_combo)
        form.addRow(plain_label("Card preview", wrap=False, name="fieldLabel"), self.preview_combo)
        form.addRow("", self.hide_after_copy)
        form.addRow("", self.unified_title_bar)

        shortcut_title = plain_label("Global shortcut", wrap=False, name="sectionTitle")
        privacy_title = plain_label("Privacy", wrap=False, name="sectionTitle")
        self.privacy = plain_label(privacy_text(database), name="muted")
        self.privacy.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.save_button = make_button("Save", name="primary")
        self.cancel_button = make_button("Cancel")
        for button in (self.save_button, self.cancel_button):
            button.setDefault(False)
        self.save_button.clicked.connect(lambda: self.attempt_save())
        self.cancel_button.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.save_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_5, SPACE_5, SPACE_5, SPACE_4)
        layout.setSpacing(SPACE_4)
        layout.addWidget(heading)
        layout.addLayout(form)
        layout.addWidget(shortcut_title)
        layout.addLayout(hotkey_row)
        layout.addWidget(self.hotkey_status)
        layout.addWidget(hotkey_hint)
        layout.addWidget(privacy_title)
        layout.addWidget(self.privacy)
        self.save_error = plain_label(name="formError")
        self.save_error.setAccessibleName("Settings error")
        self.save_error.hide()
        layout.addStretch(1)
        layout.addWidget(self.save_error)
        layout.addLayout(buttons)
        QShortcut(QKeySequence.StandardKey.Save, self, lambda: self.attempt_save())
        self._check_hotkey()

    def attempt_save(self) -> bool:
        """Apply and persist through the controller; stay open with the reason on failure."""
        if self.hotkey_edit.recording:
            self.hotkey_edit.cancel_recording()
        try:
            self._save_handler(self.preferences())
        except SettingsSaveError as exc:
            self.save_error.setText(str(exc))
            self.save_error.show()
            return False
        self.accept()
        return True

    def _reset_hotkey(self) -> None:
        self.hotkey_edit.set_hotkey(DEFAULT_HOTKEY)
        self._check_hotkey()

    def _check_hotkey(self) -> None:
        if not self._hotkey_supported:
            self._set_status("", ok=True)
            return
        if not self.hotkey_enabled.isChecked():
            self._set_status("The global shortcut is off.", ok=True)
            return
        hotkey = self.hotkey_edit.hotkey
        problem = self._hotkey_checker(hotkey)
        if problem:
            self._set_status(problem, ok=False)
        else:
            self._set_status(f"{hotkey.display()} is available.", ok=True)

    def _set_status(self, text: str, *, ok: bool) -> None:
        self.hotkey_status.setText(text)
        self.hotkey_status.setVisible(bool(text))
        self.hotkey_status.setObjectName("fieldHint" if ok else "formError")
        self.hotkey_status.style().unpolish(self.hotkey_status)
        self.hotkey_status.style().polish(self.hotkey_status)

    def preferences(self) -> UiPreferences:
        return UiPreferences(
            theme=self.theme_combo.currentData(),
            preview_lines=self.preview_combo.currentData(),
            hide_after_copy=self.hide_after_copy.isChecked(),
            # Keep the stored choice where the option doesn't apply (non-macOS).
            unified_title_bar=(
                self.unified_title_bar.isChecked()
                if self._unified_supported
                else self._original.unified_title_bar
            ),
            hotkey_enabled=(
                self.hotkey_enabled.isChecked()
                if self._hotkey_supported
                else self._original.hotkey_enabled
            ),
            hotkey=(
                self.hotkey_edit.hotkey.to_text()
                if self._hotkey_supported
                else self._original.hotkey
            ),
        ).validated()
