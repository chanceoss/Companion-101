"""Opt-in Open Trivia DB questions with local play, daily challenge, and scores."""
from datetime import date
import hashlib
import html
import random
import time
from urllib.parse import urlencode
from PySide6.QtCore import QObject,Signal
from .http import JsonClient

# Original local questions; no network or downloaded dataset is needed.
LOCAL_QUESTIONS=(
 ('Which planet is known as the Red Planet?','Mars',['Venus','Jupiter','Mercury'],'easy'),
 ('How many sides does a hexagon have?','6',['5','7','8'],'easy'),
 ('What is the capital of the Philippines?','Manila',['Cebu City','Davao City','Iloilo City'],'easy'),
 ('Which gas do plants absorb during photosynthesis?','Carbon dioxide',['Oxygen','Nitrogen','Helium'],'easy'),
 ('What is the chemical symbol for gold?','Au',['Ag','Fe','Pb'],'medium'),
 ('What does CPU stand for?','Central processing unit',['Computer power utility','Central program user','Core power unit'],'medium'),
 ('Which ocean is the largest?','Pacific',['Atlantic','Indian','Arctic'],'medium'),
 ('Which number is prime?','29',['21','27','33'],'medium'),
 ('What is the SI unit of electrical resistance?','Ohm',['Volt','Ampere','Watt'],'hard'),
 ('Who wrote the first published algorithm intended for a machine?','Ada Lovelace',['Grace Hopper','Alan Turing','Charles Babbage'],'hard'),
 ('What is the smallest perfect number?','6',['4','8','12'],'hard'),
 ('Which element has atomic number 14?','Silicon',['Aluminium','Phosphorus','Magnesium'],'hard'),
)


def question(data,rng):
    if not isinstance(data,dict) or not isinstance(data.get('question'),str):raise ValueError('Unreadable trivia question.')
    correct=data.get('correct_answer');incorrect=data.get('incorrect_answers')
    if not isinstance(correct,str) or not isinstance(incorrect,list) or len(incorrect)!=3 or not all(isinstance(a,str) for a in incorrect):
        raise ValueError('Unreadable multiple-choice answers.')
    answers=[html.unescape(value)[:500] for value in [correct,*incorrect]]
    if len(set(answers))!=4:raise ValueError('Trivia answers were not distinct.')
    good=answers[0];rng.shuffle(answers)
    prompt=html.unescape(data['question'])[:1500]
    return {'id':hashlib.sha256((prompt+good).encode()).hexdigest(),'question':prompt,
            'answers':answers,'correct':answers.index(good),'difficulty':data.get('difficulty','easy')}


class TriviaService(QObject):
    ready=Signal(dict)
    status=Signal(str)
    scored=Signal(bool,str)
    def __init__(self,settings,parent=None,client=None,rng=None,clock=time.monotonic,today=date.today):
        super().__init__(parent);self.settings=settings;self.client=client or JsonClient(self)
        self.rng=rng or random.Random();self.clock=clock;self.today=today
        self.client.succeeded.connect(self._received);self.client.failed.connect(self._failed)
        self.queue=[];self.current=None;self.answered=False;self.last_request=-float('inf')
        self.requested_difficulty='easy';self.daily=False

    def local(self,difficulty='easy',daily=False):
        source=[q for q in LOCAL_QUESTIONS if q[3]==difficulty] or list(LOCAL_QUESTIONS)
        rng=random.Random(self.today().isoformat()) if daily else self.rng
        prompt,good,bad,level=rng.choice(source)
        result=question({'question':prompt,'correct_answer':good,'incorrect_answers':bad,'difficulty':level},rng)
        result.update(source='Offline daily challenge' if daily else 'Offline Biscuit trivia',daily=daily)
        self.present(result)

    def next(self,difficulty='easy',daily=False):
        if difficulty not in ('easy','medium','hard'):difficulty='easy'
        self.client.cancel('trivia');self.daily=daily
        if daily or not self.settings.get('trivia_enabled'):
            self.local(difficulty,daily);return
        if self.queue and self.queue[0]['difficulty']==difficulty:
            self.present(self.queue.pop(0));return
        if self.clock()-self.last_request<6:
            self.local(difficulty)
            self.status.emit('Online trivia is limited to one batch per six seconds. Here is a local question.');return
        self.last_request=self.clock();self.requested_difficulty=difficulty
        self.status.emit('Getting a small question batch from Open Trivia DB…')
        self.client.request('trivia','https://opentdb.com/api.php?'+urlencode({'amount':5,'type':'multiple','difficulty':difficulty}),retries=0)

    def _received(self,tag,data):
        if tag!='trivia':return
        try:
            if not isinstance(data,dict) or data.get('response_code')!=0:raise ValueError('No questions available.')
            self.queue=[]
            for item in data.get('results',[])[:5]:
                parsed=question(item,self.rng);parsed.update(source='Open Trivia DB · CC BY-SA 4.0',daily=False)
                self.queue.append(parsed)
            if not self.queue:raise ValueError('No questions available.')
            self.present(self.queue.pop(0))
        except (ValueError,KeyError,TypeError):self._failed(tag,'Online trivia was unavailable. Switching to local questions.')

    def _failed(self,tag,message):
        self.local(self.requested_difficulty)
        self.status.emit(message+' · A local question is shown. '+self.score_text())

    def present(self,result):
        self.current=result;self.answered=False
        if result.get('daily') and self.settings.get('trivia_daily_date')==self.today().isoformat():
            self.answered=bool(self.settings.get('trivia_daily_answered'))
        result=dict(result,locked=self.answered,score=self.score_text())
        self.ready.emit(result)

    def answer(self,index):
        if not self.current or self.answered or not isinstance(index,int) or not 0<=index<4:return
        self.answered=True;correct=index==self.current['correct']
        changes={'trivia_total':(self.settings.get('trivia_total') or 0)+1,
                 'trivia_correct':(self.settings.get('trivia_correct') or 0)+int(correct)}
        if self.current.get('daily'):
            changes.update(trivia_daily_date=self.today().isoformat(),trivia_daily_answered=True)
        try:self.settings.update(**changes)
        except OSError:
            self.status.emit('The score could not be saved. You can still play.');return
        answer=self.current['answers'][self.current['correct']]
        text=('Nice one! '+answer+'.' if correct else 'Good try! The answer is '+answer+'.')+' · '+self.score_text()
        self.scored.emit(correct,text)

    def score_text(self):return f"Score: {self.settings.get('trivia_correct') or 0}/{self.settings.get('trivia_total') or 0}"
    def shutdown(self):self.client.shutdown()
