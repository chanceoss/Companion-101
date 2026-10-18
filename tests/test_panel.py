import pytest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QFontInfo
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractButton, QScrollArea, QTabWidget
from desktop_pet.app import Application
from desktop_pet.chat_widgets import BubbleText
from desktop_pet.storage import Settings
from desktop_pet.theme import ui_font


@pytest.fixture
def controller(app, tmp_path):
    instance = Application(app, Settings(tmp_path))
    instance.hello_timer.stop()
    instance.pet.timer.stop()
    instance.focus_timer.stop()
    yield instance
    instance.cleanup()
    instance.panel.preferences.hide()
    instance.panel.hide()
    instance.pet.hide()
    instance.pet.bubble.deleteLater()
    instance.pet.deleteLater()
    instance.panel.deleteLater()
    instance.menu.deleteLater()
    instance.tray.deleteLater()


def test_companion_and_chat_are_visible_together_and_enter_sends(controller):
    panel = controller.panel
    panel.resize(1040, 900)
    QTest.qWait(20)
    assert panel.sidebar.isVisible() and panel.chat_panel.isVisible()
    assert panel.sidebar.mapTo(panel, QPoint()).x() < panel.chat_panel.mapTo(panel, QPoint()).x()
    assert panel.findChildren(QTabWidget) == []
    QTest.mouseClick(panel.input, Qt.LeftButton)
    QTest.keyClicks(panel.input, "hello")
    QTest.keyClick(panel.input, Qt.Key_Return)
    assert panel.input.text() == ""
    assert "Hi, friend!" in panel.transcript.toPlainText()
    assert "You\nhello" in panel.transcript.toPlainText()


def test_gear_opens_reusable_preferences_and_escape_leaves_pet_running(controller):
    panel = controller.panel
    assert not panel.preferences.isVisible()
    QTest.mouseClick(panel.settings_button, Qt.LeftButton)
    assert panel.preferences.isVisible()
    assert panel.chat_panel.isVisible()
    original = panel.preferences
    panel.preferences.name.setText("Crumble")
    QTest.keyClick(panel.preferences, Qt.Key_Escape)
    assert not panel.preferences.isVisible()
    assert panel.isVisible() and controller.pet.isVisible()
    QTest.mouseClick(panel.settings_button, Qt.LeftButton)
    assert panel.preferences is original
    assert panel.preferences.name.text() == "Crumble"
    QTest.mouseClick(panel.preferences.close_button, Qt.LeftButton)
    assert not panel.preferences.isVisible()


def test_preferences_save_updates_name_badge_and_size_without_plaintext_key(controller, monkeypatch):
    panel, settings = controller.panel, controller.settings
    panel.open_preferences()
    preferences = panel.preferences
    saved_keys = []
    monkeypatch.setattr(controller.companion, "save_key", lambda key, remember: saved_keys.append((key, remember)))
    preferences.name.setText("Crumble")
    preferences.reminders.setChecked(True)
    preferences.provider.setChecked(True)
    preferences.endpoint.setText("https://example.com/v1")
    preferences.model.setText("test-model")
    preferences.key.setText("test-session-key")
    preferences.remember.setChecked(False)
    preferences.scale.setValue(125)
    assert controller.pet.width() == round(290 * 1.25)
    QTest.mouseClick(preferences.save_button, Qt.LeftButton)
    assert settings.get("name") == "Crumble"
    assert panel.pet_name.text() == "Crumble"
    assert settings.get("reminders") is True
    assert settings.get("provider") is False
    assert saved_keys == []
    QTest.mouseClick(preferences.ai_save_button, Qt.LeftButton)
    assert settings.get("provider") is True
    assert panel.mode.text() == "●  AI enabled"
    assert saved_keys == [("test-session-key", False)]
    assert "test-session-key" not in settings.path.read_text()
    assert "saved" in preferences.status.text().lower()


def test_invalid_preferences_remain_open_with_explanation(controller):
    preferences = controller.panel.preferences
    controller.panel.open_preferences()
    preferences.model.clear()
    preferences.provider.setChecked(True)
    QTest.mouseClick(preferences.ai_save_button, Qt.LeftButton)
    assert "base URL and model" in preferences.ai_status.text()
    assert controller.settings.get("model") == "gpt-4o-mini"
    assert preferences.isVisible()


def test_preferences_keyboard_shortcut_and_return_saves_instead_of_quitting(controller, monkeypatch):
    panel = controller.panel
    panel.activateWindow()
    QTest.qWait(20)
    QTest.keyClick(panel, Qt.Key_Comma, Qt.ControlModifier)
    assert panel.preferences.isVisible()
    monkeypatch.setattr(controller.companion, "save_key", lambda *args: None)
    panel.preferences.name.setText("Muffin")
    panel.preferences.name.setFocus()
    QTest.keyClick(panel.preferences.name, Qt.Key_Return)
    assert controller.settings.get("name") == "Muffin"
    assert panel.pet_name.text() == "Muffin"
    assert controller.pet.allow_close is False


@pytest.mark.parametrize("size", [(840, 680), (1040, 900), (1280, 960)])
def test_two_column_layout_and_composer_fit_resized_window(controller, size):
    panel = controller.panel
    panel.resize(*size)
    QTest.qWait(30)
    assert panel.sidebar.width() >= 248
    assert panel.chat_panel.width() >= 360
    for widget in (panel.settings_button, panel.input, panel.send_button):
        origin = widget.mapTo(panel, QPoint())
        assert origin.x() >= 0 and origin.y() >= 0
        assert origin.x() + widget.width() <= panel.width()
        assert origin.y() + widget.height() <= panel.height()
    assert panel.sidebar.horizontalScrollBar().maximum() == 0
    assert not panel.grab().isNull()


def test_settings_scroll_without_squeezing_fields_or_hiding_save(controller):
    preferences = controller.panel.preferences
    preferences.resize(460, 500)
    controller.panel.open_preferences()
    QTest.qWait(30)
    assert preferences.model.height() >= 40
    origin = preferences.save_button.mapTo(preferences, QPoint())
    assert origin.y() + preferences.save_button.height() <= preferences.height()
    assert any(scroll.verticalScrollBar().maximum() > 0 for scroll in preferences.findChildren(QScrollArea))


def test_chat_wraps_long_text_keeps_plain_text_and_scrolls_to_reply(controller):
    panel = controller.panel
    panel.resize(840, 680)
    text = '<img src="https://example.com/never-load.png"> <b>plain text</b>\n' + "longword" * 300
    panel.add_message("Biscuit", text)
    QTest.qWait(80)
    bubbles = panel.transcript.findChildren(BubbleText)
    assert any(bubble.toPlainText() == text for bubble in bubbles)
    assert all(not bubble.openExternalLinks() for bubble in bubbles)
    assert panel.transcript.horizontalScrollBar().maximum() == 0
    bar = panel.transcript.verticalScrollBar()
    assert bar.maximum() > 0
    assert bar.value() == bar.maximum()
    panel.clear_chat()
    assert text not in panel.transcript.toPlainText()
    assert "fresh little start" in panel.transcript.toPlainText()


def test_work_countdown_is_visible_on_its_activity_card(controller):
    panel = controller.panel
    controller.activate_activity("work")
    assert panel.activity_buttons["work"].text() == "25:00"
    assert not panel.focus.isHidden()
    controller.activate_activity("nap")
    assert panel.activity_buttons["work"].text() == "Work"
    assert panel.focus.isHidden()


def test_only_explore_tile_controls_roaming_and_stays_in_sync_with_tray(controller):
    panel = controller.panel
    explore = panel.activity_buttons["explore"]
    assert [widget for widget in panel.findChildren(QAbstractButton)
            if "Explore" in widget.text()] == [explore]
    QTest.mouseClick(explore, Qt.LeftButton)
    assert controller.pet.activity == "explore"
    assert controller.settings.get("wander") and controller.wander.isChecked()
    controller.wander.trigger()
    assert controller.pet.activity == "idle" and not explore.isChecked()
    QTest.mouseClick(explore, Qt.LeftButton)
    QTest.mouseClick(explore, Qt.LeftButton)
    assert not controller.settings.get("wander")


def test_compact_layout_fits_and_restores_wide_layout_without_losing_chat(controller):
    panel = controller.panel
    panel.add_message("You", "Keep this conversation", mine=True)
    controller.activate_activity("work")
    controller.settings.update(provider=True)
    panel.refresh_mode()
    panel.set_busy(True)
    for width, height in ((480, 540), (640, 600), (799, 620), (1040, 900), (480, 540)):
        panel.resize(width, height)
        QTest.qWait(30)
        assert (panel.width(), panel.height()) == (width, height)
        compact = width < 800
        assert panel.compact is compact
        assert panel.portrait.isVisible() is not compact
        assert panel.sidebar.horizontalScrollBar().maximum() == 0
        for widget in (panel.settings_button, panel.input, panel.send_button,
                       *panel.activity_buttons.values()):
            assert widget.isVisible()
            origin = widget.mapTo(panel, QPoint())
            assert 0 <= origin.x() <= panel.width() - widget.width()
            assert 0 <= origin.y() <= panel.height() - widget.height()
        if compact:
            assert panel.sidebar.verticalScrollBar().maximum() == 0
            assert panel.sidebar.y() < panel.chat_panel.y()
        else:
            assert panel.sidebar.x() < panel.chat_panel.x()
        assert panel.activity_buttons["work"].isChecked()
        assert "Keep this conversation" in panel.transcript.toPlainText()
    panel.set_busy(False)


def test_general_preferences_ignore_ai_fields_and_keep_conversation(controller, monkeypatch):
    panel, companion = controller.panel, controller.companion
    history = [{"role": "assistant", "content": "Remember our conversation"}]
    companion.history = history.copy()
    panel.add_message("Biscuit", history[0]["content"])
    cancelled, credentials = [], []
    monkeypatch.setattr(companion, "cancel_pending", lambda: cancelled.append(True))
    monkeypatch.setattr(companion, "save_key", lambda *args: credentials.append(args))
    preferences = panel.preferences
    preferences.provider.setChecked(True)
    preferences.endpoint.clear()
    preferences.model.clear()
    preferences.name.setText("Muffin")
    preferences.save()
    assert controller.settings.get("name") == "Muffin"
    assert controller.settings.get("provider") is False
    assert "saved" in preferences.status.text().lower()
    assert companion.history == history
    assert history[0]["content"] in panel.transcript.toPlainText()
    assert cancelled == credentials == []


def test_disabled_ai_allows_empty_connection_and_saving_does_not_clear_chat(controller, monkeypatch):
    panel, companion = controller.panel, controller.companion
    history = [{"role": "assistant", "content": "Still here"}]
    companion.history = history.copy()
    panel.add_message("Biscuit", "Still here")
    preferences = panel.preferences
    preferences.endpoint.clear()
    preferences.model.clear()
    credentials = []
    monkeypatch.setattr(companion, "save_key", lambda *args: credentials.append(args))
    preferences.save_ai()
    preferences.save_ai()
    assert controller.settings.get("endpoint") == controller.settings.get("model") == ""
    assert controller.settings.get("provider") is False
    assert "saved" in preferences.ai_status.text().lower()
    assert credentials == []
    assert companion.history == history
    assert "Still here" in panel.transcript.toPlainText()
    QTest.mouseClick(panel.clear_button, Qt.LeftButton)
    assert companion.history == []
    assert "Still here" not in panel.transcript.toPlainText()


def test_enter_in_ai_field_saves_connection_separately(controller):
    preferences = controller.panel.preferences
    controller.panel.open_preferences()
    preferences.name.setText("Not saved yet")
    preferences.model.setText("new-local-model")
    QTest.keyClick(preferences.model, Qt.Key_Return)
    assert controller.settings.get("model") == "new-local-model"
    assert controller.settings.get("name") == "Biscuit"


def test_bundled_fonts_load_without_network(controller):
    assert QFontInfo(ui_font(16)).family() == "Nunito"
    assert QFontInfo(ui_font(32, 600, heading=True)).family() == "Fredoka"
