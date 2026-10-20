import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from PySide6.QtTest import QTest
from desktop_pet.services.http import JsonClient


def wait(predicate, seconds=6):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert predicate()


@pytest.fixture
def endpoint():
    calls = []
    statuses = [200]

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append((self.path, time.monotonic()))
            status = statuses.pop(0) if len(statuses) > 1 else statuses[0]
            self.send_response(status)
            if status == 302:
                self.send_header("Location", "http://127.0.0.1:1/never-follow")
            self.end_headers()
            data = {"value": "x" * 10000} if self.path == "/large" else {"ok": True}
            try:
                self.wfile.write(json.dumps(data).encode())
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", calls, statuses
    server.shutdown()
    server.server_close()
    thread.join(2)


def test_read_retries_are_exponential_and_bounded(app, endpoint):
    url, calls, statuses = endpoint
    statuses[:] = [503, 503, 200]
    client = JsonClient()
    results = []
    client.succeeded.connect(lambda tag, data: results.append(data))
    client.request("read", url + "/retry")
    wait(lambda: bool(results))
    assert len(calls) == 3
    assert calls[1][1] - calls[0][1] >= 0.8 and calls[2][1] - calls[1][1] >= 1.6
    assert client.pending == {} and not client.timers
    client.shutdown()


def test_replacing_a_request_cancels_its_old_retry_and_shutdown_stops_all(
    app, endpoint
):
    url, calls, statuses = endpoint
    statuses[:] = [503, 200]
    client = JsonClient()
    results = []
    client.succeeded.connect(lambda tag, data: results.append(data))
    client.request("read", url + "/old")
    wait(lambda: bool(client.retry_timers))
    client.request("read", url + "/new", retries=0)
    wait(lambda: bool(results))
    QTest.qWait(1100)
    assert [path for path, _ in calls] == ["/old", "/new"]
    assert not client.retry_timers
    client.shutdown()
    client.request("read", url + "/must-not-start")
    assert len(calls) == 2


def test_redirects_and_large_responses_are_rejected_without_following(app, endpoint):
    url, calls, statuses = endpoint
    statuses[:] = [302]
    client = JsonClient()
    errors = []
    client.failed.connect(lambda tag, text: errors.append(text))
    client.request("read", url + "/redirect", retries=0)
    wait(lambda: bool(errors))
    assert "302" in errors[-1] and len(calls) == 1
    statuses[:] = [200]
    client.MAX_BYTES = 1024
    client.request("large", url + "/large", retries=0)
    wait(lambda: len(errors) == 2)
    assert "too large" in errors[-1]
    client.shutdown()
