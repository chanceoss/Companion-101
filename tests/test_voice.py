import base64
import sys
from types import SimpleNamespace
import numpy as np
from PySide6.QtCore import Qt,QProcess
from PySide6.QtTest import QTest
from desktop_pet.assets import voice_worker
from desktop_pet.services.voice import VoiceService,SpeechJob
from desktop_pet.services.speech_recognition import SpeechRecognition
from desktop_pet.storage import Settings
from desktop_pet.app import Application


def test_piper_worker_uses_explicit_local_voice_and_speed(tmp_path,monkeypatch):
    model=tmp_path/'voice.onnx';model.write_bytes(b'model');(tmp_path/'voice.onnx.json').write_text('{}')
    calls=[]
    class Voice:
        @staticmethod
        def load(path):calls.append(path);return Voice()
        def synthesize_wav(self,text,wav,syn_config):
            calls.append((text,syn_config.length_scale));wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000);wav.writeframes(b'\0\0'*10)
    monkeypatch.setitem(sys.modules,'piper',SimpleNamespace(PiperVoice=Voice,SynthesisConfig=lambda **kw:SimpleNamespace(**kw)))
    output=tmp_path/'speech.wav'
    result=voice_worker.run('speak',{'model':str(model),'text':'Hello Biscuit','speed':2,'output':str(output)})
    assert result['path']==str(output) and output.is_file()
    assert calls==[str(model),('Hello Biscuit',.5)]


def test_whisper_worker_keeps_audio_in_memory_resamples_and_never_downloads(tmp_path,monkeypatch):
    (tmp_path/'model.bin').write_bytes(b'model');calls=[]
    class Whisper:
        def __init__(self,path,**kwargs):calls.append((path,kwargs))
        def transcribe(self,audio,**kwargs):
            assert isinstance(audio,np.ndarray) and audio.shape==(160,)
            assert np.max(audio)<=1 and kwargs['language']=='tl'
            return iter([SimpleNamespace(text=' Kumusta ')]),None
    monkeypatch.setitem(sys.modules,'faster_whisper',SimpleNamespace(WhisperModel=Whisper))
    raw=np.full((480,2),12000,dtype='<i2').tobytes()
    result=voice_worker.run('transcribe',{'model':str(tmp_path),'audio':base64.b64encode(raw).decode(),
        'rate':48000,'channels':2,'format':'Int16','language':'tl'})
    assert result=={'text':'Kumusta'}
    assert calls[0][1]['local_files_only'] is True
    assert list(tmp_path.iterdir())==[tmp_path/'model.bin']


def test_text_mode_does_not_load_audio_models_or_start_capture(app,tmp_path,monkeypatch):
    settings=Settings(tmp_path);voice=VoiceService(settings);recognition=SpeechRecognition(settings)
    calls=[];status=[]
    monkeypatch.setattr(voice.job,'start',lambda *a,**k:calls.append(a))
    recognition.status.connect(status.append)
    voice.speak('Silent by default');recognition.start()
    assert not calls and recognition.source is None and 'Push-to-talk' in status[-1]
    voice.shutdown();recognition.shutdown()


def test_microphone_denied_is_reported_without_recording(app,tmp_path,monkeypatch):
    (tmp_path/'model.bin').write_bytes(b'model')
    settings=Settings(tmp_path);settings.update(voice_mode='ptt',whisper_model=str(tmp_path))
    recorder=SpeechRecognition(settings);messages=[];recorder.status.connect(messages.append)
    monkeypatch.setattr(app,'checkPermission',lambda permission:Qt.PermissionStatus.Denied)
    recorder.start()
    assert recorder.source is None and 'denied' in messages[-1]
    assert not recorder.timer.isActive()
    recorder.shutdown()


def test_speech_worker_cancellation_ends_process(app):
    job=SpeechJob();process=QProcess();process.start(sys.executable,['-c','import time; time.sleep(30)'])
    assert process.waitForStarted(3000)
    job.process=process;job.timer.start(60000);job.shutdown()
    assert job.process is None and not job.timer.isActive()
    assert process.state()==QProcess.NotRunning


def test_transcription_is_reviewed_without_submitting_and_draft_is_preserved(app,tmp_path):
    controller=Application(app,Settings(tmp_path))
    controller.hello_timer.stop();controller.pet.timer.stop()
    try:
        controller.panel.input.setText('My existing draft.')
        before=controller.panel.transcript.toPlainText()
        controller.recognition.transcribed.emit('Kumusta Biscuit')
        assert controller.panel.input.text()=='My existing draft. Kumusta Biscuit'
        assert controller.panel.transcript.toPlainText()==before
        controller.settings.update(voice_mode='ptt');controller.apply_services()
        controller.panel.resize(480,540);app.processEvents()
        controller.panel.set_voice_status('Transcribing locally…')
        app.processEvents()
        assert controller.panel.width()==480 and controller.panel.height()==540
        assert controller.panel.microphone_button.isVisible()
    finally:
        controller.cleanup();controller.pet.hide();controller.panel.hide()
        for widget in (controller.pet.bubble,controller.pet,controller.panel,controller.menu,controller.tray):widget.deleteLater()
