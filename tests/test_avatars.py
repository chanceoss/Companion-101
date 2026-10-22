"""Companion changes keep native state, conversation and provider credentials."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QBitmap, QRegion

from desktop_pet.animations import Animator
from desktop_pet.app import Application
from desktop_pet.chat_widgets import Avatar
from desktop_pet.model import offline_reply
from desktop_pet.sprites import SpriteBank
from desktop_pet.storage import Settings, normalize_settings


@pytest.fixture
def controller(app, tmp_path):
    instance = Application(app, Settings(tmp_path))
    for timer in (instance.pet.timer, instance.hello_timer, instance.focus_timer,
                  instance.panel.portrait.timer):
        timer.stop()
    instance.pet.set_state("idle", transition=False)
    yield instance
    instance.cleanup()
    instance.pet.hide()
    instance.panel.hide()
    for widget in (instance.pet.bubble, instance.pet, instance.panel,
                   instance.menu, instance.tray):
        widget.deleteLater()


def choose(controller, avatar):
    preferences = controller.panel.preferences
    preferences.avatar.setCurrentIndex(preferences.avatar.findData(avatar))
    preferences.save()


@pytest.mark.parametrize("value", [None, [], {}, "../../other", "unknown"])
def test_invalid_avatar_recovers_to_original(value):
    assert normalize_settings({"avatar": value})["avatar"] == "biscuit"
    assert normalize_settings({})["avatar"] == "biscuit"


def test_tori_art_covers_all_states_with_transparent_padded_frames(app):
    original, tori = SpriteBank(), SpriteBank(avatar="tori")
    assert set(original.states) <= set(tori.states)
    assert len(tori.images) == 24
    for frame in tori.images.values():
        image = frame.toImage()
        assert image.hasAlphaChannel() and image.pixelColor(0, 0).alpha() == 0
        bounds = QRegion(QBitmap.fromImage(image.createAlphaMask(Qt.ThresholdAlphaDither))).boundingRect()
        assert bounds.top() >= 20 and bounds.bottom() <= 465
        assert bounds.left() >= 5 and bounds.right() <= 475
    for state in tori.states:
        assert tori.eyes(state) == []  # Do not paint orange Biscuit eyelids on Tori.
        assert not tori.frame(state, .2).isNull()
    assert tori.frame("walking", 0, "side").cacheKey() != tori.frame("walking", .125, "side").cacheKey()
    assert tori.frame("walking", 0, "side").cacheKey() != tori.frame("walking", 0, "back").cacheKey()
    assert tori.spec("walking")["mirror_left"]


def test_switch_updates_surfaces_and_persists_without_touching_chat(controller):
    c = controller
    c.handle_message("hello")
    c.companion.history = [{"role": "user", "content": "Keep this conversation"}]
    c.companion.key = "dummy-session-key"
    history = list(c.companion.history)
    transcript = c.panel.transcript.toPlainText()
    position = c.pet.pos()
    original = c.sprites
    choose(c, "tori")
    assert c.sprites.avatar == "tori"
    assert c.pet.sprites is c.panel.sprites is c.panel.portrait.sprites is c.panel.transcript.sprites is c.sprites
    assert c.panel.pet_name.text() == "Tori"
    assert c.pet.windowTitle().startswith("Tori") and c.tray.toolTip().startswith("Tori")
    assert c.panel.gesture_actions["tail_wag"].text() == "Shell wiggle"
    assert c.gesture_actions["tail_wag"].text() == "Shell wiggle"
    for tile in c.panel.activity_buttons.values():
        assert tile.sprite.cacheKey() == c.sprites.frame(tile.activity.scene, 0).cacheKey()
    for avatar in c.panel.transcript.findChildren(Avatar):
        if not avatar.mine:
            assert avatar.sprite.cacheKey() == c.sprites.frame("idle", 0).cacheKey()
    assert c.pet.pos() == position
    assert c.companion.history == history and c.companion.key == "dummy-session-key"
    assert c.panel.transcript.toPlainText() == transcript
    reloaded = Settings(c.settings.directory)
    assert reloaded.get("avatar") == "tori" and reloaded.get("name") == "Tori"
    assert not c.pet.grab().isNull() and not c.panel.grab().isNull()
    choose(c, "biscuit")
    assert c.sprites is original and c.settings.get("name") == "Biscuit"
    assert c.panel.transcript.toPlainText() == transcript


@pytest.mark.parametrize("activity", ["work", "nap", "explore", "follow", "greet"])
def test_switch_preserves_activity_focus_and_animation_clock(controller, activity):
    c = controller
    c.activate_activity(activity)
    c.pet.pose = c.pet.animator.advance(.2)
    state, elapsed = c.pet.animator.state, c.pet.animator.elapsed
    deadline, greeting = c.focus_deadline, c.pet.greeting_until
    choose(c, "tori")
    assert c.pet.animator.state == state and c.pet.animator.elapsed == elapsed
    assert c.focus_deadline == deadline and c.pet.greeting_until == greeting
    assert c.pet.display_activity == activity
    assert c.panel.portrait.activity == activity


def test_switch_keeps_inflight_reaction_and_reacts_to_reply(controller):
    c = controller
    c.companion.busy_changed.emit(True)
    choose(c, "tori")
    assert c.pet.gesture == c.panel.portrait.gesture == "chat_thinking"
    assert c.panel.input.placeholderText() == "Tori is thinking…"
    c._chat_user_text = "I'm sad today"
    c.companion.answered.emit("I'm here with you.")
    c.companion.busy_changed.emit(False)
    assert c.pet.gesture == c.panel.portrait.gesture == "comforting"
    assert c.panel.transcript.messages[-1][0] == "Tori"


def test_custom_name_preserved_and_selection_waits_for_save(controller, monkeypatch):
    c = controller
    p = c.panel.preferences
    p.name.setText("Pebble")
    p.avatar.setCurrentIndex(p.avatar.findData("tori"))
    assert c.sprites.avatar == c.settings.get("avatar") == "biscuit"
    p.save()
    assert c.settings.get("name") == "Pebble"
    choose(c, "biscuit")
    assert c.settings.get("name") == "Pebble"
    def fail(**values):
        raise OSError("Cannot save preferences")
    monkeypatch.setattr(c.settings, "update", fail)
    choose(c, "tori")
    assert c.sprites.avatar == c.settings.get("avatar") == "biscuit"
    assert "Cannot save" in p.status.text()


def test_switch_out_of_avatar_specific_idle_and_crossfade_is_safe(app):
    original, tori = SpriteBank(), SpriteBank(avatar="tori")
    animator = Animator(library=tori.animation_library)
    animator.set_state("idle_blink", transition=False)
    animator.advance(.1)
    animator.set_library(original.animation_library)
    assert animator.state == "idle"
    animator.advance(.1)
    animator.set_library(tori.animation_library)
    animator.set_state("idle_blink", transition=False)
    animator.set_state("happy")
    animator.advance(.1)
    animator.set_library(original.animation_library)
    assert all(state in original.states for state, _, _ in animator.layers())
    animator.advance(2)


def test_tori_startup_and_offline_identity(app, tmp_path):
    settings = Settings(tmp_path)
    settings.update(avatar="tori", name="Tori")
    c = Application(app, settings, show_panel=False)
    try:
        c.hello_timer.stop()
        assert c.sprites.avatar == "tori" and c.panel.pet_name.text() == "Tori"
        c.handle_message("hello")
        assert "I’m Tori" in c.panel.transcript.toPlainText()
        assert "shell" in offline_reply("cute", "Tori", "tori")
        assert "fuzzy ears" not in offline_reply("test", "Tori", "tori")
    finally:
        c.cleanup()
        c.pet.hide()
        c.panel.hide()
        for widget in (c.pet.bubble, c.pet, c.panel, c.menu, c.tray):
            widget.deleteLater()
