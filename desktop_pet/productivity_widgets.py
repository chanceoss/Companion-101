"""Native on-demand productivity tools with explicit cloud-write confirmations."""

from datetime import datetime, timezone
import sqlite3
from PySide6.QtCore import Qt, QDateTime
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QComboBox,
    QDateTimeEdit,
    QCheckBox,
    QMessageBox,
)
from .services.reminders import local_zone, local_to_utc
from .services.tasks import accept_cloud_copy, link_existing_task


def label(text=""):
    result = QLabel(text)
    result.setTextFormat(Qt.PlainText)
    result.setWordWrap(True)
    return result


def button(text, callback):
    result = QPushButton(text)
    result.clicked.connect(callback)
    result.setAutoDefault(False)
    return result


class RemindersPage(QWidget):
    def __init__(self, service, settings, parent=None):
        super().__init__(parent)
        self.service = service
        self.settings = settings
        rows = QVBoxLayout(self)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.title = QLineEdit()
        self.title.setPlaceholderText("A little thing to remember")
        self.description = QLineEdit()
        self.date = QDateTimeEdit(QDateTime.currentDateTime().addSecs(1800))
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.zone = QLineEdit(settings.get("reminder_timezone") or str(local_zone()))
        self.notify = QCheckBox("Notify when due")
        self.notify.setChecked(True)
        form.addRow("Title", self.title)
        form.addRow("Notes", self.description)
        form.addRow("Local date / time", self.date)
        form.addRow("Timezone", self.zone)
        form.addRow(self.notify)
        rows.addLayout(form)
        rows.addWidget(button("Save local reminder", self.create))
        self.items = QListWidget()
        self.items.setMinimumHeight(90)
        rows.addWidget(self.items, 1)
        actions = QHBoxLayout()
        actions.addWidget(button("Mark selected done", self.complete))
        actions.addWidget(button("Refresh", self.refresh))
        rows.addLayout(actions)
        self.status = label(
            service.error or "Stored on this computer. No cloud AI is needed."
        )
        rows.addWidget(self.status)
        service.changed.connect(self.refresh)
        service.status.connect(self.status.setText)
        self.refresh()

    def create(self):
        try:
            if not self.service.store:
                raise ValueError(self.service.error)
            zone = local_zone(self.zone.text().strip())
            due = local_to_utc(
                self.date.dateTime().toPython().replace(tzinfo=None), zone
            )
            if due <= datetime.now(timezone.utc):
                raise ValueError("Choose a future date and time.")
            self.service.store.add_reminder(
                self.title.text(),
                due,
                str(zone),
                self.description.text(),
                self.notify.isChecked(),
            )
            self.title.clear()
            self.description.clear()
            self.status.setText("Reminder saved locally.")
            self.service.changed.emit()
        except (ValueError, sqlite3.Error, OSError) as exc:
            self.status.setText(
                str(exc)
                if isinstance(exc, ValueError)
                else "Reminder could not be saved. Existing data was preserved."
            )

    def complete(self):
        selected = self.items.currentItem()
        if selected and self.service.store:
            self.service.store.complete_reminder(selected.data(Qt.UserRole))
            self.service.changed.emit()

    def refresh(self):
        self.items.clear()
        if not self.service.store:
            return
        try:
            for value in self.service.store.reminders():
                moment = datetime.fromtimestamp(
                    value["due_at"], timezone.utc
                ).astimezone(local_zone(value["timezone"]))
                item = QListWidgetItem(
                    f"{moment:%Y-%m-%d %H:%M} · {value['title']} ({value['timezone']})"
                )
                item.setData(Qt.UserRole, value["id"])
                self.items.addItem(item)
        except (ValueError, sqlite3.Error):
            self.status.setText(
                "Reminders could not be read. Existing data was preserved."
            )


class TasksPage(QWidget):
    def __init__(self, reminders, google, parent=None):
        super().__init__(parent)
        self.reminders = reminders
        self.store = reminders.store
        self.google = google
        rows = QVBoxLayout(self)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.title = QLineEdit()
        self.description = QLineEdit()
        self.due = QLineEdit()
        self.due.setPlaceholderText("YYYY-MM-DD, optional")
        form.addRow("Task", self.title)
        form.addRow("Notes", self.description)
        form.addRow("Due date", self.due)
        rows.addLayout(form)
        rows.addWidget(button("Create local task", self.create))
        self.items = QListWidget()
        self.items.setMinimumHeight(100)
        rows.addWidget(self.items, 1)
        self.lists = QComboBox()
        self.remote = QComboBox()
        rows.addWidget(self.lists)
        actions = QHBoxLayout()
        actions.addWidget(button("Refresh Google lists", google.load_lists))
        actions.addWidget(button("Read / sync selected list", self.read_list))
        rows.addLayout(actions)
        actions = QHBoxLayout()
        actions.addWidget(button("Upload selected…", self.upload))
        actions.addWidget(button("Mark selected done…", self.complete))
        rows.addLayout(actions)
        rows.addWidget(self.remote)
        actions = QHBoxLayout()
        actions.addWidget(button("Link existing task…", self.link))
        actions.addWidget(button("Use cloud copy…", self.resolve))
        rows.addLayout(actions)
        self.status = label(
            "Local tasks work offline. Google writes always ask first. Google due dates have no time of day."
        )
        rows.addWidget(self.status)
        google.lists_loaded.connect(self.show_lists)
        google.tasks_loaded.connect(self.show_remote)
        google.task_written.connect(lambda *_: self.refresh())
        google.status.connect(
            lambda kind, text: self.status.setText(text) if kind == "tasks" else None
        )
        reminders.changed.connect(self.refresh)
        self.refresh()

    def selected(self):
        item = self.items.currentItem()
        return self.store.task(item.data(Qt.UserRole)) if item and self.store else None

    def create(self):
        try:
            if not self.store:
                raise ValueError(self.reminders.error)
            self.store.add_task(
                self.title.text(),
                self.description.text(),
                self.due.text().strip() or None,
            )
            self.title.clear()
            self.description.clear()
            self.due.clear()
            self.refresh()
        except (ValueError, sqlite3.Error) as exc:
            self.status.setText(
                str(exc)
                if isinstance(exc, ValueError)
                else "Task could not be saved. Data was preserved."
            )

    def refresh(self):
        selected = self.items.currentItem()
        identifier = selected.data(Qt.UserRole) if selected else None
        self.items.clear()
        if not self.store:
            return
        try:
            for task in self.store.tasks():
                marker = "✓ " if task["status"] == "completed" else "• "
                text = (
                    marker
                    + task["title"]
                    + (" · " + task["due_at"][:10] if task["due_at"] else "")
                    + " · "
                    + task["source"]
                )
                if task["conflict"]:
                    text += " · needs review"
                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, task["id"])
                item.setToolTip(task["conflict"] or task["description"])
                self.items.addItem(item)
                if task["id"] == identifier:
                    self.items.setCurrentItem(item)
        except sqlite3.Error:
            self.status.setText("Task data is unavailable; it was left unchanged.")

    def show_lists(self, items):
        self.lists.clear()
        for item in items:
            self.lists.addItem(item.get("title", "Untitled list"), item.get("id"))
        self.status.setText(
            "Choose a Google list and read/sync it. This never uploads or deletes anything."
        )

    def read_list(self):
        if self.lists.currentData():
            self.google.load_tasks(self.lists.currentData())
        else:
            self.status.setText("Connect Google Tasks and load your lists first.")

    def show_remote(self, list_id, items):
        self.remote.clear()
        for item in items:
            self.remote.addItem(item.get("title", "Untitled task"), item)
        self.refresh()
        self.status.setText(
            "Cloud read finished. Local edits/conflicts are preserved; nothing was uploaded."
        )

    def confirm(self, title, text):
        return QMessageBox.question(self, title, text) == QMessageBox.Yes

    def upload(self):
        task = self.selected()
        list_id = self.lists.currentData()
        if not task or not list_id:
            self.status.setText("Select a local task and a Google list first.")
            return
        if self.confirm(
            "Create Google task?",
            f"Upload “{task['title']}”, its notes, and due date to “{self.lists.currentText()}”? This writes to the connected Google Tasks account.",
        ):
            self.google.create_task(task["id"], list_id)

    def complete(self):
        task = self.selected()
        if not task:
            return
        if task["external_id"]:
            if self.confirm(
                "Complete Google task?",
                f"Mark “{task['title']}” completed in the connected Google Tasks account?",
            ):
                self.google.complete_task(task["id"])
        else:
            self.store.complete_task(task["id"])
            self.refresh()

    def link(self):
        task = self.selected()
        remote = self.remote.currentData()
        list_id = self.lists.currentData()
        if not task or not remote or not list_id:
            return
        if self.confirm(
            "Link existing task?",
            f"Link local “{task['title']}” to cloud “{remote.get('title', 'Untitled')}”? This merges a redundant local cache, makes no cloud write, and avoids retrying an uncertain upload.",
        ):
            try:
                link_existing_task(self.store, task["id"], list_id, remote)
                self.refresh()
            except (ValueError, sqlite3.Error) as exc:
                self.status.setText(
                    str(exc)
                    if isinstance(exc, ValueError)
                    else "Could not link; data was preserved."
                )

    def resolve(self):
        task = self.selected()
        if not task:
            return
        remote = next(
            (
                item
                for item in self.google.snapshots.get(task["list_id"], [])
                if item.get("id") == task["external_id"]
            ),
            None,
        )
        if remote is None:
            self.status.setText("Read the matching Google list first.")
            return
        if self.confirm(
            "Use cloud copy locally?",
            f"Replace the local copy of “{task['title']}” with the retrieved cloud version? Local edits to this copy will be discarded; Google is unchanged.",
        ):
            try:
                accept_cloud_copy(self.store, task["id"], remote)
                self.refresh()
            except (ValueError, sqlite3.Error) as exc:
                self.status.setText(
                    str(exc)
                    if isinstance(exc, ValueError)
                    else "Could not resolve; data was preserved."
                )


class GooglePage(QWidget):
    def __init__(self, google, settings, connect_callback, parent=None):
        super().__init__(parent)
        rows = QVBoxLayout(self)
        self.google = google
        self.settings = settings
        rows.addWidget(
            label(
                "Choose your Desktop OAuth client JSON in Preferences. Authorize Tasks and Calendar separately. Calendar access is read-only."
            )
        )
        self.statuses = {}
        for kind, title in (("tasks", "Google Tasks"), ("calendar", "Google Calendar")):
            rows.addWidget(label(title))
            actions = QHBoxLayout()
            actions.addWidget(
                button(
                    "Connect…", lambda checked=False, key=kind: connect_callback(key)
                )
            )
            actions.addWidget(
                button(
                    "Disconnect", lambda checked=False, key=kind: google.disconnect(key)
                )
            )
            rows.addLayout(actions)
            status = label("Off until connected")
            self.statuses[kind] = status
            rows.addWidget(status)
        rows.addWidget(button("Refresh schedule", google.refresh_calendar))
        self.events = QListWidget()
        self.events.setMinimumHeight(120)
        rows.addWidget(self.events, 1)
        self.last_update = label("No calendar information has been retrieved.")
        rows.addWidget(self.last_update)
        google.status.connect(lambda kind, text: self.statuses[kind].setText(text))
        google.events_loaded.connect(self.show_events)
        google.connection_changed.connect(
            lambda kind, on: self.statuses[kind].setText(
                "Connected" if on else "Disconnected"
            )
        )

    def show_events(self, items):
        self.events.clear()
        for item in items:
            self.events.addItem(item["display"] + " · " + item["title"])
        self.last_update.setText(
            "Retrieved from Google Calendar · "
            + datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
            if self.settings.get("google_calendar_enabled")
            else "Disconnected; no calendar information is displayed."
        )
