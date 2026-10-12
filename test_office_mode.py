"""Office bot access restrictions and configured Telegram identity checks."""
import asyncio
from fastapi.testclient import TestClient
from app.main import app
from app.storage import init_db, connect
from app.telegram import handle_update


def test_office_denies_unknown_and_supports_authorized_draft(monkeypatch, tmp_path):
    monkeypatch.setenv('DB_PATH', str(tmp_path/'office.db'))
    monkeypatch.setenv('PPM_BOT_MODE','office')
    monkeypatch.setenv('TELEGRAM_OWNER_USER_IDS','101')
    init_db()
    sent=[]
    async def fake(method, payload):
        sent.append(payload)
        return True
    monkeypatch.setattr('app.telegram.tg', fake)
    asyncio.run(handle_update({'update_id':111,'message':{'chat':{'id':202,'type':'private'},'from':{'id':202},'text':'/start'}}))
    assert 'private' in sent[-1]['text'].lower()
    asyncio.run(handle_update({'update_id':112,'message':{'chat':{'id':202,'type':'private'},'from':{'id':202},'text':'/new'}}))
    with connect() as db:
        assert db.execute('SELECT COUNT(*) AS c FROM admin_sessions').fetchone()['c']==0
    asyncio.run(handle_update({'update_id':113,'message':{'chat':{'id':101,'type':'private'},'from':{'id':101},'text':'/start'}}))
    assert '/new' in sent[-1]['text']
    asyncio.run(handle_update({'update_id':114,'message':{'chat':{'id':101,'type':'private'},'from':{'id':101},'text':'/new'}}))
    with connect() as db:
        assert db.execute('SELECT step FROM admin_sessions WHERE telegram_id=101').fetchone()['step']=='audience'


def test_office_mode_prevents_public_subscriptions(monkeypatch, tmp_path):
    monkeypatch.setenv('DB_PATH', str(tmp_path/'subscriptions.db'))
    monkeypatch.setenv('PPM_BOT_MODE','office')
    monkeypatch.setenv('TELEGRAM_OWNER_USER_IDS','101')
    init_db()
    async def fake(*args,**kwargs):return True
    monkeypatch.setattr('app.telegram.tg',fake)
    asyncio.run(handle_update({'update_id':222,'message':{'chat':{'id':101,'type':'private'},'from':{'id':101},'text':'/alerts'}}))
    with connect() as db:
        assert db.execute('SELECT COUNT(*) AS c FROM members').fetchone()['c']==0
    asyncio.run(handle_update({'update_id':223,'callback_query':{'id':'c1','from':{'id':101},'message':{'chat':{'id':101,'type':'private'}},'data':'pref:morning_prayer'}}))
    with connect() as db:
        assert db.execute('SELECT COUNT(*) AS c FROM preferences').fetchone()['c']==0


def test_telegram_identity_refuses_wrong_bot(monkeypatch, tmp_path):
    monkeypatch.setenv('DB_PATH', str(tmp_path/'identity.db'))
    monkeypatch.setenv('APP_ADMIN_TOKEN','test-only-admin-secret')
    monkeypatch.setenv('PPM_EXPECTED_BOT_USERNAME','PPMOfficeBot')
    init_db()
    async def fake(method,body): return {'username':'AnotherBot'}
    monkeypatch.setattr('app.telegram.tg',fake)
    client=TestClient(app)
    h={'Authorization':'Bearer test-only-admin-secret'}
    assert client.get('/admin/telegram/identity',headers=h).status_code==409
    async def good(method,body): return {'username':'PPMOfficeBot'}
    monkeypatch.setattr('app.telegram.tg',good)
    r=client.get('/admin/telegram/identity',headers=h)
    assert r.status_code==200 and r.json()['verified'] is True
