"""Cancellable JSON subprocess jobs for optional local libraries and OAuth."""
import json
from pathlib import Path
from PySide6.QtCore import QObject,Signal,QProcess,QTimer


class ProcessJob(QObject):
    succeeded=Signal(dict)
    failed=Signal(str)
    def __init__(self,parent=None,worker="voice_worker.py"):
        super().__init__(parent)
        self.process=None;self.closed=False;self.worker=worker
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.timeout)

    def start(self,python,operation,payload,timeout_ms=120000):
        self.cancel()
        if not python or not Path(python).is_file():
            self.failed.emit('Select the Python executable for this optional integration.');return
        worker=Path(__file__).resolve().parent.parent/'assets'/self.worker
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
                self.failed.emit(text or 'The optional worker could not finish. Check its setup.')
        def error(error):
            if error==QProcess.FailedToStart and self.process is process:
                self.timer.stop();self.process=None;process.deleteLater()
                self.failed.emit('The optional Python executable could not be started.')
        process.started.connect(started);process.finished.connect(finished);process.errorOccurred.connect(error)
        process.start();self.timer.start(timeout_ms)

    def timeout(self):
        self.cancel();self.failed.emit('The background operation timed out and was cancelled.')

    def cancel(self):
        self.timer.stop()
        process,self.process=self.process,None
        if process is not None:
            process.kill()
            process.waitForFinished(500)
            process.deleteLater()

    def shutdown(self):
        self.closed=True;self.cancel()

