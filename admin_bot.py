"""Private Telegram operator interface, backed by role-specific grants.

/draft audience|topic|text
/queue, /preview ID, /approve ID, /reject ID, /send ID
Editors may NOT approve; approvers may NOT publish unless explicitly granted.
"""
from app.roles import can,role_for
from app.settings import setting, TOPICS, CONFIDENTIAL_TERMS
from app.storage import connect,now_iso,audit
from app.campaigns import create_draft

COMMAND_PERMISSIONS={
    '/queue':'queue','/preview':'preview','/draft':'draft','/new':'new',
    '/approve':'approve','/reject':'reject','/send':'send'}

def authorized(uid):
    return role_for(uid)!='none'

async def handle_admin_message(uid, text, tg):
    cmd,*rest=text.strip().split(' ',1)
    cmd=cmd.split('@')[0]
    permission=COMMAND_PERMISSIONS.get(cmd)
    async def tell(x):return await tg('sendMessage',{'chat_id':uid,'text':x[:3900]})
    if not permission:
        await tell('Staff commands: /queue, /preview ID, /draft audience|topic|text, /approve ID, /reject ID, /send ID.');return
    if not can(uid,permission):
        await tell('You are not authorized for this action. Ask the ministry owner to grant a specific role.');return
    arg=rest[0].strip() if rest else ''
    actor=f'telegram:{uid}'
    if cmd=='/new':
        with connect() as db:
            db.execute('''INSERT INTO admin_sessions(telegram_id,step,updated_at) VALUES(?,?,?)
                 ON CONFLICT(telegram_id) DO UPDATE SET step=excluded.step,audience=NULL,topic=NULL,updated_at=excluded.updated_at''',
                 (uid,'audience',now_iso()))
        await tg('sendMessage',{'chat_id':uid,'text':'Create announcement — where should it go?',
             'reply_markup':{'inline_keyboard':[[{'text':label,'callback_data':'admin:dest:'+key}]
                    for key,label in [('official','Official channel'),('free','Free mentorship'),('paid','Paid Spiritual Foundation'),('telegram_personal','Personal alerts to opted-in members')]]}})
        return
    if cmd=='/queue':
        with connect() as db:
            pending=db.execute("SELECT draft_id,audience,status,text FROM drafts ORDER BY draft_id DESC LIMIT 10").fetchall()
        detail='\n\n'.join(f"#{r['draft_id']} [{r['audience']} / {r['status']}] {r['text'][:110]}" for r in pending)
        await tell(detail or 'No announcements in the queue.');return
    if cmd=='/draft':
        parts=[p.strip() for p in arg.split('|',2)]
        if len(parts)!=3:
            await tell('Use: /draft official|schools|The approved message. Destinations: official, free, paid, telegram_personal.');return
        audience,topic,msg=parts
        if any(t in msg.casefold() for t in CONFIDENTIAL_TERMS):
            await tell('Confidential owner-only plans are blocked.');return
        try:
            did=create_draft({'audience':audience,'topic':topic,'text':msg})
            audit(actor,'draft_created',{'id':did})
            await tell(f'Draft #{did} created. NOTHING SENT. Approver: /preview {did}, then /approve {did}.')
        except (ValueError,KeyError) as ex:await tell(f'Draft rejected: {ex}')
        return
    if not arg.isdecimal():
        await tell(f'Use: {cmd} 123');return
    did=int(arg)
    with connect() as db:
        r=db.execute('SELECT * FROM drafts WHERE draft_id=?',(did,)).fetchone()
    if not r:await tell('That draft does not exist.');return
    if cmd=='/preview':
        await tell(f"DRAFT #{did}\nDestination: {r['audience']}\nTopic: {r['topic']}\nStatus: {r['status']}\nScheduled: {r['scheduled_at']}\n\n{r['text']}\n\nSending requires approval and live sending enabled.")
        return
    if cmd in ('/approve','/reject'):
        if r['status'] not in ('DRAFT','EXPORT_ONLY'):
            await tell('This announcement is not awaiting approval.');return
        if cmd=='/approve':
            next_state='APPROVED_EXPORT' if r['audience'] in ('clearstream','whatsapp') else 'APPROVED'
        else:next_state='REJECTED'
        with connect() as db:
            db.execute('UPDATE drafts SET status=?,approved_by=?,approved_at=? WHERE draft_id=? AND status IN (\'DRAFT\',\'EXPORT_ONLY\')',
                (next_state,actor,now_iso(),did))
        audit(actor,cmd[1:]+'_draft',{'draft_id':did,'state':next_state})
        await tell(f'Draft #{did}: {next_state}. '+('Nothing sent.' if cmd=='/approve' else 'Draft rejected.'))
        return
    if cmd=='/send':
        from app.dispatch import send_one
        try:
            result=await send_one(did,actor)
            await tell(f"Published approved draft #{did}. Delivered to {result['sent']} destination(s).")
        except Exception as ex:
            await tell(f'Not sent / requires review: {str(ex)[:230]}')


async def handle_admin_callback(uid,data,tg,callback_id):
    """Guided admin message flow; never sends directly."""
    async def tell(text,markup=None):
        body={'chat_id':uid,'text':text}
        if markup:body['reply_markup']=markup
        return await tg('sendMessage',body)
    await tg('answerCallbackQuery',{'callback_query_id':callback_id})
    if not can(uid,'draft'):return
    with connect() as db:
        session=db.execute('SELECT * FROM admin_sessions WHERE telegram_id=?',(uid,)).fetchone()
        if not session:return
        if data.startswith('admin:dest:') and session['step']=='audience':
            aud=data[len('admin:dest:'):]
            if aud not in ('official','free','paid','telegram_personal'):return
            db.execute('UPDATE admin_sessions SET step=?,audience=?,updated_at=? WHERE telegram_id=?',
                       ('topic',aud,now_iso(),uid))
            await tell('Choose a notification category for this announcement:',
                {'inline_keyboard':[[{'text':label,'callback_data':'admin:topic:'+key}]
                    for key,label in TOPICS.items()]})
        elif data.startswith('admin:topic:') and session['step']=='topic':
            topic=data[len('admin:topic:'):]
            if topic not in TOPICS:return
            db.execute('UPDATE admin_sessions SET step=?,topic=?,updated_at=? WHERE telegram_id=?',
                       ('message',topic,now_iso(),uid))
            await tell('Send the exact announcement text as your next message. It will become a DRAFT for approval, not a live post.')

async def handle_admin_free_text(uid,text,tg):
    if not can(uid,'draft'):return False
    with connect() as db:
        session=db.execute('SELECT * FROM admin_sessions WHERE telegram_id=?',(uid,)).fetchone()
    if not session or session['step']!='message':return False
    try:
        did=create_draft({'audience':session['audience'],'topic':session['topic'],'text':text})
        with connect() as db:
            db.execute('DELETE FROM admin_sessions WHERE telegram_id=?',(uid,))
        audit(f'telegram:{uid}','guided_draft_created',{'draft_id':did})
        await tg('sendMessage',{'chat_id':uid,'text':
             f'Draft #{did} saved. NOTHING SENT. Your approver can review it with /preview {did} and /approve {did}.'})
    except Exception as ex:
        await tg('sendMessage',{'chat_id':uid,'text':f'Invalid draft: {str(ex)[:180]}. Please revise your message.'})
    return True
