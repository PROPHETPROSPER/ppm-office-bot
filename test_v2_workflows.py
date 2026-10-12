"""Security/behavior tests for actual bot launch gates (no external network)."""
import asyncio
from datetime import datetime,date
from zoneinfo import ZoneInfo
import pytest
from app.roles import can,role_for
from app.storage import init_db,connect
from app.admin_bot import handle_admin_message
from app.telegram import handle_update
from app.campaigns import create_draft,add_event,approve_event
from app.dispatch import send_one,send_approved_due
from app.worker import routine_reminders,live_topic,live_check

@pytest.fixture(autouse=True)
def isolate(tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'bot.db'))
    for x in ('TELEGRAM_OWNER_USER_IDS','TELEGRAM_ADMIN_USER_IDS','TELEGRAM_EDITOR_USER_IDS',
              'TELEGRAM_APPROVER_USER_IDS','TELEGRAM_PUBLISHER_USER_IDS',
              'AUTO_APPROVE_LIVE_ALERTS','AUTO_APPROVE_ROUTINE_REMINDERS','ZOOM_PRAYER_URL',
              'PAID_MENTORSHIP_URL','TELEGRAM_OFFICIAL_CHANNEL_ID','TELEGRAM_FREE_GROUP_ID','LIVE_SENDING_ENABLED'):
        monkeypatch.delenv(x,raising=False)
    init_db()

def test_least_privilege(monkeypatch):
    monkeypatch.setenv('TELEGRAM_EDITOR_USER_IDS','101')
    monkeypatch.setenv('TELEGRAM_APPROVER_USER_IDS','102')
    monkeypatch.setenv('TELEGRAM_PUBLISHER_USER_IDS','103')
    monkeypatch.setenv('TELEGRAM_OWNER_USER_IDS','104')
    assert can(101,'draft') and not can(101,'approve') and not can(101,'send')
    assert can(102,'approve') and not can(102,'send')
    assert can(103,'send') and not can(103,'approve')
    assert can(104,'approve') and can(104,'send')
    assert not can(999,'queue')

def test_nonapprover_cannot_approve_through_chat(monkeypatch):
    monkeypatch.setenv('TELEGRAM_EDITOR_USER_IDS','101')
    monkeypatch.setenv('TELEGRAM_APPROVER_USER_IDS','102')
    out=[]
    async def fake(method,body):out.append(body['text'])
    asyncio.run(handle_admin_message(101,'/draft official|schools|Study tonight',fake))
    with connect() as db: did=db.execute('SELECT draft_id FROM drafts').fetchone()['draft_id']
    asyncio.run(handle_admin_message(101,f'/approve {did}',fake))
    with connect() as db:assert db.execute('SELECT status FROM drafts').fetchone()['status']=='DRAFT'
    asyncio.run(handle_admin_message(102,f'/preview {did}',fake))
    assert 'Study tonight' in out[-1]
    asyncio.run(handle_admin_message(102,f'/approve {did}',fake))
    with connect() as db:assert db.execute('SELECT status FROM drafts').fetchone()['status']=='APPROVED'

def test_rejection_never_sends(monkeypatch):
    monkeypatch.setenv('TELEGRAM_APPROVER_USER_IDS','102')
    monkeypatch.setenv('LIVE_SENDING_ENABLED','true')
    did=create_draft({'audience':'official','topic':'schools','text':'No promotion'})
    async def fake(method,body):pass
    asyncio.run(handle_admin_message(102,f'/reject {did}',fake))
    with pytest.raises(ValueError):asyncio.run(send_one(did))

def test_duplicate_update_cannot_flip_preference(monkeypatch):
    sent=[]
    async def fake(method,body):sent.append(method)
    monkeypatch.setattr('app.telegram.tg',fake)
    asyncio.run(handle_update({'update_id':10,'message':{'chat':{'id':42,'type':'private'},'from':{'id':42,'first_name':'P'},'text':'/start'}}))
    q={'update_id':11,'callback_query':{'id':'call1','from':{'id':42},
       'message':{'chat':{'id':42,'type':'private'}},'data':'pref:morning_prayer'}}
    asyncio.run(handle_update(q));asyncio.run(handle_update(q))
    with connect() as db:assert db.execute("SELECT enabled FROM preferences WHERE telegram_id=42 AND topic='morning_prayer'").fetchone()['enabled']==1

def test_welcome_only_known_groups(monkeypatch):
    sent=[]
    async def fake(method,body):sent.append(body)
    monkeypatch.setattr('app.telegram.tg',fake)
    monkeypatch.setenv('TELEGRAM_FREE_GROUP_ID','-100123')
    message={'message':{'chat':{'id':-100999,'type':'supergroup'},'new_chat_members':[{'first_name':'New'}]}}
    asyncio.run(handle_update(message));assert not sent
    message['message']['chat']['id']=-100123
    asyncio.run(handle_update(message));assert len(sent)==1

def test_unapproved_and_disabled_send_never_calls_telegram(monkeypatch):
    monkeypatch.setenv('TELEGRAM_OFFICIAL_CHANNEL_ID','-100123')
    did=create_draft({'audience':'official','topic':'schools','text':'Hello'})
    calls=[]
    async def fake(*a):calls.append(a)
    monkeypatch.setattr('app.dispatch.tg',fake)
    with pytest.raises(PermissionError):asyncio.run(send_one(did))
    monkeypatch.setenv('LIVE_SENDING_ENABLED','true')
    with pytest.raises(ValueError):asyncio.run(send_one(did))
    assert calls==[]

def test_single_destination_no_retry_after_send(monkeypatch):
    monkeypatch.setenv('TELEGRAM_OFFICIAL_CHANNEL_ID','-100123')
    monkeypatch.setenv('LIVE_SENDING_ENABLED','true')
    did=create_draft({'audience':'official','topic':'schools','text':'Approved program'})
    with connect() as db: db.execute("UPDATE drafts SET status='APPROVED' WHERE draft_id=?",(did,))
    calls=[]
    async def fake(method,body):calls.append(body)
    monkeypatch.setattr('app.dispatch.tg',fake)
    assert asyncio.run(send_one(did))['sent']==1
    with pytest.raises(ValueError):asyncio.run(send_one(did))
    assert len(calls)==1

def test_partial_personal_send_flags_manual_review(monkeypatch):
    monkeypatch.setenv('LIVE_SENDING_ENABLED','true')
    with connect() as db:
        for uid in (401,402):
            db.execute('INSERT INTO members(telegram_id,first_name,started_at,last_seen_at) VALUES(?,?,?,?)',(uid,'Person','now','now'))
            db.execute("INSERT INTO preferences(telegram_id,topic,enabled) VALUES(?,?,1)",(uid,'morning_prayer'))
    did=create_draft({'audience':'telegram_personal','topic':'morning_prayer','text':'Join now'})
    with connect() as db: db.execute("UPDATE drafts SET status='APPROVED' WHERE draft_id=?",(did,))
    calls=[]
    async def fake(method,body):
        calls.append(body['chat_id'])
        if body['chat_id']==402:raise TimeoutError('Network ambiguous')
    monkeypatch.setattr('app.dispatch.tg',fake)
    with pytest.raises(RuntimeError,match='Manual review'):
        asyncio.run(send_one(did))
    with connect() as db:
        assert db.execute('SELECT status FROM drafts WHERE draft_id=?',(did,)).fetchone()['status']=='NEEDS_MANUAL_REVIEW'
        assert [r['state'] for r in db.execute('SELECT state FROM telegram_deliveries ORDER BY telegram_id')] == ['SENT','MANUAL_REVIEW']
    assert calls==[401,402]

def test_live_classification_and_private_hold():
    et=ZoneInfo('America/New_York')
    assert live_topic('Hour of Prayer',datetime(2026,10,12,9,tzinfo=et))=='morning_prayer'
    assert live_topic('Divine Visitation',datetime(2026,10,12,19,tzinfo=et))=='evening_teaching'
    assert live_topic('Divine Visitation',datetime(2026,10,11,19,tzinfo=et)) is None # Sunday
    assert live_topic('Dallas event',datetime(2026,10,12,19,tzinfo=et)) is None
    assert live_topic('random music',datetime(2026,10,12,19,tzinfo=et)) is None

def test_live_drafts_require_policy_for_autoapproval(monkeypatch):
    async def source():return [{'id':'VID123','snippet':{'title':'Divine Visitation Day 2'}}]
    monkeypatch.setattr('app.worker.youtube_active_broadcasts',source)
    now=datetime(2026,10,12,19,tzinfo=ZoneInfo('America/New_York'))
    assert asyncio.run(live_check(now=now))['drafts_created']==3
    with connect() as db:assert db.execute("SELECT COUNT(*) n FROM drafts WHERE status='APPROVED'").fetchone()['n']==0
    assert asyncio.run(live_check(now=now))['drafts_created']==0

def test_live_autoapproval_requires_explicit_flag(monkeypatch):
    monkeypatch.setenv('AUTO_APPROVE_LIVE_ALERTS','true')
    async def source():return [{'id':'VID124','snippet':{'title':'Divine Visitation Day 3'}}]
    monkeypatch.setattr('app.worker.youtube_active_broadcasts',source)
    now=datetime(2026,10,13,19,tzinfo=ZoneInfo('America/New_York'))
    assert asyncio.run(live_check(now=now))['auto_approved_for_dispatch']==3
    monkeypatch.setenv('LIVE_SENDING_ENABLED','false')
    assert asyncio.run(send_approved_due())['status']=='DISABLED'

def test_routine_schedule_and_separation(monkeypatch):
    monkeypatch.setenv('ZOOM_PRAYER_URL','https://example.org/approved-zoom')
    monkeypatch.setenv('PAID_MENTORSHIP_URL','https://example.org/private')
    assert routine_reminders(target_day=date(2026,10,17))['created']>=3
    with connect() as db:
        paid=db.execute("SELECT text FROM drafts WHERE audience='paid'").fetchall()
        official=db.execute("SELECT text FROM drafts WHERE audience='official'").fetchall()
    assert len(paid)==1
    assert all('example.org/private' not in r['text'] for r in official)
    assert routine_reminders(target_day=date(2026,10,24))['created']>=1
    with connect() as db:
        assert db.execute("SELECT COUNT(*) n FROM drafts WHERE audience='paid' AND dedupe_key LIKE '%2026-10-24%'").fetchone()['n']==0

def test_routine_without_zoom_url_skips_unsafe_reminder(monkeypatch):
    result=routine_reminders(target_day=date(2026,10,12))
    assert any('Zoom URL not confirmed' in x for x in result['missing_links_or_held'])
    with connect() as db:
        assert db.execute('SELECT COUNT(*) n FROM drafts').fetchone()['n']==2

def test_guided_admin_draft_needs_separate_approver(monkeypatch):
    monkeypatch.setenv('TELEGRAM_EDITOR_USER_IDS','808')
    monkeypatch.setenv('TELEGRAM_APPROVER_USER_IDS','809')
    calls=[]
    async def fake(method,body):calls.append((method,body))
    monkeypatch.setattr('app.telegram.tg',fake)
    asyncio.run(handle_update({'update_id':901,'message':{'chat':{'type':'private','id':808},
               'from':{'id':808,'first_name':'Editor'},'text':'/new'}}))
    assert any(b.get('reply_markup') for m,b in calls if m=='sendMessage')
    for index,action in [(902,'admin:dest:official'),(903,'admin:topic:schools')]:
        asyncio.run(handle_update({'update_id':index,'callback_query':{'id':f'c{index}',
            'from':{'id':808},'message':{'chat':{'type':'private','id':808}},'data':action}}))
    asyncio.run(handle_update({'update_id':904,'message':{'chat':{'type':'private','id':808},
        'from':{'id':808},'text':'Upcoming prophetic school: https://prophetprosper.com'}}))
    with connect() as db:
        r=db.execute('SELECT audience,topic,text,status FROM drafts').fetchone()
        assert (r['audience'],r['topic'],r['status'])==('official','schools','DRAFT')
        assert 'prophetprosper.com' in r['text']
    assert not can(808,'approve') and can(809,'approve')

def test_group_callback_cannot_modify_preference(monkeypatch):
    sent=[]
    async def fake(method,body):sent.append(method)
    monkeypatch.setattr('app.telegram.tg',fake)
    asyncio.run(handle_update({'message':{'chat':{'id':101,'type':'private'},'from':{'id':101},'text':'/start'}}))
    asyncio.run(handle_update({'callback_query':{'id':'bad','from':{'id':101},
        'message':{'chat':{'id':-1006,'type':'supergroup'}},'data':'pref:schools'}}))
    with connect() as db:
        assert db.execute('SELECT COUNT(*) n FROM preferences').fetchone()['n']==0
