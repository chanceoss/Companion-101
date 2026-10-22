"""Windows timezone formats and absent database must not block the desktop UI."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfoNotFoundError

import pytest
from PySide6.QtCore import QByteArray

from desktop_pet import timezones
from desktop_pet.app import Application
from desktop_pet.productivity_widgets import RemindersPage
from desktop_pet.services.reminders import local_to_utc, parse_reminder
from desktop_pet.storage import Settings, normalize_settings


@pytest.mark.parametrize("name,hours", [
    ("UTC", 0), ("Etc/UTC", 0), ("GMT", 0), ("UTC+08:00", 8),
    ("UTC-05:00", -5), ("UTC+05:30", 5.5), ("GMT+05:45", 5.75),
    ("Asia/Manila", 8), ("China Standard Time", 8),
])
def test_formats_resolve_without_changing_time(name, hours):
    zone = timezones.local_zone(name)
    assert datetime(2026, 10, 22, tzinfo=zone).utcoffset() == timedelta(hours=hours)
    assert timezones.local_zone(str(zone)).utcoffset(datetime(2026, 10, 22)) == timedelta(hours=hours)
    assert normalize_settings({"reminder_timezone": name})["reminder_timezone"] == name


@pytest.mark.parametrize("name", ["UTC+24:00", "UTC+08:60", "UTC+08:00:60", "No/Such_Zone", "../UTC"])
def test_invalid_explicit_zones_do_not_silently_become_utc(name):
    with pytest.raises(ValueError, match="Timezone unavailable"):
        timezones.local_zone(name)


def test_windows_mapping_keeps_daylight_saving_rules():
    zone = timezones.local_zone("Eastern Standard Time")
    assert datetime(2026, 1, 1, tzinfo=zone).utcoffset() == timedelta(hours=-5)
    assert datetime(2026, 7, 1, tzinfo=zone).utcoffset() == timedelta(hours=-4)
    with pytest.raises(ValueError, match="occurs twice"):
        local_to_utc(datetime(2026, 11, 1, 1, 30), zone)
    with pytest.raises(ValueError, match="does not exist"):
        local_to_utc(datetime(2026, 3, 8, 2, 30), zone)


def test_fixed_offset_reminders_round_trip():
    now = datetime(2026, 10, 22, 4, tzinfo=timezone.utc)
    _, due, name = parse_reminder("Remind me to stretch at 3 PM", "UTC+08:00", now)
    assert due == datetime(2026, 10, 22, 7, tzinfo=timezone.utc)
    assert due.astimezone(timezones.local_zone(name)).hour == 15


@pytest.mark.parametrize("identifier,missing_data", [
    ("UTC+08:00", False), ("China Standard Time", False),
    ("Unrecognized local timezone", False), ("Asia/Manila", True), ("", False),
])
def test_native_app_starts_even_if_optional_reminder_timezone_unavailable(
    app, tmp_path, monkeypatch, identifier, missing_data
):
    monkeypatch.setattr(timezones.QTimeZone, "systemTimeZoneId", lambda: QByteArray(identifier.encode()))
    if missing_data:
        def absent(_):
            raise ZoneInfoNotFoundError("simulated absent data")
        monkeypatch.setattr(timezones, "ZoneInfo", absent)
        assert timezones.local_zone("UTC") is timezone.utc
        assert timezones.local_zone("UTC+08:00").utcoffset(None) == timedelta(hours=8)
    controller = Application(app, Settings(tmp_path), show_panel=False)
    try:
        controller.hello_timer.stop()
        page = controller.tools.findChild(RemindersPage)
        assert page is not None
        if missing_data or identifier in ("", "Unrecognized local timezone"):
            assert "Timezone unavailable" in page.status.text()
            response = controller.reminders.handle_message("Remind me to stretch in 30 minutes")
            assert "Timezone unavailable" in response
            assert controller.reminders.store.reminders() == []
            assert "Timezone unavailable" in controller.reminders.handle_message("show my tasks")
        else:
            assert timezones.local_zone(page.zone.text()).utcoffset(datetime(2026, 10, 22)) == timedelta(hours=8)
        # Basic preferences, avatar changes and offline chat remain usable.
        preferences = controller.panel.preferences
        preferences.avatar.setCurrentIndex(preferences.avatar.findData("tori"))
        preferences.save()
        assert controller.sprites.avatar == "tori"
        controller.handle_message("hello")
        assert "I’m Tori" in controller.panel.transcript.toPlainText()
    finally:
        controller.cleanup()
        controller.pet.hide()
        controller.panel.hide()
        for widget in (controller.pet.bubble, controller.pet, controller.panel,
                       controller.menu, controller.tray):
            widget.deleteLater()
