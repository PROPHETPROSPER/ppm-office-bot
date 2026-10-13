"""Core office completion: end-to-end staff onboarding and fact-based reports."""
import asyncio
from datetime import date
from zoneinfo import ZoneInfo
import pytest
from app.storage import init_db, connect
from app.office_tracker import request_access, add_staff, create_assignment, seed_day, update_task, daily_report, staff_role
from app.roles import role_for, can
from app.telegram import handle_update


@pytest.fixture(autouse=True)
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path/'ppm.sqlite3'))
    monkeypatch.setenv('PPM_BOT_MODE', 'office')
    monkeypatch.setenv('TELEGRAM_OWNER_USER_IDS', '1643599394')
    monkeypatch.setenv('LIVE_SENDING_ENABLED', 'false')
    monkeypatch.setenv('PPM_SCHEDULER_ENABLED', 'false')
    init_db()


def pm(uid, message, update_id):
    return {'update_id': update_id, 'message': {'chat': {'id':uid, 'type':'private'},
            'from': {'id':uid,'first_name':'Michelle' if uid==202 else 'Staff','username':'ppmworker'},
            'text':message}}


def gm(uid, message, update_id):
    return {'update_id': update_id, 'message': {'chat': {'id':-10072,'type':'supergroup','title':'Private PPM Office'},
            'from': {'id':uid,'first_name':'Staff','username':'ppmworker'}, 'text':message}}


def test_unapproved_worker_can_request_in_private(monkeypatch):
    sent=[]
    async def fake(method,body):
        sent.append((method,body))
        return {}
    monkeypatch.setattr('app.telegram.tg',fake)
    asyncio.run(handle_update(pm(202,'/start',101)))
    assert 'requestaccess' in sent[-1][1]['text']
    asyncio.run(handle_update(pm(202,'/requestaccess',102)))
    assert 'request recorded' in sent[-1][1]['text'].lower()
    assert role_for(202)=='none'
    asyncio.run(handle_update(pm(1643599394,'/requests',103)))
    assert '202' in sent[-1][1]['text']
    asyncio.run(handle_update(pm(1643599394,'/staffadd 202 coordinator',104)))
    assert role_for(202)=='coordinator'
    assert can(202,'approve') is False
    assert can(202,'send') is False
    asyncio.run(handle_update(pm(202,'/start',105)))
    assert 'coordinator' in sent[-1][1]['text'].lower()


def test_unknown_user_can_read_own_id_but_no_office_data(monkeypatch):
    sent=[]
    async def fake(method,body):sent.append(body['text']);return {}
    monkeypatch.setattr('app.telegram.tg',fake)
    asyncio.run(handle_update(pm(202,'/myid',111)))
    assert '202' in sent[-1]
    asyncio.run(handle_update(pm(202,'/pending',112)))
    assert not any('PPM LIVE' in v for v in sent)


def test_report_counts_are_recorded_not_inferred():
    request_access({'id':202,'first_name':'Michelle','username':'michelleppm'},-10072)
    request_access({'id':303,'first_name':'Amoy','username':'amoyppm'},-10072)
    add_staff(1643599394,202,'coordinator')
    add_staff(1643599394,303,'worker')
    seed_day(202,-10072,date(2026,10,13))
    result=create_assignment(202,-10072,'Zoom prayer leader | @amoyppm | 2026-10-13 | 6 PM')
    assert 'Awaiting' in result
    report=daily_report(-10072,'2026-10-13')
    assert 'AWAITING CONFIRMATION: 1' in report
    assert 'CONFIRMED TO SERVE: 0' in report
    assert 'MARKED COMPLETE: 0' in report
    assert 'not proof' in report
    with connect() as db: task=db.execute("SELECT task_id FROM office_tasks WHERE title='Zoom prayer leader'").fetchone()['task_id']
    assert 'CONFIRMED' in update_task(303,-10072,task,'confirm')
    assert 'CONFIRMED TO SERVE: 1' in daily_report(-10072,'2026-10-13')
    assert 'DONE' in update_task(303,-10072,task,'done')
    assert 'MARKED COMPLETE: 1' in daily_report(-10072,'2026-10-13')
    assert 'NEEDS ATTENTION: 6' in daily_report(-10072,'2026-10-13')


def test_report_role_restriction_in_group(monkeypatch):
    sent=[]
    async def fake(method,body): sent.append(body['text']);return {}
    monkeypatch.setattr('app.telegram.tg',fake)
    asyncio.run(handle_update(gm(1643599394,'/linkoffice@PPMOfficeBot',201)))
    request_access({'id':202,'first_name':'Michelle','username':'michelle'},-10072)
    request_access({'id':303,'first_name':'Amoy','username':'amoy'},-10072)
    add_staff(1643599394,202,'coordinator')
    add_staff(1643599394,303,'worker')
    asyncio.run(handle_update(gm(303,'/report@PPMOfficeBot',202)))
    assert 'restricted' in sent[-1].lower()
    asyncio.run(handle_update(gm(202,'/setupday@PPMOfficeBot 2026-10-13',203)))
    assert 'created' in sent[-1]
    asyncio.run(handle_update(gm(202,'/report@PPMOfficeBot 2026-10-13',204)))
    assert 'PPM OFFICE REPORT' in sent[-1]
    assert '7' in sent[-1]
    asyncio.run(handle_update(pm(202,'/report 2026-10-13',205)))
    assert 'PPM OFFICE REPORT' in sent[-1]


def test_private_group_only_link(monkeypatch):
    sent=[]
    async def fake(method,body):sent.append(body['text']);return {}
    monkeypatch.setattr('app.telegram.tg',fake)
    payload=gm(1643599394,'/linkoffice@PPMOfficeBot',301)
    payload['message']['chat']['username']='public_ppm'
    asyncio.run(handle_update(payload))
    assert 'private' in sent[-1].lower()
    with connect() as db:
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='office_groups'").fetchone() or not db.execute('SELECT * FROM office_groups').fetchone()


def test_report_no_fake_completion_and_no_data():
    text=daily_report(-10072,'2026-10-13')
    assert 'No assignments entered' in text
    assert 'Positions recorded: 0' in text


def test_setupday_idempotent_future_day_group(monkeypatch):
    sent=[]
    async def fake(method,body): sent.append(body['text']);return {}
    monkeypatch.setattr('app.telegram.tg',fake)
    asyncio.run(handle_update(gm(1643599394,'/linkoffice@PPMOfficeBot',401)))
    asyncio.run(handle_update(gm(1643599394,'/setupday@PPMOfficeBot 2026-10-14',402)))
    assert 'new' in sent[-1]
    asyncio.run(handle_update(gm(1643599394,'/setupday@PPMOfficeBot 2026-10-14',403)))
    assert '0 new' in sent[-1]


def test_group_not_authorized_without_owner_approval(monkeypatch):
    sent=[]
    async def fake(method,body): sent.append(body['text']);return {}
    monkeypatch.setattr('app.telegram.tg',fake)
    asyncio.run(handle_update(gm(1643599394,'/linkoffice@PPMOfficeBot',501)))
    asyncio.run(handle_update(gm(202,'/requestaccess@PPMOfficeBot',502)))
    assert role_for(202)=='none'
    n=len(sent)
    asyncio.run(handle_update(gm(202,'/pending@PPMOfficeBot',503)))
    assert len(sent)==n


def test_assignment_sends_private_notice_without_auto_confirm(monkeypatch):
    sent=[]
    async def fake(method,body):sent.append(body);return {}
    monkeypatch.setattr('app.telegram.tg',fake)
    asyncio.run(handle_update(gm(1643599394,'/linkoffice@PPMOfficeBot',601)))
    request_access({'id':303,'first_name':'Amoy','username':'amoy'},-10072)
    add_staff(1643599394,303,'worker')
    asyncio.run(handle_update(gm(1643599394,'/assign@PPMOfficeBot Zoom host | @amoy | 2026-10-13 | 6 PM',602)))
    assert sent[-2]['chat_id']==303
    assert '/confirm' in sent[-2]['text']
    assert 'Worker notified privately' in sent[-1]['text']
    with connect() as db:
        row=db.execute('SELECT status FROM office_tasks LIMIT 1').fetchone()
        assert row['status']=='ASSIGNED'


def test_dm_failure_does_not_break_assignment(monkeypatch):
    sent=[]
    async def fake(method,body):
        if body['chat_id']==303:raise RuntimeError('bot not started')
        sent.append(body)
        return {}
    monkeypatch.setattr('app.telegram.tg',fake)
    asyncio.run(handle_update(gm(1643599394,'/linkoffice@PPMOfficeBot',701)))
    request_access({'id':303,'first_name':'Amoy','username':'amoy'},-10072)
    add_staff(1643599394,303,'worker')
    asyncio.run(handle_update(gm(1643599394,'/assign@PPMOfficeBot Zoom host | @amoy | 2026-10-13 | 6 PM',702)))
    assert 'could not DM' in sent[-1]['text']
    with connect() as db:
        assert db.execute("SELECT status FROM office_tasks LIMIT 1").fetchone()['status']=='ASSIGNED'


def test_open_assignment_does_not_send_worker_dm(monkeypatch):
    sent=[]
    async def fake(method,body):sent.append(body);return {}
    monkeypatch.setattr('app.telegram.tg',fake)
    asyncio.run(handle_update(gm(1643599394,'/linkoffice@PPMOfficeBot',801)))
    asyncio.run(handle_update(gm(1643599394,'/assign@PPMOfficeBot Zoom host | open | 2026-10-13 | 6 PM',802)))
    assert len(sent)==2
    assert 'UNASSIGNED' in sent[-1]['text']


def test_october_special_services_seed_correctly():
    seed_day(1643599394,-10072,date(2026,10,23))
    text=daily_report(-10072,'2026-10-23')
    assert 'Watchman Series Zoom host' in text
    assert 'Friday Encounter ushers' in text
    seed_day(1643599394,-10072,date(2026,10,24))
    text=daily_report(-10072,'2026-10-24')
    assert 'Watchman Series moderator' in text
    assert 'Spiritual Foundation mentorship host' not in text  # Confirm Saturday conflict before assigning.
    seed_day(1643599394,-10072,date(2026,10,17))
    text=daily_report(-10072,'2026-10-17')
    assert 'Spiritual Foundation mentorship host' in text
