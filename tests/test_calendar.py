from datetime import datetime,timezone
from desktop_pet.services.calendar import normalize_events,schedule_summary
from desktop_pet.assets.google_worker import SCOPES,validate_client,PublicError
import pytest


def test_calendar_parses_offset_times_all_day_and_never_invents_events():
    events=normalize_events([
        {'id':'1','summary':'Meeting','start':{'dateTime':'2026-10-20T15:00:00+08:00'},'end':{'dateTime':'2026-10-20T16:00:00+08:00'}},
        {'id':'2','summary':'Holiday','start':{'date':'2026-10-20'},'end':{'date':'2026-10-21'}},
        {'id':'3','status':'cancelled','start':{'date':'2026-10-20'}},
        {'id':'bad','start':{}},
    ],'Asia/Manila')
    assert len(events)==2 and events[0]['all_day'] is True
    summary=schedule_summary(events,'Asia/Manila',datetime(2026,10,20,4,tzinfo=timezone.utc))
    assert '2 event(s)' in summary and '03:00 PM' in summary and 'Meeting' in summary
    assert 'no events' in schedule_summary([],'UTC')
    assert SCOPES['calendar']==['https://www.googleapis.com/auth/calendar.events.readonly']
    assert not any('write' in scope for scope in SCOPES['calendar'])


@pytest.mark.parametrize('client',[
    {'web':{}},
    {'installed':{'auth_uri':'http://accounts.google.com/auth','token_uri':'https://oauth2.googleapis.com/token'}},
    {'installed':{'auth_uri':'https://accounts.google.com/auth','token_uri':'https://untrusted.example/token'}},
])
def test_oauth_refuses_non_desktop_or_non_google_authorization_endpoints(client):
    with pytest.raises(PublicError):validate_client(client)
