"""Opt-in Open-Meteo weather, manual geocoding, and a persistent bounded cache."""
from datetime import datetime
import json
import math
from pathlib import Path
import time
from urllib.parse import urlencode
from PySide6.QtCore import QObject, Signal, QTimer
from .http import JsonClient

WEATHER_CODES={0:'Clear',1:'Mostly clear',2:'Partly cloudy',3:'Overcast',45:'Fog',48:'Freezing fog',
 51:'Light drizzle',53:'Drizzle',55:'Heavy drizzle',56:'Freezing drizzle',57:'Freezing drizzle',
 61:'Light rain',63:'Rain',65:'Heavy rain',66:'Freezing rain',67:'Freezing rain',
 71:'Light snow',73:'Snow',75:'Heavy snow',77:'Snow grains',80:'Rain showers',81:'Rain showers',
 82:'Heavy showers',85:'Snow showers',86:'Heavy snow showers',95:'Thunderstorm',96:'Thunderstorm with hail',99:'Thunderstorm with hail'}


def parse_weather(data):
    current=data.get('current',{})
    temperature=current.get('temperature_2m'); code=current.get('weather_code')
    if (isinstance(temperature,bool) or not isinstance(temperature,(int,float)) or not math.isfinite(temperature)
            or not isinstance(code,int)):
        raise ValueError('Weather data is incomplete. Please try again later.')
    daily=data.get('daily',{}); forecast=[]
    for i,day in enumerate(daily.get('time',[])[:3]):
        try:
            entry={'date':day,'low':float(daily['temperature_2m_min'][i]),
                   'high':float(daily['temperature_2m_max'][i]),
                   'rain':int(daily['precipitation_probability_max'][i])}
            if not all(math.isfinite(entry[k]) for k in ('low','high','rain')): continue
            forecast.append(entry)
        except (IndexError,KeyError,TypeError,ValueError): continue
    reaction='yawning' if current.get('is_day')==0 else 'sitting' if temperature<15 else 'tail_wag' if code>=51 else 'hopping'
    message=('A sleepy evening outside.' if current.get('is_day')==0 else
             'A cozy day for warm socks.' if temperature<15 else
             'You might want an umbrella.' if code in range(51,68) or code>=80 else
             'A little sunshine for your day.' if code<3 else 'A gentle day outside.')
    return {'temperature':temperature,'condition':WEATHER_CODES.get(code,'Conditions unavailable'),
            'forecast':forecast,'reaction':reaction,'message':message,'timezone':data.get('timezone',''),
            'attribution':'Weather: Open-Meteo · CC BY 4.0'}


class WeatherService(QObject):
    updated=Signal(dict)
    locations=Signal(list)
    status=Signal(str)

    def __init__(self,settings,parent=None,client=None,clock=time.time):
        super().__init__(parent)
        self.settings=settings;self.clock=clock
        self.client=client or JsonClient(self)
        self.client.succeeded.connect(self._received)
        self.client.failed.connect(self._failed)
        self.timer=QTimer(self);self.timer.timeout.connect(self.refresh)
        self.path=Path(settings.directory)/'weather-cache.json'
        self.last_request=-float('inf');self.cache=None;self.last_search=-float('inf')
        try:
            cached=json.loads(self.path.read_text())
            if isinstance(cached,dict): self.cache=cached
        except (OSError,ValueError): pass

    def apply_settings(self):
        self.timer.stop()
        if self.settings.get('weather_enabled'):
            self.timer.start(max(15,int(self.settings.get('weather_interval') or 30))*60000)
            self.refresh()
        else:
            self.client.cancel('weather')
            self.status.emit('Weather is off. Choose a location and enable it in Preferences.')

    def location_key(self):
        return [self.settings.get('weather_latitude'),self.settings.get('weather_longitude')]

    def refresh(self,force=False):
        if not self.settings.get('weather_enabled'):
            self.status.emit('Weather is disabled. Enable it in Preferences.');return
        lat,lon=self.location_key()
        if (not isinstance(lat,(int,float)) or not isinstance(lon,(int,float))
                or not -90<=lat<=90 or not -180<=lon<=180):
            self.status.emit('Choose a location first. Biscuit never locates you automatically.');return
        now=self.clock();ttl=max(15,int(self.settings.get('weather_interval') or 30))*60
        if self.cache and self.cache.get('location')==[lat,lon]:
            age=max(0,now-self.cache.get('at',0))
            if age<ttl and not force:
                try:
                    result=parse_weather(self.cache['data']);result.update(cached=True,age_seconds=age)
                    self.updated.emit(result);return
                except (ValueError,KeyError,TypeError): self.cache=None
        if now-self.last_request<60:
            self.status.emit('Weather refresh is limited to once a minute.');return
        self.last_request=now
        query=urlencode({'latitude':lat,'longitude':lon,'current':'temperature_2m,weather_code,is_day',
            'daily':'temperature_2m_max,temperature_2m_min,precipitation_probability_max',
            'forecast_days':3,'timezone':'auto'})
        self._requested_location=[lat,lon]
        self.client.request('weather','https://api.open-meteo.com/v1/forecast?'+query)
        self.status.emit('Refreshing weather from Open-Meteo…')

    def search(self,city):
        city=city.strip()
        if len(city)<2:
            self.status.emit('Enter a city with at least two characters.');return
        now=self.clock()
        if now-self.last_search<3:
            self.status.emit('Please wait a moment between city searches.');return
        self.last_search=now
        self.client.request('geocode','https://geocoding-api.open-meteo.com/v1/search?'+urlencode({'name':city,'count':5,'language':'en','format':'json'}))

    def _received(self,tag,data):
        if tag=='geocode':
            candidates=[]
            for place in data.get('results',[]) if isinstance(data,dict) else []:
                if isinstance(place,dict) and all(k in place for k in ('name','latitude','longitude')):
                    candidates.append(place)
            self.locations.emit(candidates)
            self.status.emit('Choose a city; no precise location is collected.' if candidates else 'No matching cities found.')
        elif tag=='weather':
            try: result=parse_weather(data)
            except (ValueError,TypeError,AttributeError) as exc:
                self.status.emit(str(exc));return
            if self._requested_location!=self.location_key() or not self.settings.get('weather_enabled'): return
            self.cache={'location':self._requested_location,'at':self.clock(),'data':data}
            try:
                self.path.parent.mkdir(parents=True,exist_ok=True)
                self.path.write_text(json.dumps(self.cache),encoding='utf-8')
            except OSError: pass
            result.update(cached=False,age_seconds=0)
            self.updated.emit(result)
            self.status.emit('Updated · Open-Meteo · CC BY 4.0')

    def _failed(self,tag,message):
        self.status.emit(message)
        if tag=='weather' and self.cache and self.cache.get('location')==self.location_key():
            try:
                result=parse_weather(self.cache['data'])
                result.update(cached=True,stale=True,age_seconds=max(0,self.clock()-self.cache['at']))
                self.updated.emit(result)
            except (ValueError,KeyError,TypeError): pass

    def shutdown(self):
        self.timer.stop();self.client.shutdown()
