"""Provider presets and discovery; models are never installed automatically."""

import shutil
from urllib.parse import urlparse
from PySide6.QtCore import QObject, Signal

PRESETS = {
    "offline": ("Offline — Biscuit responses", "", ""),
    "ollama": ("Ollama — local AI", "http://localhost:11434/v1", ""),
    "groq": ("Groq — cloud AI", "https://api.groq.com/openai/v1", ""),
    "custom": ("Custom OpenAI-compatible", "https://api.openai.com/v1", "gpt-4o-mini"),
}


def provider_id(settings):
    if not settings.get("provider"):
        return "offline"
    selected = settings.get("ai_provider")
    return selected if selected in ("ollama", "groq", "custom") else "custom"


def local_endpoint(endpoint):
    return urlparse(endpoint).hostname in ("localhost", "127.0.0.1", "::1")


class ProviderDiscovery(QObject):
    models_found = Signal(list)
    status = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        from .services.http import JsonClient

        self.client = JsonClient(self)
        self.client.succeeded.connect(self._models)
        self.client.failed.connect(lambda tag, text: self.status.emit(text))

    def discover(self, selected, endpoint, key=""):
        if selected == "offline":
            self.status.emit("Offline replies need no connection.")
            return
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
            "models", endpoint.rstrip("/") + "/models", key=key, retries=0
        )

    def _models(self, tag, data):
        items = data.get("data", []) if isinstance(data, dict) else []
        models = sorted(
            {
                item["id"]
                for item in items
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            }
        )
        self.models_found.emit(models)
        self.status.emit(
            f"Connected · {len(models)} models available."
            if models
            else "Connected, but no models found. Install an Ollama model yourself or enter a supported model ID."
        )

    def shutdown(self):
        self.client.shutdown()
