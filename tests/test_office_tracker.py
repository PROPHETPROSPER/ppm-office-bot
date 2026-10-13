"""Office staff/assignment state and authorization tests; nothing sent to Telegram."""
import asyncio
from datetime import datetime,date
from zoneinfo import ZoneInfo
import pytest
from app.storage import connect,init_db
from app.office_tracker import request_access,add_staff,remove_staff,staff_role,seed_day,create_assignment,list_tasks,update_task,requests_text
from app.office_group import _today_text
from app.roles import role_for,can
from app.telegram import handle_update

@pytest.fixture(autouse=True)
def db_env(tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'office.db'))
    monkeypatch.setenv('PPM_BOT_MODE','office')
    monkeypatch.setenv('TELEGRAM_OWNER_USER_IDS','101')
    monkeypatch.delenv('TELEGRAM_EDITOR_USER_IDS',raising=False)
    init_db()


def test_requests_and_approval_no_implicit_publishing():
    assert role_for(202)=='none'
    assert 'recorded' in request_access({'id':202,'first_name':'Michelle','username':'michelleppm'},-10088)
    assert 'Michelle' in requests_text()
    assert role_for(202)=='none'
    assert 'approved' in add_staff(101,202,'coordinator')
    assert role_for(202)=='coordinator'
    assert not can(202,'draft') and not can(202,'approve') and not can(202,'send')
    assert 'revoked' in remove_staff(101,202)
    assert role_for(202)=='none'


def test_assignment_lifecycle_and_reassign():
    request_access({'id':202,'first_name':'Michelle','username':'michelleppm'},-10088)
    request_access({'id':303,'first_name':'Amoy','username':'amoyppm'},-10088)
    add_staff(101,202,'coordinator');add_staff(101,303,'worker')
    t=create_assignment(202,-10088,'Zoom host | @amoyppm | 2026-10-13 | 6 PM')
    assert 'Awaiting their confirmation' in t
    assert 'Only the assigned worker' in update_task(202,-10088,1,'confirm')
    assert 'CONFIRMED' in update_task(303,-10088,1,'confirm')
    assert 'CONFIRMED' in list_tasks(-10088)
    assert 'DONE' in update_task(303,-10088,1,'done')
    assert 'No tasks have been recorded' in list_tasks(-10088)
    assert 'already completed' in create_assignment(202,-10088,'Zoom host | open | 2026-10-13 | 6 PM')


def test_office_shift_seed_is_idempotent_and_never_assumes_confirmation():
    assert 'new' in seed_day(101,-10088,date(2026,10,13))
    first=list_tasks(-10088)
    assert 'Zoom prayer leader' in first and 'UNASSIGNED' in first
    assert '0 new' in seed_day(101,-10088,date(2026,10,13))
    with connect() as db:
        assert db.execute("SELECT COUNT(*) FROM office_tasks WHERE status='CONFIRMED'").fetchone()[0]==0


def test_group_request_then_worker_confirm(monkeypatch):
    sent=[]
    async def fake(method,payload):sent.append(payload['text']);return {}
    monkeypatch.setattr('app.telegram.tg',fake)
    def msg(uid,text,update):return {'update_id':update,'message':{'chat':{'id':-10088,'type':'supergroup','title':'OFFICE'},'from':{'id':uid,'first_name':'Michelle' if uid==202 else 'A'},'text':text}}
    asyncio.run(handle_update(msg(101,'/linkoffice@PPMOfficeBot',1)))
    asyncio.run(handle_update(msg(202,'/requestaccess@PPMOfficeBot',2)))
    assert 'recorded' in sent[-1]
    assert role_for(202)=='none'
    add_staff(101,202,'coordinator')
    asyncio.run(handle_update(msg(202,'/setupday@PPMOfficeBot',3)))
    asyncio.run(handle_update(msg(202,'/pending@PPMOfficeBot',4)))
    assert 'UNASSIGNED' in sent[-1]
    asyncio.run(handle_update(msg(202,'/assign@PPMOfficeBot YouTube moderator | open | 2026-10-13 | 7 PM',5)))
    assert 'UNASSIGNED' in sent[-1]


def test_tuesday_no_friday_encounter_and_sunday_no_regular_youtube():
    t=_today_text(datetime(2026,10,13,17,tzinfo=ZoneInfo('America/New_York')))
    assert 'Divine Visitation YouTube Teaching' in t and 'Friday Encounter' not in t
    sunday=_today_text(datetime(2026,10,18,17,tzinfo=ZoneInfo('America/New_York')))
    assert 'Divine Visitation YouTube Teaching' not in sunday
