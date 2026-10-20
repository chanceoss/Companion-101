"""Local speech in cancellable subprocesses; Qt playback remains asynchronous."""

from pathlib import Path
import sys
from PySide6.QtCore import QObject, Signal, QTemporaryDir, QUrl


from .worker import ProcessJob as SpeechJob


def speech_python(settings):
    configured = settings.get("voice_python") or ""
    if configured:
        return configured
    return "" if getattr(sys, "frozen", False) else sys.executable


class VoiceService(QObject):
    status = Signal(str)
    speaking = Signal(bool)
    downloaded = Signal(str, str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.player = None
        self.audio = None
        self.directory = QTemporaryDir()
        self.job = SpeechJob(self)
        self.download_job = SpeechJob(self)
        self.job.succeeded.connect(self.play)
        self.job.failed.connect(self._failed)
        self.download_job.failed.connect(self.status)
        self.download_job.succeeded.connect(self._downloaded)
        self._download_kind = ""
        self.session_mute = None

    def is_muted(self):
        return (
            self.settings.get("voice_muted")
            if self.session_mute is None
            else self.session_mute
        )

    def apply_settings(self):
        if self.settings.get("voice_mode") == "text" or self.is_muted():
            self.stop()
        if self.audio:
            self.audio.setVolume((self.settings.get("voice_volume") or 0) / 100)

    def speak(self, text):
        if (
            self.settings.get("voice_mode")
            not in (
                "spoken",
                "ptt",
            )
            or self.is_muted()
        ):
            return
        model = Path(self.settings.get("piper_model") or "")
        if not model.is_file() or model.suffix.lower() != ".onnx":
            self.status.emit(
                "Choose a local Piper .onnx voice in Preferences to hear replies."
            )
            return
        self.stop()
        output = str(Path(self.directory.path()) / "reply.wav")
        self.status.emit("Generating speech locally…")
        self.job.start(
            speech_python(self.settings),
            "speak",
            {
                "model": str(model),
                "text": text,
                "output": output,
                "speed": self.settings.get("voice_speed") or 1,
            },
        )

    def play(self, result):
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

            if self.player is None:
                self.audio = QAudioOutput(self)
                self.player = QMediaPlayer(self)
                self.player.setAudioOutput(self.audio)
                self.player.mediaStatusChanged.connect(self._playback_status)
                self.player.errorOccurred.connect(
                    lambda *_: self._failed(
                        "Audio playback is unavailable. Check the output device."
                    )
                )
            self.audio.setVolume((self.settings.get("voice_volume") or 0) / 100)
            self.player.setSource(QUrl.fromLocalFile(result["path"]))
            self.player.play()
            self.status.emit("Speaking locally…")
            self.speaking.emit(True)
        except (ImportError, KeyError, RuntimeError):
            self._failed("Audio playback is unavailable in this installation.")

    def _playback_status(self, status):
        if status == self.player.EndOfMedia:
            self.status.emit("Ready · local speech")
            self.speaking.emit(False)

    def _failed(self, text):
        self.status.emit(text)
        self.speaking.emit(False)

    def stop(self):
        self.job.cancel()
        if self.player:
            self.player.stop()
            self.player.setSource(QUrl())
        for path in Path(self.directory.path()).glob("*.wav"):
            try:
                path.unlink()
            except OSError:
                pass
        self.speaking.emit(False)

    def download(self, kind, directory, size="tiny"):
        self._download_kind = kind
        self.status.emit(
            "Downloading the approved model. You can cancel in Voice tools."
        )
        self.download_job.start(
            speech_python(self.settings),
            "download_" + kind,
            {"directory": directory, "size": size},
            timeout_ms=600000,
        )

    def _downloaded(self, data):
        self.status.emit(
            "Model downloaded. It is selected locally; save preferences to use it."
        )
        self.downloaded.emit(self._download_kind, data["model"])

    def shutdown(self):
        self.stop()
        self.job.shutdown()
        self.download_job.shutdown()
        if self.player:
            self.player.setSource(QUrl())
        self.directory.remove()
