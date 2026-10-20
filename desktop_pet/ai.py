"""Asynchronous OpenAI-compatible chat. No tools or desktop access."""
import json
from datetime import date
import time
from urllib.parse import urlparse
from PySide6.QtCore import QObject, Signal, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from .model import offline_reply


def validate_endpoint(base):
    try:
        parsed = urlparse(base.strip())
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1")):
            raise ValueError("Use an HTTPS API address, or HTTP for a local model on localhost.")
        if (not parsed.hostname or any(c.isspace() for c in parsed.hostname)
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError("Enter a base API URL without credentials, query parameters, or fragments.")
        _ = parsed.port
    except ValueError as exc:
        raise ValueError(str(exc)) from None


class Companion(QObject):
    answered = Signal(str)
    failed = Signal(str)
    busy_changed = Signal(bool)
    notice = Signal(str)
    fallback_available = Signal(str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.network = QNetworkAccessManager(self)
        self.key = ""
        self.remember_key = False
        self.history = []
        self.reply = None
        self.pending = ""
        self._context_route = settings.get('endpoint').rstrip('/')
        self._context_start = 0
        self._failed_message = ''
        self._cooldown_until = 0
        self._credential_provider = settings.get('ai_provider') or 'custom'

    def credential_account(self):
        return 'api-key' if self._credential_provider in ('custom', 'offline') else 'api-key-' + self._credential_provider

    def select_provider(self, selected):
        if selected != self._credential_provider:
            self._credential_provider = selected
            self.load_key()

    def select_context(self, endpoint, include_previous=False):
        """A destination change starts fresh unless the user opts into sharing."""
        route = endpoint.rstrip('/')
        if route != self._context_route:
            self._context_route = route
            self._context_start = 0 if include_previous else len(self.history)
            if self.history:
                self.notice.emit('Earlier chat will be included with this connection.' if include_previous else
                                 'Earlier chat stays visible; this connection starts with new messages only.')

    def load_key(self):
        try:
            import keyring
            self.key = keyring.get_password("BiscuitCompanion", self.credential_account()) or ""
            self.remember_key = bool(self.key)
        except Exception:
            self.key = ""
            self.remember_key = False

    def save_key(self, key, remember):
        self.key = key.strip()
        self.remember_key = False
        try:
            import keyring
            if remember and self.key:
                keyring.set_password("BiscuitCompanion", self.credential_account(), self.key)
                self.remember_key = True
            else:
                try:
                    keyring.delete_password("BiscuitCompanion", self.credential_account())
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
        if time.monotonic() < self._cooldown_until:
            self._failure('The provider asked us to wait. Please try again shortly.', message)
            return
        try:
            validate_endpoint(base)
        except ValueError as exc:
            self._failure(str(exc), message)
            return
        self.select_context(base)
        from .providers import local_endpoint
        if not local_endpoint(base):
            usage = self.settings.get('ai_usage') or {}
            count = usage.get('count', 0) if usage.get('day') == date.today().isoformat() else 0
            limit = self.settings.get('ai_daily_limit') or 0
            if limit and count >= limit:
                self._failure('Your daily cloud-message limit has been reached. Local/offline chat remains available.', message)
                return
            self.settings.update(ai_usage={'day': date.today().isoformat(), 'count': count + 1})
        request = QNetworkRequest(QUrl(base + "/chat/completions"))
        request.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")
        request.setAttribute(QNetworkRequest.RedirectPolicyAttribute, QNetworkRequest.ManualRedirectPolicy)
        request.setTransferTimeout(45000)
        if self.key:
            request.setRawHeader(b"Authorization", ("Bearer " + self.key).encode())
        system = {"role": "system", "content": f"You are {self.settings.get('name')}, a friendly little orange desktop pet. Be warm, concise, playful, and helpful. You can chat but cannot see or control the desktop. Never pretend to have performed actions."}
        self.pending = message
        payload = {"model": self.settings.get("model"), "messages": [system] + self.history[self._context_start:][-20:] + [{"role": "user", "content": message}],
                   "max_tokens": self.settings.get('ai_max_tokens') or 400,
                   "temperature": self.settings.get('ai_temperature')}
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
                    try:
                        delay = min(300, max(1, int(bytes(reply.rawHeader('Retry-After')) or b'10')))
                    except (ValueError, TypeError):
                        delay = 10
                    self._cooldown_until = time.monotonic() + delay
                elif status == 404:
                    reason = 'The endpoint or model is unavailable. Discover installed/supported models in Preferences.'
                elif status:
                    reason = f"The provider returned HTTP {status}. Check the base URL and model."
                self._failure(reason, self.pending)
                return
            data = json.loads(bytes(reply.readAll()))
            text = data["choices"][0]["message"]["content"]
            if not isinstance(text, str) or not text.strip():
                raise ValueError("Empty response")
            self.history.extend([{"role": "user", "content": self.pending}, {"role": "assistant", "content": text}])
            self._context_start = max(0, self._context_start - max(0, len(self.history) - 20))
            self.history = self.history[-20:]
            self.answered.emit(text[:12000])
        except (ValueError, KeyError, IndexError, TypeError):
            self._failure("The provider returned an unsupported chat response. Use an OpenAI-compatible chat completions API.", self.pending)
        finally:
            reply.deleteLater()
            self.busy_changed.emit(False)

    def _failure(self, text, message):
        self.failed.emit(text)
        self._failed_message = message
        if self.settings.get('ai_fallback'):
            self.retry_offline()
        else:
            self.fallback_available.emit('Use an offline reply, or choose a configured provider in Preferences. Nothing is sent to another provider automatically.')

    def retry_offline(self):
        if self._failed_message:
            message, self._failed_message = self._failed_message, ''
            self.answered.emit('[Offline fallback] ' + offline_reply(message, self.settings.get('name')))

    def cancel_pending(self):
        """Cancel transport without discarding the completed conversation."""
        if self.reply is not None:
            reply, self.reply = self.reply, None
            reply.finished.disconnect(self._finished)
            reply.abort()
            reply.deleteLater()
            self.busy_changed.emit(False)
        self.pending = ""

    def clear(self):
        # A cleared conversation must not reappear when an in-flight reply arrives.
        self.cancel_pending()
        self.history.clear()
        self._context_start = 0
        self._failed_message = ''

    def shutdown(self):
        self.clear()
