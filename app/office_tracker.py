"""PPM office task and staff-access tracker. No public broadcasts.

All writes use the same persistent SQLite volume as the bot. A Telegram group
membership is never sufficient authorization to use office workflows.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import re
from app.storage import connect, now_iso, audit

ET=ZoneInfo('America/New_York')
STAFF_ROLES={'coordinator','worker'}
TASK_STATUSES={'UNASSIGNED','ASSIGNED','CONFIRMED','DECLINED','DONE','CANCELED'}


def ensure(db):
    db.execute('''CREATE TABLE IF NOT EXISTS office_access_requests (
         telegram_id INTEGER PRIMARY KEY, first_name TEXT NOT NULL,
         username TEXT NOT NULL DEFAULT '', requested_at TEXT NOT NULL,
         chat_id INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'PENDING')''')
    db.execute('''CREATE TABLE IF NOT EXISTS office_staff (
         telegram_id INTEGER PRIMARY KEY, first_name TEXT NOT NULL,
         username TEXT NOT NULL DEFAULT '', role TEXT NOT NULL,
         added_by INTEGER NOT NULL, added_at TEXT NOT NULL,
         active INTEGER NOT NULL DEFAULT 1)''')
    db.execute('''CREATE TABLE IF NOT EXISTS office_tasks (
        task_id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL, title TEXT NOT NULL,
        due_date TEXT NOT NULL, due_time TEXT NOT NULL DEFAULT '',
        assignee_id INTEGER, status TEXT NOT NULL,
        created_by INTEGER NOT NULL, created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL, confirmed_at TEXT,
        UNIQUE(chat_id,title,due_date))''')


def staff_role(uid):
    with connect() as db:
        ensure(db)
        row=db.execute('SELECT role FROM office_staff WHERE telegram_id=? AND active=1',(uid,)).fetchone()
        return row['role'] if row else 'none'


def request_access(user,chat_id):
    uid=int(user['id']);name=str(user.get('first_name') or 'Team member')[:90]
    username=str(user.get('username') or '')[:60]
    with connect() as db:
        ensure(db)
        existing=db.execute('SELECT active FROM office_staff WHERE telegram_id=?',(uid,)).fetchone()
        if existing and existing['active']:
            return 'You already have an approved office role.'
        db.execute('''INSERT INTO office_access_requests(telegram_id,first_name,username,requested_at,chat_id,status)
             VALUES(?,?,?,?,?,'PENDING')
             ON CONFLICT(telegram_id) DO UPDATE SET first_name=excluded.first_name,username=excluded.username,
             requested_at=excluded.requested_at,chat_id=excluded.chat_id,status='PENDING' ''',
             (uid,name,username,now_iso(),chat_id))
    audit(f'telegram:{uid}','staff_access_requested',{'chat_id':chat_id})
    return 'Office access request recorded. The owner must approve it. Nothing is granted automatically.'


def requests_text():
    with connect() as db:
        ensure(db)
        rows=db.execute("SELECT telegram_id,first_name,username FROM office_access_requests WHERE status='PENDING' ORDER BY requested_at LIMIT 20").fetchall()
    if not rows:return 'No pending staff requests.'
    return 'PPM STAFF REQUESTS — OWNER REVIEW\n\n'+'\n'.join(f"{r['first_name']} (@{r['username'] or 'no_username'}) — ID {r['telegram_id']}" for r in rows)+'\n\nApprove only a verified worker:\n/staffadd ID worker\n/staffadd ID coordinator'


def add_staff(owner_id,target_id,role):
    if role not in STAFF_ROLES or target_id<=0: return 'Use: /staffadd TELEGRAM_ID worker or /staffadd TELEGRAM_ID coordinator.'
    with connect() as db:
        ensure(db)
        req=db.execute("SELECT * FROM office_access_requests WHERE telegram_id=? AND status='PENDING'",(target_id,)).fetchone()
        if not req:return 'There is no pending access request from that ID. Ask them to send /requestaccess to @PPMOfficeBot privately or in the office group.'
        db.execute('''INSERT INTO office_staff(telegram_id,first_name,username,role,added_by,added_at,active)
           VALUES(?,?,?,?,?,?,1) ON CONFLICT(telegram_id) DO UPDATE SET
           first_name=excluded.first_name,username=excluded.username,role=excluded.role,
           added_by=excluded.added_by,added_at=excluded.added_at,active=1''',
           (target_id,req['first_name'],req['username'],role,owner_id,now_iso()))
        db.execute("UPDATE office_access_requests SET status='APPROVED' WHERE telegram_id=?",(target_id,))
    audit(f'telegram:{owner_id}','staff_approved',{'id':target_id,'role':role})
    return f"Access approved for {req['first_name']} — role: {role}. Ask them to open @PPMOfficeBot privately and send /start."


def remove_staff(owner_id,target_id):
    with connect() as db:
        ensure(db)
        cur=db.execute('UPDATE office_staff SET active=0 WHERE telegram_id=? AND active=1',(target_id,))
        count=cur.rowcount
    if count:audit(f'telegram:{owner_id}','staff_revoked',{'id':target_id})
    return ('Office access revoked for that account.' if count else 'That ID does not have an active office staff role.')


def staff_text():
    with connect() as db:
        ensure(db)
        rows=db.execute('SELECT telegram_id,first_name,username,role FROM office_staff WHERE active=1 ORDER BY role,first_name').fetchall()
    if not rows:return 'No additional staff accounts have been approved yet. The owner can approve requests privately.'
    return 'PPM APPROVED OFFICE STAFF\n\n'+'\n'.join(f"{r['first_name']} — {r['role']} ({'@'+r['username'] if r['username'] else 'ID '+str(r['telegram_id'])})" for r in rows)


def due_on(value):
    if value.strip().lower() in ('today','tonight'): return datetime.now(ET).date().isoformat()
    if value.strip().lower() == 'tomorrow': return (datetime.now(ET).date()+timedelta(days=1)).isoformat()
    if value.strip().lower() == 'yesterday': return (datetime.now(ET).date()-timedelta(days=1)).isoformat()
    try: return date.fromisoformat(value.strip()).isoformat()
    except ValueError: return None


def _linked_chat(db):
    row=db.execute('SELECT chat_id FROM office_groups LIMIT 1').fetchone()
    return int(row['chat_id']) if row else None


def _resolve_person(db,descriptor):
    name=descriptor.strip()
    if name.lower() in ('open','unassigned','none','vacant','tbd'):return None
    if name.isdecimal():
        row=db.execute('SELECT telegram_id FROM office_staff WHERE telegram_id=? AND active=1',(int(name),)).fetchone()
    elif name.startswith('@') and re.fullmatch(r'@[A-Za-z0-9_]{4,60}',name):
        row=db.execute('SELECT telegram_id FROM office_staff WHERE lower(username)=? AND active=1',(name[1:].lower(),)).fetchone()
    else:
        row=None
    return int(row['telegram_id']) if row else 'INVALID'


def _display_person(db,uid):
    if uid is None:return 'OPEN — worker not assigned'
    row=db.execute('SELECT first_name,username FROM office_staff WHERE telegram_id=?',(uid,)).fetchone()
    if not row:return f'ID {uid}'
    return row['first_name'] + (' (@'+row['username']+')' if row['username'] else '')


def create_assignment(actor,chat_id,command):
    # /assign Zoom host | @username | 2026-10-13 | 6 PM
    parts=[x.strip() for x in command.split('|')]
    if len(parts) not in (3,4): return 'Format: /assign Task | @username (or open) | today (or YYYY-MM-DD) | optional time\nExample: /assign Zoom host | open | today | 6 PM'
    title,person,day=parts[:3]; when=parts[3] if len(parts)==4 else ''
    dt=due_on(day)
    if not (4<=len(title)<=110 and dt and len(when)<=30 and len(person)<=80):return 'Invalid task, worker, date or time. Use /assign Task | @username (or open) | today | 6 PM'
    if any(x in title.casefold() for x in ('passport number','social security','medical diagnosis','bank details')):
        return 'Do not store sensitive member information in office assignment titles.'
    with connect() as db:
        ensure(db)
        uid=_resolve_person(db,person)
        if uid=='INVALID':return 'That worker is not approved yet. Ask them to use /requestaccess; owner reviews via /requests in private chat.'
        existing=db.execute('SELECT task_id FROM office_tasks WHERE chat_id=? AND title=? AND due_date=?',(chat_id,title,dt)).fetchone()
        if existing:
            old=db.execute('SELECT status FROM office_tasks WHERE task_id=?',(existing['task_id'],)).fetchone()['status']
            if old=='DONE': return 'This task is already completed. Choose a different title if you mean a new assignment.'
            db.execute('''UPDATE office_tasks SET assignee_id=?,due_time=?,status=?,updated_at=?,confirmed_at=NULL WHERE task_id=?''',
                  (uid,when,'ASSIGNED' if uid else 'UNASSIGNED',now_iso(),existing['task_id']))
            task_id=int(existing['task_id'])
        else:
            cur=db.execute('''INSERT INTO office_tasks(chat_id,title,due_date,due_time,assignee_id,status,created_by,created_at,updated_at)
                 VALUES(?,?,?,?,?,?,?,?,?)''',(chat_id,title,dt,when,uid,'ASSIGNED' if uid else 'UNASSIGNED',actor,now_iso(),now_iso()))
            task_id=cur.lastrowid
        person_label=_display_person(db,uid)
    audit(f'telegram:{actor}','office_task_assigned',{'id':task_id,'assignee':uid,'day':dt})
    return f'ASSIGNMENT #{task_id} SAVED\n{title} — {dt}'+(f' at {when}' if when else '')+f'\nResponsible: {person_label}\nStatus: {"Awaiting their confirmation" if uid else "UNASSIGNED"}\n\nWorker: /confirm {task_id} or /decline {task_id}. Nothing is assumed confirmed.'


def list_tasks(chat_id,view='pending',user_id=None,day=None):
    with connect() as db:
        ensure(db)
        query='SELECT * FROM office_tasks WHERE chat_id=?';args=[chat_id]
        if view=='pending': query+=" AND status NOT IN ('DONE','CANCELED')"
        if view=='today': query+=' AND due_date=?';args.append(day or datetime.now(ET).date().isoformat())
        if view=='mine':query+=' AND assignee_id=?';args.append(user_id)
        query+=' ORDER BY due_date,due_time,task_id LIMIT 35'
        tasks=db.execute(query,args).fetchall()
        if not tasks:return ('No tasks have been recorded in the live tracker yet. Owner or coordinator: run /setupday or /assign.' if view!='mine' else 'No assignments are recorded for your account.')
        today=datetime.now(ET).date().isoformat()
        out=[f'PPM LIVE TASK TRACKER — {view.upper()}','(Recorded confirmations only; no assumed completions)','']
        for t in tasks:
            icon='✓' if t['status']=='DONE' else '•'
            due=('TODAY' if t['due_date']==today else t['due_date']) + (' '+t['due_time'] if t['due_time'] else '')
            who=_display_person(db,t['assignee_id'])
            out.append(f"{icon} #{t['task_id']} {t['title']}\n    {due} · {who}\n    {t['status']}")
        out.append('\nWorker: /confirm ID, /decline ID, /done ID.\nCoordinator: /assign Task | @username | today | time')
        return '\n\n'.join(out)[:3800]


def update_task(actor,chat_id,task_id,verb,is_coordinator=False):
    with connect() as db:
        ensure(db)
        row=db.execute('SELECT * FROM office_tasks WHERE task_id=? AND chat_id=?',(task_id,chat_id)).fetchone()
        if not row:return f'Assignment #{task_id} not found in this office group.'
        if row['assignee_id']!=actor:
            return 'Only the assigned worker can confirm or decline this assignment.'
        previous=row['status']
        status={'confirm':'CONFIRMED','decline':'DECLINED','done':'DONE'}.get(verb)
        allowed={'confirm':('ASSIGNED','DECLINED'),'decline':('ASSIGNED','CONFIRMED'),'done':('CONFIRMED',)}
        if previous not in allowed.get(verb,()):return f'Cannot {verb} assignment #{task_id} while status is {previous}. Ask Michelle to reassign if needed.'
        db.execute('UPDATE office_tasks SET status=?,updated_at=?,confirmed_at=? WHERE task_id=?',
                   (status,now_iso(),now_iso() if verb=='confirm' else row['confirmed_at'],task_id))
    audit(f'telegram:{actor}','office_task_'+verb,{'id':task_id})
    return f'Assignment #{task_id} — {row["title"]}\nStatus: {status}. Recorded in the live office tracker.'


def seed_day(actor,chat_id,day=None):
    d=date.fromisoformat(day) if isinstance(day,str) else (day or datetime.now(ET).date())
    wd=d.weekday();fasting=date(2026,10,11)<=d<=date(2026,11,9)
    roles=[]
    if wd in (0,2,4):roles+= [('Morning Prayer lead','9 AM'),('Morning Prayer Zoom host','9 AM')]
    if fasting:
        roles+= [('Zoom prayer leader','6 PM'),('Corporate prayer Zoom host','6 PM'),('Prayer backup','6 PM')]
        if wd!=6:roles+= [('YouTube moderator','7 PM'),('YouTube media coverage','7 PM')]
    if wd == 5 and fasting and d != date(2026,10,24):
        roles += [('Spiritual Foundation mentorship host','2 PM')]
    if date(2026,10,21) <= d <= date(2026,10,24):
        roles += [('Watchman Series Zoom host','2 PM'),('Watchman Series moderator','2 PM')]
    if d in (date(2026,10,16),date(2026,10,23),date(2026,10,30)):
        roles+= [('Friday Encounter ushers','7 PM'),('Friday Encounter AV','7 PM')]
    roles+=[('Connections follow-up coverage',''),('Office call-back coverage','')]
    count=0
    with connect() as db:
        ensure(db)
        for title,at in roles:
            cur=db.execute('''INSERT OR IGNORE INTO office_tasks(chat_id,title,due_date,due_time,assignee_id,status,created_by,created_at,updated_at)
              VALUES(?,?,?,?,NULL,'UNASSIGNED',?,?,?)''',(chat_id,title,d.isoformat(),at,actor,now_iso(),now_iso()))
            count+=cur.rowcount
    if count:audit(f'telegram:{actor}','office_day_setup',{'day':d.isoformat(),'created':count})
    return f'{d.isoformat()} office shift created: {count} new, unassigned roles.\nSend /pending to see them. Use /assign Task | @username | today | time to assign. Nothing was automatically confirmed.'


def daily_report(chat_id, day=None):
    """Owner/coordinator-facing facts from recorded tasks, never guessed attendance.

    Program completion, attendance, and actual service quality are *not* inferred
    from assignment status. The live report is deliberately marked as incomplete
    until people record their work.
    """
    date_value = day or datetime.now(ET).date().isoformat()
    if isinstance(date_value, date): date_value = date_value.isoformat()
    if not date_value or not isinstance(date_value, str):
        return 'Choose a valid date for the report.'
    with connect() as db:
        ensure(db)
        records=db.execute("SELECT * FROM office_tasks WHERE chat_id=? AND due_date=? ORDER BY due_time,task_id",(chat_id,date_value)).fetchall()
        counts={s:0 for s in TASK_STATUSES}
        for t in records: counts[t['status']]+=1
        total=len(records)
        not_ready=counts['UNASSIGNED']+counts['ASSIGNED']+counts['DECLINED']
        lines=[f'PPM OFFICE REPORT — {date_value}',
               'Recorded assignment status only — not proof a ministry program happened.', '',
               f'Positions recorded: {total}',
               f'OPEN / UNASSIGNED: {counts["UNASSIGNED"]}',
               f'AWAITING CONFIRMATION: {counts["ASSIGNED"]}',
               f'WORKERS DECLINED: {counts["DECLINED"]}',
               f'CONFIRMED TO SERVE: {counts["CONFIRMED"]}',
               f'MARKED COMPLETE: {counts["DONE"]}',
               f'CANCELED: {counts["CANCELED"]}', '',
               f'NEEDS ATTENTION: {not_ready} position(s)']
        if not records:
            lines.extend(['','No assignments entered for this day.',
                          'Coordinator: use /setupday and /assign before checking reports.'])
        else:
            problems=[t for t in records if t['status'] in ('UNASSIGNED','ASSIGNED','DECLINED')]
            if problems:
                lines.extend(['','UNRESOLVED POSITIONS'])
                for t in problems[:20]:
                    who=_display_person(db,t['assignee_id'])
                    lines.append(f'#{t["task_id"]} {t["title"]} — {t["status"]} ({who})')
                if len(problems)>20: lines.append(f'...and {len(problems)-20} more; check /pending.')
            completed=[t for t in records if t['status']=='DONE']
            if completed:
                lines.extend(['','COMPLETED ASSIGNMENTS (STAFF-RECORDED)'])
                for t in completed[:12]: lines.append(f'#{t["task_id"]} {t["title"]} — {_display_person(db,t["assignee_id"])}')
                if len(completed)>12:lines.append(f'...and {len(completed)-12} more.')
        lines.extend(['','MANUAL FOLLOW-UP FOR MICHELLE:',
                      'Confirm what programs occurred, who actually served, any issues, and tomorrow’s preparations.',
                      'A task marked DONE is a worker report, not independently verified attendance.'])
        return '\n'.join(lines)[:3800]


async def notify_assignee(group_id, saved_assignment_message, send_tg):
    """Best-effort private notice to an approved assignee, not a public campaign.

    A group command remains successful if Telegram prohibits the bot from
    opening a private chat. Workers may always check /mytasks themselves.
    """
    match=re.match(r'ASSIGNMENT #(\d+) SAVED\b', saved_assignment_message or '')
    if not match:
        return ''
    task_id=int(match.group(1))
    with connect() as db:
        ensure(db)
        row=db.execute('''SELECT t.*, s.active FROM office_tasks t JOIN office_staff s
                ON s.telegram_id=t.assignee_id WHERE t.task_id=? AND t.chat_id=?''',
                (task_id,group_id)).fetchone()
    if not row or row['status']!='ASSIGNED' or not row['active']:
        return ''
    uid=int(row['assignee_id'])
    msg=(f'PPM OFFICE — NEW ASSIGNMENT #{task_id}\n'
         f'{row["title"]}\nDate: {row["due_date"]}'
         + (f' · {row["due_time"]}' if row['due_time'] else '')
         + f'\n\nPlease reply with /confirm {task_id} or /decline {task_id}. '
         'After serving, use /done '+str(task_id)+'. '
         'Nobody is marked confirmed until you personally confirm.')
    try:
        await send_tg('sendMessage',{'chat_id':uid,'text':msg})
        audit('office','assignment_notice_sent',{'task_id':task_id,'to':uid})
        return '\n\nWorker notified privately. Confirmation is still required.'
    except Exception:
        audit('office','assignment_notice_failed',{'task_id':task_id,'to':uid})
        return ('\n\nTelegram could not DM the worker. Ask them to open @PPMOfficeBot, '
                'send /start, and then /mytasks. Assignment remains unconfirmed.')
