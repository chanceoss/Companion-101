"""Conversation expressions use the real pet lifecycle and cached sprite art."""

import time

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QBitmap, QRegion

from desktop_pet.app import Application
from desktop_pet.conversation import conversation_reaction
from desktop_pet.gestures import CONVERSATION_GESTURES, GESTURE_STATES
from desktop_pet.sprites import SpriteBank
from desktop_pet.storage import Settings


@pytest.fixture
def controller(app, tmp_path):
    instance = Application(app, Settings(tmp_path))
    instance.pet.timer.stop()
    instance.hello_timer.stop()
    instance.focus_timer.stop()
    instance.panel.portrait.timer.stop()
    instance.pet.set_state("idle", transition=False)
    yield instance
    instance.cleanup()
    instance.pet.hide()
    instance.panel.hide()
    for widget in (
        instance.pet.bubble,
        instance.pet,
        instance.panel,
        instance.menu,
        instance.tray,
    ):
        widget.deleteLater()


@pytest.mark.parametrize(
    "user,reply,state",
    [
        ("I'm feeling sad and lonely", "Here's a joke! 😂", "comforting"),
        ("I'm not sad", "Let's take a little walk.", "tail_wag"),
        ("I'm stressed about today", "You can do this.", "comforting"),
        ("Malungkot ako", "Nandito ako.", "comforting"),
        ("Thanks, you're so cute", "Aw, thank you!", "bashful"),
        ("Salamat Biscuit!", "You're welcome.", "bashful"),
        ("Tell me a joke", "Why did the cat sit on the laptop?", "laughing"),
        ("hahaha 😂", "Glad you liked it.", "laughing"),
        ("Wow, I can't believe it!", "What a surprise.", "surprised"),
        ("I finally passed my exam!", "Congratulations!", "dancing"),
        ("I'm so sleepy, goodnight", "Sweet dreams.", "yawning"),
        ("Can you explain this?", "Let's go step by step.", "curious"),
        ("hello", "Hi, friend!", "tail_wag"),
        ("Look at this example: `sad lonely stressed`", "Got it.", "tail_wag"),
        ("An example:\n```python\nsad = True\n```", "Okay.", "tail_wag"),
        ("> I'm sad\nWhat does this mean?", "Let's discuss it.", "curious"),
        (
            "Something happened",
            "I'm sorry to hear that. I'm here for you.",
            "comforting",
        ),
    ],
)
def test_local_rules_choose_appropriate_safe_reactions(user, reply, state):
    assert conversation_reaction(user, reply) == state
    assert state in GESTURE_STATES


def test_new_atlas_contains_24_distinct_padded_transparent_frames(app):
    sprites = SpriteBank()
    keys = set()
    for state, _ in CONVERSATION_GESTURES:
        spec = sprites.spec(state)
        frames = [
            sprites.frame(state, i / spec["fps"]) for i in range(len(spec["frames"]))
        ]
        assert len({frame.cacheKey() for frame in frames}) == 4
        for frame in frames:
            keys.add(frame.cacheKey())
            image = frame.toImage()
            assert image.hasAlphaChannel() and image.pixelColor(0, 0).alpha() == 0
            bounds = QRegion(
                QBitmap.fromImage(image.createAlphaMask(Qt.ThresholdAlphaDither))
            ).boundingRect()
            assert bounds.top() >= 20 and bounds.bottom() <= 465
            assert bounds.left() >= 5 and bounds.right() <= 475
        assert sprites.eyes(state) == []
        assert spec["playback"] == "once" and spec["next"] == "idle"
    assert len(keys) == 24


def test_offline_reply_reacts_in_both_widgets_without_a_network_call(
    controller, monkeypatch
):
    monkeypatch.setattr(
        controller.companion.network,
        "post",
        lambda *args: pytest.fail("Offline reaction made an AI call"),
    )
    controller.handle_message("I'm sad and lonely today")
    assert controller.pet.gesture == "comforting"
    assert controller.panel.portrait.gesture == "comforting"
    assert "I’m right here" in controller.panel.transcript.toPlainText()
    assert controller._chat_user_text == "" and controller.companion.reply is None
    assert not controller.pet.grab().isNull()


def test_thinking_loop_blends_to_reply_and_restores_activity(controller):
    controller.activate_activity("explore")
    controller._chat_user_text = "Tell me a joke"
    controller.companion.busy_changed.emit(True)
    assert controller.pet.gesture == "chat_thinking"
    controller.pet.pose = controller.pet.animator.advance(12)
    assert controller.pet.animator.state == "chat_thinking"
    controller.companion.answered.emit("Haha, a tiny paw-some joke!")
    controller.companion.busy_changed.emit(False)
    assert controller.pet.gesture == "laughing"
    assert controller.panel.portrait.gesture == "laughing"
    assert controller.pet.activity == "explore"
    assert {
        state for state, _, weight in controller.pet.animator.layers() if weight > 0
    } == {"chat_thinking"}
    controller.pet.pose = controller.pet.animator.advance(0.17)
    assert len(controller.pet.animator.layers()) == 2
    controller.pet.pose = controller.pet.animator.advance(3)
    controller.pet._last = time.monotonic()
    controller.pet.tick()
    assert controller.pet.gesture is None
    assert controller.pet.animator.state == "exploring"
    assert controller.panel.portrait.animator.state == "exploring"


@pytest.mark.parametrize(
    "activity,state", [("work", "working"), ("nap", "sleeping"), ("greet", "greeting")]
)
def test_automatic_chat_reactions_preserve_focus_naps_and_greetings(
    controller, activity, state
):
    controller.activate_activity(activity)
    deadline = controller.focus_deadline
    controller.companion.busy_changed.emit(True)
    controller.answer("Haha, that's funny!")
    controller.companion.busy_changed.emit(False)
    assert controller.pet.animator.state == state and controller.pet.gesture is None
    assert controller.focus_deadline == deadline


def test_explicit_reaction_takes_priority_over_pending_chat(controller):
    controller.companion.busy_changed.emit(True)
    controller.perform_gesture("hopping")
    controller.answer("Wow!")
    controller.companion.busy_changed.emit(False)
    assert controller.pet.gesture == "hopping" and controller._chat_gesture is None
    assert controller.panel.portrait.gesture == "hopping"


def test_cancel_and_clear_stop_only_the_chat_owned_loop(controller):
    controller.companion.busy_changed.emit(True)
    controller.companion.failed.emit("HTTP 401: Authentication failed.")
    controller.companion.busy_changed.emit(False)
    assert controller.pet.gesture is None and controller.pet.animator.state == "idle"
    assert "HTTP 401" in controller.panel.transcript.toPlainText()
    controller.companion.busy_changed.emit(True)
    controller._chat_user_text = "Private earlier message"
    controller.panel.clear_chat()
    assert controller._chat_user_text == "" and controller._chat_gesture is None
    assert controller.pet.gesture is None and controller.panel.portrait.gesture is None
    controller.perform_gesture("thinking")
    controller.companion.busy_changed.emit(False)
    assert controller.pet.gesture == "thinking"


def test_disabling_automatic_reactions_stops_waiting_but_keeps_manual_menu(controller):
    preferences = controller.panel.preferences
    controller.companion.busy_changed.emit(True)
    preferences.chat_reactions.setChecked(False)
    preferences.save()
    assert controller.settings.get("chat_reactions") is False
    assert Settings(controller.settings.directory).get("chat_reactions") is False
    assert controller.pet.gesture is None
    controller.answer("Haha, that's funny!")
    assert controller.pet.gesture is None
    controller.panel.gesture_actions["curious"].trigger()
    assert controller.pet.gesture == "curious"


@pytest.mark.parametrize("unavailable", ["dragged", "leaving", "hidden"])
def test_chat_does_not_summon_or_interrupt_unavailable_pet(controller, unavailable):
    if unavailable == "hidden":
        controller.pet.hide()
    else:
        controller.pet.set_state(unavailable)
    controller.companion.busy_changed.emit(True)
    controller.answer("You're adorable!")
    controller.companion.busy_changed.emit(False)
    assert controller.pet.gesture is None
    if unavailable == "hidden":
        assert not controller.pet.isVisible()
    else:
        assert controller.pet.animator.state == unavailable
