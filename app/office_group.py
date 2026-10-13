"""Small, intentionally non-sensitive group interface for the PPM Office Bot.

A verified owner must link one private staff group using /linkoffice@PPMOfficeBot.
Role-specific publication, draft review and permissions stay exclusively in DMs.
"""
from datetime import datetime, date
from zoneinfo import ZoneInfo

from app.settings import setting
from app.roles import role_for
from app.storage import connect, now_iso, audit

COMMANDS = {'/start', '/help', '/today', '/schedule', '/team', '/pending', '/status', '/linkoffice', '/unlinkoffice', '/assign', '/setupday', '/mytasks', '/confirm', '/decline', '/done', '/requestaccess', '/myid', '/report'}
PRIVATE_ONLY = {'/new', '/queue', '/preview', '/draft', '/approve', '/reject', '/send', '/alerts', '/connections'}


def _programs(today: date):
    wd = today.weekday()
    fasting = date(2026, 10, 11) <= today <= date(2026, 11, 9)
    events = []
    if wd in (0, 2, 4):
        events.append('9:00 AM ET — Morning Prayer')
    if fasting:
        events.append('6:00–7:00 PM ET — Divine Visitation Zoom Prayer')
        if wd != 6:
            events.append('7:00–9:00 PM ET — Divine Visitation YouTube Teaching')
    if today in (date(2026,10,16),date(2026,10,23),date(2026,10,30)):
        events.append('7:00 PM ET — Friday Encounter (in person); confirm overlap with online teaching')
    if wd == 5 and today != date(2026, 10, 24):
        events.append('2:00 PM ET — Paid Spiritual Foundation Mentorship (members only)')
    if date(2026, 10, 21) <= today <= date(2026, 10, 24):
        events.append('2:00–4:00 PM ET — Authority Over Resistance, Watchman Series')
    if today == date(2026, 10, 24):
        events.append('NOTE: Saturday mentorship overlaps Watchman Series. Verify the replacement time.')
    return events


def _today_text(now=None, chat_id=None):
    local = now or datetime.now(ZoneInfo('America/New_York'))
    events = _programs(local.date())
    from app.office_tracker import list_tasks
    status = list_tasks(chat_id,'today',day=local.date().isoformat()) if chat_id else 'Live office tracker available in the linked group via /today.'
    return ('PPM OFFICE — ' + local.strftime('%A, %B %-d, %Y').upper() + '\n\n'
            + 'PROGRAMS\n' + ('\n'.join(events) if events else 'No daily program confirmed in the bot for today.')
            + '\n\nTODAY’S STAFF ASSIGNMENTS\n' + status + '\n\n'
            'NEXT ACTION: Michelle should assign open roles; workers confirm their own shifts. '
            'No confirmation is assumed without a recorded /confirm.')


async def handle_office_group_message(message, tg):
    chat = message.get('chat') or {}
    user = message.get('from') or {}
    text = (message.get('text') or '').strip()
    if not text.startswith('/') or not user.get('id') or not chat.get('id'):
        return
    # Ignore commands specifically addressed to another bot in a group.
    first = text.split(maxsplit=1)[0]
    name = setting('PPM_EXPECTED_BOT_USERNAME', 'PPMOfficeBot').lstrip('@').casefold()
    if '@' in first and first.split('@', 1)[1].casefold() != name:
        return
    cmd = first.split('@', 1)[0].lower()
    if cmd not in COMMANDS | PRIVATE_ONLY:
        return
    uid = int(user['id'])
    chat_id = int(chat['id'])
    role = role_for(uid)
    if role == 'none' and cmd not in ('/requestaccess','/myid'):
        # Never disclose office data to an unapproved member.
        return

    def is_private_group():
        return chat.get('type') in ('group', 'supergroup')

    async def reply(txt):
        return await tg('sendMessage', {'chat_id': chat_id, 'text': txt[:3900]})

    if cmd == '/linkoffice':
        if role != 'owner':
            await reply('Only the ministry bot owner can link an office group.')
            return
        if not is_private_group():
            return
        if chat.get('username'):
            await reply('Only a private office group without a public @username may be linked. Remove its public username first.')
            return
        # Link one group at a time; owner can intentionally move it to a replacement group.
        with connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS office_groups (chat_id INTEGER PRIMARY KEY, title TEXT NOT NULL, linked_by INTEGER NOT NULL, linked_at TEXT NOT NULL)')
            db.execute('DELETE FROM office_groups')
            db.execute('INSERT INTO office_groups(chat_id,title,linked_by,linked_at) VALUES(?,?,?,?)',
                       (chat_id, str(chat.get('title') or 'PPM Office Group')[:120], uid, now_iso()))
        audit(f'telegram:{uid}', 'office_group_linked', {'chat_id': chat_id})
        await reply('PPM OFFICE GROUP CONNECTED.\n\nStaff commands are now available here: /today, /schedule, /team, /pending, /status.\n\nSensitive actions (/new, /queue, approvals, publishing) stay in private messages with @PPMOfficeBot. Joining this group does not grant bot admin permissions.')
        return

    with connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS office_groups (chat_id INTEGER PRIMARY KEY, title TEXT NOT NULL, linked_by INTEGER NOT NULL, linked_at TEXT NOT NULL)')
        linked = db.execute('SELECT chat_id FROM office_groups WHERE chat_id=?', (chat_id,)).fetchone() is not None
    if not linked:
        if role == 'owner' and cmd in COMMANDS:
            await reply('This group is not linked yet. As the bot owner, send /linkoffice@PPMOfficeBot here. Group commands are restricted until linked.')
        return

    from app.office_tracker import request_access, create_assignment, list_tasks, update_task, seed_day, staff_text, daily_report, due_on, notify_assignee
    arg = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) == 2 else ''
    if cmd == '/myid':
        await reply(f'Your Telegram ID: {uid}.\nOnly the bot owner may approve access.')
        return
    if cmd == '/requestaccess':
        await reply(request_access(user,chat_id))
        return
    if role == 'none':
        return
    if cmd == '/setupday':
        if role not in ('owner','coordinator'):
            await reply('Only the owner or approved operations coordinator may create an office shift.')
        else:
            day=due_on(arg) if arg else None
            await reply(seed_day(uid,chat_id,day=day) if day or not arg else 'Use /setupday today, tomorrow, or YYYY-MM-DD.')
        return
    if cmd == '/report':
        if role not in ('owner','coordinator'):
            await reply('Daily reports are restricted to the owner and approved coordinator.')
        elif arg and not due_on(arg):
            await reply('Use /report today, yesterday, or YYYY-MM-DD.')
        else:
            await reply(daily_report(chat_id,due_on(arg) if arg else None))
        return
    if cmd == '/assign':
        if role not in ('owner','coordinator'):
            await reply('Only the owner or approved coordinator can assign staff.')
        else:
            answer=create_assignment(uid,chat_id,arg)
            notice=await notify_assignee(chat_id,answer,tg)
            await reply(answer+notice)
        return
    if cmd in ('/confirm','/decline','/done'):
        if not arg.isdecimal():
            await reply('Use /'+cmd[1:]+' ASSIGNMENT_ID, for example /confirm 12.')
        else:
            await reply(update_task(uid,chat_id,int(arg),cmd[1:]))
        return
    if cmd == '/mytasks':
        await reply(list_tasks(chat_id,'mine',uid))
        return
    if cmd == '/unlinkoffice':
        if role != 'owner':
            await reply('Only the ministry bot owner can unlink the office group.')
            return
        with connect() as db:
            db.execute('DELETE FROM office_groups WHERE chat_id=?', (chat_id,))
        audit(f'telegram:{uid}', 'office_group_unlinked', {'chat_id': chat_id})
        await reply('Office group unlinked. No office commands will be processed here unless linked again.')
    elif cmd in ('/start', '/help'):
        await reply('PROPHET PROSPER MINISTRIES — OFFICE\n\n'
                    'Shared group commands:\n'
                    '/requestaccess — Request owner approval for office access\n'
                    '/setupday — Create today’s unassigned shift roles (owner/coordinator)\n'
                    '/assign Task | @username | today | time — Assign a worker\n'
                    '/mytasks — View your responsibilities\n'
                    '/confirm ID, /decline ID, /done ID — Update your own tasks\n'
                    '/report — Daily assignment status report (owner/coordinator)\n'
                    '/today — Today’s operational briefing\n'
                    '/schedule — Ministry programs and exceptions\n'
                    '/team — Approved office staff\n'
                    '/pending — Live outstanding assignments\n'
                    '/status — Bot readiness status\n\n'
                    'Drafting, queue review, and approvals take place PRIVATELY at @PPMOfficeBot. '
                    'Only people individually approved by the owner have those permissions.')
    elif cmd == '/today':
        await reply(_today_text(chat_id=chat_id))
    elif cmd == '/schedule':
        await reply('PPM PROGRAM SCHEDULE (Eastern Time)\n\n'
                    '• Morning Prayer: Monday / Wednesday / Friday, 9 AM.\n'
                    '• Divine Visitation Zoom prayer: daily, 6–7 PM, Oct 11–Nov 9.\n'
                    '• YouTube Teaching: Monday–Saturday, 7–9 PM during the fast. No regular Sunday teaching.\n'
                    '• Paid Spiritual Foundation: Saturdays, 2 PM, except Oct 24 conflict.\n'
                    '• Watchman Series: Oct 21–24, 2–4 PM.\n\n'
                    'Check current approved links with Michelle. Do not share private mentorship links in this group.')
    elif cmd == '/team':
        await reply('OFFICE TEAM — APPROVED ACCESS ONLY\n\n'+staff_text()+
                   '\n\nOwner: approve new requests privately using /requests and /staffadd.\nJoining the group alone grants nothing.')
    elif cmd == '/pending':
        await reply(list_tasks(chat_id,'pending'))
    elif cmd == '/status':
        sending = setting('LIVE_SENDING_ENABLED', 'false').lower() == 'true'
        scheduler = setting('PPM_SCHEDULER_ENABLED', 'false').lower() == 'true'
        await reply('PPM OFFICE BOT STATUS\n'
                    '• Group linked: Yes\n'
                    '• Office commands: Enabled for approved staff\n'
                    f'• Automatic publishing: {"ON" if sending else "OFF (private test)"}\n'
                    f'• Background scheduler: {"ON" if scheduler else "OFF (private test)"}\n'
                    '• Staff tracker: ACTIVE (saved on private Railway volume)\n'
                    '• Publishing approvals: Private bot chat only')
    elif cmd in PRIVATE_ONLY:
        await reply('For security, please open @PPMOfficeBot privately and send ' + cmd + '. This group cannot draft, approve, or publish announcements.')
