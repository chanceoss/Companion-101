from datetime import datetime, timedelta, timezone
import sqlite3
import pytest
from desktop_pet.services.reminders import (
    ProductivityStore,
    ReminderService,
    parse_reminder,
    local_to_utc,
    local_zone,
)
from desktop_pet.storage import Settings
from desktop_pet.app import Application

UTC = timezone.utc


def test_deterministic_reminder_parsing_and_dst_rejection():
    now = datetime(2026, 10, 20, 4, tzinfo=UTC)
    title, due, zone = parse_reminder(
        "Remind me to take a break in 30 minutes.", "Asia/Manila", now
    )
    assert (
        title == "take a break"
        and due == now + timedelta(minutes=30)
        and zone == "Asia/Manila"
    )
    assert parse_reminder(
        "Remind me to attend my meeting at 3 PM.", "Asia/Manila", now
    )[1] == datetime(2026, 10, 20, 7, tzinfo=UTC)
    assert parse_reminder("Remind me to sleep tomorrow at 12 AM", "Asia/Manila", now)[
        1
    ] == datetime(2026, 10, 20, 16, tzinfo=UTC)
    with pytest.raises(ValueError, match="does not exist"):
        local_to_utc(datetime(2026, 3, 8, 2, 30), local_zone("America/New_York"))
    with pytest.raises(ValueError, match="occurs twice"):
        local_to_utc(datetime(2026, 11, 1, 1, 30), local_zone("America/New_York"))
    assert parse_reminder("hello", "a bad timezone", now) is None


def test_migrations_persist_reminders_tasks_and_notification_delivery(app, tmp_path):
    settings = Settings(tmp_path)
    now = datetime.now(UTC)
    service = ReminderService(settings, clock=lambda: now)
    store = service.store
    identifier = store.add_reminder(
        "Meeting", now - timedelta(seconds=1), "Asia/Manila", description="Notes"
    )
    task = store.add_task("Write report", "Locally stored", "2026-10-20")
    delivered = []
    service.due_reminder.connect(delivered.append)
    service.check_due()
    service.check_due()
    assert [row["id"] for row in delivered] == [identifier]
    service.acknowledge(identifier)
    service.shutdown()
    restored = ReminderService(settings, clock=lambda: now)
    restored.due_reminder.connect(delivered.append)
    restored.check_due()
    assert len(delivered) == 1 and restored.store.task(task)["title"] == "Write report"
    with restored.store.connection() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
    restored.store.complete_reminder(identifier)
    assert restored.store.reminders() == []
    restored.shutdown()


def test_newer_or_corrupt_database_is_preserved_and_companion_can_continue(
    app, tmp_path
):
    path = tmp_path / "productivity.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version=99")
    before = path.read_bytes()
    service = ReminderService(Settings(tmp_path))
    assert service.store is None and path.read_bytes() == before
    assert "left unchanged" in service.error
    service.shutdown()


def test_local_chat_commands_never_call_cloud_and_focus_defers_notifications(
    app, tmp_path, monkeypatch
):
    controller = Application(app, Settings(tmp_path))
    controller.hello_timer.stop()
    controller.pet.timer.stop()
    sent = []
    monkeypatch.setattr(controller.companion, "send", sent.append)
    try:
        controller.settings.update(reminder_timezone="Asia/Manila")
        controller.handle_message("Remind me to take a break in 30 minutes")
        assert sent == [] and len(controller.reminders.store.reminders()) == 1
        assert "saved locally" in controller.panel.transcript.toPlainText()
        controller.activate_activity("work")
        now = datetime.now(UTC)
        identifier = controller.reminders.store.add_reminder(
            "A due reminder", now - timedelta(seconds=1), "UTC"
        )
        controller.reminders.check_due()
        assert (
            controller._pending_notices
            and identifier not in controller.panel.transcript.toPlainText()
        )
        before = controller.panel.transcript.toPlainText()
        controller.stop_focus()
        assert (
            "A due reminder" in controller.panel.transcript.toPlainText()
            and controller._pending_notices == []
        )
        assert len(controller.reminders.store.due(datetime.now(UTC))) == 0
        controller.handle_message("hello")
        assert sent == ["hello"]
    finally:
        controller.cleanup()
        controller.pet.hide()
        controller.panel.hide()
        for widget in (
            controller.pet.bubble,
            controller.pet,
            controller.panel,
            controller.menu,
            controller.tray,
        ):
            widget.deleteLater()
