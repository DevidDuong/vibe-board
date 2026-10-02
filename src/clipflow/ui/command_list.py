"""Command cards: list model, painting delegate, and a keyboard-first list view."""

from __future__ import annotations

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QPersistentModelIndex,
    QPoint,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetricsF, QKeyEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QListView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)

from clipflow.models.command import Command
from clipflow.ui.icons import draw_glyph
from clipflow.ui.theme import LIGHT, RADIUS_CARD, Theme

CommandRole = Qt.ItemDataRole.UserRole + 1

CARD_MARGIN_X = 2
CARD_MARGIN_Y = 4
CARD_PAD = 12
TAB_DISPLAY = "    "


def command_lines(text: str) -> list[str]:
    """Display lines for a preview (tabs expanded). The stored text is never modified."""
    lines = text.splitlines() or [""]
    return [line.replace("\t", TAB_DISPLAY) for line in lines]


def accessible_text(command: Command) -> str:
    lines = command_lines(command.command)
    parts = [command.title]
    if command.is_pinned:
        parts.append("pinned")
    parts.append(f"category {command.category}" if command.category else "uncategorized")
    parts.append(f"command: {lines[0]}")
    if len(lines) > 1:
        parts.append(f"{len(lines)} lines")
    return ", ".join(parts)


class CommandListModel(QAbstractListModel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._commands: list[Command] = []

    def set_commands(self, commands: list[Command]) -> None:
        self.beginResetModel()
        self._commands = list(commands)
        self.endResetModel()

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._commands)

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = 0) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self._commands):
            return None
        command = self._commands[index.row()]
        if role == CommandRole:
            return command
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole):
            return accessible_text(command)
        if role == Qt.ItemDataRole.ToolTipRole:
            return command.description or command.title
        return None

    def command_at(self, row: int) -> Command | None:
        return self._commands[row] if 0 <= row < len(self._commands) else None

    def row_of(self, command_id: int) -> int:
        return next((i for i, c in enumerate(self._commands) if c.id == command_id), -1)


class CommandCardDelegate(QStyledItemDelegate):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.theme: Theme = LIGHT
        self.preview_lines = 3

    # -- fonts / metrics -------------------------------------------------------------

    @staticmethod
    def _fonts(base: QFont) -> tuple[QFont, QFont, QFont]:
        title = QFont(base)
        title.setWeight(QFont.Weight.DemiBold)
        mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        mono.setPointSizeF(max(base.pointSizeF() * 0.95, 9.0))
        small = QFont(base)
        small.setPointSizeF(max(base.pointSizeF() * 0.88, 8.5))
        return title, mono, small

    def _layout(self, command: Command, base: QFont) -> tuple[int, int, bool]:
        """(shown preview lines, hidden line count, has meta row)."""
        total = len(command_lines(command.command))
        shown = min(total, self.preview_lines)
        hidden = total - shown
        return shown, hidden, bool(command.description or hidden)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        command: Command | None = index.data(CommandRole)
        if command is None:
            return super().sizeHint(option, index)
        title_font, mono, small = self._fonts(option.font)
        shown, _hidden, has_meta = self._layout(command, option.font)
        height = CARD_PAD * 2 + QFontMetricsF(title_font).height() + 8
        height += shown * QFontMetricsF(mono).lineSpacing() + 12
        if has_meta:
            height += 6 + QFontMetricsF(small).height()
        return QSize(option.rect.width() or 300, int(height + CARD_MARGIN_Y * 2 + 0.5))

    # -- painting --------------------------------------------------------------------

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        command: Command | None = index.data(CommandRole)
        if command is None:
            return
        t = self.theme
        title_font, mono, small = self._fonts(option.font)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        view = option.widget
        focused = selected and view is not None and view.hasFocus()

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        card = QRectF(option.rect).adjusted(
            CARD_MARGIN_X, CARD_MARGIN_Y, -CARD_MARGIN_X, -CARD_MARGIN_Y
        )
        background = t.selected if selected else (t.hover if hovered else t.surface)
        border_width = 2.0 if focused else (1.5 if selected else 1.0)
        painter.setPen(QPen(QColor(t.accent if selected else t.border), border_width))
        painter.setBrush(QColor(background))
        inset = border_width / 2
        painter.drawRoundedRect(
            card.adjusted(inset, inset, -inset, -inset), RADIUS_CARD, RADIUS_CARD
        )

        content = card.adjusted(CARD_PAD, CARD_PAD, -CARD_PAD, -CARD_PAD)
        title_metrics = QFontMetricsF(title_font)
        small_metrics = QFontMetricsF(small)
        title_h = title_metrics.height()
        right = content.right()

        # Category pill and pin marker (right side of the title row).
        painter.setFont(small)
        if command.category:
            label = small_metrics.elidedText(
                command.category, Qt.TextElideMode.ElideRight, content.width() * 0.4
            )
            pill_w = small_metrics.horizontalAdvance(label) + 16
            pill = QRectF(right - pill_w, content.top() + (title_h - 20) / 2, pill_w, 20)
            painter.setPen(QPen(QColor(t.border), 1))
            painter.setBrush(QColor(t.code_bg))
            painter.drawRoundedRect(pill, 10, 10)
            painter.setPen(QColor(t.muted))
            painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, label)
            right = pill.left() - 8
        if command.is_pinned:
            pin = QRectF(right - 14, content.top() + (title_h - 14) / 2, 14, 14)
            draw_glyph(painter, "pin", pin, t.accent)
            right = pin.left() - 8

        painter.setFont(title_font)
        painter.setPen(QColor(t.text))
        title_rect = QRectF(content.left(), content.top(), right - content.left(), title_h)
        painter.drawText(
            title_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            title_metrics.elidedText(
                command.title, Qt.TextElideMode.ElideRight, title_rect.width()
            ),
        )

        # Monospace preview block.
        shown, hidden, has_meta = self._layout(command, option.font)
        mono_metrics = QFontMetricsF(mono)
        line_h = mono_metrics.lineSpacing()
        block = QRectF(
            content.left(), title_rect.bottom() + 8, content.width(), shown * line_h + 12
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(t.code_bg))
        painter.drawRoundedRect(block, 6, 6)
        painter.setFont(mono)
        painter.setPen(QColor(t.text))
        text_width = block.width() - 16
        for i, line in enumerate(command_lines(command.command)[:shown]):
            line_rect = QRectF(block.left() + 8, block.top() + 6 + i * line_h, text_width, line_h)
            painter.drawText(
                line_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                mono_metrics.elidedText(line, Qt.TextElideMode.ElideRight, text_width),
            )

        # Meta row: description (left) and hidden-line count (right).
        if has_meta:
            painter.setFont(small)
            painter.setPen(QColor(t.muted))
            meta = QRectF(
                content.left(), block.bottom() + 6, content.width(), small_metrics.height()
            )
            more = f"+{hidden} more line{'s' if hidden != 1 else ''}" if hidden else ""
            more_w = small_metrics.horizontalAdvance(more) + (12 if more else 0)
            if more:
                painter.drawText(
                    meta, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, more
                )
            if command.description:
                first = command.description.splitlines()[0]
                painter.drawText(
                    meta.adjusted(0, 0, -more_w, 0),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    small_metrics.elidedText(
                        first, Qt.TextElideMode.ElideRight, meta.width() - more_w
                    ),
                )
        painter.restore()


class CommandListView(QListView):
    copy_requested = Signal(int)
    context_requested = Signal(int, QPoint)  # command id, global position
    type_ahead = Signal(str)  # printable text typed while the list has focus

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("commandList")
        self.setAccessibleName("Commands")
        self.setAccessibleDescription("Use arrow keys to choose a command and Enter to copy it.")
        self.command_model = CommandListModel(self)
        self.setModel(self.command_model)
        self.card_delegate = CommandCardDelegate(self)
        self.setItemDelegate(self.card_delegate)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setUniformItemSizes(False)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.doubleClicked.connect(self._on_double_clicked)

    def set_theme(self, theme: Theme) -> None:
        self.card_delegate.theme = theme
        self.viewport().update()

    def set_preview_lines(self, lines: int) -> None:
        self.card_delegate.preview_lines = lines
        self.scheduleDelayedItemsLayout()  # card heights change
        self.viewport().update()

    def current_command(self) -> Command | None:
        index = self.currentIndex()
        return index.data(CommandRole) if index.isValid() else None

    def select_row(self, row: int) -> None:
        if 0 <= row < self.command_model.rowCount():
            index = self.command_model.index(row)
            self.setCurrentIndex(index)
            self.scrollTo(index)

    def move_selection(self, step: int) -> None:
        count = self.command_model.rowCount()
        if count:
            current = self.currentIndex().row()
            self.select_row(min(max(current + step, 0), count - 1) if current >= 0 else 0)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            command = self.current_command()
            if command is not None:
                self.copy_requested.emit(command.id)
            return
        text = event.text()
        plain = not event.modifiers() & ~Qt.KeyboardModifier.ShiftModifier
        if text and text.isprintable() and not text.isspace() and plain:
            self.type_ahead.emit(text)
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self.viewport().update()  # focus ring on the selected card

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self.viewport().update()

    def _on_double_clicked(self, index: QModelIndex) -> None:
        command: Command | None = index.data(CommandRole)
        if command is not None:
            self.copy_requested.emit(command.id)

    def _on_context_menu(self, pos: QPoint) -> None:
        index = self.indexAt(pos)
        if index.isValid():
            self.setCurrentIndex(index)
            self.context_requested.emit(
                index.data(CommandRole).id, self.viewport().mapToGlobal(pos)
            )
