"""Isolated synthetic records and fake providers; no real network or lead data."""
import asyncio
import json
from datetime import datetime, timezone, timedelta
import pytest
from app.storage import init_db, connect
from app.office_tracker import request_access, add_staff, remove_staff
from app.oneonone import (sync, normalize, callback, deliver, source_record,
                         preview, SHEET_ID, HEADERS, COLLECTIONS)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'test.db'))
    monkeypatch.setenv('TELEGRAM_OWNER_USER_IDS', '101')
    monkeypatch.setenv('PPM_BOT_MODE', 'office')
    monkeypatch.setenv('PPM_1ON1_ENABLED', 'true')
    monkeypatch.setenv('PPM_1ON1_STAFF_ALERTS_ENABLED', 'false')
    monkeypatch.setenv('LIVE_SENDING_ENABLED', 'false')
    monkeypatch.setenv('PPM_1ON1_MICHELLE_USER_ID', '202')
    monkeypatch.setenv('PPM_1ON1_CRYSTAL_USER_ID', '303')
    monkeypatch.delenv('PPM_1ON1_TEST_EMAILS', raising=False)
    init_db()
    for uid, name, role in [(202, 'Michelle', 'coordinator'), (303, 'Crystal', 'worker')]:
        request_access({'id': uid, 'first_name': name}, uid)
        add_staff(101, uid, role)


def record(sid='synthetic-id', days=0):
    return {'submission_id': sid, 'collection': 'contact12',
            'submitted_at': (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(),
            'first_name': 'Synthetic', 'last_name': 'Person', 'phone': '2025550101',
            'email': 'person@synthetic.invalid', 'country': 'United States'}


class Source:
    def __init__(self, records): self.records = records
    def read_all(self): return self.records


class Sheet:
    def __init__(self): self.ids = set(); self.rows = []; self.fail = None
    def read_ids(self): return set(self.ids)
    def append(self, row):
        self.rows.append(row)
        if self.fail != 'before': self.ids.add(row[9])
        if self.fail: raise TimeoutError('Synthetic timeout')


class Telegram:
    def __init__(self): self.calls = []; self.fail = False; self.identity = 'PPMOfficeBot'
    async def __call__(self, method, body):
        self.calls.append((method, body))
        if method == 'getMe': return {'username': self.identity}
        if method == 'sendMessage' and self.fail: raise TimeoutError('Synthetic timeout')
        return {'message_id': len(self.calls)}


def rows(table):
    with connect() as db: return [dict(r) for r in db.execute('SELECT * FROM ' + table)]


def setup_new(monkeypatch, sid='new-id'):
    sheet = Sheet()
    sync(Source([]), sheet, baseline=True)
    p = record(sid)
    sync(Source([p]), sheet)
    monkeypatch.setenv('PPM_1ON1_STAFF_ALERTS_ENABLED', 'true')
    monkeypatch.setenv('LIVE_SENDING_ENABLED', 'true')
    tg = Telegram()
    asyncio.run(deliver(tg))
    return rows('oneonone_requests')[0]['ref'], sheet, tg


def click(ref, action, uid, message_id, tg, chat_type='private'):
    cb = {'id': 'synthetic-callback', 'data': f'one:{action}:{ref}',
          'from': {'id': uid}, 'message': {'message_id': message_id,
          'chat': {'type': chat_type, 'id': uid}}}
    asyncio.run(callback(cb, tg))


def test_baseline_silent_keeps_original_time_and_existing_rows():
    p = record(days=-1); sheet = Sheet(); sheet.ids.add(p['submission_id'])
    result = sync(Source([p, p]), sheet, baseline=True)
    assert result['seen'] == 1 and not sheet.rows
    assert not rows('oneonone_notices')
    assert json.loads(rows('oneonone_requests')[0]['payload'])['submitted_at'] == p['submitted_at']
    assert rows('oneonone_requests')[0]['historical'] == 1
    with pytest.raises(RuntimeError, match='already established'): sync(Source([p]), sheet, baseline=True)


def test_new_duplicate_event_appends_once_and_preserves_consent_history():
    sheet = Sheet(); sync(Source([]), sheet, baseline=True)
    p = record()
    sync(Source([p, p]), sheet); sync(Source([p]), sheet)
    assert len(sheet.rows) == 1 and len(rows('oneonone_notices')) == 1
    row = sheet.rows[0]
    assert row[0] == p['submitted_at'] and row[9] == p['submission_id']
    assert all(row[i] == '' for i in [3, 11, 12, 13, 14, 17, 18, 19, 20, 21, 22, 23])


def test_baseline_requires_complete_sheet_and_no_implicit_activation():
    with pytest.raises(RuntimeError, match='reconcile first'):
        sync(Source([record(days=-1)]), Sheet(), baseline=True)
    with pytest.raises(RuntimeError, match='baseline first'):
        sync(Source([]), Sheet())


def test_historical_late_record_suppressed():
    sheet = Sheet(); sync(Source([]), sheet, baseline=True)
    sync(Source([record(days=-2)]), sheet)
    assert len(sheet.rows) == 1 and not rows('oneonone_notices')


def test_conflict_and_source_change_held():
    p = record(); changed = {**p, 'phone': '2025550102'}
    sheet = Sheet(); sync(Source([]), sheet, baseline=True)
    with pytest.raises(ValueError, match='Conflicting'): sync(Source([p, changed]), sheet)
    assert not sheet.rows
    sync(Source([p]), sheet); sync(Source([changed]), sheet)
    assert len(sheet.rows) == 1 and rows('oneonone_requests')[0]['status'] == 'REVIEW'
    assert rows('oneonone_requests')[0]['review']


@pytest.mark.parametrize('change', [{'email': 'test@example.com'}, {'first_name': ''},
                                    {'submitted_at': ''}, {'submitted_at': '2026-10-13T12:00:00'},
                                    {'phone': '12'}])
def test_test_and_incomplete_records_never_alert(change):
    sheet = Sheet(); sync(Source([]), sheet, baseline=True)
    sync(Source([{**record(), **change}]), sheet)
    assert rows('oneonone_requests')[0]['review'] and not rows('oneonone_notices')


@pytest.mark.parametrize('failure', ['before', 'after'])
def test_ambiguous_sheet_write_not_blindly_retried(failure):
    sheet = Sheet(); sync(Source([]), sheet, baseline=True); sheet.fail = failure
    p = record()
    with pytest.raises(TimeoutError): sync(Source([p]), sheet)
    sheet.fail = None
    if failure == 'before':
        with pytest.raises(RuntimeError, match='manual reconciliation'): sync(Source([p]), sheet)
    else:
        sync(Source([p]), sheet)
        assert rows('oneonone_requests')[0]['sheet_state'] == 'PRESENT'
    assert len(sheet.rows) == 1


def test_delivery_off_no_network():
    tg = Telegram(); assert asyncio.run(deliver(tg))['disabled']; assert not tg.calls


def test_uncertain_telegram_delivery_not_repeated(monkeypatch):
    sheet = Sheet(); sync(Source([]), sheet, baseline=True); sync(Source([record()]), sheet)
    monkeypatch.setenv('PPM_1ON1_STAFF_ALERTS_ENABLED', 'true'); monkeypatch.setenv('LIVE_SENDING_ENABLED', 'true')
    tg = Telegram(); tg.fail = True
    asyncio.run(deliver(tg)); asyncio.run(deliver(tg))
    assert len([c for c in tg.calls if c[0] == 'sendMessage']) == 1
    assert rows('oneonone_notices')[0]['state'] == 'UNCERTAIN'


def test_identity_mismatch_blocks_send(monkeypatch):
    monkeypatch.setenv('PPM_1ON1_STAFF_ALERTS_ENABLED', 'true'); monkeypatch.setenv('LIVE_SENDING_ENABLED', 'true')
    tg = Telegram(); tg.identity = 'DifferentBot'
    with pytest.raises(RuntimeError, match='identity mismatch'): asyncio.run(deliver(tg))
    assert all(c[0] != 'sendMessage' for c in tg.calls)


def test_private_authorized_route_and_duplicate_assignment(monkeypatch):
    ref, sheet, tg = setup_new(monkeypatch)
    message_id = rows('oneonone_notices')[0]['message_id']
    for uid, mid, chat in [(404, message_id, 'private'), (202, message_id + 1, 'private'),
                            (202, message_id, 'supergroup'), (303, message_id, 'private')]:
        click(ref, 'route', uid, mid, tg, chat)
        assert rows('oneonone_requests')[0]['status'] == 'NEW'
    click(ref, 'route', 202, message_id, tg); click(ref, 'route', 202, message_id, tg)
    assert rows('oneonone_requests')[0]['status'] == 'ASSIGNED'
    assert len(rows('oneonone_notices')) == 2
    asyncio.run(deliver(tg)); asyncio.run(deliver(tg))
    assert len([c for c in tg.calls if c[0] == 'sendMessage']) == 2
    crystal_mid = next(n['message_id'] for n in rows('oneonone_notices') if n['kind'] == 'crystal')
    click(ref, 'scheduled', 303, crystal_mid, tg)
    assert rows('oneonone_requests')[0]['status'] == 'ASSIGNED'
    for action, state in [('accept', 'ACCEPTED'), ('contacted', 'CONTACTED'),
                          ('followup', 'FOLLOW_UP'), ('scheduled', 'SCHEDULED')]:
        click(ref, action, 303, crystal_mid, tg)
        assert rows('oneonone_requests')[0]['status'] == state
    assert len(sheet.rows) == 1
    for method, body in tg.calls:
        if method == 'sendMessage': assert body['chat_id'] in (202, 303)
    markup = preview(ref, 'michelle')['reply_markup']['inline_keyboard']
    assert SHEET_ID in markup[1][0]['url']


def test_revoked_staff_cannot_route(monkeypatch):
    ref, _, tg = setup_new(monkeypatch)
    mid = rows('oneonone_notices')[0]['message_id']; remove_staff(101, 202)
    with pytest.raises(RuntimeError, match='approved office access'): click(ref, 'route', 202, mid, tg)
    assert rows('oneonone_requests')[0]['status'] == 'NEW'


def test_wix_mapping_requires_original_time_not_created_date():
    fields = {'submitted_at': 'submissionTime', 'first_name': 'firstName',
              'phone': 'phone', 'email': 'email', 'country': 'country'}
    item = {'id': 'synthetic-id', 'data': {'_createdDate': {'$date': '2026-01-01T00:00:00Z'},
            'submissionTime': {'$date': '2026-01-02T00:00:01Z'}, 'firstName': 'Synthetic',
            'phone': '2025550101', 'email': 'person@synthetic.invalid', 'country': 'United States'}}
    p = source_record('contact12', item, fields)
    assert p['submitted_at'] == '2026-01-02T00:00:01Z'
    with pytest.raises(ValueError, match='mapping'): source_record('contact12', item, {})


def test_google_exact_target_raw_and_header_guard(monkeypatch):
    from app.oneonone_providers import GoogleSheet
    monkeypatch.setenv('GOOGLE_SHEETS_ACCESS_TOKEN', 'synthetic-token')
    for key in ['GOOGLE_SHEETS_CLIENT_ID', 'GOOGLE_SHEETS_CLIENT_SECRET', 'GOOGLE_SHEETS_REFRESH_TOKEN']:
        monkeypatch.delenv(key, raising=False)
    sheet = GoogleSheet()
    monkeypatch.setattr(sheet, 'request', lambda *a, **k: {'values': [['Wrong header']]})
    with pytest.raises(RuntimeError, match='headers changed'): sheet.read_ids()


def test_telegram_dispatches_oneonone_callback_in_office_mode(monkeypatch):
    from app.telegram import handle_update
    ref, _, tg = setup_new(monkeypatch)
    monkeypatch.setattr('app.telegram.tg', tg)
    mid = rows('oneonone_notices')[0]['message_id']
    update = {'update_id': 1001, 'callback_query': {'id': 'synthetic', 'data': f'one:route:{ref}',
              'from': {'id': 202}, 'message': {'message_id': mid, 'chat': {'id': 202, 'type': 'private'}}}}
    asyncio.run(handle_update(update)); asyncio.run(handle_update(update))
    assert len(rows('oneonone_notices')) == 2


def test_future_timestamp_requires_review():
    assert 'future' in normalize(record(days=2))['review']


def test_provider_requests_use_all_collections_paging_and_literal_append(monkeypatch):
    import httpx
    from app.oneonone_providers import WixSource, GoogleSheet
    calls = []
    item = {'id': 'synthetic-id', 'data': {'time': '2026-01-01T00:00:00Z',
            'name': 'Synthetic', 'phone': '2025550101', 'email': 'person@synthetic.invalid', 'country': 'United States'}}
    def handler(request):
        body = json.loads(request.content) if request.content else {}
        calls.append((request, body))
        if request.url.host == 'www.wixapis.com':
            collection = body['dataCollectionId']; offset = body['query']['paging']['offset']
            data = [dict(item, id=f'synthetic-{i}') for i in range(100)] if collection == 'contact12' and offset == 0 else []
            return httpx.Response(200, json={'dataItems': data})
        assert request.url.host == 'sheets.googleapis.com'
        assert SHEET_ID in request.url.path
        assert request.url.params['valueInputOption'] == 'RAW'
        assert body['values'][0][1] == '=synthetic_formula'
        return httpx.Response(200, json={'updates': {'updatedRows': 1}})
    original = httpx.Client
    monkeypatch.setattr('app.oneonone_providers.httpx.Client', lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setenv('WIX_1ON1_API_TOKEN', 'synthetic-token')
    fields = {'submitted_at': 'time', 'first_name': 'name', 'phone': 'phone', 'email': 'email', 'country': 'country'}
    monkeypatch.setenv('PPM_1ON1_WIX_FIELD_MAP', json.dumps({c: fields for c in COLLECTIONS}))
    records = WixSource().read_all()
    assert len(records) == 100
    assert {b['dataCollectionId'] for _, b in calls} == set(COLLECTIONS)
    assert calls[1][1]['query']['paging']['offset'] == 100
    monkeypatch.setenv('GOOGLE_SHEETS_ACCESS_TOKEN', 'synthetic-token')
    for key in ['GOOGLE_SHEETS_CLIENT_ID', 'GOOGLE_SHEETS_CLIENT_SECRET', 'GOOGLE_SHEETS_REFRESH_TOKEN']:
        monkeypatch.delenv(key, raising=False)
    row = [''] * 27; row[1] = '=synthetic_formula'
    GoogleSheet().append(row)


def test_protected_admin_routes_do_not_run_without_authorization(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setenv('APP_ADMIN_TOKEN', 'synthetic-admin-secret')
    with TestClient(app) as client:
        for endpoint in ['baseline', 'sync', 'deliver-staff-notices']:
            assert client.post('/admin/1on1/' + endpoint).status_code == 401
        assert client.get('/admin/1on1/status').status_code == 401
        status = client.get('/admin/1on1/status', headers={'Authorization': 'Bearer synthetic-admin-secret'})
        assert status.status_code == 200
        assert not status.json()['historical_baseline_established']


def test_source_field_mapping_incomplete_for_empty_form_blocks_sync(monkeypatch):
    from app.oneonone_providers import WixSource
    monkeypatch.setenv('WIX_1ON1_API_TOKEN', 'synthetic-token')
    monkeypatch.setenv('PPM_1ON1_WIX_FIELD_MAP', '{}')
    with pytest.raises(RuntimeError, match='all three'): WixSource().read_all()
