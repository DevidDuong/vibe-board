"""Add/edit dialog. Nothing is persisted until the user presses Save (or Cmd+S)."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontDatabase, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from clipflow import APP_NAME
from clipflow.models.command import Command, CommandDraft
from clipflow.repositories.database import StorageError
from clipflow.services.command_service import (
    CommandNotFoundError,
    SecretPolicyError,
    ValidationError,
)
from clipflow.ui.icons import glyph_pixmap
from clipflow.ui.theme import LIGHT, SPACE_2, SPACE_4, SPACE_5, Theme
from clipflow.ui.widgets import make_button, plain_label, set_tab_width

# (draft, acknowledge_secret_warnings) -> saved command
SaveHandler = Callable[[CommandDraft, bool], Command]

SECRET_NOTE = (
    f"Don't store passwords, tokens, or keys. {APP_NAME} warns about common secret formats "
    "but can't recognize every secret. Commands are only copied, never run."
)


class CommandEditorDialog(QDialog):
    saved = Signal(object)  # Command

    def __init__(
        self,
        *,
        save_handler: SaveHandler,
        categories: list[str],
        initial: Command | None = None,
        theme: Theme = LIGHT,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._save_handler = save_handler
        self._initial = initial.to_draft() if initial else CommandDraft(title="", command="")
        self.saved_command: Command | None = None
        self.setWindowTitle("Edit Command" if initial else "New Command")
        self.setMinimumSize(520, 520)
        self.resize(620, 600)

        heading = plain_label(self.windowTitle(), wrap=False, name="heading")
        subtitle = plain_label("Nothing is stored until you press Save.", name="muted")

        self.title_edit = QLineEdit(self._initial.title)
        self.title_edit.setPlaceholderText("e.g. Show listening ports")
        self.command_edit = QPlainTextEdit()
        self.command_edit.setObjectName("commandInput")
        self.command_edit.setPlainText(self._initial.command)
        self.command_edit.setPlaceholderText("Type or paste the command. Multiple lines are kept.")
        self.command_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.command_edit.setTabChangesFocus(True)
        self.command_edit.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        set_tab_width(self.command_edit)
        self.command_edit.setMinimumHeight(150)
        self.command_stats = plain_label(wrap=False, name="fieldHint")
        self.category_edit = QComboBox()
        self.category_edit.setEditable(True)
        self.category_edit.addItems(categories)
        self.category_edit.setCurrentText(self._initial.category)
        self.category_edit.lineEdit().setPlaceholderText("Optional, e.g. Git")
        self.description_edit = QPlainTextEdit(self._initial.description)
        self.description_edit.setPlaceholderText("Optional notes: when to use it, what it does")
        self.description_edit.setTabChangesFocus(True)
        self.description_edit.setFixedHeight(72)
        for widget, name, description in (
            (self.title_edit, "Title", "Required"),
            (self.command_edit, "Command", "Required. Stored exactly as typed."),
            (self.category_edit, "Category", "Optional"),
            (self.description_edit, "Description", "Optional"),
        ):
            widget.setAccessibleName(name)
            widget.setAccessibleDescription(description)

        self.error_label = plain_label(name="formError")
        self.error_label.setAccessibleName("Form error")
        self.error_label.hide()

        note = QFrame()
        note.setObjectName("secretNote")
        note_icon = QLabel()
        note_icon.setPixmap(glyph_pixmap("alert", theme.muted, 16))
        note_text = plain_label(SECRET_NOTE, name="muted")
        note_row = QHBoxLayout(note)
        note_row.setContentsMargins(10, 8, 10, 8)
        note_row.addWidget(note_icon, 0, Qt.AlignmentFlag.AlignTop)
        note_row.addWidget(note_text, 1)

        self.save_button = make_button(
            "Save", name="primary", tooltip=f"Save to your library ({_native('Ctrl+S')})"
        )
        self.cancel_button = make_button("Cancel", tooltip="Close without saving (Esc)")
        # No default button: Enter in a field must never save implicitly.
        for button in (self.save_button, self.cancel_button):
            button.setAutoDefault(False)
            button.setDefault(False)
        self.save_button.clicked.connect(lambda: self.attempt_save())
        self.cancel_button.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.save_button)

        category_column = _field("Category", self.category_edit)
        category_column.addStretch(1)  # top-align next to the taller description field
        details = QHBoxLayout()
        details.setSpacing(SPACE_4)
        details.addLayout(category_column, 1)
        details.addLayout(_field("Description", self.description_edit), 2)
        command_field = _field("Command", self.command_edit, required=True, stretch=True)
        command_field.addWidget(self.command_stats)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_5, SPACE_5, SPACE_5, SPACE_4)
        layout.setSpacing(SPACE_4)
        header = QVBoxLayout()
        header.setSpacing(2)
        header.addWidget(heading)
        header.addWidget(subtitle)
        layout.addLayout(header)
        layout.addLayout(_field("Title", self.title_edit, required=True))
        layout.addLayout(command_field, 1)
        layout.addLayout(details)
        layout.addWidget(self.error_label)
        layout.addWidget(note)
        layout.addLayout(buttons)

        QShortcut(QKeySequence.StandardKey.Save, self, lambda: self.attempt_save())
        self.title_edit.textChanged.connect(self._update_save_enabled)
        self.command_edit.textChanged.connect(self._update_save_enabled)
        self.command_edit.textChanged.connect(self._update_stats)
        self._update_save_enabled()
        self._update_stats()
        self.title_edit.setFocus()

    def draft(self) -> CommandDraft:
        return CommandDraft(
            title=self.title_edit.text(),
            command=self.command_edit.toPlainText(),
            description=self.description_edit.toPlainText(),
            category=self.category_edit.currentText(),
        )

    def is_dirty(self) -> bool:
        return self.saved_command is None and self.draft() != self._initial

    def attempt_save(self, acknowledge_warnings: bool = False) -> bool:
        if not self.save_button.isEnabled():
            return False
        try:
            command = self._save_handler(self.draft(), acknowledge_warnings)
        except ValidationError as exc:
            self._show_error("\n".join(exc.problems.values()))
            return False
        except SecretPolicyError as exc:
            if exc.blocked:
                self.show_blocked(exc)
                return False
            if self.confirm_secret_warning(exc):
                return self.attempt_save(acknowledge_warnings=True)
            return False
        except CommandNotFoundError:
            self._show_error("This command no longer exists. It may have been deleted.")
            return False
        except StorageError as exc:
            self._show_error(str(exc))
            return False
        self.saved_command = command
        self.saved.emit(command)
        self.accept()
        return True

    def show_blocked(self, error: SecretPolicyError) -> None:
        self._message(
            QMessageBox.Icon.Critical,
            "Can't Save Command",
            f"This looks like it contains a private key, which {APP_NAME} won't store.",
            _describe(error),
        ).exec()

    def confirm_secret_warning(self, error: SecretPolicyError) -> bool:
        box = self._message(
            QMessageBox.Icon.Warning,
            "Possible Secret",
            "This command may contain a secret. Saved commands are stored unencrypted.",
            _describe(error) + "\n\nReplace it with a variable such as $API_TOKEN if you can.",
        )
        save_anyway = box.addButton("Save Anyway", QMessageBox.ButtonRole.AcceptRole)
        go_back = box.addButton("Go Back", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(go_back)
        box.exec()
        return box.clickedButton() is save_anyway

    def confirm_discard(self) -> bool:
        box = self._message(
            QMessageBox.Icon.Question, "Discard Changes", "Discard your unsaved changes?", ""
        )
        discard = box.addButton("Discard", QMessageBox.ButtonRole.DestructiveRole)
        keep = box.addButton("Keep Editing", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(keep)
        box.exec()
        return box.clickedButton() is discard

    def reject(self) -> None:
        if self.is_dirty() and not self.confirm_discard():
            return
        super().reject()

    def _message(self, icon: QMessageBox.Icon, title: str, text: str, detail: str) -> QMessageBox:
        box = QMessageBox(self)
        box.setIcon(icon)
        box.setWindowTitle(title)
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(text)
        box.setInformativeText(detail)
        if icon is QMessageBox.Icon.Critical:
            box.addButton(QMessageBox.StandardButton.Ok)
        return box

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()

    def _update_stats(self) -> None:
        text = self.command_edit.toPlainText()
        lines = len(text.splitlines()) if text else 0
        self.command_stats.setText(
            f"{lines} line{'s' if lines != 1 else ''} · {len(text)} characters · kept exactly"
        )

    def _update_save_enabled(self) -> None:
        draft = self.draft()
        self.save_button.setEnabled(bool(draft.title.strip() and draft.command.strip()))


def _native(sequence: str) -> str:
    return QKeySequence(sequence).toString(QKeySequence.SequenceFormat.NativeText)


def _field(
    label: str, widget: QWidget, *, required: bool = False, stretch: bool = False
) -> QVBoxLayout:
    column = QVBoxLayout()
    column.setSpacing(SPACE_2 - 2)
    caption = plain_label(f"{label}{'  ·  required' if required else ''}", name="fieldLabel")
    caption.setBuddy(widget)
    column.addWidget(caption)
    column.addWidget(widget, 1 if stretch else 0)
    return column


def _describe(error: SecretPolicyError) -> str:
    # Kinds and field names only; the matched values are never shown or logged.
    lines = sorted({f"• {f.kind} (in {f.field})" for f in error.findings})
    return "Detected:\n" + "\n".join(lines)
