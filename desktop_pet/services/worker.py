"""Cancellable JSON subprocess jobs for optional local libraries and OAuth."""

import json
import sys
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QProcess, QTimer


def run_packaged_worker(arguments):
    """Dispatch only bundled helpers, before any desktop window is created."""
    allowed = {
        "google_worker.py": {
            "connect",
            "task_lists",
            "tasks",
            "create_task",
            "complete_task",
            "calendar",
            "protocol_test",
        },
        "voice_worker.py": {
            "speak",
            "transcribe",
            "download_piper",
            "download_whisper",
            "protocol_test",
        },
    }
    if (
        len(arguments) != 2
        or arguments[0] not in allowed
        or arguments[1] not in allowed[arguments[0]]
    ):
        return 2
    if sys.platform == "win32" and (sys.stdin is None or sys.stdout is None):
        import ctypes
        from ctypes import wintypes
        import io
        import msvcrt
        import os

        get_handle = ctypes.windll.kernel32.GetStdHandle
        get_handle.argtypes = [wintypes.DWORD]
        get_handle.restype = wintypes.HANDLE
        for attribute, identifier, flags, mode in (
            ("stdin", -10, os.O_RDONLY, "rb"),
            ("stdout", -11, os.O_WRONLY, "wb"),
        ):
            if getattr(sys, attribute) is None:
                handle = get_handle(identifier & 0xFFFFFFFF)
                if not handle or handle == wintypes.HANDLE(-1).value:
                    return 2
                descriptor = msvcrt.open_osfhandle(handle, flags | os.O_BINARY)
                setattr(
                    sys,
                    attribute,
                    io.TextIOWrapper(os.fdopen(descriptor, mode), encoding="utf-8"),
                )
    if sys.stderr is None:
        import os

        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    import runpy

    worker = Path(__file__).resolve().parent.parent / "assets" / arguments[0]
    sys.argv = [str(worker), arguments[1]]
    runpy.run_path(str(worker), run_name="__main__")
    return 0


class ProcessJob(QObject):
    succeeded = Signal(dict)
    failed = Signal(str)

    def __init__(self, parent=None, worker="voice_worker.py"):
        super().__init__(parent)
        self.process = None
        self.closed = False
        self.worker = worker
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.timeout)

    def start(self, python, operation, payload, timeout_ms=120000):
        if self.closed:
            return
        self.cancel()
        if not python or not Path(python).is_file():
            self.failed.emit(
                "Select the Python executable for this optional integration."
            )
            return
        worker = Path(__file__).resolve().parent.parent / "assets" / self.worker
        process = QProcess(self)
        self.process = process
        process.setProgram(python)
        frozen = (
            getattr(sys, "frozen", False)
            and Path(python).resolve() == Path(sys.executable).resolve()
        )
        process.setArguments(
            ["--integration-worker", self.worker, operation]
            if frozen
            else [str(worker), operation]
        )
        process.setProcessChannelMode(QProcess.SeparateChannels)

        def started():
            process.write(json.dumps(payload).encode("utf-8"))
            process.closeWriteChannel()

        def finished(code, status):
            if self.process is not process:
                return
            self.timer.stop()
            self.process = None
            body = bytes(process.readAllStandardOutput())
            process.readAllStandardError()
            process.deleteLater()
            if self.closed:
                return
            try:
                response = json.loads(body)
                if code != 0 or not response.get("ok"):
                    raise ValueError()
                self.succeeded.emit(response["result"])
            except (ValueError, KeyError, TypeError):
                text = (
                    response.get("error")
                    if isinstance(locals().get("response"), dict)
                    else None
                )
                self.failed.emit(
                    text or "The optional worker could not finish. Check its setup."
                )

        def error(error):
            if error == QProcess.FailedToStart and self.process is process:
                self.timer.stop()
                self.process = None
                process.deleteLater()
                self.failed.emit("The optional Python executable could not be started.")

        process.started.connect(started)
        process.finished.connect(finished)
        process.errorOccurred.connect(error)
        self.timer.start(timeout_ms)
        process.start()

    def timeout(self):
        self.cancel()
        self.failed.emit("The background operation timed out and was cancelled.")

    def cancel(self):
        self.timer.stop()
        process, self.process = self.process, None
        if process is not None:
            process.kill()
            process.waitForFinished(500)
            process.deleteLater()

    def shutdown(self):
        self.closed = True
        self.cancel()
