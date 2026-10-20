from datetime import date
import random
from PySide6.QtCore import QObject,Signal,Qt
from desktop_pet.services.trivia import TriviaService,question
from desktop_pet.storage import Settings
from desktop_pet.trivia_widgets import TriviaPage

class Client(QObject):
    succeeded=Signal(str,object);failed=Signal(str,str)
    def __init__(self):super().__init__();self.calls=[]
    def request(self,*args,**kwargs):self.calls.append((args,kwargs))
    def cancel(self,*args):pass
    def shutdown(self):pass


def test_trivia_offline_scoring_once_and_persistence(app,tmp_path):
    settings=Settings(tmp_path);client=Client();game=TriviaService(settings,client=client,rng=random.Random(2))
    questions=[];game.ready.connect(questions.append)
    game.next('hard');assert not client.calls and len(questions[0]['answers'])==4
    game.answer(questions[0]['correct']);game.answer(0)
    assert settings.get('trivia_correct')==settings.get('trivia_total')==1
    assert Settings(tmp_path).get('trivia_total')==1
    game.shutdown()


def test_online_trivia_decodes_entities_batches_and_shows_network_fallback(app,tmp_path):
    settings=Settings(tmp_path);settings.update(trivia_enabled=True)
    client=Client();game=TriviaService(settings,client=client,clock=lambda:100)
    questions=[];messages=[];game.ready.connect(questions.append);game.status.connect(messages.append)
    game.next('easy');assert len(client.calls)==1 and client.calls[0][1]['retries']==0
    data={'question':'A &quot;literal&quot; &lt;img src=x&gt; question?',
          'correct_answer':'A &amp; B','incorrect_answers':['C','D','E'],'difficulty':'easy'}
    client.succeeded.emit('trivia',{'response_code':0,'results':[data,data]})
    assert questions[-1]['question']=='A "literal" <img src=x> question?'
    assert 'A & B' in questions[-1]['answers']
    game.next('easy');assert len(client.calls)==1
    game.next('hard');assert len(client.calls)==1 and 'six seconds' in messages[-1]
    client.failed.emit('trivia','Network unavailable')
    assert questions[-1]['source']=='Offline Biscuit trivia' and 'Network unavailable' in messages[-1]
    game.shutdown()


def test_daily_challenge_is_stable_and_cannot_be_scored_twice(app,tmp_path):
    today=lambda:date(2026,10,20)
    settings=Settings(tmp_path);first=TriviaService(settings,client=Client(),today=today)
    seen=[];first.ready.connect(seen.append);first.next('medium',daily=True)
    first.answer(seen[-1]['correct']);identifier=seen[-1]['id']
    second=TriviaService(Settings(tmp_path),client=Client(),today=today);second.ready.connect(seen.append)
    second.next('medium',daily=True)
    assert seen[-1]['id']==identifier and seen[-1]['locked'] is True
    second.answer(seen[-1]['correct']);assert second.settings.get('trivia_total')==1
    first.shutdown();second.shutdown()


def test_trivia_remote_text_is_plain_and_answers_lock_after_a_choice(app,tmp_path):
    game=TriviaService(Settings(tmp_path),client=Client());page=TriviaPage(game)
    parsed=question({'question':'<b>Plain text</b>','correct_answer':'<img src=x>',
        'incorrect_answers':['One','Two','Three']},random.Random(1))
    parsed.update(source='Test',daily=False);game.present(parsed)
    assert page.prompt.textFormat()==Qt.PlainText and page.prompt.text()=='<b>Plain text</b>'
    assert all(label.textFormat()==Qt.PlainText for label in page.labels)
    page.answers[parsed['correct']].click()
    assert all(not button.isEnabled() for button in page.answers)
    game.shutdown();page.deleteLater()
