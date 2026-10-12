import os,pytest
from fastapi.testclient import TestClient
from app.main import app
from app.storage import init_db,connect
from app.campaigns import add_event,approve_event,plan_campaign
from app.ai_content import check_exact_quotes,draft_teaching
from app.integrations import morethanpanel_readonly
from app.comparison import compare_scenarios

@pytest.fixture(autouse=True)
def configure(tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'test.db'))
    monkeypatch.setenv('APP_ADMIN_TOKEN','unit-test-secret')
    monkeypatch.setenv('LIVE_SENDING_ENABLED','false')
    init_db()

def headers():return {'Authorization':'Bearer unit-test-secret'}

def test_access_and_health():
    c=TestClient(app)
    assert c.get('/health').json()['purchasing']=='NEVER_SUPPORTED'
    assert c.get('/admin/drafts').status_code==401
    assert c.get('/admin/drafts',headers=headers()).status_code==200

def test_campaign_approval_and_idempotency():
    data={'event_id':'SCHOOL1','name':'Bible School','start_date':'2026-11-01',
          'url':'https://prophetprosper.com/school','topic':'schools','time_label':'2 PM ET'}
    add_event(data)
    assert plan_campaign(start_day=__import__('datetime').date(2026,10,10))['new_drafts']==0
    approve_event('SCHOOL1','tester')
    a=plan_campaign(start_day=__import__('datetime').date(2026,10,10))
    assert a['new_drafts']>0
    assert plan_campaign(start_day=__import__('datetime').date(2026,10,10))['new_drafts']==0

def test_confidential_event_blocked():
    add_event({'event_id':'S','name':'Private Dallas gathering','start_date':'2027-01-05',
               'url':'https://prophetprosper.com','topic':'gatherings'})
    with pytest.raises(ValueError):approve_event('S','tester')
    assert plan_campaign(start_day=__import__('datetime').date(2026,10,10))['new_drafts']==0

def test_no_send_without_activation():
    c=TestClient(app)
    r=c.post('/admin/drafts',json={'audience':'official','topic':'morning_prayer','text':'Morning Prayer at 9 AM'},headers=headers())
    assert r.status_code==200
    did=r.json()['draft_id']
    assert c.post(f'/admin/drafts/{did}/approve',headers=headers()).status_code==200
    assert c.post(f'/admin/drafts/{did}/send',headers=headers()).status_code==403

def test_sms_remains_export_only():
    c=TestClient(app)
    did=c.post('/admin/drafts',json={'audience':'clearstream','topic':'schools','text':'School starts next week'},headers=headers()).json()['draft_id']
    assert c.post(f'/admin/drafts/{did}/approve',headers=headers()).json()['status']=='APPROVED_EXPORT'
    assert c.post(f'/admin/drafts/{did}/send',headers=headers()).status_code==403

def test_quote_fidelity_and_offline():
    t='Prayer is not a performance. It is a discipline that shapes our lives.'
    a=draft_teaching(t,'test','offline','')
    assert a['status']=='READY_FOR_HUMAN_REVIEW'
    assert not a['quote_verification_issues']
    assert check_exact_quotes(t,{'slides':[{'quote':'Something I never said'}]*3,'reels':[{'exact_excerpt':'Prayer is not a performance.'}]})

def test_service_catalog_only():
    with pytest.raises(ValueError):morethanpanel_readonly('add')
    with pytest.raises(ValueError):morethanpanel_readonly('refill')
    with pytest.raises(ValueError):morethanpanel_readonly('cancel')

def test_comparison_is_not_accusation():
    r=compare_scenarios([{'label':'sample','impressions':100,'profile_or_link_clicks':25,'verified_opt_ins':10,
                            'verified_attendance':6,'returning_attendees':4}])
    assert r['comparisons'][0]['click_through_pct']==25
    assert 'not proof' in r['comparisons'][0]['note']

def test_webhook_requires_telegram_secret():
    c=TestClient(app)
    assert c.post('/telegram/webhook',json={'message':{'text':'/start'}}).status_code==403

def test_bot_preferences(monkeypatch):
    from app.telegram import handle_update
    import asyncio
    async def fake_tg(*args): return {'ok':True}
    monkeypatch.setattr('app.telegram.tg',fake_tg)
    asyncio.run(handle_update({'message':{'chat':{'id':101,'type':'private'},'from':{'id':101,'first_name':'P'},'text':'/start'}}))
    asyncio.run(handle_update({'callback_query':{'id':'abc','from':{'id':101},'data':'pref:morning_prayer'}}))
    with connect() as db:
        assert db.execute("SELECT enabled FROM preferences WHERE telegram_id=101 AND topic='morning_prayer'").fetchone()['enabled']==1
    asyncio.run(handle_update({'message':{'chat':{'id':101,'type':'private'},'from':{'id':101},'text':'/stop'}}))
    with connect() as db:
        assert db.execute("SELECT stopped_at FROM members WHERE telegram_id=101").fetchone()['stopped_at']

def test_wix_missing_page_url_is_not_guessed():
    from app.wix_sync import normalize_event
    assert normalize_event({'id':'1','title':'Prayer Chain','dateAndTimeSettings':{'startDate':'2026-10-14T16:00:00Z'}}) is None
    assert normalize_event({'id':'2','title':'Dallas PPP','dateAndTimeSettings':{'startDate':'2027-01-14T16:00:00Z'},'eventPageUrl':'https://example.com/a'}) is None

def test_approved_event_unchanged_keeps_approval_but_change_revokes():
    event={'event_id':'E1','name':'School','start_date':'2026-11-01','url':'https://prophetprosper.com/a','topic':'schools'}
    add_event(event);approve_event('E1','editor')
    assert add_event(event)['status']=='APPROVAL_PRESERVED'
    event['url']='https://prophetprosper.com/b'
    assert add_event(event)['status']=='HOLD_REVIEW'
