"""Private 1-on-1 intake and staff routing. Disabled until explicitly configured.

No lead messaging. Imports never imply consent, payment, or a booked session.
Delivery claims persist before Telegram calls; uncertain delivery is never retried.
"""
import asyncio
import hashlib
import json
import re
import threading
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from app.settings import setting
from app.storage import connect, now_iso, audit
from app.office_tracker import staff_role

SHEET_ID = '1dCldUJxv9shtJFifidkZjmWakZpOsyjChFpMb0n1N6o'
TAB = 'Wix 1on1 Registrations'
COLLECTIONS = {'contact12': '1 on 1 Booking Form',
               'Forms/contact12': '1 on 1 Booking Form 2',
               'Forms/contact122': '1 on 1 Booking Form 3'}
HEADERS = ['Submission Time', 'First Name', 'Last Name', 'Ready for 1-1',
           'Full Name', 'Phone', 'Phone Normalized', 'Email', 'Country',
           'Submission ID', 'Form ID', 'SMS Consent', 'Do Not Text', 'SMS Status',
           'Confirmation Status', 'Needs Human Review', 'Notes',
           'Schedule Request Sent', 'Call Status', 'Call Outcome', 'Called At',
           'Preferred Day/Time', 'Confirmation Call Status',
           'Confirmation Called At', 'Wix Form ID (Source)',
           'Verification / Import Status', 'Registration Time (Eastern)']
_sync_lock = threading.Lock()


def ensure(db):
    db.execute('''CREATE TABLE IF NOT EXISTS oneonone_meta (
        key TEXT PRIMARY KEY, value TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS oneonone_requests (
        ref TEXT PRIMARY KEY, submission_id TEXT UNIQUE NOT NULL,
        payload TEXT NOT NULL, fingerprint TEXT NOT NULL, review TEXT NOT NULL,
        historical INTEGER NOT NULL, sheet_state TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'NEW', created_at TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS oneonone_notices (
        ref TEXT NOT NULL REFERENCES oneonone_requests(ref), kind TEXT NOT NULL,
        recipient INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'PENDING',
        message_id INTEGER, updated_at TEXT NOT NULL, PRIMARY KEY(ref,kind))''')


def enabled(name):
    return setting(name, 'false').lower() == 'true'


def staff_id(kind):
    value = setting('PPM_1ON1_' + kind.upper() + '_USER_ID')
    if not value.isdecimal() or int(value) <= 0:
        raise RuntimeError('Configure verified numeric staff IDs first')
    uid = int(value)
    if staff_role(uid) not in ('coordinator', 'worker'):
        raise RuntimeError('Configured recipient does not have approved office access')
    if kind == 'michelle' and staff_role(uid) != 'coordinator':
        raise RuntimeError('Michelle must have existing coordinator access')
    return uid


def source_record(collection, item, fields):
    if collection not in COLLECTIONS:
        raise ValueError('Unapproved Wix collection')
    # The field mapping must be verified against the live collection schema.
    if any(not fields.get(k) for k in ('submitted_at', 'first_name', 'phone', 'email', 'country')):
        raise ValueError('Verified Wix field mapping required')
    data = item.get('data') or {}
    result = {'submission_id': str(item.get('id') or ''), 'collection': collection}
    for key in ('submitted_at', 'first_name', 'last_name', 'phone', 'email', 'country'):
        value = data.get(fields.get(key, ''), '')
        if isinstance(value, dict) and key == 'submitted_at':
            value = value.get('$date', '')
        if value is None:
            value = ''
        if not isinstance(value, (str, int, float)):
            raise ValueError('Unsupported Wix field value; review mapping')
        result[key] = str(value)
    return normalize(result)


def normalize(raw):
    keys = ('submission_id', 'collection', 'submitted_at', 'first_name',
            'last_name', 'phone', 'email', 'country')
    out = {k: str(raw.get(k) or '') for k in keys}
    if not out['submission_id'] or out['collection'] not in COLLECTIONS:
        raise ValueError('Stable Wix ID and approved collection required')
    problems = []
    try:
        dt = datetime.fromisoformat(out['submitted_at'].replace('Z', '+00:00'))
        if dt.tzinfo is None:
            raise ValueError('Timezone absent')
        out['eastern'] = dt.astimezone(ZoneInfo('America/New_York')).strftime('%b %d, %Y, %-I:%M:%S %p %Z')
        if dt > datetime.now(timezone.utc) + timedelta(minutes=5):
            problems.append('Original timestamp is in the future')
    except ValueError:
        out['eastern'] = ''
        problems.append('Missing or invalid original timestamp')
    if not out['first_name'].strip(): problems.append('Missing name')
    if not out['phone'].strip(): problems.append('Missing phone')
    if not out['country'].strip(): problems.append('Missing country')
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', out['email']): problems.append('Missing or invalid email')
    phone = re.sub(r'\D', '', out['phone'])
    out['phone_normalized'] = ''
    if out['phone'].startswith('+') and 8 <= len(phone) <= 15:
        out['phone_normalized'] = '+' + phone
    elif out['country'] in ('United States', 'Canada') and len(phone) == 10:
        out['phone_normalized'] = '+1' + phone
    elif out['country'] in ('United States', 'Canada') and len(phone) == 11 and phone.startswith('1'):
        out['phone_normalized'] = '+' + phone
    elif out['phone']:
        problems.append('Phone format requires manual verification')
    tests = {v.strip().casefold() for v in setting('PPM_1ON1_TEST_EMAILS').split(',') if v.strip()}
    if (out['email'].casefold() in tests or out['email'].casefold().endswith('@example.com')
            or re.search(r'\b(test|verify|smscheck|replytest)\b', out['first_name'] + ' ' + out['last_name'], re.I)):
        problems.append('Likely test; classification provisional')
    out['review'] = '; '.join(problems)
    return out


def sheet_values(p, historical):
    values = [''] * len(HEADERS)
    notes = ('Authoritative Wix source: ' + COLLECTIONS[p['collection']] +
             '; collection ID ' + p['collection'] + '. Form component ID not exposed. '
             'Consent, payment and scheduling not verified. ' + p['review'])
    status = ('LIKELY TEST — review before outreach' if 'Likely test' in p['review'] else
              'REVIEW REQUIRED — ' + p['review'] if p['review'] else
              'WIX SOURCE VERIFIED — ' + ('historical; no alerts' if historical else 'new registration'))
    for i, v in {0: p['submitted_at'], 1: p['first_name'], 2: p['last_name'],
                 4: ' '.join(v for v in (p['first_name'], p['last_name']) if v),
                 5: p['phone'], 6: p['phone_normalized'], 7: p['email'],
                 8: p['country'], 9: p['submission_id'], 10: p['collection'],
                 15: 'TRUE' if p['review'] else '', 16: notes, 24: p['collection'],
                 25: status, 26: p['eastern']}.items():
        values[i] = v
    return values


def sync(source, sheet, baseline=False):
    """Caller provides source/Sheet adapters. First baseline is explicit and silent."""
    if not enabled('PPM_1ON1_ENABLED'):
        raise RuntimeError('1-on-1 integration is disabled')
    with _sync_lock:
        # Complete all reads before touching state, including the empty Form 2.
        records = [normalize(p) for p in source.read_all()]
        unique = {}
        for p in records:
            old = unique.get(p['submission_id'])
            if old and old != p:
                raise ValueError('Conflicting Wix submission ID; sync held')
            unique[p['submission_id']] = p
        sheet_ids = sheet.read_ids()
        if baseline and any(sid not in sheet_ids for sid in unique):
            raise RuntimeError('Baseline has Wix records missing from the Sheet; reconcile first')
        with connect() as db:
            ensure(db)
            marker = db.execute("SELECT value FROM oneonone_meta WHERE key='baseline_at'").fetchone()
            if baseline and marker:
                raise RuntimeError('Baseline already established; refusing to suppress new alerts')
            if not baseline and not marker:
                raise RuntimeError('Establish the silent historical baseline first')
            cutoff = now_iso() if baseline else marker['value']
        counts = {'baseline': baseline, 'seen': len(unique), 'new': 0, 'review': 0, 'appended': 0}
        for p in unique.values():
            sid = p['submission_id']
            ref = hashlib.sha256(sid.encode()).hexdigest()[:20]
            fingerprint = hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()
            historical = baseline or not p['eastern'] or datetime.fromisoformat(p['submitted_at'].replace('Z', '+00:00')) <= datetime.fromisoformat(cutoff)
            with connect() as db:
                ensure(db)
                old = db.execute('SELECT * FROM oneonone_requests WHERE submission_id=?', (sid,)).fetchone()
                if old:
                    if old['fingerprint'] != fingerprint:
                        db.execute("UPDATE oneonone_requests SET review='Wix source changed; manual reconciliation required', status='REVIEW' WHERE ref=?", (old['ref'],))
                        counts['review'] += 1
                    continue
                db.execute('INSERT INTO oneonone_requests(ref,submission_id,payload,fingerprint,review,historical,sheet_state,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
                           (ref, sid, json.dumps(p), fingerprint, p['review'], int(historical),
                            'PRESENT' if sid in sheet_ids else 'PENDING', 'REVIEW' if p['review'] else 'NEW', now_iso()))
            counts['new'] += 1
        # Resume interrupted appends only after re-reading IDs; never overwrite rows.
        with connect() as db:
            pending = db.execute("SELECT * FROM oneonone_requests WHERE sheet_state!='PRESENT'").fetchall()
        for row in pending:
            sid = row['submission_id']
            ids = sheet.read_ids()
            if sid not in ids:
                if row['sheet_state'] == 'UNCERTAIN':
                    raise RuntimeError('Ambiguous Sheet append requires manual reconciliation')
                with connect() as db:
                    claim = db.execute("UPDATE oneonone_requests SET sheet_state='UNCERTAIN' WHERE ref=? AND sheet_state='PENDING'", (row['ref'],))
                    if not claim.rowcount:
                        raise RuntimeError('Another writer claimed this registration; reconcile before retry')
                sheet.append(sheet_values(json.loads(row['payload']), bool(row['historical'])))
                if sid not in sheet.read_ids():
                    raise RuntimeError('Sheet append not verified; sync held')
                counts['appended'] += 1
            with connect() as db:
                db.execute("UPDATE oneonone_requests SET sheet_state='PRESENT' WHERE ref=?", (row['ref'],))
        with connect() as db:
            if baseline:
                db.execute("INSERT INTO oneonone_meta(key,value) VALUES('baseline_at',?)", (cutoff,))
            candidates = db.execute("SELECT ref FROM oneonone_requests WHERE historical=0 AND review='' AND status='NEW' AND sheet_state='PRESENT'").fetchall()
        if candidates:
            michelle = staff_id('michelle')
            with connect() as db:
                for row in candidates:
                    db.execute("INSERT OR IGNORE INTO oneonone_notices(ref,kind,recipient,state,updated_at) VALUES(?,'michelle',?,'PENDING',?)", (row['ref'], michelle, now_iso()))
        audit('oneonone', 'sync', counts)
        return counts


def preview(ref, kind):
    with connect() as db:
        ensure(db)
        row = db.execute('SELECT * FROM oneonone_requests WHERE ref=?', (ref,)).fetchone()
    if not row: raise ValueError('Unknown registration')
    p = json.loads(row['payload'])
    text = (f'PPM OFFICE — {"NEW 1-ON-1 REQUEST" if kind == "michelle" else "CONNECTIONS ASSIGNMENT"}\n'
            f'Name: {p["first_name"]} {p["last_name"]}\nPhone: {p["phone"]}\nEmail: {p["email"]}\n'
            f'Form: {COLLECTIONS[p["collection"]]}\nSubmitted: {p["eastern"] or p["submitted_at"]}\n'
            'Payment: Not verified\nScheduling: Not yet confirmed\n'
            'Staff must contact the person manually; this bot sends no lead messages.')
    actions = [('Send to Crystal', 'route'), ('View Registration', 'view'), ('Disregard', 'disregard')] if kind == 'michelle' else [
        ('Accept Assignment', 'accept'), ('Contacted', 'contacted'), ('Follow Up', 'followup'), ('Scheduled', 'scheduled')]
    buttons = [[{'text': label, 'url': f'https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid=1205524250'}]
               if action == 'view' else [{'text': label, 'callback_data': f'one:{action}:{ref}'}]
               for label, action in actions]
    return {'text': text[:3500], 'reply_markup': {'inline_keyboard': buttons}}


async def deliver(send_tg):
    if not all(enabled(k) for k in ('PPM_1ON1_ENABLED', 'PPM_1ON1_STAFF_ALERTS_ENABLED', 'LIVE_SENDING_ENABLED')):
        return {'sent': 0, 'disabled': True}
    identity = await send_tg('getMe', {})
    if (identity.get('username') or '').casefold() != 'ppmofficebot':
        raise RuntimeError('Telegram identity mismatch; no notices sent')
    michelle, crystal = staff_id('michelle'), staff_id('crystal')
    if michelle == crystal: raise RuntimeError('Staff recipients must be distinct')
    with connect() as db:
        ensure(db)
        pending = db.execute("SELECT n.*, r.status, r.historical, r.review FROM oneonone_notices n JOIN oneonone_requests r ON r.ref=n.ref WHERE n.state='PENDING'").fetchall()
    sent = 0
    for n in pending:
        expected = staff_id(n['kind'])
        if n['recipient'] != expected or n['historical'] or n['review'] or n['status'] not in ('NEW', 'ASSIGNED'):
            continue
        with connect() as db:
            claim = db.execute("""UPDATE oneonone_notices SET state='UNCERTAIN',updated_at=?
                WHERE ref=? AND kind=? AND state='PENDING' AND EXISTS (
                SELECT 1 FROM oneonone_requests r WHERE r.ref=oneonone_notices.ref
                AND r.historical=0 AND r.review='' AND r.status IN ('NEW','ASSIGNED'))""",
                (now_iso(), n['ref'], n['kind']))
            if not claim.rowcount: continue
        # Persist UNCERTAIN before external I/O: process crashes cannot resend blindly.
        try:
            result = await send_tg('sendMessage', {'chat_id': expected, **preview(n['ref'], n['kind'])})
            message_id = result['message_id']
        except Exception:
            audit('oneonone', 'notice_uncertain', {'ref': n['ref'], 'kind': n['kind']})
            continue
        with connect() as db:
            db.execute("UPDATE oneonone_notices SET state='SENT', message_id=?,updated_at=? WHERE ref=? AND kind=?", (message_id, now_iso(), n['ref'], n['kind']))
        sent += 1
    return {'sent': sent, 'disabled': False}


async def callback(cb, send_tg):
    uid = (cb.get('from') or {}).get('id')
    message = cb.get('message') or {}
    chat = message.get('chat') or {}
    answer = 'This action is not available.'
    parts = cb.get('data', '').split(':')
    if (enabled('PPM_1ON1_ENABLED') and len(parts) == 3 and parts[0] == 'one'
            and chat.get('type') == 'private' and chat.get('id') == uid):
        _, action, ref = parts
        michelle, crystal = staff_id('michelle'), staff_id('crystal')
        kind = 'michelle' if uid == michelle else 'crystal' if uid == crystal else None
        with connect() as db:
            ensure(db)
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM oneonone_requests WHERE ref=?', (ref,)).fetchone()
            notice = db.execute("SELECT * FROM oneonone_notices WHERE ref=? AND kind=? AND recipient=? AND state='SENT' AND message_id=?", (ref, kind, uid, message.get('message_id'))).fetchone() if kind else None
            if row and notice and not row['historical'] and not row['review']:
                if kind == 'michelle' and action == 'view':
                    answer = 'Registration is in the existing Wix 1on1 Registrations tab.'
                elif kind == 'michelle' and action == 'route' and row['status'] == 'NEW':
                    db.execute("UPDATE oneonone_requests SET status='ASSIGNED' WHERE ref=? AND status='NEW'", (ref,))
                    db.execute("INSERT OR IGNORE INTO oneonone_notices(ref,kind,recipient,state,updated_at) VALUES(?,'crystal',?,'PENDING',?)", (ref, crystal, now_iso()))
                    answer = 'Assigned to Crystal. Staff notice queued; the lead was not contacted.'
                elif kind == 'michelle' and action == 'disregard' and row['status'] == 'NEW':
                    db.execute("UPDATE oneonone_requests SET status='DISREGARDED' WHERE ref=?", (ref,))
                    answer = 'Disregarded. Registration preserved.'
                elif kind == 'crystal':
                    transitions = {'accept': ({'ASSIGNED'}, 'ACCEPTED'),
                                   'contacted': ({'ACCEPTED', 'FOLLOW_UP'}, 'CONTACTED'),
                                   'followup': ({'CONTACTED'}, 'FOLLOW_UP'),
                                   'scheduled': ({'CONTACTED', 'FOLLOW_UP'}, 'SCHEDULED')}
                    if action in transitions and row['status'] in transitions[action][0]:
                        status = transitions[action][1]
                        db.execute('UPDATE oneonone_requests SET status=? WHERE ref=?', (status, ref))
                        answer = 'Staff-reported status recorded: ' + status
                else:
                    answer = 'Already handled; no duplicate assignment created.'
        audit(f'telegram:{uid}', 'oneonone_action', {'ref': ref, 'action': action, 'result': answer})
    await send_tg('answerCallbackQuery', {'callback_query_id': cb['id'], 'text': answer, 'show_alert': False})


def queue_summary():
    with connect() as db:
        ensure(db)
        counts = db.execute('SELECT status,COUNT(*) AS n FROM oneonone_requests GROUP BY status').fetchall()
        uncertain = db.execute("SELECT COUNT(*) FROM oneonone_notices WHERE state='UNCERTAIN'").fetchone()[0]
        uncertain_sheets = db.execute("SELECT COUNT(*) FROM oneonone_requests WHERE sheet_state='UNCERTAIN'").fetchone()[0]
        baseline = bool(db.execute("SELECT value FROM oneonone_meta WHERE key='baseline_at'").fetchone())
        pending = db.execute("SELECT COUNT(*) FROM oneonone_notices WHERE state='PENDING'").fetchone()[0]
    return {'statuses': {r['status']: r['n'] for r in counts}, 'uncertain_notices': uncertain,
            'uncertain_sheet_writes': uncertain_sheets, 'pending_notices': pending,
            'historical_baseline_established': baseline,
            'enabled': enabled('PPM_1ON1_ENABLED'),
            'staff_alerts_enabled': enabled('PPM_1ON1_STAFF_ALERTS_ENABLED')}


async def poll():
    """Dedicated opt-in worker; does not enable the unrelated campaign scheduler."""
    from app.oneonone_providers import WixSource, GoogleSheet
    from app.telegram import tg
    from app.storage import init_db
    init_db()
    interval = max(60, int(setting('PPM_1ON1_POLL_SECONDS', '300')))
    while enabled('PPM_1ON1_ENABLED') and enabled('PPM_1ON1_POLLING_ENABLED'):
        try:
            await asyncio.to_thread(lambda: sync(WixSource(), GoogleSheet()))
            await deliver(tg)
            print('1-on-1 poll completed', flush=True)
        except Exception:
            # No provider response bodies, private record data, or tokens in logs.
            print('1-on-1 poll held; check protected status and configuration', flush=True)
        await asyncio.sleep(interval)


if __name__ == '__main__':
    asyncio.run(poll())
