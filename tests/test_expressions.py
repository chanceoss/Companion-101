"""Reactions run in the real desktop controls without disrupting activities."""
import time
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from desktop_pet.app import Application
from desktop_pet.gestures import GESTURES
from desktop_pet.storage import Settings


@pytest.fixture
def controller(app, tmp_path):
    instance = Application(app, Settings(tmp_path))
    instance.pet.timer.stop()
    instance.hello_timer.stop()
    instance.focus_timer.stop()
    instance.panel.portrait.timer.stop()
    yield instance
    instance.cleanup()
    instance.pet.hide()
    instance.panel.hide()
    for widget in (instance.pet.bubble, instance.pet, instance.panel,
                   instance.menu, instance.tray):
        widget.deleteLater()


def finish_reaction(controller):
    pet = controller.pet
    pet.pose = pet.animator.advance(pet.animator.library.duration(pet.gesture) + .01)
    pet._last = time.monotonic()
    pet.tick()


@pytest.mark.parametrize("state", [state for state, _ in GESTURES])
def test_panel_reaction_menu_preserves_work_session(controller, state):
    controller.activate_activity("work")
    deadline = controller.focus_deadline
    controller.panel.gesture_actions[state].trigger()
    assert controller.pet.gesture == state
    assert controller.pet.animator.state == state
    assert controller.panel.portrait.animator.state == state
    assert controller.panel.activity_buttons["work"].isChecked()
    assert controller.pet.activity == "work"
    assert controller.focus_deadline == deadline
    controller.pet.pose = controller.pet.animator.advance(.15)
    assert not controller.pet.grab().isNull()
    finish_reaction(controller)
    assert controller.pet.gesture is None
    assert controller.pet.animator.state == "working"
    assert controller.panel.portrait.animator.state == "working"
    assert controller.focus_deadline == deadline


@pytest.mark.parametrize("activity,scene", [("nap", "sleeping"), ("follow", "following")])
def test_tray_reactions_return_to_underlying_activity(controller, monkeypatch, activity, scene):
    pet = controller.pet
    controller.activate_activity(activity)
    # Keep the pointer at the pet so Follow returns to its waiting pose.
    pointer = QPoint(round(pet.x() + pet.width() / 2), round(pet.y() + pet.height() * .65))
    monkeypatch.setattr("desktop_pet.pet.QCursor", SimpleNamespace(pos=lambda: pointer))
    controller.gesture_actions["tail_wag"].trigger()
    assert pet.gesture == "tail_wag"
    start = pet.pos()
    pet._last = time.monotonic() - .1
    pet.tick()
    assert pet.pos() == start
    assert controller.panel.activity_buttons[activity].isChecked()
    finish_reaction(controller)
    assert pet.activity == activity
    assert pet.animator.state == scene
    assert controller.panel.portrait.animator.state == scene


def test_reaction_pauses_and_resumes_greeting(controller, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr("desktop_pet.pet.time.monotonic", lambda: clock[0])
    controller.activate_activity("work")
    deadline = controller.focus_deadline
    controller.activate_activity("greet")
    clock[0] += .7
    controller.pet.pose = controller.pet.animator.advance(.7)
    remaining = controller.pet.greeting_until - clock[0]
    controller.perform_gesture("stretching")
    clock[0] += 10
    assert controller.pet.display_activity == "greet"
    finish_reaction(controller)
    assert controller.pet.animator.state == "greeting"
    assert controller.pet.greeting_until == pytest.approx(clock[0] + remaining)
    assert controller.pet.display_activity == "greet"
    assert controller.focus_deadline == deadline
    clock[0] += remaining + .01
    controller.pet.tick()
    assert controller.pet.animator.state == "working"
    assert controller.pet.display_activity == "work"


def test_rapid_reactions_and_activity_switch_do_not_restore_stale_state(controller):
    controller.activate_activity("work")
    controller.perform_gesture("sitting")
    controller.pet.pose = controller.pet.animator.advance(.2)
    controller.perform_gesture("dancing")
    controller.pet.pose = controller.pet.animator.advance(.2)
    controller.perform_gesture("hopping")
    assert controller.pet.gesture == "hopping"
    finish_reaction(controller)
    assert controller.pet.animator.state == "working"
    controller.perform_gesture("yawning")
    controller.activate_activity("nap")
    assert controller.pet.gesture is None
    assert controller.pet.animator.state == "sleeping"
    assert controller.panel.portrait.animator.state == "sleeping"
    assert controller.focus_deadline is None


def test_gestures_do_not_override_leaving_or_dragging(controller):
    pet = controller.pet
    controller.perform_gesture("dancing")
    controller.hide_pet()
    assert pet.gesture is None
    controller.perform_gesture("hopping")
    assert pet.animator.state == "leaving"
    controller.summon()
    pet.set_state("dragged")
    controller.perform_gesture("dancing")
    assert pet.animator.state == "dragged"
    assert pet.gesture is None
    with pytest.raises(ValueError, match="Unknown Biscuit reaction"):
        pet.perform_gesture("not_a_reaction")


def test_chat_reply_keeps_nap_and_explicit_reaction_intact(controller):
    controller.activate_activity("nap")
    controller.answer("Sweet dreams.")
    assert controller.pet.animator.state == "sleeping"
    controller.perform_gesture("yawning")
    controller.answer("Take your time.")
    assert controller.pet.animator.state == "yawning"
    finish_reaction(controller)
    assert controller.pet.animator.state == "sleeping"


def test_drag_interrupts_reaction_and_restores_current_activity(controller):
    controller.activate_activity("work")
    deadline = controller.focus_deadline
    controller.perform_gesture("tail_wag")
    pet = controller.pet
    QTest.mousePress(pet, Qt.LeftButton, pos=QPoint(140, 150))
    QTest.mouseMove(pet, QPoint(190, 170))
    QTest.mouseRelease(pet, Qt.LeftButton, pos=QPoint(190, 170))
    assert pet.gesture is None
    assert pet.activity == "work"
    assert pet.animator.state == "working"
    assert controller.focus_deadline == deadline


def test_compact_panel_keeps_reaction_menu_and_chat_controls_visible(controller, app):
    panel = controller.panel
    panel.resize(480, 540)
    app.processEvents()
    assert panel.size().width() == 480
    assert panel.size().height() == 540
    for widget in (panel.gesture_button, panel.input, panel.send_button, panel.clear_button):
        assert widget.isVisible()
        assert panel.rect().contains(widget.mapTo(panel, widget.rect().bottomRight()))
    assert panel.gesture_button.menu() == panel.gesture_menu
    assert len(panel.gesture_menu.actions()) == len(GESTURES)
    assert controller.tray.contextMenu() == controller.menu
    assert controller.gesture_menu.menuAction() in controller.menu.actions()
