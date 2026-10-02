"""Icons painted with QPainter (no emoji, no bundled assets). Crisp at any display scale."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap

Painter = Callable[[QPainter], None]


def clipboard_icon(points: int = 18, scale: int = 2) -> QIcon:
    """Monochrome clipboard glyph marked as a template image so macOS tints it for the menu bar."""
    size = points * scale
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    stroke = size * 0.085
    pen = QPen(QColor("black"), stroke)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)

    board = QRectF(size * 0.2, size * 0.16, size * 0.6, size * 0.74)
    painter.drawRoundedRect(board, size * 0.1, size * 0.1)

    clip = QPainterPath()
    clip.addRoundedRect(
        QRectF(size * 0.35, size * 0.06, size * 0.3, size * 0.18), size * 0.05, size * 0.05
    )
    painter.fillPath(clip, QColor("black"))

    for i, width in enumerate((0.36, 0.28, 0.36)):
        y = size * (0.45 + i * 0.14)
        painter.drawLine(int(size * 0.32), int(y), int(size * (0.32 + width)), int(y))
    painter.end()

    pixmap.setDevicePixelRatio(scale)
    icon = QIcon(pixmap)
    icon.setIsMask(True)
    return icon


# -- line icons on a 16x16 grid ------------------------------------------------------------


def _search(p: QPainter) -> None:
    p.drawEllipse(QRectF(2.5, 2.5, 8, 8))
    p.drawLine(QPointF(9.5, 9.5), QPointF(13.5, 13.5))


def _plus(p: QPainter) -> None:
    p.drawLine(QPointF(8, 3), QPointF(8, 13))
    p.drawLine(QPointF(3, 8), QPointF(13, 8))


def _gear(p: QPainter) -> None:
    p.drawEllipse(QRectF(5.5, 5.5, 5, 5))
    p.drawEllipse(QRectF(3, 3, 10, 10))
    for x1, y1, x2, y2 in (
        (8, 0.8, 8, 3),
        (8, 13, 8, 15.2),
        (0.8, 8, 3, 8),
        (13, 8, 15.2, 8),
        (2.9, 2.9, 4.5, 4.5),
        (11.5, 11.5, 13.1, 13.1),
        (2.9, 13.1, 4.5, 11.5),
        (11.5, 4.5, 13.1, 2.9),
    ):
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))


def _pin(p: QPainter) -> None:
    path = QPainterPath()
    path.moveTo(5.5, 2)
    path.lineTo(10.5, 2)
    path.lineTo(9.8, 7)
    path.lineTo(12, 9.5)
    path.lineTo(4, 9.5)
    path.lineTo(6.2, 7)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(QPointF(8, 9.5), QPointF(8, 14.5))


def _copy(p: QPainter) -> None:
    p.drawRoundedRect(QRectF(5.5, 5.5, 8, 8.5), 1.6, 1.6)
    p.drawPolyline([QPointF(3, 10.5), QPointF(2.5, 10.5), QPointF(2.5, 2.5), QPointF(10.5, 2.5)])


def _edit(p: QPainter) -> None:
    path = QPainterPath()
    path.moveTo(3, 13)
    path.lineTo(3.6, 10.2)
    path.lineTo(10.8, 3)
    path.lineTo(13, 5.2)
    path.lineTo(5.8, 12.4)
    path.closeSubpath()
    p.drawPath(path)


def _trash(p: QPainter) -> None:
    p.drawLine(QPointF(2.5, 4.5), QPointF(13.5, 4.5))
    p.drawPolyline([QPointF(6, 4.5), QPointF(6.5, 2.5), QPointF(9.5, 2.5), QPointF(10, 4.5)])
    p.drawPolyline([QPointF(4, 4.5), QPointF(4.8, 13.5), QPointF(11.2, 13.5), QPointF(12, 4.5)])


def _check(p: QPainter) -> None:
    p.drawPolyline([QPointF(3, 8.5), QPointF(6.5, 12), QPointF(13, 4.5)])


def _chevron(p: QPainter) -> None:
    p.drawPolyline([QPointF(4, 6), QPointF(8, 10), QPointF(12, 6)])


def _alert(p: QPainter) -> None:
    p.drawEllipse(QRectF(2, 2, 12, 12))
    p.drawLine(QPointF(8, 5), QPointF(8, 9))
    p.drawPoint(QPointF(8, 11.3))


def _terminal(p: QPainter) -> None:
    p.drawRoundedRect(QRectF(1.5, 2.5, 13, 11), 2, 2)
    p.drawPolyline([QPointF(4.5, 6), QPointF(6.8, 8), QPointF(4.5, 10)])
    p.drawLine(QPointF(8.5, 10.5), QPointF(11.5, 10.5))


GLYPHS: dict[str, Painter] = {
    "search": _search,
    "plus": _plus,
    "gear": _gear,
    "pin": _pin,
    "copy": _copy,
    "edit": _edit,
    "trash": _trash,
    "check": _check,
    "alert": _alert,
    "chevron": _chevron,
    "terminal": _terminal,
}


def glyph_pixmap(name: str, color: str, size: int, dpr: float = 2.0) -> QPixmap:
    pixmap = QPixmap(round(size * dpr), round(size * dpr))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size * dpr / 16, size * dpr / 16)
    pen = QPen(QColor(color), 1.6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    GLYPHS[name](painter)
    painter.end()
    pixmap.setDevicePixelRatio(dpr)
    return pixmap


def glyph_icon(name: str, color: str, size: int = 16) -> QIcon:
    icon = QIcon()
    for dpr in (1.0, 2.0, 3.0):
        icon.addPixmap(glyph_pixmap(name, color, size, dpr))
    return icon


def draw_glyph(painter: QPainter, name: str, rect: QRectF, color: str) -> None:
    """Draw a glyph directly (used by item delegates)."""
    painter.save()
    painter.translate(rect.topLeft())
    painter.scale(rect.width() / 16, rect.height() / 16)
    pen = QPen(QColor(color), 1.6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    GLYPHS[name](painter)
    painter.restore()


def app_icon_pixmap(size: int) -> QPixmap:
    """Application icon (placeholder artwork): a terminal glyph on an accent tile.

    Follows the macOS icon grid: the tile fills ~80% of the canvas with transparent margin.
    Used for the bundle's .icns (packaging/make_icon.py) and the window icon at runtime.
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    margin = size * 0.1
    tile = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
    gradient = QLinearGradient(tile.topLeft(), tile.bottomLeft())
    gradient.setColorAt(0.0, QColor("#7083FF"))
    gradient.setColorAt(1.0, QColor("#4453D6"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    painter.drawRoundedRect(tile, tile.width() * 0.225, tile.width() * 0.225)

    # Prompt chevron and cursor bar, drawn on a 16-unit grid inside the tile.
    painter.translate(tile.topLeft())
    painter.scale(tile.width() / 16, tile.height() / 16)
    pen = QPen(QColor("white"), 1.5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.drawPolyline([QPointF(4.2, 5.2), QPointF(7.4, 8), QPointF(4.2, 10.8)])
    painter.drawLine(QPointF(8.8, 11), QPointF(12, 11))
    painter.end()
    return pixmap


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 32, 64, 128, 256, 512):
        icon.addPixmap(app_icon_pixmap(size))
    return icon
