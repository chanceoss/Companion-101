"""Provider presets and discovery; models are never installed automatically."""

import shutil
from urllib.parse import urlparse

from PySide6.QtCore import QObject, Signal

from .ai_protocol import (
    AI_HEADERS,
    GROQ_ENDPOINT,
    chat_payload,
    chat_text,
    provider_error,
    validate_connection,
)

PRESETS = {
    "offline": ("Offline — Biscuit responses", "", ""),
    "ollama": ("Ollama — local AI", "http://localhost:11434/v1", ""),
    "groq": ("Groq — cloud AI", GROQ_ENDPOINT, ""),
    "custom": ("Custom OpenAI-compatible", "https://api.openai.com/v1", "gpt-4o-mini"),
}


def provider_id(settings):
    if not settings.get("provider"):
        return "offline"
    selected = settings.get("ai_provider")
    return selected if selected in ("ollama", "groq", "custom") else "custom"


def local_endpoint(endpoint):
    return urlparse(endpoint).hostname in ("localhost", "127.0.0.1", "::1")


def credential_account(selected):
    # Legacy Custom credentials stay compatible; no cross-provider fallback.
    return "api-key" if selected in ("custom", "offline") else "api-key-" + selected


class ProviderDiscovery(QObject):
    models_found = Signal(list)
    status = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        from .services.http import JsonClient

        self.client = JsonClient(self)
        self.client.succeeded.connect(self._received)
        self.client.failed.connect(self._failed)
        self._probe = None

    def cancel(self):
        self.client.cancel("models")
        self.client.cancel("chat-test")
        self._probe = None

    def _failed(self, tag, text):
        self._probe = None
        phase = "Model discovery" if tag == "models" else "Chat test"
        self.status.emit(phase + " · " + text)

    def discover(
        self,
        selected,
        endpoint,
        key="",
        *,
        model="",
        test_chat=False,
        temperature=0.7,
        max_tokens=128,
    ):
        self.cancel()
        if selected == "offline":
            self.status.emit("Offline replies need no connection.")
            return
        endpoint = endpoint.strip().rstrip("/")
        try:
            key = validate_connection(selected, endpoint, key)
        except ValueError as exc:
            self.status.emit(str(exc))
            return
        self._probe = (
            selected,
            endpoint,
            key,
            model.strip(),
            test_chat,
            temperature,
            max_tokens,
        )
        if selected == "ollama":
            installed = bool(shutil.which("ollama"))
            self.status.emit(
                "Ollama executable found; checking the server…"
                if installed
                else "Checking the Ollama server; the executable is not on PATH…"
            )
        else:
            self.status.emit("Checking available models…")
        self.client.request(
            "models",
            endpoint + "/models",
            key=key,
            retries=0,
            headers=AI_HEADERS,
            error_formatter=provider_error,
        )

    def _received(self, tag, data):
        if tag == "chat-test":
            try:
                chat_text(data)
            except ValueError as exc:
                self.status.emit("Chat test · " + str(exc))
            else:
                self.status.emit(
                    "Chat test passed (HTTP 200). A chat reply was received; no conversation history was sent."
                )
            return
        probe, self._probe = self._probe, None
        if probe is None:
            return
        selected, endpoint, key, model, test_chat, temperature, max_tokens = probe
        items = data.get("data") if isinstance(data, dict) else None
        if not isinstance(items, list):
            self.status.emit(
                "Model discovery · HTTP 200: the service returned an unsupported model list. Check the API base URL."
            )
            return
        models = sorted(
            {
                item["id"]
                for item in items
                if isinstance(item, dict)
                and isinstance(item.get("id"), str)
                and 0 < len(item["id"]) <= 200
                and item["id"].isprintable()
            }
        )
        self.models_found.emit(models)
        if model and model not in models:
            self.status.emit(
                "Models received (HTTP 200), but the selected model is not listed for this key. Select a discovered model before testing chat."
            )
        elif not models:
            self.status.emit(
                "Models received (HTTP 200), but none are available. Install an Ollama model yourself or check account permissions."
            )
        elif test_chat and not model:
            self.status.emit(
                "Models received (HTTP 200). Select a discovered model, then repeat the minimal chat test."
            )
        elif test_chat:
            self.status.emit(
                "Models received (HTTP 200); selected model is listed. Testing a minimal chat request…"
            )
            payload = chat_payload(
                selected,
                model,
                [{"role": "user", "content": "Reply with OK."}],
                max_tokens,
                temperature,
            )
            self.client.request(
                "chat-test",
                endpoint + "/chat/completions",
                method="POST",
                data=payload,
                key=key,
                retries=0,
                headers=AI_HEADERS,
                error_formatter=provider_error,
            )
        else:
            self.status.emit(
                f"Models received (HTTP 200) · {len(models)} available. Chat completion has not been tested."
            )

    def shutdown(self):
        self.cancel()
        self.client.shutdown()
