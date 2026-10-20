"""Explicit, bounded microphone capture in memory and local transcription."""

import base64
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QBuffer, QIODevice, QTimer
from .voice import SpeechJob, speech_python


class SpeechRecognition(QObject):
    status = Signal(str)
    listening = Signal(bool)
    transcribed = Signal(str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.source = None
        self.buffer = None
        self.format = None
        self.job = SpeechJob(self)
        self.job.succeeded.connect(self._transcribed)
        self.job.failed.connect(self.status)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.stop)
        self.last_format = None

    def toggle(self):
        if self.source:
            self.stop()
        else:
            self.start()

    def start(self):
        if self.settings.get("voice_mode") != "ptt":
            self.status.emit(
                "Choose Push-to-talk in Preferences to enable the microphone."
            )
            return
        model = Path(self.settings.get("whisper_model") or "")
        if not model.is_dir() or not (model / "model.bin").is_file():
            self.status.emit(
                "Choose an installed multilingual Faster Whisper model first."
            )
            return
        if self.job.process is not None:
            self.status.emit(
                "Transcription is still running. Cancel it in Voice tools before recording again."
            )
            return
        try:
            from PySide6.QtCore import QCoreApplication, QMicrophonePermission, Qt

            permission = QMicrophonePermission()
            app = QCoreApplication.instance()
            access = app.checkPermission(permission)
            if access == Qt.PermissionStatus.Denied:
                self.status.emit(
                    "Microphone access was denied. Enable it in your system privacy settings."
                )
                return
            if access == Qt.PermissionStatus.Undetermined:
                app.requestPermission(
                    permission,
                    lambda result: (
                        self.start()
                        if result.status() == Qt.PermissionStatus.Granted
                        else self.status.emit("Microphone permission was not granted.")
                    ),
                )
                return
            from PySide6.QtMultimedia import QMediaDevices, QAudioFormat, QAudioSource

            device_id = self.settings.get("microphone_device") or ""
            devices = QMediaDevices.audioInputs()
            device = next(
                (d for d in devices if bytes(d.id()).hex() == device_id),
                QMediaDevices.defaultAudioInput(),
            )
            if device.isNull():
                self.status.emit("No microphone found. Check your input device.")
                return
            audio_format = QAudioFormat()
            audio_format.setSampleRate(16000)
            audio_format.setChannelCount(1)
            audio_format.setSampleFormat(QAudioFormat.Int16)
            if not device.isFormatSupported(audio_format):
                audio_format = device.preferredFormat()
            if audio_format.sampleFormat() not in (
                QAudioFormat.Int16,
                QAudioFormat.Int32,
                QAudioFormat.UInt8,
                QAudioFormat.Float,
            ):
                self.status.emit(
                    "This microphone format is unsupported. Choose another input device."
                )
                return
            self.format = audio_format
            self.buffer = QBuffer(self)
            self.buffer.open(QIODevice.ReadWrite)
            self.buffer.bytesWritten.connect(
                lambda count: (
                    QTimer.singleShot(0, self.stop)
                    if self.buffer and self.buffer.size() > 16 * 1024 * 1024
                    else None
                )
            )
            self.source = QAudioSource(device, audio_format, self)
            self.source.stateChanged.connect(self._device_state)
            self.source.start(self.buffer)
            if self.source is None:
                return
            self.timer.start(60000)
            self.listening.emit(True)
            self.status.emit(
                "Listening · click Stop when done · 60-second limit · not saved"
            )
        except (ImportError, RuntimeError, AttributeError):
            self.cancel()
            self.status.emit(
                "Microphone capture is unavailable. Check permissions and the audio device."
            )

    def _device_state(self, state):
        if self.source:
            from PySide6.QtMultimedia import QAudio

            if self.source.error() != QAudio.NoError:
                self.cancel()
                self.status.emit(
                    "The microphone could not record. Check device access and permissions."
                )

    def stop(self):
        self.timer.stop()
        if self.source is None:
            return
        source, self.source = self.source, None
        source.stop()
        source.deleteLater()
        raw = bytes(self.buffer.data())
        self.buffer.close()
        self.buffer.deleteLater()
        self.buffer = None
        self.listening.emit(False)
        if not raw:
            self.status.emit("No audio captured. Try again.")
            return
        audio_format = self.format
        name = audio_format.sampleFormat().name
        self.status.emit("Transcribing locally… You can edit the result before Send.")
        self.job.start(
            speech_python(self.settings),
            "transcribe",
            {
                "audio": base64.b64encode(raw).decode(),
                "rate": audio_format.sampleRate(),
                "channels": audio_format.channelCount(),
                "format": name,
                "model": self.settings.get("whisper_model"),
                "language": self.settings.get("voice_language") or "",
            },
        )

    def _transcribed(self, result):
        text = result.get("text", "").strip()
        if text:
            self.transcribed.emit(text)
            self.status.emit("Review the text, then press Send.")
        else:
            self.status.emit("No speech recognized. Try again or type your message.")

    def cancel(self):
        self.timer.stop()
        if self.source:
            source, self.source = self.source, None
            source.stop()
            source.deleteLater()
        if self.buffer:
            self.buffer.close()
            self.buffer.deleteLater()
            self.buffer = None
        self.job.cancel()
        self.listening.emit(False)

    def shutdown(self):
        self.cancel()
        self.job.shutdown()
