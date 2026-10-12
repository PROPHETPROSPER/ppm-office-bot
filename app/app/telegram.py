import httpx
from app.settings import TOPICS, setting, AUDIENCES
from app.storage import connect, now_iso, audit
from app.settings import CONFIDENTIAL_TERMS

async def tg(method, body):
    token=setting('TELEGRAM_BOT_TOKEN')
    if not token:
        raise RuntimeError('TELEGRAM_BOT_TOKEN is not configured')
    async with httpx.AsyncClient(timeout=20) as client:
        res=await client.post(f'https://api.telegram.org/bot{token}/{method}',json=body)
        res.raise_for_status()
        payload=res.json()
        if not payload.get('ok'):
            raise RuntimeError(f'Telegram method {method} failed')
        return payload.get('result')

def choices_markup():
    return {'inline_keyboard':[[{'text':label,'callback_data':'pref:'+key}]
                              for key,label in TOPICS.items()]+[[{'text':'🔕 Stop all alerts','callback_data':'stop:all'}]]}

async def handle_update(update):
    # Telegram may resend the same update. Toggle callbacks must be idempotent.
    update_id=update.get('update_id')
    if isinstance(update_id,int):
        with connect() as db:
            cur=db.execute('''INSERT OR IGNORE INTO processed_telegram_updates
                (update_id,status,seen_at) VALUES(?,?,?)''',(update_id,'PROCESSING',now_iso()))
            if not cur.rowcount:return
    try:
        await _handle_update_impl(update)
    except Exception:
        if isinstance(update_id,int):
            with connect() as db:
                db.execute('DELETE FROM processed_telegram_updates WHERE update_id=? AND status=?',(update_id,'PROCESSING'))
        raise
    if isinstance(update_id,int):
        with connect() as db:
            db.execute("UPDATE processed_telegram_updates SET status='DONE' WHERE update_id=?",(update_id,))

def office_only():
    return setting('PPM_BOT_MODE', 'public').strip().casefold() == 'office'

async def _handle_update_impl(update):
    message=update.get('message') or {}
    if message:
        chat=message.get('chat') or {}
        user=message.get('from') or {}
        chat_id=chat.get('id')
        # Welcome only in groups; do not DM people until they start the bot.
        joined=message.get('new_chat_members') or []
        if not office_only() and joined and chat.get('type') in ('group','supergroup') and str(chat_id) in {str(setting(x)) for x in ('TELEGRAM_FREE_GROUP_ID','TELEGRAM_PAID_GROUP_ID') if setting(x)}:
            people=[m.get('first_name','friend')[:50] for m in joined[:6] if not m.get('is_bot')]
            if people:
                try:
                    await tg('sendMessage', {'chat_id':chat_id,'text':
                        f"Welcome, {', '.join(people)}! Please read the pinned group rules and resources. For optional personal ministry alerts, start the ministry bot privately and choose /alerts."})
                except Exception:
                    audit('telegram','welcome_failure',{'chat_id':chat_id})
        cmd=(message.get('text') or '').strip().split(' ')[0].split('@')[0]
        if office_only() and chat.get('type') in ('group','supergroup'):
            from app.office_group import handle_office_group_message
            await handle_office_group_message(message,tg)
            return
        if chat.get('type')=='private' and user.get('id'):
            uid=int(user['id'])
            if office_only():
                from app.roles import role_for
                if role_for(uid)=='none':
                    if cmd in ('/start','/help'):
                        await tg('sendMessage',{'chat_id':uid,'text':'This is the private Prophet Prosper Ministries Office Bot. Please contact ministry administration for access. Public updates are available on the official ministry channel.'})
                    return
                if cmd in ('/start','/help'):
                    from app.roles import role_for
                    await tg('sendMessage',{'chat_id':uid,'text':
                        'PROPHET PROSPER MINISTRIES — OFFICE BOT\n'
                        f'Your current staff role: {role_for(uid).title()}\n\n'
                        'OPERATIONS\n'
                        '/today — Today’s ministry briefing\n'
                        '/schedule — Ministry meeting times\n'
                        '/team — Proposed staff responsibilities\n'
                        '/pending — Outstanding confirmations (not a live tracker)\n'
                        '/status — Readiness and safe-publishing status\n\n'
                        'ANNOUNCEMENTS (ROLE-RESTRICTED)\n'
                        '/new — Create announcement for approval\n'
                        '/queue — Review the announcement queue\n'
                        '/preview ID — Review an announcement\n'
                        '/approve ID — Approve a draft (approvers/owner)\n'
                        '/send ID — Publish approved draft when sending is enabled\n\n'
                        'You may also use shared read-only commands in the linked PPM Office group. '
                        'Approvals and publishing are only handled here in private chat.'})
                    return
                if cmd in ('/today','/team','/pending','/status'):
                    from app.office_group import _today_text
                    if cmd=='/today': answer=_today_text()
                    elif cmd=='/team':
                        answer=('PPM STAFF — PROPOSED ASSIGNMENTS\n'
                            'Michelle: operations and connections.\n'
                            'Crystal / Adjovi: prospective prayer leaders.\n'
                            'Jia Jis: prospective moderator.\n'
                            'Davanee: communications pending availability.\n'
                            'Amoy / Alex: possible editing support.\n'
                            'Vacancies: graphic designer, 2 connections assistants, 2 office callers, backups.\n\n'
                            'Nothing is confirmed until Michelle checks with each worker.')
                    elif cmd=='/pending':
                        answer=('PRIORITY CONFIRMATIONS — NOT SYNCED WITH LIVE TRACKER\n'
                            '1. Zoom host and prayer leaders.\n'
                            '2. YouTube moderator and media worker.\n'
                            '3. Backup leaders.\n'
                            '4. Recruit graphics, connections and office support.\n'
                            '5. Assign new visitor follow-ups.\n'
                            'Ask Michelle to verify what has actually been completed.')
                    else:
                        answer=('PPM OFFICE STATUS\n'
                            '• Staff account: authorized\n'
                            '• Public campaign sending: '+('ON' if setting('LIVE_SENDING_ENABLED','false').lower()=='true' else 'OFF (private test)')+'\n'
                            '• Background scheduler: '+('ON' if setting('PPM_SCHEDULER_ENABLED','false').lower()=='true' else 'OFF (private test)')+'\n'
                            '• Live staff tracker: not connected')
                    await tg('sendMessage',{'chat_id':uid,'text':answer})
                    return
                if cmd=='/schedule':
                    await tg('sendMessage',{'chat_id':uid,'text':
                        'PPM SCHEDULE (EASTERN TIME)\n'
                        'Morning Prayer: Mon/Wed/Fri 9 AM ET.\n'
                        'Divine Visitation Zoom Prayer: daily 6–7 PM ET through Nov 9.\n'
                        'YouTube Teaching: Mon–Sat 7–9 PM ET through Nov 9 (no Sunday teaching).\n'
                        'Spiritual Foundation: Saturday 2 PM ET, except Oct 24 overlap.\n'
                        'Watchman Series: Oct 21–24, 2–4 PM ET. Links must be confirmed with Michelle.'})
                    return
                if cmd in ('/queue','/preview','/draft','/approve','/reject','/send','/new'):
                    from app.admin_bot import handle_admin_message
                    await handle_admin_message(uid,message.get('text',''),tg)
                    return
                if not cmd.startswith('/'):
                    from app.admin_bot import handle_admin_free_text
                    await handle_admin_free_text(uid,message.get('text',''),tg)
                return
            if cmd=='/start':
                with connect() as db:
                    ts=now_iso()
                    db.execute('''INSERT INTO members(telegram_id,first_name,started_at,stopped_at,last_seen_at) VALUES(?,?,?,NULL,?)
                      ON CONFLICT(telegram_id) DO UPDATE SET first_name=excluded.first_name,stopped_at=NULL,last_seen_at=excluded.last_seen_at''',
                      (uid,str(user.get('first_name',''))[:100],ts,ts))
                await tg('sendMessage',{'chat_id':uid,'text':
                    'Welcome to Prophet Prosper Ministries. Choose which alerts you WANT to receive. No alerts are enabled until you choose them. Use /stop anytime.',
                    'reply_markup':choices_markup()})
            elif cmd in ('/alerts','/help'):
                await tg('sendMessage',{'chat_id':uid,'text':'Choose or change your notifications below. Tap a topic to toggle it:',
                    'reply_markup':choices_markup()})
            elif cmd=='/status':
                with connect() as db:
                    pr=[TOPICS.get(r['topic'],r['topic']) for r in db.execute('SELECT topic FROM preferences WHERE telegram_id=? AND enabled=1',(uid,))]
                    ev=[r['name'] for r in db.execute('''SELECT e.name FROM event_subscriptions s JOIN events e ON e.event_id=s.event_id
                       WHERE s.telegram_id=? AND s.enabled=1 AND e.public_ok=1 AND e.is_private=0''',(uid,))]
                await tg('sendMessage',{'chat_id':uid,'text':'Your topic alerts: '+(', '.join(pr) or 'None')+'\nEvent alerts: '+(', '.join(ev) or 'None')+'\nManage: /alerts or /events. Stop all: /stop.'})
            elif cmd=='/schedule':
                await tg('sendMessage',{'chat_id':uid,'text':
                   'Morning Prayer: Mon/Wed/Fri 9 AM ET.\nDivine Visitation Zoom Prayer: daily 6–7 PM ET.\nYouTube Teaching: Mon–Sat 7–9 PM ET.\nSpiritual Foundation (enrolled members): Saturdays 2 PM ET.\nEvent times and links: /events.'})
            elif cmd=='/events':
                with connect() as db:
                    event_rows=db.execute('SELECT event_id,name,start_date FROM events WHERE public_ok=1 AND is_private=0 ORDER BY start_date LIMIT 15').fetchall()
                if event_rows:
                    buttons={'inline_keyboard':[[{'text':str(e['name'])[:32]+' • '+e['start_date'],
                         'callback_data':'event:'+e['event_id']}]
                         for e in event_rows if len(e['event_id'])<55]}
                    await tg('sendMessage',{'chat_id':uid,'text':'Choose an event to receive its specific reminders (tap again to turn off):',
                        'reply_markup':buttons})
                else:
                    await tg('sendMessage',{'chat_id':uid,'text':'No verified public events available for individual reminders yet.'})
            elif cmd in ('/queue','/preview','/draft','/approve','/reject','/send','/new'):
                from app.admin_bot import handle_admin_message
                await handle_admin_message(uid,message.get('text',''),tg)
            elif not cmd.startswith('/'):
                from app.admin_bot import handle_admin_free_text
                await handle_admin_free_text(uid,message.get('text',''),tg)
            elif cmd=='/stop':
                with connect() as db:
                    db.execute('UPDATE members SET stopped_at=? WHERE telegram_id=?',(now_iso(),uid))
                    db.execute('UPDATE preferences SET enabled=0 WHERE telegram_id=?',(uid,))
                    db.execute('UPDATE event_subscriptions SET enabled=0 WHERE telegram_id=?',(uid,))
                await tg('sendMessage',{'chat_id':uid,'text':'All personal bot alerts are now off. Send /start to rejoin.'})
    cb=update.get('callback_query') or {}
    data=cb.get('data',''); user=cb.get('from') or {}
    if not cb or not user.get('id'): return
    uid=int(user['id'])
    if office_only() and not data.startswith('admin:'): return
    # Only accept callbacks originally sent in the member's private DM.
    cb_chat=(cb.get('message') or {}).get('chat') or {}
    if cb_chat and (cb_chat.get('type')!='private' or cb_chat.get('id')!=uid):
        await tg('answerCallbackQuery',{'callback_query_id':cb['id'],'text':'Open the ministry bot privately to change alerts.'})
        return
    if data.startswith('admin:'):
        from app.admin_bot import handle_admin_callback
        await handle_admin_callback(uid,data,tg,cb['id'])
        return
    with connect() as db:
        started=db.execute('SELECT stopped_at FROM members WHERE telegram_id=?',(uid,)).fetchone()
        if not started or started['stopped_at'] is not None:
            answer='Send /start privately before choosing preferences.'
        elif data=='stop:all':
            db.execute('UPDATE preferences SET enabled=0 WHERE telegram_id=?',(uid,))
            db.execute('UPDATE event_subscriptions SET enabled=0 WHERE telegram_id=?',(uid,))
            db.execute('UPDATE members SET stopped_at=? WHERE telegram_id=?',(now_iso(),uid))
            answer='All alerts disabled.'
        elif data.startswith('event:'):
            ev_id=data[6:]
            exists=db.execute('SELECT event_id FROM events WHERE event_id=? AND public_ok=1 AND is_private=0',(ev_id,)).fetchone()
            if not exists: answer='This event is not available for reminders.'
            else:
                old=db.execute('SELECT enabled FROM event_subscriptions WHERE telegram_id=? AND event_id=?',(uid,ev_id)).fetchone()
                new=0 if old and old['enabled'] else 1
                db.execute('''INSERT INTO event_subscriptions(telegram_id,event_id,enabled) VALUES(?,?,?)
                      ON CONFLICT(telegram_id,event_id) DO UPDATE SET enabled=excluded.enabled''',(uid,ev_id,new))
                answer='Event reminders '+('enabled.' if new else 'disabled.')
        elif data.startswith('pref:') and data[5:] in TOPICS:
            topic=data[5:]
            old=db.execute('SELECT enabled FROM preferences WHERE telegram_id=? AND topic=?',(uid,topic)).fetchone()
            new=0 if old and old['enabled'] else 1
            db.execute('''INSERT INTO preferences(telegram_id,topic,enabled) VALUES(?,?,?)
                  ON CONFLICT(telegram_id,topic) DO UPDATE SET enabled=excluded.enabled''',(uid,topic,new))
            answer=f"{TOPICS[topic]} {'enabled' if new else 'disabled'}."
        else:
            answer='Unknown action.'
    await tg('answerCallbackQuery',{'callback_query_id':cb['id'],'text':answer,'show_alert':False})

def audience_chat_id(audience):
    env=AUDIENCES.get(audience)
    return setting(env) if env else ''
