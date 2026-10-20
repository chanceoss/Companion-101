from datetime import datetime, timezone
import importlib.abc
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from PySide6.QtCore import QPoint
from PySide6.QtTest import QTest
from desktop_pet.app import Application
from desktop_pet.storage import Settings
from desktop_pet.services.weather import parse_weather


@pytest.fixture
def controller(app, tmp_path):
    instance = Application(app, Settings(tmp_path))
    instance.hello_timer.stop()
    instance.pet.timer.stop()
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


def test_weather_system_schedule_commands_never_enter_remote_ai_context(
    controller, monkeypatch
):
    sent = []
    monkeypatch.setattr(controller.companion, "send", sent.append)
    controller.settings.update(
        weather_enabled=True,
        weather_latitude=14.6,
        weather_longitude=121,
        weather_city="Manila",
        system_enabled=True,
        google_calendar_enabled=True,
    )
    weather = parse_weather(
        {"current": {"temperature_2m": 30, "weather_code": 0, "is_day": 1}}
    )
    monkeypatch.setattr(
        controller.weather,
        "refresh",
        lambda: controller.weather.updated.emit(
            dict(weather, cached=True, age_seconds=30)
        ),
    )
    controller.system_monitor.sampler = lambda: {
        "cpu": 12,
        "ram": 34,
        "battery": {"percent": 56, "charging": True},
    }
    controller.handle_message("What's the weather?")
    controller.handle_message("system status")
    controller.google.calendar_updated_at = datetime.now(timezone.utc)
    controller.google.events = [
        {
            "start": datetime.now(timezone.utc).isoformat(),
            "display": "Today · 3 PM",
            "title": "Private meeting",
        }
    ]
    controller.handle_message("What's my schedule today?")
    text = controller.panel.transcript.toPlainText()
    assert "30°C" in text and "CPU: 12%" in text and "Private meeting" in text
    assert sent == [] and controller.companion.history == []


def test_compact_full_status_and_preferences_sections_fit(controller):
    panel = controller.panel
    controller.settings.update(provider=True, voice_mode="ptt")
    controller.apply_services()
    panel.refresh_mode()
    controller.activate_activity("work")
    panel.resize(480, 540)
    panel.set_busy(True)
    panel.set_voice_status(
        "Transcribing locally. You can review and edit the recognized text before sending it."
    )
    panel.offer_fallback("Choose offline replies after a connection failure.")
    QTest.qWait(30)
    assert (panel.width(), panel.height()) == (480, 540)
    for widget in (
        panel.settings_button,
        panel.microphone_button,
        panel.send_button,
        panel.tools_button,
        panel.mute_button,
    ):
        assert widget.isVisible() and panel.rect().contains(
            widget.mapTo(panel, widget.rect().bottomRight())
        )
    preferences = panel.preferences
    preferences.resize(460, 500)
    preferences.show()
    QTest.qWait(20)
    for index in range(preferences.section_nav.count()):
        preferences.section_nav.setCurrentIndex(index)
        QTest.qWait(10)
        assert (preferences.width(), preferences.height()) == (460, 500)
        assert preferences.scroll.horizontalScrollBar().maximum() == 0
        assert preferences.rect().contains(
            preferences.save_button.mapTo(
                preferences, preferences.save_button.rect().bottomRight()
            )
        )
    preferences.hide()


def test_shutdown_stops_services_even_when_position_cannot_be_saved(
    controller, monkeypatch
):
    monkeypatch.setattr(
        controller.settings,
        "update",
        lambda **kwargs: (_ for _ in ()).throw(PermissionError("Read only")),
    )
    controller.cleanup()
    timers = [
        controller.focus_timer,
        controller.hello_timer,
        controller.pet.timer,
        controller.panel.portrait.timer,
        controller.weather.timer,
        controller.system_monitor.timer,
        controller.reminders.timer,
        controller.google.poll,
        controller.google.notice_timer,
        controller.recognition.timer,
    ]
    assert all(not timer.isActive() for timer in timers)
    assert controller.weather.client.closed and controller.trivia.client.closed
    assert controller.voice.job.closed and controller.recognition.job.closed
    controller.apply_services()
    assert all(not timer.isActive() for timer in timers)


def test_worker_dispatch_is_bounded_and_does_not_open_the_desktop(tmp_path):
    root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [
            sys.executable,
            str(root / "run_pet.py"),
            "--integration-worker",
            "voice_worker.py",
            "protocol_test",
        ],
        input="{}",
        capture_output=True,
        text=True,
        timeout=15,
        cwd=root,
    )
    assert result.returncode == 0 and json.loads(result.stdout) == {
        "ok": True,
        "result": {"ready": True},
    }
    bad = subprocess.run(
        [
            sys.executable,
            str(root / "run_pet.py"),
            "--integration-worker",
            "../app.py",
            "protocol_test",
        ],
        capture_output=True,
        timeout=15,
        cwd=root,
    )
    assert bad.returncode == 2


def test_app_starts_when_all_optional_backend_imports_are_unavailable(tmp_path):
    root = Path(__file__).resolve().parent.parent
    code = """import importlib.abc,sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,*args):
        if fullname.split('.')[0] in {'piper','faster_whisper','psutil','google','google_auth_oauthlib','numpy','huggingface_hub'}:
            raise ModuleNotFoundError('Optional backend intentionally unavailable')
sys.meta_path.insert(0,Block())
from desktop_pet.app import main
sys.argv=['biscuit','--smoke-test']
raise SystemExit(main())
"""
    environment = os.environ.copy()
    environment.update(QT_QPA_PLATFORM="offscreen", XDG_DATA_HOME=str(tmp_path))
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr


def test_mute_works_for_the_session_when_preferences_are_read_only(
    controller, monkeypatch
):
    controller.settings.update(voice_mode="spoken")
    monkeypatch.setattr(
        controller.settings,
        "update",
        lambda **kwargs: (_ for _ in ()).throw(PermissionError("Read only")),
    )
    controller.set_muted(True)
    assert controller.voice.is_muted() is True
    assert controller.panel.preferences.features.controls["voice_muted"].isChecked()
    controller.voice.speak("Do not synthesize this")
    assert controller.voice.job.process is None


def test_saving_ai_does_not_apply_unsaved_general_integration_settings(controller):
    preferences = controller.panel.preferences
    preferences.features.controls["system_enabled"].setChecked(True)
    preferences.save_ai()
    assert (
        controller.settings.get("system_enabled") is False
        and not controller.system_monitor.timer.isActive()
    )
