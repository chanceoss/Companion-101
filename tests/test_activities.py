import math
from types import SimpleNamespace
import pytest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from desktop_pet.activities import ACTIVITIES, SCENES
from desktop_pet.app import Application
from desktop_pet.model import FollowMotion
from desktop_pet.storage import Settings


@pytest.fixture
def controller(app, tmp_path):
    instance = Application(app, Settings(tmp_path))
    instance.pet.timer.stop()
    instance.hello_timer.stop()
    instance.focus_timer.stop()
    yield instance
    instance.cleanup()
    instance.pet.hide()
    instance.panel.hide()
    instance.pet.bubble.deleteLater()
    instance.pet.deleteLater()
    instance.panel.deleteLater()
    instance.menu.deleteLater()
    instance.tray.deleteLater()


@pytest.mark.parametrize("key", [a.key for a in ACTIVITIES])
def test_native_activity_buttons_activate_real_behavior(controller, key):
    tile = controller.panel.activity_buttons[key]
    QTest.mouseClick(tile, Qt.LeftButton)
    pet = controller.pet
    assert pet.display_activity == key
    assert pet.animator.state == SCENES[key]
    assert tile.isChecked()
    assert sum(b.isChecked() for b in controller.panel.activity_buttons.values()) == 1
    assert controller.settings.get("wander") == (key == "explore")
    assert bool(controller.focus_deadline) == (key == "work")
    pet.pose = pet.animator.advance(.15)
    assert not pet.grab().isNull()
    assert controller.sprites.eyes(SCENES[key]) == []


@pytest.mark.parametrize("previous", ["idle", "explore", "work", "nap", "follow"])
def test_greeting_returns_to_previous_activity_without_losing_focus(controller, monkeypatch, previous):
    clock = [1000.0]
    monkeypatch.setattr("desktop_pet.pet.time.monotonic", lambda: clock[0])
    controller.activate_activity(previous, toggle=False)
    original_deadline = controller.focus_deadline
    controller.pet._last = clock[0]
    controller.activate_activity("greet")
    assert controller.pet.activity == previous
    clock[0] += 1
    frozen = controller.pet.pos()
    controller.pet.tick()
    assert controller.pet.pos() == frozen
    assert controller.pet.animator.state == "greeting"
    clock[0] += 3.1
    controller.pet.tick()
    assert controller.pet.display_activity == previous
    assert controller.focus_deadline == original_deadline
    if previous == "nap":
        assert controller.pet.animator.state == "sleeping"
    if previous == "work":
        assert controller.pet.animator.state == "working"


@pytest.mark.parametrize("next_activity", ["explore", "nap", "follow", "idle"])
def test_switching_activity_cancels_work_timer(controller, next_activity):
    controller.activate_activity("work")
    assert controller.focus_deadline is not None
    controller.activate_activity(next_activity)
    assert controller.focus_deadline is None
    assert controller.pet.activity == next_activity
    assert not controller.work_action.isChecked()


def test_focus_completion_rests_and_does_not_restart_laptop(controller):
    controller.activate_activity("work")
    controller.focus_deadline = -1
    controller.focus_tick()
    assert controller.focus_deadline is None
    assert controller.pet.activity == "idle"
    controller.pet.animator.advance(2)
    controller.pet.tick()
    assert controller.pet.animator.state == "idle"


def test_repeat_selection_and_rest_button_stop_activities(controller):
    for key in ("explore", "work", "nap", "follow"):
        controller.activate_activity(key)
        controller.activate_activity(key)
        assert controller.pet.activity == "idle"
        assert controller.focus_deadline is None
    controller.activate_activity("follow")
    QTest.mouseClick(controller.panel.rest_button, Qt.LeftButton)
    assert controller.pet.activity == "idle"
    assert controller.pet.walk_motion is None
    assert not controller.follow_action.isChecked()


def test_pointer_follow_walks_waits_and_ignores_other_monitors(controller, monkeypatch):
    pet = controller.pet
    pet.move(100, 80)
    controller.activate_activity("follow")
    target = [QPoint(650, 550)]
    monkeypatch.setattr("desktop_pet.pet.QCursor", SimpleNamespace(pos=lambda: target[0]))
    clock = [1000.0]
    monkeypatch.setattr("desktop_pet.pet.time.monotonic", lambda: clock[0])
    pet._last = clock[0] - .1
    original = pet.pos()
    pet.tick()
    assert pet.x() > original.x() and pet.y() > original.y()
    assert pet.animator.state == "walking"
    target[0] = QPoint(round(pet.x() + pet.width() / 2), round(pet.y() + pet.height() * .65))
    clock[0] += .1
    pet.tick()
    assert pet.animator.state == "following"
    stopped = pet.pos()
    area = pet.screen().availableGeometry()
    target[0] = QPoint(area.right() + 500, area.bottom() + 500)
    clock[0] += .1
    pet.tick()
    assert pet.pos() == stopped
    assert pet.animator.state == "following"


@pytest.mark.parametrize("key,scene", [("work", "working"), ("nap", "sleeping"), ("follow", "following")])
def test_drag_preserves_activity(controller, key, scene):
    pet = controller.pet
    pet.move(150, 100)
    controller.activate_activity(key)
    deadline = controller.focus_deadline
    QTest.mousePress(pet, Qt.LeftButton, pos=QPoint(140, 150))
    QTest.mouseMove(pet, QPoint(190, 170))
    QTest.mouseRelease(pet, Qt.LeftButton, pos=QPoint(190, 170))
    assert pet.activity == key
    assert pet.animator.state == scene
    assert controller.focus_deadline == deadline
    assert pet.follow_motion is None


def test_follow_stops_at_gap_without_overshooting():
    motion = FollowMotion(100, 100)
    width, height = 290, 310
    pointer = (800, 700)
    motion.step(50, pointer, (0, 0, 1600, 1200), width, height)
    distance = math.hypot(pointer[0] - motion.x - width / 2, pointer[1] - motion.y - height * .65)
    assert distance == pytest.approx(width * .33)
    motion.step(.1, pointer, (0, 0, 1600, 1200), width, height)
    assert not motion.moving


def test_follow_uses_hysteresis_and_screen_bounds():
    motion = FollowMotion(100, 100)
    bounds, width, height = (0, 0, 1000, 800), 290, 310
    center = (245, 301.5)
    original = motion.step(.1, (center[0] + 105, center[1]), bounds, width, height)
    assert original == (100, 100) and not motion.moving
    motion.step(.1, (center[0] + 140, center[1]), bounds, width, height)
    assert motion.moving and motion.x > 100
    stopped = (round(motion.x), round(motion.y))
    assert motion.step(.1, (-100, 100), bounds, width, height) == stopped
    assert not motion.moving
    motion = FollowMotion(-1800, 10)
    for _ in range(300):
        x, y = motion.step(.1, (-1910, 20), (-1920, 0, 0, 1080), width, height)
        assert -1920 <= x <= -290 and 0 <= y <= 770
