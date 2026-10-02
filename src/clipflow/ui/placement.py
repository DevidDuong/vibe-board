"""Where the palette opens. Pure geometry (Qt value types only, no platform calls).

Rules:
* Open on the display the user is working on (the caller passes its usable area).
* Reuse the remembered size, shrunk to fit if the display is smaller now.
* Reuse the remembered position only if the whole window still fits there on that display.
* Otherwise open centred horizontally, in the upper part of the display.
* Never leave the window partly off-screen.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QMargins, QPoint, QRect, QSize

from clipflow.models.window_state import WindowState

SCREEN_MARGIN = 8  # gap kept from the display's usable edges (menu bar, Dock)


@dataclass(frozen=True, slots=True)
class Placement:
    position: QPoint  # frame top-left, for QWidget.move()
    size: QSize  # client size, for QWidget.resize()
    remembered: bool  # the saved position was reused


def outer_size(size: QSize, frame: QMargins) -> QSize:
    return QSize(
        size.width() + frame.left() + frame.right(),
        size.height() + frame.top() + frame.bottom(),
    )


def fit_size(wanted: QSize, available: QRect, frame: QMargins, minimum: QSize) -> QSize:
    max_width = available.width() - frame.left() - frame.right() - 2 * SCREEN_MARGIN
    max_height = available.height() - frame.top() - frame.bottom() - 2 * SCREEN_MARGIN
    return QSize(
        max(min(wanted.width(), max_width), minimum.width()),
        max(min(wanted.height(), max_height), minimum.height()),
    )


def clamp_position(position: QPoint, outer: QSize, available: QRect) -> QPoint:
    left = available.left() + SCREEN_MARGIN
    top = available.top() + SCREEN_MARGIN
    right = available.left() + available.width() - SCREEN_MARGIN - outer.width()
    bottom = available.top() + available.height() - SCREEN_MARGIN - outer.height()
    return QPoint(
        min(max(position.x(), left), max(right, left)),
        min(max(position.y(), top), max(bottom, top)),
    )


def default_position(outer: QSize, available: QRect) -> QPoint:
    x = available.left() + (available.width() - outer.width()) // 2
    y = available.top() + max(SCREEN_MARGIN, (available.height() - outer.height()) // 5)
    return clamp_position(QPoint(x, y), outer, available)


def fits(position: QPoint, outer: QSize, available: QRect) -> bool:
    return available.contains(QRect(position, outer))


def place_window(
    *,
    saved: WindowState | None,
    available: QRect,
    frame: QMargins,
    default_size: QSize,
    minimum: QSize,
) -> Placement:
    wanted = QSize(saved.width, saved.height) if saved else default_size
    size = fit_size(wanted, available, frame, minimum)
    outer = outer_size(size, frame)
    if saved is not None and size == wanted:
        position = QPoint(saved.x, saved.y)
        if fits(position, outer, available):
            return Placement(position, size, remembered=True)
    return Placement(default_position(outer, available), size, remembered=False)
