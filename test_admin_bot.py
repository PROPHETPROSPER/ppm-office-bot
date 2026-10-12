import asyncio
from app.storage import init_db,connect
from app.admin_bot import handle_admin_message

def test_admin_bot_queue_draft_approve_disabled_send(monkeypatch,tmp_path):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'bot.db'))
    monkeypatch.setenv('TELEGRAM_OWNER_USER_IDS','901')
    monkeypatch.setenv('LIVE_SENDING_ENABLED','false')
    init_db()
    sent=[]
    async def tg(method,body):sent.append(body['text'])
    asyncio.run(handle_admin_message(901,'/draft official|schools|Our school opens next week',tg))
    with connect() as db:
        r=db.execute('SELECT draft_id,status FROM drafts').fetchone()
        id=r['draft_id']; assert r['status']=='DRAFT'
    asyncio.run(handle_admin_message(901,f'/approve {id}',tg))
    with connect() as db:
        assert db.execute('SELECT status FROM drafts').fetchone()['status']=='APPROVED'
    asyncio.run(handle_admin_message(901,f'/send {id}',tg))
    with connect() as db:
        assert db.execute('SELECT status FROM drafts').fetchone()['status']=='APPROVED'
    assert 'Sending disabled' in sent[-1]

def test_unapproved_admin_cannot_create(monkeypatch,tmp_path):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'bot.db'))
    monkeypatch.setenv('TELEGRAM_ADMIN_USER_IDS','901')
    init_db();sent=[]
    async def tg(method,body):sent.append(body['text'])
    asyncio.run(handle_admin_message(100,'/draft official|schools|attack',tg))
    with connect() as db:
        assert db.execute('SELECT COUNT(*) n FROM drafts').fetchone()['n']==0
