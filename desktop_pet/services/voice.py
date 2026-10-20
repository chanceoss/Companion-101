"""Local speech in cancellable subprocesses; Qt playback remains asynchronous."""
import json
from pathlib import Path
import sys
from PySide6.QtCore import QObject,Signal,QProcess,QTimer,QTemporaryDir,QUrl


class SpeechJob(QObject):
    succeeded=Signal(dict)
    failed=Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent)
        self.process=None;self.closed=False
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.timeout)

    def start(self,python,operation,payload,timeout_ms=120000):
        self.cancel()
        if not python or not Path(python).is_file():
            self.failed.emit('Select the Python executable from your optional speech environment.');return
        worker=Path(__file__).resolve().parent.parent/'assets'/'voice_worker.py'
        process=QProcess(self);self.process=process
        process.setProgram(python);process.setArguments([str(worker),operation])
        process.setProcessChannelMode(QProcess.SeparateChannels)
        def started():
            process.write(json.dumps(payload).encode('utf-8'));process.closeWriteChannel()
        def finished(code,status):
            if self.process is not process:return
            self.timer.stop();self.process=None
            body=bytes(process.readAllStandardOutput());process.readAllStandardError();process.deleteLater()
            if self.closed:return
            try:
                response=json.loads(body)
                if code!=0 or not response.get('ok'): raise ValueError()
                self.succeeded.emit(response['result'])
            except (ValueError,KeyError,TypeError):
                text=response.get('error') if isinstance(locals().get('response'),dict) else None
                self.failed.emit(text or 'Speech worker could not finish. Check your optional speech setup.')
        def error(error):
            if error==QProcess.FailedToStart and self.process is process:
                self.timer.stop();self.process=None;process.deleteLater()
                self.failed.emit('The optional speech Python executable could not be started.')
        process.started.connect(started);process.finished.connect(finished);process.errorOccurred.connect(error)
        process.start();self.timer.start(timeout_ms)

    def timeout(self):
        self.cancel();self.failed.emit('Speech processing timed out and was cancelled.')

    def cancel(self):
        self.timer.stop()
        process,self.process=self.process,None
        if process is not None:
            process.kill()
            process.waitForFinished(500)
            process.deleteLater()

    def shutdown(self):
        self.closed=True;self.cancel()


def speech_python(settings):
    configured=settings.get('voice_python') or ''
    if configured:return configured
    return '' if getattr(sys,'frozen',False) else sys.executable


class VoiceService(QObject):
    status=Signal(str)
    speaking=Signal(bool)
    downloaded=Signal(str,str)
    def __init__(self,settings,parent=None):
        super().__init__(parent)
        self.settings=settings;self.player=None;self.audio=None
        self.directory=QTemporaryDir();self.job=SpeechJob(self);self.download_job=SpeechJob(self)
        self.job.succeeded.connect(self.play);self.job.failed.connect(self._failed)
        self.download_job.failed.connect(self.status)
        self.download_job.succeeded.connect(self._downloaded)
        self._download_kind=''

    def apply_settings(self):
        if self.settings.get('voice_mode')=='text' or self.settings.get('voice_muted'):self.stop()
        if self.audio:self.audio.setVolume((self.settings.get('voice_volume') or 0)/100)

    def speak(self,text):
        if self.settings.get('voice_mode') not in ('spoken','ptt') or self.settings.get('voice_muted'):return
        model=Path(self.settings.get('piper_model') or '')
        if not model.is_file() or model.suffix.lower()!='.onnx':
            self.status.emit('Choose a local Piper .onnx voice in Preferences to hear replies.');return
        self.stop()
        output=str(Path(self.directory.path())/'reply.wav')
        self.status.emit('Generating speech locally…')
        self.job.start(speech_python(self.settings),'speak',{'model':str(model),'text':text,'output':output,
                       'speed':self.settings.get('voice_speed') or 1})

    def play(self,result):
        try:
            from PySide6.QtMultimedia import QAudioOutput,QMediaPlayer
            if self.player is None:
                self.audio=QAudioOutput(self);self.player=QMediaPlayer(self)
                self.player.setAudioOutput(self.audio)
                self.player.mediaStatusChanged.connect(self._playback_status)
                self.player.errorOccurred.connect(lambda *_:self._failed('Audio playback is unavailable. Check the output device.'))
            self.audio.setVolume((self.settings.get('voice_volume') or 0)/100)
            self.player.setSource(QUrl.fromLocalFile(result['path']));self.player.play()
            self.status.emit('Speaking locally…');self.speaking.emit(True)
        except (ImportError,KeyError,RuntimeError):self._failed('Audio playback is unavailable in this installation.')

    def _playback_status(self,status):
        if status==self.player.EndOfMedia:
            self.status.emit('Ready · local speech');self.speaking.emit(False)

    def _failed(self,text):
        self.status.emit(text);self.speaking.emit(False)

    def stop(self):
        self.job.cancel()
        if self.player:self.player.stop()
        self.speaking.emit(False)

    def download(self,kind,directory,size='tiny'):
        self._download_kind=kind
        self.status.emit('Downloading the approved model. You can cancel in Voice tools.')
        self.download_job.start(speech_python(self.settings),'download_'+kind,
                               {'directory':directory,'size':size},timeout_ms=600000)

    def _downloaded(self,data):
        self.status.emit('Model downloaded. It is selected locally; save preferences to use it.')
        self.downloaded.emit(self._download_kind,data['model'])

    def shutdown(self):
        self.stop();self.job.shutdown();self.download_job.shutdown()
        if self.player:self.player.setSource(QUrl())
        self.directory.remove()
