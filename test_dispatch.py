import asyncio
from datetime import date
from app.storage import init_db,connect
from app.campaigns import add_event,approve_event,plan_campaign,create_draft
from app.dispatch import send_approved_due,is_due

def test_dry_run_never_sends(monkeypatch,tmp_path):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'q.db'))
    monkeypatch.setenv('LIVE_SENDING_ENABLED','false')
    init_db()
    assert asyncio.run(send_approved_due())['status']=='DISABLED'

def test_due_date_time_zone():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now=datetime(2026,11,1,13,0,tzinfo=ZoneInfo('America/New_York'))
    assert is_due('2026-11-01T12:00:00',now)
    assert not is_due('2026-11-01T14:00:00',now)

def test_event_edits_suspend_old_campaign_drafts(monkeypatch,tmp_path):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'q.db'))
    init_db()
    ev={'event_id':'E','name':'Prophetic School','start_date':'2026-11-01','url':'https://prophetprosper.com/a','topic':'schools'}
    add_event(ev);approve_event('E','editor');plan_campaign(start_day=date(2026,10,10))
    with connect() as db:assert db.execute('SELECT COUNT(*) n FROM drafts').fetchone()['n']>0
    ev['url']='https://prophetprosper.com/new'
    add_event(ev)
    with connect() as db:
        assert db.execute('SELECT COUNT(*) n FROM drafts WHERE status=?',('STALE_HOLD',)).fetchone()['n']>0
    approve_event('E','editor');assert plan_campaign(start_day=date(2026,10,10))['new_drafts']>0
