import time
import pytest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from desktop_pet.app import Application
from desktop_pet.storage import Settings
from desktop_pet.sprites import ASSETS
from desktop_pet.sprites import SpriteBank
from desktop_pet.pet import PetWindow
from desktop_pet.model import WalkMotion


def test_native_desktop_flow(app, tmp_path):
    controller = Application(app, Settings(tmp_path))
    try:
        pet = controller.pet
        QTest.qWait(100)
        assert pet.isVisible()
        assert pet.windowFlags() & Qt.WindowStaysOnTopHint
        assert pet.testAttribute(Qt.WA_TranslucentBackground)
        # The actual asset is transparent and includes opaque character pixels.
        image = QImage(str(ASSETS / "biscuit.png"))
        assert image.hasAlphaChannel() and image.pixelColor(0, 0).alpha() == 0
        assert image.pixelColor(image.width() // 2, image.height() // 2).alpha() >= 245
        for state in ("idle", "walking", "happy", "sleeping", "dragged", "entering", "leaving"):
            pet.set_state(state)
            pet.pose = pet.animator.advance(.2)
            rendered = pet.grab().toImage()
            assert not rendered.isNull()
        controller.summon()
        controller.toggle_sleep()
        assert pet.animator.state == "sleeping"
        controller.toggle_sleep()
        assert pet.animator.state == "idle"
        controller.set_scale(125)
        assert pet.width() == round(290 * 1.25)
        controller.set_wander(True)
        pet.next_wander = 0
        pet.tick()
        assert pet.animator.state == "walking"
        controller.set_wander(False)
        pet.tick()
        assert pet.animator.state == "idle"
        controller.panel.tabs.setCurrentIndex(1)
        controller.panel.input.setText("hello")
        controller.panel.send()
        assert "Hi, friend!" in controller.panel.transcript.toPlainText()
        controller.panel.clear_chat()
        assert "Hi, friend!" not in controller.panel.transcript.toPlainText()
        controller.toggle_focus()
        assert controller.focus_deadline
        controller.focus_deadline = time.monotonic() - 1
        controller.focus_tick()
        assert controller.focus_deadline is None
        assert "You did it" in controller.panel.transcript.toPlainText()
        controller.hide_pet()
        pet.animator.advance(.7)
        pet.tick()
        assert not pet.isVisible()
        controller.summon()
        assert pet.isVisible()
        controller.panel.close()
        assert not controller.panel.isVisible()
        assert pet.isVisible()
    finally:
        controller.cleanup()
        controller.focus_timer.stop()
        controller.pet.hide()
        controller.panel.hide()
        controller.pet.deleteLater()
        controller.panel.deleteLater()
        controller.menu.deleteLater()


def test_drag_and_double_click(app, tmp_path):
    controller = Application(app, Settings(tmp_path), show_panel=False)
    try:
        pet = controller.pet
        pet.move(200, 200)
        pet.set_state("idle")
        QTest.mousePress(pet, Qt.LeftButton, pos=QPoint(140, 150))
        QTest.mouseMove(pet, QPoint(180, 170))
        QTest.mouseRelease(pet, Qt.LeftButton, pos=QPoint(180, 170))
        assert pet.drag_offset is None
        assert pet.animator.state == "idle"
        assert controller.settings.get("x") is not None
        QTest.mouseDClick(pet, Qt.LeftButton, pos=QPoint(140, 150))
        assert controller.panel.isVisible()
        assert controller.panel.tabs.currentIndex() == 1
    finally:
        controller.cleanup()
        controller.focus_timer.stop()
        controller.pet.hide()
        controller.panel.hide()
        controller.pet.deleteLater()
        controller.panel.deleteLater()
        controller.menu.deleteLater()


@pytest.mark.parametrize("vector,facing", [((1, 0), "side"), ((-1, 0), "side"),
                                          ((0, 1), "front"), ((0, -1), "back")])
def test_wandering_moves_and_animates_in_each_direction(app, tmp_path, monkeypatch, vector, facing):
    settings = Settings(tmp_path)
    settings.update(wander=True)
    pet = PetWindow(settings, SpriteBank())
    pet.timer.stop()
    pet.show()
    pet.move(200, 100)
    try:
        clock = [1000.0]
        monkeypatch.setattr("desktop_pet.pet.time.monotonic", lambda: clock[0])
        pet.set_state("walking")
        pet.walk_motion = WalkMotion(pet.x(), pet.y(), *vector)
        pet.wander_until = 1010
        pet._last = 999.95
        start = pet.pos()
        pet.tick()
        assert pet.walk_facing == facing
        assert (pet.x() - start.x()) * vector[0] + (pet.y() - start.y()) * vector[1] > 0
        first = pet.grab().toImage()
        for _ in range(3):
            clock[0] += .05
            pet.tick()
        assert pet.grab().toImage() != first
        pet.sleep()
        frozen = pet.pos()
        clock[0] += .05
        pet.tick()
        assert pet.pos() == frozen
        assert pet.walk_motion is None
    finally:
        pet.hide()
        pet.bubble.hide()
        pet.bubble.deleteLater()
        pet.deleteLater()
