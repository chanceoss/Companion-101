import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from PySide6.QtTest import QTest
from desktop_pet.ai import Companion
from desktop_pet.providers import ProviderDiscovery
from desktop_pet.preferences import PreferencesDialog
from desktop_pet.storage import Settings


def wait(predicate):
    for _ in range(300):
        if predicate():
            return
        QTest.qWait(10)
    assert predicate()


@pytest.fixture
def api():
    calls=[]
    response={'status':200,'body':{'choices':[{'message':{'content':'A local test reply'}}]}}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append(('GET',self.path,None))
            self.respond(200,{'data':[{'id':'local-small'},{'id':'local-large'}]})
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append(('POST',self.path,body))
            self.respond(response['status'],response['body'])
        def respond(self,status,data):
            self.send_response(status)
            self.send_header('Content-Type','application/json')
            self.end_headers()
            try: self.wfile.write(json.dumps(data).encode())
            except (BrokenPipeError,ConnectionResetError): pass
        def log_message(self,*args): pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    yield f'http://127.0.0.1:{server.server_port}/v1',calls,response
    server.shutdown();server.server_close();worker.join(2)


def test_ollama_model_discovery_uses_openai_api_without_downloading(app, api):
    endpoint,calls,_=api
    discovery=ProviderDiscovery()
    found=[]; discovery.models_found.connect(found.append)
    discovery.discover('ollama',endpoint)
    wait(lambda:bool(found))
    assert found==[['local-large','local-small']]
    assert calls==[('GET','/v1/models',None)]
    discovery.shutdown()


@pytest.mark.parametrize('share',[False,True])
def test_switching_endpoints_retains_visible_history_and_requires_opt_in_to_send_it(app,tmp_path,api,share):
    endpoint,calls,_=api
    settings=Settings(tmp_path)
    settings.update(provider=True,endpoint='http://localhost:1234/v1')
    companion=Companion(settings)
    previous=[{'role':'user','content':'Private earlier context'},{'role':'assistant','content':'Earlier answer'}]
    companion.history=previous.copy()
    companion.select_context(endpoint,share)
    settings.update(endpoint=endpoint)
    replies=[];companion.answered.connect(replies.append)
    companion.send('A new message')
    wait(lambda:bool(replies))
    payload=calls[-1][2]
    assert ('Private earlier context' in json.dumps(payload)) is share
    assert companion.history[:2]==previous
    companion.shutdown()


def test_external_settings_change_never_silently_shares_context(app,tmp_path,api):
    endpoint,calls,_=api
    settings=Settings(tmp_path);settings.update(provider=True)
    companion=Companion(settings)
    companion.history=[{'role':'assistant','content':'Do not transfer this'}]
    settings.update(endpoint=endpoint)
    answers=[];companion.answered.connect(answers.append)
    companion.send('Hello')
    wait(lambda:bool(answers))
    assert 'Do not transfer this' not in json.dumps(calls[-1][2])
    companion.shutdown()


def test_rate_limit_offline_fallback_does_not_retry_or_send_elsewhere(app,tmp_path,api):
    endpoint,calls,response=api
    response.update(status=429,body={'secret':'never display'})
    settings=Settings(tmp_path);settings.update(provider=True,endpoint=endpoint,ai_fallback=True)
    companion=Companion(settings)
    answers=[];failures=[]
    companion.answered.connect(answers.append);companion.failed.connect(failures.append)
    companion.send('Hello')
    wait(lambda:bool(answers))
    assert answers[0].startswith('[Offline fallback]')
    assert 'quota' in failures[0] and 'secret' not in failures[0]
    assert len(calls)==1 and companion.history==[]
    companion.send('Again')
    assert len(calls)==1
    companion.shutdown()


def test_provider_preferences_keep_profiles_and_separate_keyring_accounts(app,tmp_path,monkeypatch):
    import keyring
    secrets={};writes=[]
    monkeypatch.setattr(keyring,'get_password',lambda service,account:secrets.get(account))
    def store(service,account,key):
        secrets[account]=key;writes.append(account)
    monkeypatch.setattr(keyring,'set_password',store)
    settings=Settings(tmp_path);companion=Companion(settings)
    dialog=PreferencesDialog(settings,companion)
    dialog.provider.setCurrentIndex(dialog.provider.findData('groq'))
    dialog.model.setText('chosen-groq-model');dialog.key.setText('not-a-real-key')
    dialog.remember.setChecked(True);dialog.save_ai()
    assert settings.get('ai_provider')=='groq'
    assert writes==['api-key-groq']
    assert 'not-a-real-key' not in settings.path.read_text()
    dialog.provider.setCurrentIndex(dialog.provider.findData('ollama'))
    assert dialog.endpoint.text()=='http://localhost:11434/v1'
    assert dialog.key.text()==''
    dialog.model.setText('installed-local-model');dialog.save_ai()
    assert settings.get('provider_profiles')['groq']['model']=='chosen-groq-model'
    assert settings.get('ai_provider')=='ollama'
    dialog.shutdown();companion.shutdown();dialog.deleteLater()
