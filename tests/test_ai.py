import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from PySide6.QtTest import QTest
from desktop_pet.ai import Companion
from desktop_pet.storage import Settings


@pytest.fixture
def provider():
    calls = []
    responses = [{"status": 200, "body": {"choices": [{"message": {"content": "Hello from a test provider!"}}]}}]

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            item = responses[-1]
            body = json.dumps(item["body"]).encode()
            self.send_response(item["status"])
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    yield f"http://127.0.0.1:{server.server_port}/v1", calls, responses
    server.shutdown()
    server.server_close()
    worker.join(2)


def wait_until(predicate, seconds=5):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert predicate(), "Qt request did not finish"


def test_offline_uses_no_provider(app, tmp_path):
    companion = Companion(Settings(tmp_path))
    answers = []
    companion.answered.connect(answers.append)
    companion.send("hello")
    assert len(answers) == 1
    assert companion.reply is None


def test_real_async_request_and_conversation(app, tmp_path, provider):
    endpoint, calls, _ = provider
    settings = Settings(tmp_path)
    settings.update(provider=True, endpoint=endpoint, model="test-model")
    companion = Companion(settings)
    answers, busy = [], []
    companion.answered.connect(answers.append)
    companion.busy_changed.connect(busy.append)
    companion.send("hello")
    wait_until(lambda: len(answers) == 1)
    assert answers == ["Hello from a test provider!"]
    assert busy == [True, False]
    assert calls[0][0] == "/v1/chat/completions"
    assert calls[0][1]["messages"][-1]["content"] == "hello"
    assert len(companion.history) == 2
    companion.send("second")
    wait_until(lambda: len(answers) == 2)
    assert len(calls[1][1]["messages"]) == 4
    companion.clear()
    assert companion.history == []


@pytest.mark.parametrize("status,body,expected", [
    (401, {"error": "private provider text"}, "rejected access"),
    (429, {}, "quota"),
    (200, {"choices": []}, "unsupported chat response"),
    (302, {}, "HTTP 302"),
])
def test_provider_failures_are_reported_without_leaking_bodies(app, tmp_path, provider, status, body, expected):
    endpoint, _, responses = provider
    responses.append({"status": status, "body": body})
    settings = Settings(tmp_path)
    settings.update(provider=True, endpoint=endpoint)
    companion = Companion(settings)
    errors = []
    companion.failed.connect(errors.append)
    companion.send("hello")
    wait_until(lambda: bool(errors))
    assert expected in errors[0]
    assert "private provider text" not in errors[0]
    assert companion.history == []
    assert companion.reply is None


def test_insecure_remote_and_embedded_credentials_rejected(app, tmp_path):
    settings = Settings(tmp_path)
    companion = Companion(settings)
    errors = []
    companion.failed.connect(errors.append)
    for endpoint in ("http://example.com/v1", "https://user:password@example.com/v1"):
        settings.update(provider=True, endpoint=endpoint)
        companion.send("hello")
    assert len(errors) == 2
    assert companion.reply is None


def test_clear_cancels_inflight_conversation(app, tmp_path, provider):
    endpoint, _, _ = provider
    settings = Settings(tmp_path)
    settings.update(provider=True, endpoint=endpoint)
    companion = Companion(settings)
    answers, errors, busy = [], [], []
    companion.answered.connect(answers.append)
    companion.failed.connect(errors.append)
    companion.busy_changed.connect(busy.append)
    companion.send("forget this message")
    assert companion.reply is not None
    companion.clear()
    QTest.qWait(100)
    assert companion.reply is None
    assert companion.history == []
    assert answers == []
    assert errors == []
    assert busy == [True, False]
