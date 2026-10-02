"""Small reusable widgets. All user-supplied text is rendered as plain text."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from clipflow.ui.icons import glyph_icon, glyph_pixmap
from clipflow.ui.theme import Theme


def plain_label(text: str = "", *, wrap: bool = True, name: str | None = None) -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(wrap)
    if name:
        label.setObjectName(name)
    return label


def set_tab_width(editor: QPlainTextEdit, spaces: int = 4) -> None:
    """Display tabs as ``spaces`` columns (Qt defaults to 80px). The text itself is unchanged."""
    editor.setTabStopDistance(editor.fontMetrics().horizontalAdvance(" ") * spaces)


def make_button(
    text: str, *, name: str | None = None, tooltip: str = "", accessible: str = ""
) -> QPushButton:
    button = QPushButton(text)
    if name:
        button.setObjectName(name)
    if tooltip:
        button.setToolTip(tooltip)
    button.setAccessibleName(accessible or text or tooltip)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setAutoDefault(False)
    return button


@dataclass(frozen=True, slots=True)
class Filter:
    """What the list shows: everything, pinned only, or one category ("" = uncategorized)."""

    kind: str  # "all" | "pinned" | "category"
    category: str | None = None

    @property
    def label(self) -> str:
        if self.kind == "all":
            return "All"
        if self.kind == "pinned":
            return "Pinned"
        return self.category or "Uncategorized"


ALL = Filter("all")
PINNED = Filter("pinned")
UNCATEGORIZED = Filter("category", "")


class FilterBar(QScrollArea):
    """Horizontally scrolling row of exclusive filter chips."""

    changed = Signal(object)  # Filter

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("chipScroller")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName("Filters")
        self._inner = QWidget()
        self._row = QHBoxLayout(self._inner)
        self._row.setContentsMargins(0, 2, 0, 2)
        self._row.setSpacing(6)
        self.setWidget(self._inner)
        # A scroll area isn't told when its content's layout changes; forward that so the
        # bar's height tracks the (styled) chip height.
        self._inner.installEventFilter(self)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: list[tuple[Filter, QPushButton]] = []
        self._current = ALL
        self._options: list[Filter] | None = None
        self.set_categories([], has_uncategorized=False)

    def sizeHint(self) -> QSize:
        # Measured at layout time (after QSS polish) so chip padding is accounted for.
        bar = self.horizontalScrollBar().sizeHint().height()
        return QSize(super().sizeHint().width(), self._inner.sizeHint().height() + bar)

    def minimumSizeHint(self) -> QSize:
        return QSize(0, self.sizeHint().height())

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._inner and event.type() == QEvent.Type.LayoutRequest:
            self.updateGeometry()
        return super().eventFilter(watched, event)

    @property
    def current(self) -> Filter:
        return self._current

    def filters(self) -> list[Filter]:
        return [f for f, _ in self._buttons]

    def set_categories(self, categories: list[str], *, has_uncategorized: bool) -> None:
        """Rebuild chips; keeps the current filter if it still exists, else falls back to All."""
        filters = [ALL, PINNED, *(Filter("category", c) for c in categories)]
        if has_uncategorized:
            filters.append(UNCATEGORIZED)
        if self._current not in filters:
            self._current = ALL
        if filters == self._options:
            return  # unchanged: keep chips (and any keyboard focus on them)
        self._options = filters
        for _, button in self._buttons:
            self._group.removeButton(button)
            # Detach now: deleteLater alone leaves the old chip painted until the loop idles.
            button.hide()
            button.setParent(None)
            button.deleteLater()
        self._buttons.clear()
        while self._row.count():
            self._row.takeAt(0)
        for f in filters:
            chip = make_button(f.label, name="chip", accessible=f"Filter: {f.label}")
            chip.setCheckable(True)
            chip.setChecked(f == self._current)
            chip.toggled.connect(lambda on, f=f: on and self._select(f))
            self._group.addButton(chip)
            self._row.addWidget(chip)
            chip.ensurePolished()
            self._buttons.append((f, chip))
        self._row.addStretch(1)
        self.updateGeometry()

    def select(self, f: Filter) -> None:
        for candidate, chip in self._buttons:
            if candidate == f:
                chip.setChecked(True)
                return

    def cycle(self, step: int) -> None:
        filters = self.filters()
        index = filters.index(self._current) if self._current in filters else 0
        self.select(filters[(index + step) % len(filters)])

    def button_for(self, f: Filter) -> QPushButton | None:
        return next((chip for candidate, chip in self._buttons if candidate == f), None)

    def _select(self, f: Filter) -> None:
        if f != self._current:
            self._current = f
            self.changed.emit(f)


class EmptyState(QWidget):
    action_triggered = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.icon = QLabel()
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title = plain_label(name="emptyTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message = plain_label(name="muted")
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.action = make_button("", name="primary")
        self.action.clicked.connect(self.action_triggered)
        layout = QVBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(self.icon)
        layout.addWidget(self.title)
        layout.addWidget(self.message)
        layout.addWidget(self.action, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(2)
        layout.setSpacing(8)
        self._glyph = "terminal"
        self._color = "#888888"

    def set_state(self, glyph: str, title: str, message: str, action: str | None = None) -> None:
        self._glyph = glyph
        self.title.setText(title)
        self.message.setText(message)
        self.action.setText(action or "")
        self.action.setAccessibleName(action or "")
        self.action.setVisible(bool(action))
        self._render_icon()

    def set_theme(self, theme: Theme) -> None:
        self._color = theme.muted
        self._render_icon()

    def _render_icon(self) -> None:
        self.icon.setPixmap(glyph_pixmap(self._glyph, self._color, 36))


class Banner(QFrame):
    """Inline error banner with a dismiss button."""

    dismissed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("banner")
        self.icon = QLabel()
        self.text = plain_label()
        self.text.setAccessibleName("Error")
        dismiss = make_button("Dismiss", name="iconButton", accessible="Dismiss error")
        dismiss.clicked.connect(self._dismiss)
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 6, 6, 6)
        row.addWidget(self.icon)
        row.addWidget(self.text, 1)
        row.addWidget(dismiss)
        self.hide()

    def set_theme(self, theme: Theme) -> None:
        self.icon.setPixmap(glyph_pixmap("alert", theme.danger, 16))

    def show_message(self, message: str | None) -> None:
        self.text.setText(message or "")
        self.setVisible(bool(message))

    def _dismiss(self) -> None:
        self.hide()
        self.dismissed.emit()


class Toast(QFrame):
    """Transient confirmation shown over the window (e.g. "Copied …")."""

    DURATION_MS = 2400

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        self.icon = QLabel()
        self.text = plain_label(wrap=False, name="toastText")
        self.text.setAccessibleName("Status")
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 14, 8)
        row.setSpacing(8)
        row.addWidget(self.icon)
        row.addWidget(self.text)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        # One-shot hide timer, started only by an explicit user action (never polling).
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self._success = "#2E9D7A"
        self.hide()

    def set_theme(self, theme: Theme) -> None:
        self._success = theme.success
        self.icon.setPixmap(glyph_pixmap("check", theme.success, 16))

    def show_message(self, message: str) -> None:
        metrics = self.text.fontMetrics()
        max_width = max(160, self.parentWidget().width() - 80)
        self.text.setText(metrics.elidedText(message, Qt.TextElideMode.ElideMiddle, max_width))
        self.text.setAccessibleDescription(message)
        self.adjustSize()
        self.reposition()
        self.show()
        self.raise_()
        self._timer.start(self.DURATION_MS)

    def reposition(self) -> None:
        parent = self.parentWidget()
        self.move((parent.width() - self.width()) // 2, parent.height() - self.height() - 64)


class DragArea(QWidget):
    """Empty header space that moves the window (needed when the title bar is unified)."""

    def mousePressEvent(self, event: QMouseEvent) -> None:
        handle = self.window().windowHandle()
        if event.button() == Qt.MouseButton.LeftButton and handle is not None:
            handle.startSystemMove()
            event.accept()
            return
        super().mousePressEvent(event)


def icon_button(glyph: str, tooltip: str, color: str) -> QPushButton:
    button = make_button("", name="iconButton", tooltip=tooltip, accessible=tooltip)
    button.setIcon(glyph_icon(glyph, color, 16))
    return button
