"""Shared native character painting for the desktop pet and panel portrait."""
import math
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap


def draw_character(painter, sprites, animator, pose, width, *, facing="front", direction=1):
    """Paint at the caller's feet origin; blend premultiplied pixels before posing.

    A separate transparent surface keeps overlapping crossfade layers from
    dimming at the midpoint, including when a blend is interrupted repeatedly.
    """
    layers = animator.layers()
    views = getattr(animator, "render_views", {})
    frames = []
    for state, elapsed, weight in layers:
        if weight <= 0:
            continue
        source_facing, source_direction = views.get((state, elapsed), (facing, direction))
        frames.append((state, sprites.frame(state, elapsed, source_facing), weight,
                       source_facing, source_direction))
    if views:
        active = {(state, elapsed) for state, elapsed, _ in layers}
        animator.render_views = {key: view for key, view in views.items() if key in active}
    if not frames:
        return
    size = 480
    height = math.ceil(max(size * image.height() / image.width() for _, image, *_ in frames))
    surface = QPixmap(size, height)
    surface.fill(Qt.transparent)
    blend = QPainter(surface)
    blend.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    blend.setCompositionMode(QPainter.CompositionMode_Plus)
    for state, image, weight, source_facing, source_direction in frames:
        source = QPixmap(size, height)
        source.fill(Qt.transparent)
        face = QPainter(source)
        face.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        if sprites.spec(state).get("mirror_left") and source_facing == "side" and source_direction < 0:
            face.translate(size, 0)
            face.scale(-1, 1)
        frame_height = size * image.height() / image.width()
        rect = QRectF(0, height - frame_height, size, frame_height)
        face.drawPixmap(rect, image, QRectF(image.rect()))
        # Eyelids belong to a source frame, so include them in that source's
        # opacity rather than painting over every other expression in the blend.
        if pose.blink and sprites.eyes(state):
            for ex, ey, ew, eh in sprites.eyes(state):
                eye = QRectF(ex * size, rect.y() + ey * frame_height, ew * size, eh * frame_height)
                face.setPen(Qt.NoPen)
                face.setBrush(QColor("#eda33f"))
                face.drawEllipse(eye.adjusted(-2, -2, 2, 2))
                line = QPainterPath()
                line.moveTo(eye.left() + 4, eye.center().y())
                line.quadTo(eye.center().x(), eye.bottom() - 6, eye.right() - 4, eye.center().y())
                face.setPen(QPen(QColor("#53331e"), 4, Qt.SolidLine, Qt.RoundCap))
                face.drawPath(line)
        face.end()
        if weight < 1:
            # Qt's opaque-pixmap fast path combines global opacity with
            # source-over, even when Plus was requested. Preweight the pixels
            # on transparency, then add them with destination opacity 1.
            weighted = QPixmap(size, height)
            weighted.fill(Qt.transparent)
            fade = QPainter(weighted)
            fade.setOpacity(weight)
            fade.drawPixmap(0, 0, source)
            fade.end()
            source = weighted
        blend.drawPixmap(0, 0, source)
    blend.end()
    painter.save()
    unit = width / 255
    painter.translate(pose.x * unit, pose.bob * unit)
    painter.rotate(pose.rotation)
    painter.scale(pose.sx, pose.sy)
    painter.setOpacity(pose.opacity)
    painter.drawPixmap(QRectF(-width / 2, -height * width / size, width, height * width / size),
                       surface, QRectF(surface.rect()))
    painter.restore()
