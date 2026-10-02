"""Command palette window. Pure view: renders state pushed by the controller, emits intents."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QMargins, QObject, QPoint, Qt, Signal, SignalInstance
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QFontDatabase,
    QGuiApplication,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QResizeEvent,
    QShortcut,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from clipflow import APP_NAME
from clipflow.models.command import Command
from clipflow.models.window_state import WindowState
from clipflow.ui.command_list import CommandListView, command_lines
from clipflow.ui.icons import glyph_icon, glyph_pixmap
from clipflow.ui.placement import Placement
from clipflow.ui.theme import LIGHT, SPACE_2, SPACE_3, SPACE_4, Theme
from clipflow.ui.widgets import (
    ALL,
    Banner,
    DragArea,
    EmptyState,
    Filter,
    FilterBar,
    Toast,
    make_button,
    plain_label,
    set_tab_width,
)

DETAIL_MIN_WIDTH = 760  # show the side detail pane at or above this window width
HINTS_MIN_WIDTH = 640
DEFAULT_SIZE = (780, 600)
MINIMUM_SIZE = (420, 380)


def native(sequence: str) -> str:
    """Shortcut text in the platform's style (⌘E on macOS, Ctrl+E elsewhere)."""
    return QKeySequence(sequence).toString(QKeySequence.SequenceFormat.NativeText)


class PaletteWindow(QWidget):
    new_requested = Signal()
    edit_requested = Signal(int)
    delete_requested = Signal(int)  # emitted only after the user confirms
    pin_requested = Signal(int, bool)
    copy_requested = Signal(int)
    filters_changed = Signal()
    settings_requested = Signal()
    error_dismissed = Signal()
    close_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setObjectName("paletteRoot")
        self.setWindowTitle(APP_NAME)
        self.setAccessibleName(f"{APP_NAME} command library")
        self.resize(*DEFAULT_SIZE)
        self.setMinimumSize(*MINIMUM_SIZE)
        self.theme: Theme = LIGHT
        self._loading = False
        self._total = 0
        self._unified = False
        # With the blended title bar (ExpandedClientAreaHint) the client area starts under the
        # title bar. Qt then insets the layout by the window's safe area — the title bar —
        # by itself, so the content never needs (and must not add) its own spacer for it.
        self.setAttribute(Qt.WidgetAttribute.WA_ContentsMarginsRespectsSafeArea, True)

        # Header
        self.logo = QLabel()
        heading = plain_label("Commands", wrap=False, name="heading")
        self.count_label = plain_label(wrap=False, name="count")
        self.add_button = make_button(
            "Add Command", name="primary", tooltip=f"Add a command ({native('Ctrl+N')})"
        )
        self.add_button.clicked.connect(self.new_requested)
        self.settings_button = make_button(
            "", name="iconButton", tooltip=f"Settings ({native('Ctrl+,')})", accessible="Settings"
        )
        self.settings_button.clicked.connect(self.settings_requested)
        self.header = DragArea()
        header_row = QHBoxLayout(self.header)
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(SPACE_2)
        header_row.addWidget(self.logo)
        header_row.addWidget(heading)
        header_row.addWidget(self.count_label)
        header_row.addStretch(1)
        header_row.addWidget(self.add_button)
        header_row.addWidget(self.settings_button)

        self.banner = Banner()
        self.banner.dismissed.connect(self.error_dismissed)

        # Search + filters
        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("Search commands…")
        self.search.setAccessibleName("Search commands")
        self.search.setAccessibleDescription(
            "Matches title, command, and description. Up and down arrows choose; Enter copies."
        )
        self.search.setClearButtonEnabled(True)
        self._search_icon = QAction(self.search)
        self.search.addAction(self._search_icon, QLineEdit.ActionPosition.LeadingPosition)
        self.search.textChanged.connect(lambda _text: self.filters_changed.emit())
        self.search.installEventFilter(self)
        self.filter_bar = FilterBar()
        self.filter_bar.changed.connect(lambda _f: self.filters_changed.emit())

        # List / empty state
        self.list = CommandListView()
        self.list.copy_requested.connect(self.copy_requested)
        self.list.context_requested.connect(self._show_context_menu)
        self.list.type_ahead.connect(self._type_ahead)
        self.list.installEventFilter(self)
        self.list.selectionModel().currentChanged.connect(lambda *_: self._show_selected())
        self.empty = EmptyState()
        self.empty.action_triggered.connect(self._on_empty_action)
        self.list_stack = QStackedWidget()
        self.list_stack.addWidget(self.list)
        self.list_stack.addWidget(self.empty)

        # Detail pane (wide windows only)
        self.detail_title = plain_label(name="detailTitle")
        self.detail_title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail_meta = plain_label(name="muted")
        self.detail_description = plain_label()
        self.detail_description.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.detail_command = QPlainTextEdit()
        self.detail_command.setObjectName("codeView")
        self.detail_command.setReadOnly(True)
        self.detail_command.setAccessibleName("Full command text")
        self.detail_command.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.detail_command.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        set_tab_width(self.detail_command)
        self.detail_lines = plain_label(name="hint")
        detail_body = QWidget()
        detail_layout = QVBoxLayout(detail_body)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(SPACE_2)
        detail_layout.addWidget(self.detail_title)
        detail_layout.addWidget(self.detail_meta)
        detail_layout.addWidget(self.detail_description)
        detail_layout.addWidget(self.detail_command, 1)
        detail_layout.addWidget(self.detail_lines)
        self.detail_placeholder = plain_label("Select a command to see all of it.", name="muted")
        self.detail_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_stack = QStackedWidget()
        self.detail_stack.addWidget(detail_body)
        self.detail_stack.addWidget(self.detail_placeholder)
        self._detail_body = detail_body
        self.detail_pane = QFrame()
        self.detail_pane.setObjectName("detailPane")
        pane_layout = QVBoxLayout(self.detail_pane)
        pane_layout.setContentsMargins(SPACE_4, SPACE_4, SPACE_4, SPACE_3)
        pane_layout.addWidget(self.detail_stack)

        body = QHBoxLayout()
        body.setSpacing(SPACE_3)
        body.addWidget(self.list_stack, 5)
        body.addWidget(self.detail_pane, 4)

        # Action bar + hints
        self.copy_button = make_button("Copy", name="primary", tooltip="Copy to clipboard (↵)")
        self.edit_button = make_button("Edit", tooltip=f"Edit ({native('Ctrl+E')})")
        self.pin_button = make_button("Pin", tooltip=f"Pin or unpin ({native('Ctrl+P')})")
        self.delete_button = make_button(
            "Delete…", name="danger", tooltip=f"Delete ({native('Ctrl+Backspace')})"
        )
        self.copy_button.clicked.connect(lambda: self._emit_for_current(self.copy_requested))
        self.edit_button.clicked.connect(lambda: self._emit_for_current(self.edit_requested))
        self.pin_button.clicked.connect(self._toggle_pin_current)
        self.delete_button.clicked.connect(self._delete_current)
        self.hints = plain_label(
            f"↑↓ Navigate   ↵ Copy   {native('Ctrl+E')} Edit   Esc Close", wrap=False, name="hint"
        )
        actions = QHBoxLayout()
        actions.setSpacing(SPACE_2)
        for button in (self.copy_button, self.edit_button, self.pin_button, self.delete_button):
            actions.addWidget(button)
        actions.addStretch(1)
        actions.addWidget(self.hints)

        layout = QVBoxLayout(self)
        self._layout = layout
        layout.setContentsMargins(SPACE_4, SPACE_3, SPACE_4, SPACE_3)
        layout.setSpacing(SPACE_3)
        layout.addWidget(self.header)
        layout.addWidget(self.banner)
        layout.addWidget(self.search)
        layout.addWidget(self.filter_bar)
        layout.addLayout(body, 1)
        layout.addLayout(actions)

        self.toast = Toast(self)

        # Window-local shortcuts (Cmd on macOS, Ctrl elsewhere). Not global hotkeys.
        for sequence, slot in (
            ("Ctrl+N", self.new_requested.emit),
            ("Ctrl+E", lambda: self._emit_for_current(self.edit_requested)),
            ("Ctrl+P", self._toggle_pin_current),
            ("Ctrl+Backspace", self._delete_current),
            ("Ctrl+F", self.focus_search),
            ("Ctrl+L", self.focus_search),
            ("Ctrl+,", self.settings_requested.emit),
            ("Ctrl+]", lambda: self.filter_bar.cycle(1)),
            ("Ctrl+[", lambda: self.filter_bar.cycle(-1)),
            ("Ctrl+Q", self.quit_requested.emit),
        ):
            QShortcut(QKeySequence(sequence), self, slot)

        self.setTabOrder(self.search, self.list)
        self.set_theme(LIGHT)
        self._show_selected()
        self._apply_responsive_layout()

    # -- state pushed by the controller ------------------------------------------------

    def set_theme(self, theme: Theme) -> None:
        self.theme = theme
        self.logo.setPixmap(glyph_pixmap("terminal", theme.accent, 20))
        self._search_icon.setIcon(glyph_icon("search", theme.muted))
        self.add_button.setIcon(glyph_icon("plus", theme.on_accent))
        self.settings_button.setIcon(glyph_icon("gear", theme.text))
        self.copy_button.setIcon(glyph_icon("copy", theme.on_accent))
        self.edit_button.setIcon(glyph_icon("edit", theme.text))
        self.pin_button.setIcon(glyph_icon("pin", theme.text))
        self.delete_button.setIcon(glyph_icon("trash", theme.danger))
        self.list.set_theme(theme)
        self.empty.set_theme(theme)
        self.banner.set_theme(theme)
        self.toast.set_theme(theme)

    def set_preview_lines(self, lines: int) -> None:
        self.list.set_preview_lines(lines)

    def set_unified_title_bar(self, enabled: bool) -> None:
        """macOS only: extend content under a transparent title bar (pure Qt window hints)."""
        enabled = enabled and QGuiApplication.platformName() == "cocoa"
        if enabled == self._unified:
            return
        self._unified = enabled
        visible = self.isVisible()
        self.setWindowFlag(Qt.WindowType.ExpandedClientAreaHint, enabled)
        self.setWindowFlag(Qt.WindowType.NoTitleBarBackgroundHint, enabled)
        # Qt already places the content below the title bar (safe area); keep only a small gap.
        self._layout.setContentsMargins(SPACE_4, SPACE_2 if enabled else SPACE_3, SPACE_4, SPACE_3)
        if visible:  # changing window flags hides the window
            self.show()

    def set_loading(self) -> None:
        self._loading = True
        self.empty.set_state("terminal", "Loading commands…", "")
        self.list_stack.setCurrentWidget(self.empty)

    def set_filter_options(self, categories: list[str], *, has_uncategorized: bool) -> None:
        self.filter_bar.set_categories(categories, has_uncategorized=has_uncategorized)

    def set_commands(self, commands: list[Command], *, total: int) -> None:
        self._loading = False
        self._total = total
        previous = self.current_id()
        self.list.command_model.set_commands(commands)
        row = self.list.command_model.row_of(previous) if previous is not None else -1
        if commands:
            self.list.select_row(max(row, 0))
        noun = "command" if total == 1 else "commands"
        shown = len(commands)
        self.count_label.setText(
            f"{shown} of {total}" if self.is_filtered() and total else f"{total} {noun}"
        )
        if commands:
            self.list_stack.setCurrentWidget(self.list)
        elif total:
            self.empty.set_state(
                "search",
                "No matching commands",
                "Try a different search or filter.",
                "Clear Filters",
            )
            self.list_stack.setCurrentWidget(self.empty)
        else:
            self.empty.set_state(
                "terminal",
                "Your command library is empty",
                "Save commands you use often, then copy one with a single keystroke.",
                "Add Command",
            )
            self.list_stack.setCurrentWidget(self.empty)
        self._show_selected()
        self._apply_responsive_layout()

    def show_load_error(self, message: str) -> None:
        self._loading = False
        self.list.command_model.set_commands([])
        self.empty.set_state("alert", "Couldn't load commands", message, None)
        self.list_stack.setCurrentWidget(self.empty)
        self._show_selected()
        self._apply_responsive_layout()

    def show_error(self, message: str | None) -> None:
        self.banner.show_message(message)

    def show_toast(self, message: str) -> None:
        self.toast.show_message(message)

    def select_command(self, command_id: int) -> None:
        self.list.select_row(self.list.command_model.row_of(command_id))

    # -- queries ----------------------------------------------------------------------

    def query(self) -> str:
        return self.search.text()

    def current_filter(self) -> Filter:
        return self.filter_bar.current

    def is_filtered(self) -> bool:
        return bool(self.query()) or self.current_filter() != ALL

    def current_id(self) -> int | None:
        command = self.list.current_command()
        return None if command is None else command.id

    def focus_search(self) -> None:
        self.search.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search.selectAll()

    def detail_visible(self) -> bool:
        return not self.detail_pane.isHidden()

    @property
    def unified_title_bar(self) -> bool:
        return self._unified

    def frame_margins(self) -> QMargins:
        """Size of the window frame around the client area (the title bar in standard mode),
        as reported by the platform. Creates the native window if needed; never shows it."""
        if self.windowHandle() is None:
            self.winId()
        handle = self.windowHandle()
        return handle.frameMargins() if handle is not None else QMargins()

    def window_state(self) -> WindowState:
        return WindowState(self.x(), self.y(), self.width(), self.height())

    def apply_placement(self, placement: Placement) -> None:
        self.resize(placement.size)
        self.move(placement.position)

    # -- internals --------------------------------------------------------------------

    def _show_selected(self) -> None:
        command = self.list.current_command()
        for button in (self.copy_button, self.edit_button, self.pin_button, self.delete_button):
            button.setEnabled(command is not None)
        if command is None:
            self.detail_stack.setCurrentWidget(self.detail_placeholder)
            return
        self.pin_button.setText("Unpin" if command.is_pinned else "Pin")
        self.detail_title.setText(command.title)
        updated = command.updated_at.astimezone().strftime("%Y-%m-%d %H:%M")
        pinned = "Pinned · " if command.is_pinned else ""
        self.detail_meta.setText(
            f"{pinned}{command.category or 'Uncategorized'} · Updated {updated}"
        )
        self.detail_description.setText(command.description)
        self.detail_description.setVisible(bool(command.description))
        self.detail_command.setPlainText(command.command)
        count = len(command_lines(command.command))
        self.detail_lines.setText(f"{count} line{'s' if count != 1 else ''}")
        self.detail_stack.setCurrentWidget(self._detail_body)

    def _emit_for_current(self, signal: SignalInstance) -> None:
        command_id = self.current_id()
        if command_id is not None:
            signal.emit(command_id)

    def _toggle_pin_current(self) -> None:
        command = self.list.current_command()
        if command is not None:
            self.pin_requested.emit(command.id, not command.is_pinned)

    def _delete_current(self) -> None:
        command = self.list.current_command()
        if command is not None and self.confirm_delete(command.title):
            self.delete_requested.emit(command.id)

    def confirm_delete(self, title: str) -> bool:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Delete Command")
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(f"Delete “{title}”?")
        box.setInformativeText("It will be removed from your library. This can't be undone.")
        delete = box.addButton("Delete", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        return box.clickedButton() is delete

    def _show_context_menu(self, command_id: int, global_pos: QPoint) -> None:
        command = self.list.current_command()
        if command is None or command.id != command_id:
            return
        menu = QMenu(self)
        menu.addAction(glyph_icon("copy", self.theme.text), "Copy", self.copy_button.click)
        menu.addAction(glyph_icon("edit", self.theme.text), "Edit…", self.edit_button.click)
        menu.addAction(
            glyph_icon("pin", self.theme.text),
            "Unpin" if command.is_pinned else "Pin",
            self._toggle_pin_current,
        )
        menu.addSeparator()
        menu.addAction(glyph_icon("trash", self.theme.danger), "Delete…", self._delete_current)
        menu.exec(global_pos)

    def _type_ahead(self, text: str) -> None:
        self.search.setFocus(Qt.FocusReason.OtherFocusReason)
        self.search.insert(text)

    def _on_empty_action(self) -> None:
        if self._total:
            self.search.clear()
            self.filter_bar.select(ALL)
        else:
            self.new_requested.emit()

    def _apply_responsive_layout(self) -> None:
        has_rows = self.list.command_model.rowCount() > 0
        self.detail_pane.setVisible(self.width() >= DETAIL_MIN_WIDTH and has_rows)
        self.hints.setVisible(self.width() >= HINTS_MIN_WIDTH)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if watched is self.search:
                if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                    self.list.move_selection(1 if key == Qt.Key.Key_Down else -1)
                    return True
                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    self._emit_for_current(self.copy_requested)
                    return True
            if key == Qt.Key.Key_Escape:
                self._escape()
                return True
        if watched is self.list and event.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            self.list.viewport().update()
        return super().eventFilter(watched, event)

    def _escape(self) -> None:
        # Escape clears an active search first; a second Escape dismisses the window.
        if self.search.text():
            self.search.clear()
            self.search.setFocus()
        else:
            self.close_requested.emit()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._escape()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        # Presses that reach the window itself (under the transparent title bar, or in the
        # margins) drag it — native title-bar dragging doesn't apply to the client area.
        handle = self.windowHandle()
        if self._unified and event.button() == Qt.MouseButton.LeftButton and handle is not None:
            handle.startSystemMove()
            event.accept()
            return
        super().mousePressEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._apply_responsive_layout()
        if self.toast.isVisible():
            self.toast.reposition()

    def closeEvent(self, event: QCloseEvent) -> None:
        # The controller decides whether closing hides (menu bar available) or quits.
        event.ignore()
        self.close_requested.emit()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange:
            self.list.viewport().update()
