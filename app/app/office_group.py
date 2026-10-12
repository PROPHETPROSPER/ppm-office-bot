"""Small, intentionally non-sensitive group interface for the PPM Office Bot.

A verified owner must link one private staff group using /linkoffice@PPMOfficeBot.
Role-specific publication, draft review and permissions stay exclusively in DMs.
"""
from datetime import datetime, date
from zoneinfo import ZoneInfo

from app.settings import setting
from app.roles import role_for
from app.storage import connect, now_iso, audit

COMMANDS = {'/start', '/help', '/today', '/schedule', '/team', '/pending', '/status', '/linkoffice', '/unlinkoffice'}
PRIVATE_ONLY = {'/new', '/queue', '/preview', '/draft', '/approve', '/reject', '/send', '/alerts', '/connections', '/report'}


def _programs(today: date):
    wd = today.weekday()
    fasting = date(2026, 10, 11) <= today <= date(2026, 11, 9)
    events = []
    if wd in (0, 2, 4):
        events.append('9:00 AM ET — Morning Prayer')
    if fasting:
        events.append('6:00–7:00 PM ET — Divine Visitation Zoom Prayer')
        if wd != 6:
            events.append('7:00–9:00 PM ET — Divine Visitation YouTube Teaching / Friday Encounter')
    if wd == 5 and today != date(2026, 10, 24):
        events.append('2:00 PM ET — Paid Spiritual Foundation Mentorship (members only)')
    if date(2026, 10, 21) <= today <= date(2026, 10, 24):
        events.append('2:00–4:00 PM ET — Authority Over Resistance, Watchman Series')
    if today == date(2026, 10, 24):
        events.append('NOTE: Saturday mentorship overlaps Watchman Series. Verify the replacement time.')
    return events


def _today_text(now=None):
    local = now or datetime.now(ZoneInfo('America/New_York'))
    events = _programs(local.date())
    return ('PPM OFFICE — ' + local.strftime('%A, %B %-d, %Y').upper() + '\n\n'
            + 'PROGRAMS\n' + ('\n'.join(events) if events else 'No daily program confirmed in the bot for today.')
            + '\n\nOPERATIONS CHECK\n'
            '• Confirm hosts and prayer leaders with Michelle.\n'
            '• Verify livestream links, media coverage and moderation.\n'
            '• Check connection follow-ups and unresolved incidents.\n'
            '• Report unconfirmed assignments before service.\n\n'
            'Note: Staff confirmations are not yet synced with a live tracker. '
            'Use /pending for checks, not proof of completion.')


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
    if role == 'none':
        # Never disclose office data in a public group where the bot was added.
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
                    '/today — Today’s operational briefing\n'
                    '/schedule — Ministry programs and exceptions\n'
                    '/team — Proposed team responsibilities\n'
                    '/pending — Outstanding confirmation checklist\n'
                    '/status — Bot readiness status\n\n'
                    'Drafting, queue review, and approvals take place PRIVATELY at @PPMOfficeBot. '
                    'Only people individually approved by the owner have those permissions.')
    elif cmd == '/today':
        await reply(_today_text())
    elif cmd == '/schedule':
        await reply('PPM PROGRAM SCHEDULE (Eastern Time)\n\n'
                    '• Morning Prayer: Monday / Wednesday / Friday, 9 AM.\n'
                    '• Divine Visitation Zoom prayer: daily, 6–7 PM, Oct 11–Nov 9.\n'
                    '• YouTube Teaching: Monday–Saturday, 7–9 PM during the fast. No regular Sunday teaching.\n'
                    '• Paid Spiritual Foundation: Saturdays, 2 PM, except Oct 24 conflict.\n'
                    '• Watchman Series: Oct 21–24, 2–4 PM.\n\n'
                    'Check current approved links with Michelle. Do not share private mentorship links in this group.')
    elif cmd == '/team':
        await reply('PPM STAFF COORDINATION — ROLES TO CONFIRM\n\n'
                    '• Michelle — Operations and Connections Coordinator.\n'
                    '• Crystal and Adjovi — prospective prayer leaders.\n'
                    '• Jia Jis — prospective YouTube moderator.\n'
                    '• Davanee — communications support, availability unconfirmed.\n'
                    '• Amoy or Alex — prospective video editing.\n'
                    '• Graphic designer, two connections assistants, two office callers, backup leaders — vacancies.\n\n'
                    'IMPORTANT: This is a proposed roster, not confirmed attendance. Only Michelle can verify accepted assignments.')
    elif cmd == '/pending':
        await reply('PPM OPEN CONFIRMATIONS (NOT A LIVE TRACKER)\n\n'
                    '1. Confirm tonight’s Zoom host and prayer leader.\n'
                    '2. Confirm YouTube moderator and media worker.\n'
                    '3. Confirm prayer-leader backups.\n'
                    '4. Recruit graphics support, two connections assistants and two office callers.\n'
                    '5. Confirm that first-time visitor follow-ups are assigned.\n\n'
                    'Michelle: please report what is actually completed. No worker or task is assumed confirmed until recorded.')
    elif cmd == '/status':
        sending = setting('LIVE_SENDING_ENABLED', 'false').lower() == 'true'
        scheduler = setting('PPM_SCHEDULER_ENABLED', 'false').lower() == 'true'
        await reply('PPM OFFICE BOT STATUS\n'
                    '• Group linked: Yes\n'
                    '• Office commands: Enabled for assigned roles\n'
                    f'• Automatic publishing: {"ON" if sending else "OFF (private test)"}\n'
                    f'• Background scheduler: {"ON" if scheduler else "OFF (private test)"}\n'
                    '• Staff tracker: Not yet connected\n'
                    '• Publishing approvals: Private bot chat only')
    elif cmd in PRIVATE_ONLY:
        await reply('For security, please open @PPMOfficeBot privately and send ' + cmd + '. This group cannot draft, approve, or publish announcements.')
