"""Office group must be explicitly linked by owner, never expose private admin flows."""
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from app.storage import init_db, connect
from app.telegram import handle_update
from app.office_group import _today_text


def _message(uid,chat_id,text,upd):
    return {'update_id':upd,'message':{'chat':{'id':chat_id,'type':'supergroup','title':'PPM STAFF'},'from':{'id':uid,'first_name':'Tester'},'text':text}}


def test_no_role_cannot_link_or_read_group(monkeypatch,tmp_path):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'a.db'))
    monkeypatch.setenv('PPM_BOT_MODE','office')
    monkeypatch.setenv('TELEGRAM_OWNER_USER_IDS','101')
    init_db()
    sent=[]
    async def fake(method,payload):sent.append(payload);return {}
    monkeypatch.setattr('app.telegram.tg',fake)
    asyncio.run(handle_update(_message(202,-1009,'/linkoffice@PPMOfficeBot',1)))
    asyncio.run(handle_update(_message(202,-1009,'/today@PPMOfficeBot',2)))
    assert sent==[]
    with connect() as db:
        # Denied users do not even initiate office-group registration.
        assert db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='office_groups'").fetchone()[0]==0


def test_owner_link_and_team_group_commands(monkeypatch,tmp_path):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'b.db'))
    monkeypatch.setenv('PPM_BOT_MODE','office')
    monkeypatch.setenv('TELEGRAM_OWNER_USER_IDS','101')
    monkeypatch.setenv('TELEGRAM_EDITOR_USER_IDS','303')
    init_db()
    sent=[]
    async def fake(method,payload):sent.append(payload);return {}
    monkeypatch.setattr('app.telegram.tg',fake)
    asyncio.run(handle_update(_message(101,-1009,'/start@PPMOfficeBot',10)))
    assert 'not linked' in sent[-1]['text']
    asyncio.run(handle_update(_message(101,-1009,'/linkoffice@PPMOfficeBot',11)))
    assert 'CONNECTED' in sent[-1]['text']
    asyncio.run(handle_update(_message(303,-1009,'/team@PPMOfficeBot',12)))
    assert 'No additional staff accounts' in sent[-1]['text']
    asyncio.run(handle_update(_message(303,-1009,'/schedule@PPMOfficeBot',13)))
    assert 'No regular Sunday teaching' in sent[-1]['text']
    asyncio.run(handle_update(_message(303,-1009,'/status@PPMOfficeBot',14)))
    assert 'OFF (private test)' in sent[-1]['text']
    asyncio.run(handle_update(_message(303,-1009,'/pending@PPMOfficeBot',15)))
    assert 'No tasks have been recorded' in sent[-1]['text']


def test_sensitive_group_actions_redirect_only(monkeypatch,tmp_path):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'c.db'))
    monkeypatch.setenv('PPM_BOT_MODE','office')
    monkeypatch.setenv('TELEGRAM_OWNER_USER_IDS','101')
    init_db()
    sent=[]
    async def fake(method,payload):sent.append(payload);return {}
    monkeypatch.setattr('app.telegram.tg',fake)
    asyncio.run(handle_update(_message(101,-1009,'/linkoffice',21)))
    asyncio.run(handle_update(_message(101,-1009,'/new@PPMOfficeBot',22)))
    assert 'privately' in sent[-1]['text'].lower()
    with connect() as db:
        assert db.execute('SELECT COUNT(*) FROM admin_sessions').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM drafts').fetchone()[0]==0
    asyncio.run(handle_update(_message(101,-1009,'/start@AnotherBot',23)))
    assert len(sent)==2
    asyncio.run(handle_update(_message(101,-1007777,'/team@PPMOfficeBot',24)))
    assert 'not linked' in sent[-1]['text']


def test_office_group_unlink(monkeypatch,tmp_path):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'d.db'))
    monkeypatch.setenv('PPM_BOT_MODE','office')
    monkeypatch.setenv('TELEGRAM_OWNER_USER_IDS','101')
    init_db()
    sent=[]
    async def fake(method,payload):sent.append(payload);return {}
    monkeypatch.setattr('app.telegram.tg',fake)
    asyncio.run(handle_update(_message(101,-1009,'/linkoffice',31)))
    asyncio.run(handle_update(_message(101,-1009,'/unlinkoffice',32)))
    with connect() as db:
        assert db.execute('SELECT COUNT(*) FROM office_groups').fetchone()[0]==0
    assert 'unlinked' in sent[-1]['text'].lower()


def test_today_has_correct_programs_and_sunday_exception():
    tz=ZoneInfo('America/New_York')
    monday=_today_text(datetime(2026,10,12,13,tzinfo=tz))
    assert '9:00 AM ET' in monday and '6:00–7:00 PM ET' in monday and '7:00–9:00 PM ET' in monday
    sunday=_today_text(datetime(2026,10,18,13,tzinfo=tz))
    assert '6:00–7:00 PM ET' in sunday and '7:00–9:00 PM ET' not in sunday
    oct24=_today_text(datetime(2026,10,24,13,tzinfo=tz))
    assert 'overlaps Watchman Series' in oct24
