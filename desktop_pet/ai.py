"""Asynchronous OpenAI-compatible chat. No tools or desktop access."""
import json
from urllib.parse import urlparse
from PySide6.QtCore import QObject, Signal, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from .model import offline_reply


class Companion(QObject):
    answered = Signal(str)
    failed = Signal(str)
    busy_changed = Signal(bool)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.network = QNetworkAccessManager(self)
        self.key = ""
        self.history = []
        self.reply = None
        self.pending = ""

    def load_key(self):
        try:
            import keyring
            self.key = keyring.get_password("BiscuitCompanion", "api-key") or ""
        except Exception:
            self.key = ""

    def save_key(self, key, remember):
        self.key = key.strip()
        try:
            import keyring
            if remember and self.key:
                keyring.set_password("BiscuitCompanion", "api-key", self.key)
            else:
                try:
                    keyring.delete_password("BiscuitCompanion", "api-key")
                except keyring.errors.PasswordDeleteError:
                    pass
        except Exception:
            if remember:
                raise RuntimeError("Secure credential storage is unavailable. Your key works for this session, but was not saved.") from None

    def send(self, message):
        if self.reply is not None:
            return
        if not self.settings.get("provider"):
            self.answered.emit(offline_reply(message, self.settings.get("name")))
            return
        base = self.settings.get("endpoint").strip().rstrip("/")
        parsed = urlparse(base)
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1")):
            self.failed.emit("Use an HTTPS API address, or HTTP for a local model on localhost.")
            return
        if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            self.failed.emit("Enter a base API URL without credentials, query parameters, or fragments.")
            return
        request = QNetworkRequest(QUrl(base + "/chat/completions"))
        request.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")
        request.setAttribute(QNetworkRequest.RedirectPolicyAttribute, QNetworkRequest.ManualRedirectPolicy)
        request.setTransferTimeout(45000)
        if self.key:
            request.setRawHeader(b"Authorization", ("Bearer " + self.key).encode())
        system = {"role": "system", "content": f"You are {self.settings.get('name')}, a friendly little orange desktop pet. Be warm, concise, playful, and helpful. You can chat but cannot see or control the desktop. Never pretend to have performed actions."}
        self.pending = message
        payload = {"model": self.settings.get("model"), "messages": [system] + self.history[-20:] + [{"role": "user", "content": message}], "max_tokens": 400}
        self.busy_changed.emit(True)
        self.reply = self.network.post(request, json.dumps(payload).encode())
        self.reply.finished.connect(self._finished)

    def _finished(self):
        reply, self.reply = self.reply, None
        try:
            status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
            if reply.error() != QNetworkReply.NoError or status != 200:
                # Do not echo provider bodies, URLs, or headers, which can contain secrets.
                reason = "Request timed out or the server could not be reached."
                if status in (401, 403):
                    reason = "The provider rejected access. Check your API key and model permissions."
                elif status == 429:
                    reason = "The provider rate limit or quota was reached. Try again later."
                elif status:
                    reason = f"The provider returned HTTP {status}. Check the base URL and model."
                self.failed.emit(reason)
                return
            data = json.loads(bytes(reply.readAll()))
            text = data["choices"][0]["message"]["content"]
            if not isinstance(text, str) or not text.strip():
                raise ValueError("Empty response")
            self.history.extend([{"role": "user", "content": self.pending}, {"role": "assistant", "content": text}])
            self.history = self.history[-20:]
            self.answered.emit(text[:12000])
        except (ValueError, KeyError, IndexError, TypeError):
            self.failed.emit("The provider returned an unsupported chat response. Use an OpenAI-compatible chat completions API.")
        finally:
            reply.deleteLater()
            self.busy_changed.emit(False)

    def clear(self):
        # A cleared conversation must not reappear when an in-flight reply arrives.
        if self.reply is not None:
            reply, self.reply = self.reply, None
            reply.finished.disconnect(self._finished)
            reply.abort()
            reply.deleteLater()
            self.busy_changed.emit(False)
        self.pending = ""
        self.history.clear()

    def shutdown(self):
        self.clear()
