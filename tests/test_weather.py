import json
import pytest
from PySide6.QtCore import QObject,Signal
from desktop_pet.services.weather import WeatherService,parse_weather
from desktop_pet.storage import Settings

DATA={'current':{'temperature_2m':29.5,'weather_code':63,'is_day':1},'timezone':'Asia/Manila',
      'daily':{'time':['2026-10-20'],'temperature_2m_min':[24],
               'temperature_2m_max':[30],'precipitation_probability_max':[85]}}

class Client(QObject):
    succeeded=Signal(str,object);failed=Signal(str,str)
    def __init__(self): super().__init__();self.calls=[];self.closed=False
    def request(self,tag,url,**kwargs): self.calls.append((tag,url))
    def cancel(self,tag): pass
    def shutdown(self): self.closed=True


def test_weather_parsing_forecast_attribution_and_available_reaction():
    result=parse_weather(DATA)
    assert result['temperature']==29.5 and result['condition']=='Rain'
    assert result['forecast'][0]['rain']==85
    assert 'umbrella' in result['message'] and result['reaction']=='tail_wag'
    assert 'Open-Meteo' in result['attribution']
    with pytest.raises(ValueError): parse_weather({'current':{'temperature_2m':float('nan'),'weather_code':0}})


def test_weather_opt_in_cache_throttle_and_stale_offline_response(app,tmp_path):
    settings=Settings(tmp_path);client=Client();clock=[10000]
    weather=WeatherService(settings,client=client,clock=lambda:clock[0]);updates=[]
    weather.updated.connect(updates.append)
    weather.refresh();assert not client.calls
    settings.update(weather_enabled=True,weather_latitude=14.6,weather_longitude=121.0)
    weather.refresh();assert len(client.calls)==1
    assert 'latitude=14.6' in client.calls[0][1] and 'longitude=121.0' in client.calls[0][1]
    client.succeeded.emit('weather',DATA)
    assert updates[-1]['cached'] is False
    weather.refresh();weather.refresh(force=True)
    assert len(client.calls)==1 and updates[-1]['cached'] is True
    clock[0]+=1900;weather.refresh()
    client.failed.emit('weather','Offline')
    assert updates[-1]['stale'] is True
    restored=WeatherService(settings,client=Client(),clock=lambda:clock[0]-1800)
    restored.updated.connect(updates.append);restored.refresh()
    assert updates[-1]['cached'] is True and not restored.client.calls
    weather.shutdown();restored.shutdown();assert client.closed


def test_geocoding_requires_explicit_city_and_never_device_location(app,tmp_path):
    client=Client();weather=WeatherService(Settings(tmp_path),client=client)
    places=[];weather.locations.connect(places.append)
    weather.search('x');assert client.calls==[]
    weather.search('Manila')
    assert len(client.calls)==1 and 'name=Manila' in client.calls[0][1]
    client.succeeded.emit('geocode',{'results':[{'name':'Manila','latitude':14.6,'longitude':121}]})
    assert places[0][0]['name']=='Manila'
    weather.shutdown()
