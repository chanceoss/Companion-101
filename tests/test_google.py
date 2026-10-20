import json
from types import SimpleNamespace
import sys
import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox
from desktop_pet.services.google import GoogleServices
from desktop_pet.services.reminders import ProductivityStore, ReminderService
from desktop_pet.storage import Settings
from desktop_pet.productivity_widgets import TasksPage
from desktop_pet.assets import google_worker


class Job(QObject):
    succeeded = Signal(dict)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.process = None
        self.calls = []

    def start(self, python, operation, payload, **kwargs):
        self.calls.append((operation, payload))
        self.process = object()

    def finish(self, data):
        self.process = None
        self.succeeded.emit(data)

    def fail(self, text):
        self.process = None
        self.failed.emit(text)

    def cancel(self):
        self.process = None

    def shutdown(self):
        self.cancel()


@pytest.fixture
def connection(app, tmp_path, monkeypatch):
    import keyring

    secrets = {}
    monkeypatch.setattr(
        keyring,
        "set_password",
        lambda service, account, value: secrets.__setitem__(account, value),
    )
    monkeypatch.setattr(
        keyring, "get_password", lambda service, account: secrets.get(account)
    )
    monkeypatch.setattr(
        keyring, "delete_password", lambda service, account: secrets.pop(account, None)
    )
    settings = Settings(tmp_path)
    store = ProductivityStore(tmp_path / "productivity.sqlite3")
    service = GoogleServices(settings, store, job_factory=Job)
    yield settings, store, service, secrets
    service.shutdown()


def test_google_oauth_tokens_are_separate_secure_and_disconnect_blocks_further_access(
    connection, tmp_path
):
    settings, store, service, secrets = connection
    client = tmp_path / "client.json"
    client.write_text("{}")
    service.connect_account("tasks", str(client))
    job = service.jobs["tasks"]
    assert job.calls[-1][0] == "connect"
    token = {
        "token": "private-test-token",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    job.finish({"credentials": token, "connected": True})
    assert "google-tasks" in secrets and "google-calendar" not in secrets
    assert "private-test-token" not in settings.path.read_text()
    assert job.calls[-1][0] == "task_lists"
    job.finish({"items": [{"id": "list", "title": "My tasks"}], "credentials": token})
    service.disconnect("tasks")
    previous = len(job.calls)
    service.tokens["tasks"] = token
    service.load_tasks("list")
    service.start("tasks", "task_lists")
    assert len(job.calls) == previous and not settings.get("google_tasks_enabled")


def test_secure_storage_failure_never_saves_token_to_settings(
    connection, tmp_path, monkeypatch
):
    import keyring

    settings, store, service, secrets = connection
    messages = []
    service.status.connect(lambda kind, text: messages.append(text))
    monkeypatch.setattr(
        keyring,
        "set_password",
        lambda *args: (_ for _ in ()).throw(RuntimeError("No secure backend")),
    )
    client = tmp_path / "client.json"
    client.write_text("{}")
    service.connect_account("calendar", str(client))
    service.jobs["calendar"].finish(
        {"credentials": {"token": "private-test-token"}, "connected": True}
    )
    assert (
        not settings.get("google_calendar_enabled") and "calendar" not in service.tokens
    )
    assert "Secure credential storage" in messages[-1]
    assert not settings.path.exists()


def test_uncertain_cloud_writes_are_not_retried_and_completion_carries_etag(connection):
    settings, store, service, secrets = connection
    settings.update(google_tasks_enabled=True)
    service.tokens["tasks"] = {"token": "test"}
    identifier = store.add_task("Write once")
    service.create_task(identifier, "list")
    job = service.jobs["tasks"]
    assert len(job.calls) == 1
    service.create_task(identifier, "list")
    assert len(job.calls) == 1
    job.fail("Network timeout")
    assert store.task(identifier)["conflict"]
    service.create_task(identifier, "list")
    assert len(job.calls) == 1
    store.link_task(identifier, "list", {"id": "remote", "etag": "version1"})
    service.complete_task(identifier)
    assert (
        job.calls[-1][0] == "complete_task" and job.calls[-1][1]["etag"] == "version1"
    )
    job.finish(
        {
            "local_id": identifier,
            "list_id": "list",
            "task": {"id": "remote", "etag": "version2", "status": "completed"},
        }
    )
    assert store.task(identifier)["status"] == "completed"


def test_cloud_task_ui_does_nothing_when_confirmation_is_declined(
    connection, monkeypatch
):
    settings, store, service, secrets = connection
    reminders = ReminderService(settings)
    page = TasksPage(reminders, service)
    identifier = reminders.store.add_task("Do not upload")
    page.refresh()
    page.items.setCurrentRow(0)
    page.lists.addItem("Cloud list", "list")
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.No)
    page.upload()
    assert service.jobs["tasks"].calls == []
    reminders.shutdown()
    page.deleteLater()


def test_google_worker_uses_etag_no_redirects_and_readonly_calendar_scope(monkeypatch):
    calls = []

    class Credentials:
        expired = False
        refresh_token = None
        valid = True

        @staticmethod
        def from_authorized_user_info(info, scopes):
            calls.append(("scopes", scopes))
            return Credentials()

        def to_json(self):
            return json.dumps({"token_uri": "https://oauth2.googleapis.com/token"})

    class Response:
        status_code = 200

        def iter_content(self, size):
            yield b'{"id":"task","etag":"next","status":"completed"}'

        def close(self):
            pass

    class Session:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, *args, **kwargs):
            calls.append((args, kwargs))
            return Response()

        def close(self):
            pass

    monkeypatch.setitem(
        sys.modules,
        "google.oauth2.credentials",
        SimpleNamespace(Credentials=Credentials),
    )
    monkeypatch.setitem(
        sys.modules,
        "google.auth.transport.requests",
        SimpleNamespace(Request=lambda: None, AuthorizedSession=Session),
    )
    result = google_worker.run(
        "complete_task",
        {
            "kind": "tasks",
            "credentials": {"token_uri": "https://oauth2.googleapis.com/token"},
            "list_id": "list",
            "external_id": "task",
            "etag": "version1",
            "local_id": "local",
        },
    )
    assert result["task"]["status"] == "completed"
    args, kwargs = calls[-1]
    assert args[0] == "PATCH" and kwargs["headers"] == {"If-Match": "version1"}
    assert kwargs["allow_redirects"] is False and kwargs["timeout"] == 20


def test_google_desktop_flow_requests_pkce_and_only_the_selected_scope(
    tmp_path, monkeypatch
):
    calls = []

    class Flow:
        @staticmethod
        def from_client_config(client, scopes, **kwargs):
            calls.append((scopes, kwargs))
            return Flow()

        def run_local_server(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(to_json=lambda: '{"token":"test"}')

    monkeypatch.setitem(
        sys.modules, "google_auth_oauthlib.flow", SimpleNamespace(InstalledAppFlow=Flow)
    )
    client = tmp_path / "client.json"
    client.write_text(
        json.dumps(
            {
                "installed": {
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }
        )
    )
    result = google_worker.run(
        "connect", {"kind": "calendar", "client_file": str(client)}
    )
    assert result["connected"] is True
    assert calls[0] == (
        ["https://www.googleapis.com/auth/calendar.events.readonly"],
        {"autogenerate_code_verifier": True},
    )
    assert (
        calls[1]["host"] == "127.0.0.1"
        and calls[1]["port"] == 0
        and calls[1]["timeout_seconds"] == 120
    )


def test_disconnect_stays_disabled_even_if_preferences_and_credential_removal_fail(
    connection, monkeypatch
):
    import keyring

    settings, store, service, secrets = connection
    settings.update(google_tasks_enabled=True)
    service.tokens["tasks"] = {"token": "test"}
    monkeypatch.setattr(
        settings,
        "update",
        lambda **kwargs: (_ for _ in ()).throw(PermissionError("Read only")),
    )
    monkeypatch.setattr(
        keyring,
        "delete_password",
        lambda *args: (_ for _ in ()).throw(RuntimeError("Unavailable")),
    )
    service.disconnect("tasks")
    service.tokens["tasks"] = {"token": "still present in a failed store"}
    service.start("tasks", "task_lists")
    assert service.jobs["tasks"].calls == [] and "tasks" in service.disabled


def test_cancelling_an_inflight_cloud_create_marks_its_outcome_for_review(connection):
    settings, store, service, secrets = connection
    settings.update(google_tasks_enabled=True)
    service.tokens["tasks"] = {"token": "test"}
    identifier = store.add_task("Possibly created remotely")
    service.create_task(identifier, "list")
    job = service.jobs["tasks"]
    assert job.process is not None
    service.disconnect("tasks")
    assert job.process is None and "cancelled" in store.task(identifier)["conflict"]
    service.disabled.clear()
    settings.update(google_tasks_enabled=True)
    service.tokens["tasks"] = {"token": "test"}
    count = len(job.calls)
    service.create_task(identifier, "list")
    assert len(job.calls) == count


def test_disabling_calendar_cancels_reads_and_clears_cached_events(connection):
    settings, store, service, secrets = connection
    settings.update(google_calendar_enabled=True)
    service.tokens["calendar"] = {"token": "test"}
    service.start(
        "calendar",
        "calendar",
        time_min="2026-10-20T00:00:00Z",
        time_max="2026-10-21T00:00:00Z",
    )
    service.events = [{"title": "Private event"}]
    settings.update(google_calendar_enabled=False)
    service.apply_settings()
    assert service.jobs["calendar"].process is None and service.events == []
    assert not service.poll.isActive()


def test_completed_local_task_is_not_silently_uploaded_as_pending(connection):
    settings, store, service, secrets = connection
    settings.update(google_tasks_enabled=True)
    service.tokens["tasks"] = {"token": "test"}
    identifier = store.add_task("Already done")
    store.complete_task(identifier)
    service.create_task(identifier, "list")
    assert (
        service.jobs["tasks"].calls == []
        and store.task(identifier)["status"] == "completed"
    )
