"""Optional Google access: explicit OAuth, secure tokens, no automatic cloud writes."""

from datetime import datetime, timedelta, timezone
import json
import sqlite3
from pathlib import Path
import sys
import time
from PySide6.QtCore import QObject, Signal, QTimer
from .worker import ProcessJob
from .calendar import normalize_events
from .reminders import local_zone
from ..secrets import get_secret, put_secret, delete_secret


class GoogleServices(QObject):
    status = Signal(str, str)
    connection_changed = Signal(str, bool)
    lists_loaded = Signal(list)
    tasks_loaded = Signal(str, list)
    events_loaded = Signal(list)
    due_event = Signal(dict)
    task_written = Signal(str, dict)

    def __init__(self, settings, store=None, parent=None, job_factory=None):
        super().__init__(parent)
        self.settings = settings
        self.store = store
        factory = job_factory or (lambda: ProcessJob(self, worker="google_worker.py"))
        self.jobs = {kind: factory() for kind in ("calendar", "tasks")}
        self.operations = {}
        self.payloads = {}
        self.tokens = {}
        self.events = []
        self.snapshots = {}
        self.disabled = set()
        self.last_calendar = -float("inf")
        self.calendar_updated_at = None
        self.queued_events = set()
        self.poll = QTimer(self)
        self.poll.timeout.connect(self.refresh_calendar)
        self.notice_timer = QTimer(self)
        self.notice_timer.timeout.connect(self.check_events)
        for kind, job in self.jobs.items():
            job.succeeded.connect(lambda data, key=kind: self._received(key, data))
            job.failed.connect(lambda text, key=kind: self._failed(key, text))

    def python(self):
        return self.settings.get("google_python") or sys.executable

    def credential(self, kind):
        if kind in self.tokens:
            return self.tokens[kind]
        try:
            raw = get_secret("google-" + kind)
            value = json.loads(raw) if raw else None
            if isinstance(value, dict):
                self.tokens[kind] = value
                return value
        except Exception:
            pass
        return None

    def save_credential(self, kind, value):
        try:
            put_secret("google-" + kind, json.dumps(value))
        except Exception:
            raise ValueError(
                "Secure credential storage is unavailable. Google was not connected; no tokens were saved in files."
            ) from None
        self.tokens[kind] = value

    def start(self, kind, operation, **payload):
        if self.jobs[kind].process is not None:
            self.status.emit(
                kind, "An operation is already running. Please wait or disconnect."
            )
            return False
        if operation != "connect" and (
            kind in self.disabled
            or not self.settings.get("google_" + kind + "_enabled")
        ):
            self.status.emit(
                kind, "This Google integration is disabled. Connect/enable it first."
            )
            return False
        credentials = self.credential(kind) if operation != "connect" else None
        if operation != "connect" and not credentials:
            self.status.emit(kind, "Connect this Google integration first.")
            return False
        self.operations[kind] = operation
        self.payloads[kind] = payload
        self.jobs[kind].start(
            self.python(),
            operation,
            dict(
                payload,
                kind=kind,
                **({"credentials": credentials} if credentials else {}),
            ),
            timeout_ms=150000 if operation == "connect" else 90000,
        )
        return True

    def connect_account(self, kind, client_file):
        if kind not in self.jobs:
            raise ValueError("Unknown Google integration.")
        if not Path(client_file).is_file():
            self.status.emit(
                kind, "Choose your Google Desktop OAuth client JSON in Preferences."
            )
            return
        self.status.emit(kind, "Opening explicit Google authorization in your browser…")
        self.start(kind, "connect", client_file=client_file)

    def disconnect(self, kind):
        self.disabled.add(kind)
        self.cancel_operation(kind)
        self.tokens.pop(kind, None)
        try:
            delete_secret("google-" + kind)
        except Exception:
            self.status.emit(
                kind,
                "Disconnected locally; credential removal was unavailable. Remove Biscuit access from your Google account if needed.",
            )
        else:
            self.status.emit(
                kind,
                "Disconnected. Cached local tasks remain; no new Google access occurs.",
            )
        try:
            self.settings.update(**{"google_" + kind + "_enabled": False})
        except OSError:
            self.status.emit(
                kind,
                "Disconnected for this session. Preferences could not be saved; remove the grant in Google account settings if needed.",
            )
        if kind == "calendar":
            self.poll.stop()
            self.notice_timer.stop()
            self.events = []
            self.calendar_updated_at = None
            self.queued_events.clear()
            self.events_loaded.emit([])
        self.connection_changed.emit(kind, False)

    def apply_settings(self):
        self.poll.stop()
        self.notice_timer.stop()
        if (
            not self.settings.get("google_tasks_enabled")
            and self.operations.get("tasks") != "connect"
        ):
            self.cancel_operation("tasks")
        if (
            not self.settings.get("google_calendar_enabled")
            and self.operations.get("calendar") != "connect"
        ):
            self.cancel_operation("calendar")
            self.events = []
            self.calendar_updated_at = None
            self.queued_events.clear()
            self.events_loaded.emit([])
        if (
            self.settings.get("google_calendar_enabled")
            and "calendar" not in self.disabled
        ):
            self.poll.start(300000)
            self.notice_timer.start(30000)
            self.refresh_calendar()

    def refresh_calendar(self):
        if not self.settings.get("google_calendar_enabled"):
            self.status.emit("calendar", "Calendar is off. Connect/enable it first.")
            return
        if time.monotonic() - self.last_calendar < 30:
            self.status.emit(
                "calendar", "Please wait 30 seconds between Calendar refreshes."
            )
            return
        zone = local_zone(self.settings.get("reminder_timezone") or "")
        now = datetime.now(zone)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if self.start(
            "calendar",
            "calendar",
            time_min=start.isoformat(),
            time_max=(start + timedelta(days=7)).isoformat(),
        ):
            self.last_calendar = time.monotonic()

    def load_lists(self):
        if self.settings.get("google_tasks_enabled"):
            self.start("tasks", "task_lists")
        else:
            self.status.emit("tasks", "Connect Google Tasks first.")

    def load_tasks(self, list_id):
        if self.settings.get("google_tasks_enabled"):
            self.start("tasks", "tasks", list_id=list_id)

    def create_task(self, local_id, list_id):
        if not self.store:
            return
        task = self.store.task(local_id)
        if task and task["status"] != "pending":
            self.status.emit(
                "tasks",
                "Only pending local tasks can be uploaded. Completed tasks remain local.",
            )
            return
        if not task or task["external_id"] or task["conflict"]:
            self.status.emit(
                "tasks",
                "This task is already linked or needs conflict resolution. Refresh before writing.",
            )
            return
        self.start(
            "tasks",
            "create_task",
            local_id=local_id,
            list_id=list_id,
            title=task["title"],
            description=task["description"],
            due_at=task["due_at"],
        )

    def complete_task(self, local_id):
        if not self.store:
            return
        task = self.store.task(local_id)
        if not task or not task["external_id"] or task["conflict"]:
            self.status.emit(
                "tasks",
                "Refresh/link this task and resolve conflicts before a cloud write.",
            )
            return
        self.start(
            "tasks",
            "complete_task",
            local_id=local_id,
            list_id=task["list_id"],
            external_id=task["external_id"],
            etag=task["etag"],
        )

    def _received(self, kind, data):
        operation = self.operations.get(kind)
        try:
            if data.get("credentials"):
                self.save_credential(kind, data["credentials"])
            if operation == "connect":
                self.settings.update(**{"google_" + kind + "_enabled": True})
                self.disabled.discard(kind)
                self.connection_changed.emit(kind, True)
                self.status.emit(kind, "Connected securely.")
                if kind == "tasks":
                    self.load_lists()
                else:
                    self.apply_settings()
            elif operation == "task_lists":
                self.lists_loaded.emit(data.get("items", []))
            elif operation == "tasks":
                list_id = data["list_id"]
                items = data.get("items", [])
                self.snapshots[list_id] = items
                if self.store:
                    self.store.merge_tasks(list_id, items)
                self.tasks_loaded.emit(list_id, items)
            elif operation in ("create_task", "complete_task"):
                if self.store:
                    if operation == "complete_task":
                        self.store.complete_task(data["local_id"])
                    self.store.link_task(
                        data["local_id"], data["list_id"], data["task"]
                    )
                self.task_written.emit(data["local_id"], data["task"])
                self.status.emit(
                    kind,
                    "Confirmed cloud write completed. Refresh to see the latest list.",
                )
            elif operation == "calendar":
                self.events = normalize_events(
                    data.get("items", []), self.settings.get("reminder_timezone") or ""
                )
                self.calendar_updated_at = datetime.now(timezone.utc)
                self.events_loaded.emit(self.events)
                self.check_events()
            if data.get("partial"):
                self.status.emit(
                    kind,
                    "Only the first 10 pages were retrieved. Narrow the list/date range.",
                )
        except (ValueError, KeyError, TypeError, OSError, sqlite3.Error) as exc:
            self.status.emit(
                kind,
                str(exc)
                if isinstance(exc, ValueError)
                else "The integration data could not be saved. Local data was preserved.",
            )

    def _failed(self, kind, text):
        operation = self.operations.get(kind)
        payload = self.payloads.get(kind, {})
        if operation == "create_task" and self.store and payload.get("local_id"):
            self.store.mark_task_issue(
                payload["local_id"],
                "Upload outcome unknown. Refresh Google tasks and link an existing task before any retry.",
            )
            self.task_written.emit(payload["local_id"], {})
        self.status.emit(kind, text)
        if "authorization expired" in text.lower():
            self.poll.stop()
            self.notice_timer.stop()

    def check_events(self):
        if (
            not self.store
            or not self.settings.get("calendar_notifications")
            or not self.settings.get("notifications")
        ):
            return
        now = datetime.now(timezone.utc)
        lead = timedelta(minutes=self.settings.get("calendar_reminder_minutes") or 0)
        for event in self.events:
            start = datetime.fromisoformat(event["start"])
            if (
                not event["all_day"]
                and start - lead <= now <= start
                and event["notice_key"] not in self.queued_events
                and not self.store.event_notified(event["notice_key"])
            ):
                self.queued_events.add(event["notice_key"])
                self.due_event.emit(event)

    def cancel_operation(self, kind):
        active = self.jobs[kind].process is not None
        operation = self.operations.get(kind)
        identifier = self.payloads.get(kind, {}).get("local_id")
        if (
            active
            and operation in ("create_task", "complete_task")
            and identifier
            and self.store
        ):
            try:
                self.store.mark_task_issue(
                    identifier,
                    "Cloud write was cancelled; its outcome may be unknown. Refresh before another write, and link an existing task if needed.",
                )
            except sqlite3.Error:
                self.status.emit(
                    kind,
                    "The cancelled write could not be recorded locally. Refresh cloud data before retrying.",
                )
            self.task_written.emit(identifier, {})
        self.jobs[kind].cancel()

    def shutdown(self):
        self.poll.stop()
        self.notice_timer.stop()
        for kind, job in self.jobs.items():
            self.cancel_operation(kind)
            job.shutdown()
        self.tokens.clear()
