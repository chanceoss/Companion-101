import time
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from desktop_pet.app import Application
from desktop_pet.storage import Settings
from desktop_pet.sprites import ASSETS


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
