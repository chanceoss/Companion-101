"""Bounded asynchronous JSON transport with explicit endpoints and no redirects."""
import json
from PySide6.QtCore import QObject, Signal, QTimer, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from ..ai import validate_endpoint


class JsonClient(QObject):
    succeeded = Signal(str, object)
    failed = Signal(str, str)
    MAX_BYTES = 2 * 1024 * 1024

    def __init__(self, parent=None):
        super().__init__(parent)
        self.network = QNetworkAccessManager(self)
        self.pending = {}
        self.closed = False
        self.timers = set()
        self.retry_timers = {}

    def request(self, tag, url, *, method='GET', data=None, key='', retries=1):
        if self.closed:
            return
        self.cancel(tag)
        # Query strings are needed for weather/Google APIs, but never credentials.
        parsed = QUrl(url)
        base = QUrl(parsed)
        base.setQuery('')
        base.setFragment('')
        try:
            validate_endpoint(base.toString())
        except ValueError as exc:
            self.failed.emit(tag, str(exc))
            return
        request = QNetworkRequest(parsed)
        request.setHeader(QNetworkRequest.ContentTypeHeader, 'application/json')
        request.setAttribute(QNetworkRequest.RedirectPolicyAttribute, QNetworkRequest.ManualRedirectPolicy)
        request.setTransferTimeout(15000)
        if key:
            request.setRawHeader(b'Authorization', ('Bearer ' + key).encode())
        payload = json.dumps(data).encode() if data is not None else b''
        reply = self.network.sendCustomRequest(request, method.encode(), payload)
        self.pending[tag] = reply
        body = bytearray()
        overflow = [False]

        def read():
            body.extend(bytes(reply.readAll()))
            if len(body) > self.MAX_BYTES:
                overflow[0] = True
                reply.abort()

        def finished():
            if self.pending.get(tag) is not reply:
                return
            self.pending.pop(tag, None)
            read()
            status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
            ok = reply.error() == QNetworkReply.NoError and status is not None and 200 <= status < 300
            reply.deleteLater()
            if self.closed:
                return
            if ok and not overflow[0]:
                try:
                    result = json.loads(body) if body else {}
                except (ValueError, UnicodeError):
                    self.failed.emit(tag, 'The service returned an unreadable response.')
                    return
                self.succeeded.emit(tag, result)
            elif not overflow[0] and method == 'GET' and retries > 0 and (status in (429, 502, 503, 504) or status is None):
                # Only idempotent reads retry, at most once by default.
                timer = QTimer(self)
                timer.setSingleShot(True)
                self.timers.add(timer)
                self.retry_timers[tag] = timer
                def retry():
                    self.timers.discard(timer)
                    self.retry_timers.pop(tag, None)
                    timer.deleteLater()
                    self.request(tag, url, method=method, data=data, key=key, retries=retries - 1)
                timer.timeout.connect(retry)
                timer.start(2000 * (2 ** (1 - min(1, retries))))
            else:
                message = ('The service response was too large.' if overflow[0] else
                           'The service rejected authorization. Reconnect or check the key.' if status in (401, 403) else
                           'The service rate limit was reached. Please wait and try again.' if status == 429 else
                           f'The service returned HTTP {status}.' if status else
                           'The service could not be reached. Check the connection.')
                self.failed.emit(tag, message)
        reply.readyRead.connect(read)
        reply.finished.connect(finished)

    def cancel(self, tag):
        timer = self.retry_timers.pop(tag, None)
        if timer is not None:
            timer.stop()
            self.timers.discard(timer)
            timer.deleteLater()
        reply = self.pending.pop(tag, None)
        if reply is not None:
            reply.finished.disconnect()
            reply.abort()
            reply.deleteLater()

    def shutdown(self):
        self.closed = True
        for timer in self.timers:
            timer.stop()
            timer.deleteLater()
        self.timers.clear()
        self.retry_timers.clear()
        for tag in list(self.pending):
            self.cancel(tag)
