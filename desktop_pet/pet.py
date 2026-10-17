import math
import random
import time
from PySide6.QtCore import Qt, QPoint, QPointF, QRectF, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QFont
from PySide6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout
from .model import Animator, WalkMotion, clamp_position


class SpeechBubble(QWidget):
    def __init__(self):
        super().__init__(None, Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 14)
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setMaximumWidth(230)
        self.label.setTextFormat(Qt.PlainText)
        self.label.setStyleSheet("color: #4b3526; background: #fff9ee; border: 1px solid #ead8ba; border-radius: 14px; padding: 12px; font: 10pt 'Segoe UI';")
        layout.addWidget(self.label)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)

    def say(self, text, pet):
        self.label.setText(text[:160] + ("…" if len(text) > 160 else ""))
        self.adjustSize()
        area = pet.screen().availableGeometry()
        x, y = clamp_position(pet.x() + (pet.width() - self.width()) // 2,
                              pet.y() - self.height() + 35,
                              area.left(), area.top(), area.right() + 1, area.bottom() + 1,
                              self.width(), self.height())
        self.move(x, y)
        self.show()
        self.timer.start(6500)


class PetWindow(QWidget):
    open_requested = Signal()
    menu_requested = Signal(QPoint)
    position_saved = Signal(int, int)
    state_changed = Signal(str)
    hidden_to_tray = Signal()

    def __init__(self, settings, sprites):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.settings = settings
        self.allow_close = False
        self.sprites = sprites
        self.setWindowTitle("Biscuit · Desktop pet")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.setCursor(Qt.OpenHandCursor)
        walking = sprites.spec("walking")
        self.animator = Animator(walking["fps"], len(walking["frames"]))
        self.pose = self.animator.advance(0)
        self.bubble = SpeechBubble()
        self.drag_offset = None
        self.dragged = False
        self.press_pos = QPoint()
        self.click_timer = QTimer(self)
        self.click_timer.setSingleShot(True)
        self.click_timer.timeout.connect(self.pet)
        self.direction = 1
        self.walk_motion = None
        self.wander_until = 0
        self.next_wander = time.monotonic() + 8
        self.next_reminder = time.monotonic() + 25 * 60
        self.particles = []
        self.click_through = False
        self._last = time.monotonic()
        self.set_scale(settings.get("scale"))
        self.restore_position()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(33)

    def set_scale(self, scale):
        factor = scale / 100
        self.setFixedSize(round(290 * factor), round(310 * factor))
        if self.isVisible():
            self.keep_on_screen()
        self.update()

    def restore_position(self):
        screens = QApplication.screens()
        area = QApplication.primaryScreen().availableGeometry()
        x, y = self.settings.get("x"), self.settings.get("y")
        if x is None or y is None or not any(s.availableGeometry().contains(QPoint(x + self.width() // 2, y + self.height() // 2)) for s in screens):
            x, y = area.right() - self.width() - 35, area.bottom() - self.height() + 1
        self.move(x, y)
        self.keep_on_screen()

    def keep_on_screen(self):
        area = self.screen().availableGeometry()
        self.move(*clamp_position(self.x(), self.y(), area.left(), area.top(), area.right() + 1,
                                 area.bottom() + 1, self.width(), self.height()))

    def set_state(self, state):
        self.animator.set_state(state)
        if state != "walking":
            self.walk_motion = None
        self.state_changed.emit(state)

    def start_walk(self, now):
        # Mostly horizontal strolls, with front/back and diagonal exploration too.
        vector = random.choice(((1, 0), (-1, 0), (0, 1), (0, -1),
                                (2, 1), (-2, 1), (1, -2), (-1, -2)))
        self.walk_motion = WalkMotion(self.x(), self.y(), *vector)
        self.wander_until = now + random.uniform(3, 7)
        self.set_state("walking")

    def advance_walk(self, dt):
        if self.walk_motion is None:
            self.walk_motion = WalkMotion(self.x(), self.y(), self.direction, 0)
        area = self.screen().availableGeometry()
        bounds = (area.left(), area.top(), area.right() + 1, area.bottom() + 1)
        self.move(*self.walk_motion.step(dt, bounds, self.width(), self.height()))
        self.direction = -1 if self.walk_motion.vx < 0 else 1

    @property
    def walk_facing(self):
        return self.walk_motion.facing if self.walk_motion else "side"

    def tick(self):
        now = time.monotonic()
        dt = min(.1, now - self._last)
        self._last = now
        if not self.isVisible():
            return
        state = self.animator.state
        if state == "leaving" and self.animator.elapsed >= .6:
            self.hide()
            self.bubble.hide()
            self.hidden_to_tray.emit()
            return
        if self.settings.get("wander") and state in ("idle", "walking"):
            if now >= self.next_wander and state == "idle":
                self.start_walk(now)
            if self.animator.state == "walking":
                self.advance_walk(dt)
                if now >= self.wander_until:
                    self.set_state("idle")
                    self.next_wander = now + random.uniform(10, 25)
                    self.position_saved.emit(self.x(), self.y())
        elif state == "walking":
            self.set_state("idle")
        if self.settings.get("reminders") and now >= self.next_reminder and state != "sleeping":
            self.say("Time for a little stretch and a sip of water. You’ve earned a moment. 🧡")
            self.next_reminder = now + 25 * 60
        previous = self.animator.state
        self.pose = self.animator.advance(dt)
        if previous != self.animator.state:
            self.state_changed.emit(self.animator.state)
        self.particles = [(x, age + dt) for x, age in self.particles if age + dt < 1.3]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        unit = self.width() / 290
        pose = self.pose
        painter.save()
        painter.setOpacity(pose.opacity)
        painter.translate(self.width() / 2, self.height() - 20 * unit + pose.bob * unit)
        painter.rotate(pose.rotation)
        painter.scale(pose.sx, pose.sy)
        walking = self.animator.state == "walking"
        if walking and self.walk_facing == "side" and self.direction < 0:
            painter.scale(-1, 1)
        pixmap = self.sprites.frame(self.animator.state, self.animator.elapsed, self.walk_facing)
        width = 255 * unit
        height = width * pixmap.height() / pixmap.width()
        rect = QRectF(-width / 2, -height, width, height)
        painter.drawPixmap(rect, pixmap, QRectF(pixmap.rect()))
        # Coordinates live in the manifest so replacement art can move the eyelids.
        if pose.blink:
            for ex, ey, ew, eh in self.sprites.eyes(self.animator.state):
                eye = QRectF(rect.x() + ex * width, rect.y() + ey * height, ew * width, eh * height)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor("#eda33f"))
                painter.drawEllipse(eye.adjusted(-unit, -unit, unit, unit))
                line = QPainterPath()
                line.moveTo(eye.left() + 2 * unit, eye.center().y())
                line.quadTo(eye.center().x(), eye.bottom() - 3 * unit, eye.right() - 2 * unit, eye.center().y())
                painter.setPen(QPen(QColor("#53331e"), 2 * unit, Qt.SolidLine, Qt.RoundCap))
                painter.drawPath(line)
        painter.restore()
        painter.setFont(QFont("Segoe UI", round(17 * unit), QFont.Bold))
        for x, age in self.particles:
            painter.setOpacity(max(0, 1 - age / 1.3))
            painter.setPen(QColor("#dc7554"))
            painter.drawText(QPointF(self.width() * x, self.height() * .4 - age * 60 * unit), "♥")
        if self.animator.state == "sleeping":
            painter.setOpacity(.8)
            painter.setPen(QColor("#887b9b"))
            painter.drawText(QPointF(self.width() * .72, 50 * unit + math.sin(self.animator.elapsed * 2) * 5), "z Z")

    def pet(self):
        self.set_state("happy")
        self.particles.extend([(random.uniform(.3, .7), i * -.12) for i in range(3)])
        self.say(random.choice(["A little affection goes a long way. 🧡", "That’s the spot!", "You + me = a very good day.", "Tiny paws. Big feelings. 🐾"]))

    def say(self, message):
        if self.isVisible():
            self.bubble.say(message, self)

    def sleep(self, enabled=True):
        self.set_state("sleeping" if enabled else "idle")
        self.next_wander = time.monotonic() + 10
        self.say("Just resting my eyes… zzz" if enabled else "Ready for a little adventure!")

    def hide_animated(self):
        self.bubble.hide()
        self.set_state("leaving")

    def summon(self):
        self.set_click_through(False)
        self.restore_position()
        self.set_state("entering")
        self._last = time.monotonic()
        self.show()
        self.raise_()

    def set_click_through(self, enabled):
        self.click_through = enabled
        self.setWindowFlag(Qt.WindowTransparentForInput, enabled)
        self.setCursor(Qt.ArrowCursor if enabled else Qt.OpenHandCursor)
        self.show()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.press_pos = event.globalPosition().toPoint()
            self.drag_offset = self.press_pos - self.pos()
            self.dragged = False
            self.bubble.hide()

    def mouseMoveEvent(self, event):
        if self.drag_offset is not None:
            if (event.globalPosition().toPoint() - self.press_pos).manhattanLength() > QApplication.startDragDistance():
                self.dragged = True
                self.click_timer.stop()
                self.set_state("dragged")
                self.setCursor(Qt.ClosedHandCursor)
            if self.dragged:
                self.move(event.globalPosition().toPoint() - self.drag_offset)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.drag_offset is not None:
            self.drag_offset = None
            self.setCursor(Qt.OpenHandCursor)
            if self.dragged:
                self.keep_on_screen()
                self.set_state("idle")
                self.position_saved.emit(self.x(), self.y())
                self.next_wander = time.monotonic() + 10
            else:
                self.click_timer.start(QApplication.doubleClickInterval())

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.click_timer.stop()
            self.drag_offset = None
            self.open_requested.emit()

    def contextMenuEvent(self, event):
        self.menu_requested.emit(event.globalPos())

    def closeEvent(self, event):
        # App owns lifetime; the pet itself never kills the tray controller.
        if self.allow_close:
            event.accept()
            return
        event.ignore()
        self.hide_animated()
