"""Small native painting helpers and bundled, offline fonts for the companion UI."""
import math
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QIcon, QPainter, QPainterPath,
                          QPen, QPixmap, QPolygonF)
from .sprites import ASSETS

_fonts_loaded = False


def load_fonts():
    global _fonts_loaded
    if not _fonts_loaded:
        for name in ("Fredoka.ttf", "Nunito.ttf", "Nunito-Bold.ttf"):
            QFontDatabase.addApplicationFont(str(ASSETS / "fonts" / name))
        _fonts_loaded = True


def ui_font(pixels=15, weight=QFont.Normal, heading=False):
    font = QFont("Fredoka" if heading else "Nunito")
    font.setPixelSize(pixels)
    font.setWeight(QFont.Weight(weight))
    return font


def paw(painter, x, y, size=24, color="#efc69c", angle=0):
    painter.save()
    painter.translate(x, y)
    painter.rotate(angle)
    painter.scale(size / 24, size / 24)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))
    painter.drawEllipse(QRectF(6, 11, 13, 11))
    for box in ((1, 7, 6, 8), (6, 1, 6, 8), (13, 1, 6, 8), (19, 7, 5, 8)):
        painter.drawEllipse(QRectF(*box))
    painter.restore()


def sparkle(painter, x, y, size=12, color="#ffd77f"):
    painter.save()
    painter.translate(x, y)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))
    path = QPainterPath()
    path.moveTo(0, -size)
    path.quadTo(size * .2, -size * .2, size * .7, 0)
    path.quadTo(size * .2, size * .2, 0, size)
    path.quadTo(-size * .2, size * .2, -size * .7, 0)
    path.quadTo(-size * .2, -size * .2, 0, -size)
    painter.drawPath(path)
    painter.restore()


def garden(painter, rect, corner=False):
    """Paint a quiet garden directly in Qt, with no extra image or browser runtime."""
    painter.save()
    painter.translate(rect.x(), rect.y())
    w, h = rect.width(), rect.height()
    painter.setClipRect(QRectF(0, 0, w, h), Qt.IntersectClip)
    painter.setPen(Qt.NoPen)
    if corner:
        for x, y, rw, rh, color in ((w - 120, h - 95, 180, 200, "#eff1db"),
                                    (w - 215, h - 48, 260, 120, "#e8edce"),
                                    (w - 300, h - 14, 350, 100, "#f0efd3")):
            painter.setBrush(QColor(color))
            painter.drawEllipse(QRectF(x, y, rw, rh))
        clusters = ((w - 36, h - 30, 1), (w - 126, h - 16, .8), (w - 195, h - 8, .6))
    else:
        for x, y, rw, rh, color in ((-60, h - 110, w + 100, 200, "#e5ebcd"),
                                    (-60, h - 50, w + 180, 140, "#eff0d6"),
                                    (w - 90, h - 150, 160, 180, "#e5ebcf")):
            painter.setBrush(QColor(color))
            painter.drawEllipse(QRectF(x, y, rw, rh))
        clusters = ((26, h - 15, 1), (w - 24, h - 20, .9), (w * .66, h - 8, .65))
    for x, y, scale in clusters:
        painter.save()
        painter.translate(x, y)
        painter.scale(scale, scale)
        for angle, offset, color in ((-30, -8, "#cbd7a9"), (20, 4, "#d7dfb8"), (55, 10, "#bdce9a")):
            painter.save()
            painter.translate(offset, 0)
            painter.rotate(angle)
            painter.setBrush(QColor(color))
            painter.drawEllipse(QRectF(-6, -32, 12, 34))
            painter.restore()
        painter.restore()
    for x, y in ((w - 40, h - 50), (w - 155, h - 40)) if corner else ((32, h - 42), (w - 42, h - 60)):
        painter.setBrush(QColor("#fffdf4"))
        for angle in range(0, 360, 72):
            a = math.radians(angle)
            painter.drawEllipse(QRectF(x + math.cos(a) * 6 - 5, y + math.sin(a) * 6 - 5, 10, 10))
        painter.setBrush(QColor("#f9d984"))
        painter.drawEllipse(QRectF(x - 4, y - 4, 8, 8))
    painter.restore()


def icon(name, color="#a7866c", size=24):
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(size / 24, size / 24)
    p.setPen(QPen(QColor(color), 1.9, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    if name == "paw":
        paw(p, 0, 0, 23, color)
    elif name == "gear":
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(color))
        p.translate(12, 12)
        p.drawEllipse(QRectF(-7.5, -7.5, 15, 15))
        for _ in range(8):
            p.drawRoundedRect(QRectF(-2.1, -10.5, 4.2, 5.5), 1.4, 1.4)
            p.rotate(45)
        p.setCompositionMode(QPainter.CompositionMode_Clear)
        p.drawEllipse(QRectF(-3.4, -3.4, 6.8, 6.8))
    elif name == "chat":
        path = QPainterPath()
        path.moveTo(6, 19)
        path.lineTo(3, 21)
        path.lineTo(4.5, 16)
        path.cubicTo(-1, 8, 4, 2, 12, 2)
        path.cubicTo(23, 2, 26, 15, 17, 18)
        path.quadTo(12, 20, 6, 19)
        p.drawPath(path)
        p.drawLine(QPointF(8, 9), QPointF(16, 9))
        p.drawLine(QPointF(8, 13), QPointF(12, 13))
    elif name == "chevron":
        p.drawPolyline(QPolygonF([QPointF(9, 5), QPointF(16, 12), QPointF(9, 19)]))
    elif name == "clear":
        p.drawLine(6, 7, 18, 7)
        p.drawLine(9, 4, 15, 4)
        p.drawRoundedRect(QRectF(7, 7, 10, 14), 2, 2)
        p.drawLine(10, 11, 10, 17)
        p.drawLine(14, 11, 14, 17)
    p.end()
    return QIcon(pixmap)
