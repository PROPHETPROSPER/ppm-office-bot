"""Exactly-once-attempt Telegram dispatch of explicitly approved drafts.

Network ambiguity is never blindly retried. Personal deliveries are journaled
per recipient; an operator must review a partial failure before resuming.
"""
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from app.settings import setting, CONFIDENTIAL_TERMS
from app.storage import connect, now_iso, audit
from app.telegram import tg, audience_chat_id

AUDIENCES=('official','free','paid','telegram_personal')

def is_due(value, now=None):
    now=now or datetime.now(ZoneInfo('America/New_York'))
    dt=datetime.fromisoformat(value)
    if dt.tzinfo is None:dt=dt.replace(tzinfo=ZoneInfo('America/New_York'))
    return dt<=now

def eligible(d, db):
    if d['audience'] not in AUDIENCES: return 'Telegram destinations only; SMS/WhatsApp are export-only.'
    if any(term.lower() in d['text'].lower() for term in CONFIDENTIAL_TERMS): return 'Confidential plans detected.'
    if d['event_id']:
        event=db.execute('SELECT public_ok,is_private FROM events WHERE event_id=?',(d['event_id'],)).fetchone()
        if not event or not event['public_ok'] or event['is_private']:return 'Event is not approved for public promotion.'
    return None

def recipients(d,db):
    if d['audience']!='telegram_personal':
        cid=audience_chat_id(d['audience'])
        if not cid:raise RuntimeError('Destination ID is not configured.')
        return [int(cid)]
    if d['event_id']:
        q='''SELECT m.telegram_id FROM members m JOIN event_subscriptions x ON x.telegram_id=m.telegram_id
             WHERE m.stopped_at IS NULL AND x.event_id=? AND x.enabled=1'''
        rows=db.execute(q,(d['event_id'],)).fetchall()
    else:
        q='''SELECT m.telegram_id FROM members m JOIN preferences p ON p.telegram_id=m.telegram_id
             WHERE m.stopped_at IS NULL AND p.topic=? AND p.enabled=1'''
        rows=db.execute(q,(d['topic'],)).fetchall()
    if len(rows)>1000:raise RuntimeError('Recipient cap 1000 exceeded. Upgrade batching before sending.')
    return [int(r['telegram_id']) for r in rows]

async def send_one(draft_id, actor='scheduler'):
    """Returns result; rejects a second or concurrent attempt; never auto-retries ambiguous results."""
    if setting('LIVE_SENDING_ENABLED','false').lower()!='true':
        raise PermissionError('LIVE_SENDING_ENABLED=false. Sending disabled.')
    with connect() as db:
        d=db.execute('SELECT * FROM drafts WHERE draft_id=?',(draft_id,)).fetchone()
        if not d:raise ValueError('Draft not found')
        if d['status']!='APPROVED':raise ValueError('Only approved drafts may be sent')
        failure=eligible(d,db)
        if failure:
            db.execute("UPDATE drafts SET status='STALE_HOLD',last_error=? WHERE draft_id=?",(failure,draft_id))
            raise ValueError(failure)
        all_ids=recipients(d,db)
        # First attempt is journaled; a crash cannot cause auto-redelivery.
        for uid in all_ids:
            db.execute('''INSERT OR IGNORE INTO telegram_deliveries(draft_id,telegram_id,state,updated_at)
                VALUES(?,?,'PENDING',?)''',(draft_id,uid,now_iso()))
        claimed=db.execute("UPDATE drafts SET status='SENDING' WHERE draft_id=? AND status='APPROVED'",(draft_id,))
        if not claimed.rowcount:raise ValueError('Already claimed by another sender')
    delivered=0
    try:
        for uid in all_ids:
            with connect() as db:
                existing=db.execute('SELECT state FROM telegram_deliveries WHERE draft_id=? AND telegram_id=?',(draft_id,uid)).fetchone()
                if existing['state']=='SENT':continue
                db.execute('''UPDATE telegram_deliveries SET state='SENDING',updated_at=?
                   WHERE draft_id=? AND telegram_id=?''',(now_iso(),draft_id,uid))
            # A timeout may mean Telegram already accepted it. Never blindly retry.
            try:
                await tg('sendMessage',{'chat_id':uid,'text':d['text'],'disable_web_page_preview':True})
            except Exception as ex:
                with connect() as db:
                    db.execute('''UPDATE telegram_deliveries SET state='MANUAL_REVIEW',updated_at=?,last_error=?
                        WHERE draft_id=? AND telegram_id=?''',(now_iso(),str(ex)[:250],draft_id,uid))
                raise
            with connect() as db:
                db.execute('''UPDATE telegram_deliveries SET state='SENT',updated_at=?
                    WHERE draft_id=? AND telegram_id=?''',(now_iso(),draft_id,uid))
            delivered+=1
            if d['audience']=='telegram_personal':await asyncio.sleep(.05)
        with connect() as db:
            db.execute("UPDATE drafts SET status='SENT',sent_at=? WHERE draft_id=?",(now_iso(),draft_id))
        audit(actor,'sent_draft',{'draft_id':draft_id,'recipients':delivered})
        return {'draft_id':draft_id,'status':'SENT','sent':delivered}
    except Exception as ex:
        with connect() as db:
            db.execute('''UPDATE drafts SET status='NEEDS_MANUAL_REVIEW',last_error=? WHERE draft_id=?''',
                       (str(ex)[:250],draft_id))
        audit(actor,'send_ambiguous',{'draft_id':draft_id,'sent_before_failure':delivered})
        raise RuntimeError('Some sends may have succeeded. Manual review is required; do not retry automatically.') from ex

async def send_approved_due(limit=20):
    if setting('LIVE_SENDING_ENABLED','false').lower()!='true':
        return {'status':'DISABLED','sent':0,'errors':0,'held':0}
    with connect() as db:
        items=[dict(x) for x in db.execute("SELECT * FROM drafts WHERE status='APPROVED' ORDER BY scheduled_at LIMIT ?",(max(1,min(limit,50)),))]
    results={'sent':0,'errors':0,'held':0}
    for item in items:
        if not is_due(item['scheduled_at']):continue
        try:
            await send_one(item['draft_id'])
            results['sent']+=1
        except ValueError:
            results['held']+=1
        except Exception:
            results['errors']+=1
    return results
