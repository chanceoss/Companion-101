"""Real Qt HTTP transport against a local fixture, using only dummy credentials."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtTest import QTest

from desktop_pet.ai import Companion
from desktop_pet.ai_protocol import GROQ_ENDPOINT, provider_error
from desktop_pet.preferences import PreferencesDialog
from desktop_pet.providers import ProviderDiscovery
from desktop_pet.storage import Settings

MODEL = "openai/gpt-oss-20b"


def wait(predicate):
    for _ in range(500):
        if predicate():
            return
        QTest.qWait(10)
    assert predicate(), "Qt request did not finish"


@pytest.fixture
def groq_api():
    state = {
        "get_status": 200,
        "get_body": {"data": [{"id": MODEL}]},
        "post_status": 200,
        "post_body": {"choices": [{"message": {"content": "OK"}}]},
    }
    calls, routes = [], []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.respond("get")

        def do_POST(self):
            self.respond("post")

        def respond(self, method):
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length)) if length else None
            calls.append(
                {
                    "method": method,
                    "path": self.path,
                    "payload": payload,
                    "key": self.headers.get("Authorization"),
                    "accept": self.headers.get("Accept"),
                    "agent": self.headers.get("User-Agent"),
                }
            )
            body = json.dumps(state[method + "_body"]).encode()
            self.send_response(state[method + "_status"])
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Retry-After", "2")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()

    class LocalNetwork(QNetworkAccessManager):
        def createRequest(self, operation, request, outgoingData=None):
            routes.append(request.url().toString())
            redirected = QNetworkRequest(request)
            redirected.setUrl(
                QUrl(f"http://127.0.0.1:{server.server_port}" + request.url().path())
            )
            return super().createRequest(operation, redirected, outgoingData)

    yield state, calls, routes, LocalNetwork
    server.shutdown()
    server.server_close()
    worker.join(2)


def chat_client(tmp_path, network):
    settings = Settings(tmp_path)
    settings.update(
        provider=True, ai_provider="groq", endpoint=GROQ_ENDPOINT, model=MODEL
    )
    client = Companion(settings)
    client.key = "dummy-groq-key"
    client.network = network(client)
    return client


@pytest.mark.parametrize("phase", ["chat", "models", "probe"])
@pytest.mark.parametrize(
    "status,code,expected",
    [
        (400, "unsupported_parameter", "Invalid chat request"),
        (401, "invalid_api_key", "Authentication failed"),
        (403, "model_permission_blocked", "Access forbidden"),
        (404, "model_not_found", "selected model is unavailable"),
        (429, "rate_limit_exceeded", "rate limit or quota"),
        (503, "service_unavailable", "service is unavailable"),
    ],
)
def test_http_failures_are_specific_and_never_echo_private_fields(
    app, tmp_path, groq_api, phase, status, code, expected
):
    state, calls, routes, network = groq_api
    prefix = "get" if phase == "models" else "post"
    state.update(
        {
            prefix + "_status": status,
            prefix + "_body": {
                "error": {
                    "code": code,
                    "type": "dummy-groq-key",
                    "param": "temperature",
                    "message": "Bearer dummy-groq-key private conversation",
                }
            },
        }
    )
    errors = []
    if phase == "chat":
        client = chat_client(tmp_path, network)
        client.failed.connect(errors.append)
        client.send("private conversation")
    else:
        client = ProviderDiscovery()
        client.client.network = network(client)
        client.status.connect(errors.append)
        client.discover(
            "groq",
            GROQ_ENDPOINT,
            "dummy-groq-key",
            model=MODEL,
            test_chat=phase == "probe",
        )
    wait(lambda: any(f"HTTP {status}" in message for message in errors))
    error = errors[-1]
    assert expected in error and code in error
    assert "dummy-groq-key" not in error and "private conversation" not in error
    if status == 400:
        assert "Parameter: temperature" in error
    assert len(calls) == (2 if phase == "probe" else 1)
    assert calls[0]["key"] == "Bearer dummy-groq-key"
    assert routes[0].startswith(GROQ_ENDPOINT + "/")
    client.shutdown()


def test_authenticated_models_then_minimal_chat_use_matching_groq_contract(
    app, groq_api
):
    _, calls, routes, network = groq_api
    discovery = ProviderDiscovery()
    discovery.client.network = network(discovery)
    statuses, models = [], []
    discovery.status.connect(statuses.append)
    discovery.models_found.connect(models.append)
    discovery.discover(
        "groq", GROQ_ENDPOINT, "dummy-groq-key", model=MODEL, test_chat=True
    )
    wait(lambda: "Chat test passed" in statuses[-1])
    assert models == [[MODEL]]
    assert routes == [GROQ_ENDPOINT + "/models", GROQ_ENDPOINT + "/chat/completions"]
    assert all(call["key"] == "Bearer dummy-groq-key" for call in calls)
    assert all(call["accept"] == "application/json" for call in calls)
    assert all(call["agent"].startswith("BiscuitCompanion/") for call in calls)
    payload = calls[1]["payload"]
    assert payload == {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Reply with OK."}],
        "max_completion_tokens": 128,
        "temperature": 0.7,
    }
    discovery.shutdown()


def test_model_discovery_alone_does_not_claim_chat_success(app, groq_api):
    _, calls, _, network = groq_api
    discovery = ProviderDiscovery()
    discovery.client.network = network(discovery)
    statuses = []
    discovery.status.connect(statuses.append)
    discovery.discover("groq", GROQ_ENDPOINT, "dummy-groq-key", model=MODEL)
    wait(lambda: "Chat completion has not been tested" in statuses[-1])
    assert len(calls) == 1 and calls[0]["method"] == "get"
    discovery.shutdown()


def test_unlisted_model_blocks_chat_probe(app, groq_api):
    _, calls, _, network = groq_api
    discovery = ProviderDiscovery()
    discovery.client.network = network(discovery)
    statuses = []
    discovery.status.connect(statuses.append)
    discovery.discover(
        "groq",
        GROQ_ENDPOINT,
        "dummy-groq-key",
        model="unavailable-model",
        test_chat=True,
    )
    wait(lambda: "not listed for this key" in statuses[-1])
    assert len(calls) == 1
    discovery.shutdown()


def test_normal_chat_uses_current_parameter_and_preserves_personality(
    app, tmp_path, groq_api
):
    _, calls, _, network = groq_api
    client = chat_client(tmp_path, network)
    answers = []
    client.answered.connect(answers.append)
    client.send("hello")
    wait(lambda: bool(answers))
    payload = calls[0]["payload"]
    assert payload["model"] == MODEL and payload["max_completion_tokens"] == 400
    assert "max_tokens" not in payload
    assert payload["messages"][0]["role"] == "system"
    assert "Biscuit" in payload["messages"][0]["content"]
    assert client.history[-1] == {"role": "assistant", "content": "OK"}
    client.shutdown()


def test_reasoning_token_exhaustion_is_not_misreported_as_authentication(
    app, tmp_path, groq_api
):
    state, _, _, network = groq_api
    state["post_body"] = {
        "choices": [{"message": {"content": None}, "finish_reason": "length"}]
    }
    client = chat_client(tmp_path, network)
    errors = []
    client.failed.connect(errors.append)
    client.send("hello")
    wait(lambda: bool(errors))
    assert "HTTP 200" in errors[0] and "Increase Reply tokens" in errors[0]
    assert client.history == []
    client.shutdown()


@pytest.mark.parametrize(
    "body",
    [
        b"<html>secret-key private prompt</html>",
        json.dumps(
            {
                "error": {
                    "code": "secret-key",
                    "type": "private-prompt",
                    "param": "private prompt",
                    "message": "secret-key",
                }
            }
        ).encode(),
        b'{"error": ["secret-key"]}',
        b"\xffsecret-key",
    ],
)
def test_untrusted_error_fields_are_not_echoed(body):
    message = provider_error(403, body)
    assert "HTTP 403" in message and "Access forbidden" in message
    assert "secret-key" not in message and "private" not in message


def test_switching_through_offline_never_copies_groq_key_into_custom(
    app, tmp_path, monkeypatch
):
    from desktop_pet import ai, preferences

    secrets = {"api-key-groq": "dummy-groq-key", "api-key": "dummy-custom-key"}
    reads = []

    def read(account):
        reads.append(account)
        return secrets.get(account)

    monkeypatch.setattr(ai, "get_secret", read)
    monkeypatch.setattr(preferences, "get_secret", read)
    settings = Settings(tmp_path)
    settings.update(
        provider=True, ai_provider="groq", endpoint=GROQ_ENDPOINT, model=MODEL
    )
    client = Companion(settings)
    client.load_key()
    dialog = PreferencesDialog(settings, client)
    assert (
        client.credential_account() == "api-key-groq" and client.key == "dummy-groq-key"
    )
    dialog.provider.setCurrentIndex(dialog.provider.findData("offline"))
    dialog.save_ai()
    dialog.provider.setCurrentIndex(dialog.provider.findData("custom"))
    assert dialog.key.text() == "dummy-custom-key"
    assert dialog.endpoint.text() == "https://api.openai.com/v1"
    assert reads[-1] == "api-key"
    dialog.provider.setCurrentIndex(dialog.provider.findData("groq"))
    assert dialog.key.text() == "dummy-groq-key"
    dialog.shutdown()
    client.shutdown()
    dialog.deleteLater()


def test_external_provider_switch_reloads_only_its_own_key(
    app, tmp_path, groq_api, monkeypatch
):
    from desktop_pet import ai

    _, calls, _, network = groq_api
    settings = Settings(tmp_path)
    settings.update(provider=True)
    client = Companion(settings)
    client.key = "dummy-custom-key"
    reads = []
    monkeypatch.setattr(
        ai, "get_secret", lambda account: reads.append(account) or "dummy-groq-key"
    )
    settings.update(ai_provider="groq", endpoint=GROQ_ENDPOINT, model=MODEL)
    client.network = network(client)
    answers = []
    client.answered.connect(answers.append)
    client.send("hello")
    wait(lambda: bool(answers))
    assert reads == ["api-key-groq"]
    assert calls[0]["key"] == "Bearer dummy-groq-key"
    client.shutdown()


def test_saved_groq_key_survives_restart_and_is_sent_as_bearer(
    app, tmp_path, groq_api, monkeypatch
):
    from desktop_pet import ai, preferences

    _, calls, _, network = groq_api
    secrets = {"api-key": "dummy-custom-key"}
    monkeypatch.setattr(ai, "get_secret", secrets.get)
    monkeypatch.setattr(preferences, "get_secret", secrets.get)
    monkeypatch.setattr(
        ai, "put_secret", lambda account, value: secrets.update({account: value})
    )
    settings = Settings(tmp_path)
    client = Companion(settings)
    client.load_key()
    dialog = PreferencesDialog(settings, client)
    dialog.provider.setCurrentIndex(dialog.provider.findData("groq"))
    assert dialog.key.text() == ""
    dialog.key.setText("dummy-groq-key")
    dialog.model.setText(MODEL)
    dialog.remember.setChecked(True)
    dialog.save_ai()
    assert secrets == {"api-key": "dummy-custom-key", "api-key-groq": "dummy-groq-key"}
    assert "dummy" not in settings.path.read_text()
    dialog.shutdown()
    client.shutdown()
    dialog.deleteLater()
    restarted = Companion(Settings(tmp_path))
    restarted.load_key()
    restarted.network = network(restarted)
    answers = []
    restarted.answered.connect(answers.append)
    restarted.send("hello")
    wait(lambda: bool(answers))
    assert calls[0]["key"] == "Bearer dummy-groq-key"
    restarted.shutdown()


def test_unavailable_groq_key_never_falls_back_to_custom(app, tmp_path, monkeypatch):
    from desktop_pet import ai

    settings = Settings(tmp_path)
    settings.update(
        provider=True, ai_provider="groq", endpoint=GROQ_ENDPOINT, model=MODEL
    )
    accounts = []
    monkeypatch.setattr(
        ai, "get_secret", lambda account: accounts.append(account) or None
    )
    client = Companion(settings)
    client.load_key()
    errors = []
    client.failed.connect(errors.append)
    client.send("hello")
    assert accounts == ["api-key-groq"]
    assert client.reply is None and "No Groq API key is loaded" in errors[0]
    client.shutdown()


def test_probe_is_cancelled_when_provider_changes(app, tmp_path, groq_api):
    _, _, _, network = groq_api
    client = chat_client(tmp_path, network)
    dialog = PreferencesDialog(client.settings, client)
    dialog.discovery.client.network = network(dialog.discovery)
    dialog.test_chat.setChecked(True)
    dialog.test_connection()
    dialog.provider.setCurrentIndex(dialog.provider.findData("offline"))
    QTest.qWait(50)
    assert dialog.discovery.client.pending == {}
    assert dialog.discovery._probe is None
    assert dialog.ai_status.text() == "Offline · no AI requests."
    assert dialog.model_choices.count() == 0
    dialog.shutdown()
    client.shutdown()
    dialog.deleteLater()


@pytest.mark.parametrize(
    "endpoint,key",
    [
        ("https://api.groq.com", "dummy-groq-key"),
        (GROQ_ENDPOINT, ""),
        (GROQ_ENDPOINT, "Bearer dummy-key"),
        (GROQ_ENDPOINT, "dummy\r\nkey"),
    ],
)
def test_invalid_groq_configuration_is_blocked_before_network(
    app, tmp_path, groq_api, endpoint, key
):
    _, calls, _, network = groq_api
    client = chat_client(tmp_path, network)
    client.settings.update(endpoint=endpoint)
    client.key = key
    errors = []
    client.failed.connect(errors.append)
    client.send("hello")
    assert errors and client.reply is None and calls == []
    assert "dummy" not in errors[0]
    client.shutdown()


def test_preferences_chat_test_is_explicit_and_does_not_send_history(
    app, tmp_path, groq_api
):
    _, calls, _, network = groq_api
    client = chat_client(tmp_path, network)
    client.history = [{"role": "user", "content": "private earlier chat"}]
    dialog = PreferencesDialog(client.settings, client)
    dialog.discovery.client.network = network(dialog.discovery)
    assert dialog.test_chat.isChecked() is False
    dialog.test_chat.setChecked(True)
    dialog.test_connection()
    wait(lambda: "Chat test passed" in dialog.ai_status.text())
    assert "private earlier chat" not in json.dumps(calls)
    assert calls[1]["payload"]["max_completion_tokens"] == dialog.max_tokens.value()
    assert client.history == [{"role": "user", "content": "private earlier chat"}]
    dialog.shutdown()
    client.shutdown()
    dialog.deleteLater()


def test_changed_host_blocks_discovery_with_saved_key(app, tmp_path, monkeypatch):
    client = Companion(Settings(tmp_path))
    client.key = "dummy-custom-key"
    dialog = PreferencesDialog(client.settings, client)
    dialog.provider.setCurrentIndex(dialog.provider.findData("custom"))
    dialog.endpoint.setText("https://different.test/v1")
    calls = []
    monkeypatch.setattr(
        dialog.discovery, "discover", lambda *args, **kwargs: calls.append(args)
    )
    dialog.test_connection()
    assert calls == [] and "host changed" in dialog.ai_status.text()
    dialog.shutdown()
    client.shutdown()
    dialog.deleteLater()
