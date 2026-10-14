"""Wix read-only and exact-target Sheets adapters; never used during offline tests."""
import json
from urllib.parse import quote
import httpx
from app.settings import setting
from app.oneonone import COLLECTIONS, HEADERS, SHEET_ID, TAB, source_record

SITE_ID = '9ce2c32c-6895-4799-9bd5-49bbb8cd0f53'


class WixSource:
    def read_all(self):
        token = setting('WIX_1ON1_API_TOKEN')
        if not token:
            raise RuntimeError('WIX_1ON1_API_TOKEN is missing')
        try:
            mappings = json.loads(setting('PPM_1ON1_WIX_FIELD_MAP', '{}'))
        except ValueError:
            raise RuntimeError('Invalid Wix field mapping configuration') from None
        if set(mappings) != set(COLLECTIONS):
            raise RuntimeError('Verify field mappings for all three Wix collections first')
        result = []
        with httpx.Client(timeout=30) as client:
            for collection in COLLECTIONS:
                offset = 0
                while offset < 10000:
                    response = client.post('https://www.wixapis.com/wix-data/v2/items/query',
                        headers={'Authorization': token, 'wix-site-id': SITE_ID},
                        json={'dataCollectionId': collection,
                              'query': {'sort': [{'fieldName': '_id', 'order': 'ASC'}],
                                        'paging': {'limit': 100, 'offset': offset}}})
                    response.raise_for_status()
                    payload = response.json()
                    if 'dataItems' not in payload or not isinstance(payload['dataItems'], list):
                        raise RuntimeError('Unrecognized Wix response; no partial sync allowed')
                    items = payload['dataItems']
                    for item in items:
                        if item.get('dataCollectionId', collection) != collection:
                            raise RuntimeError('Wix returned a different collection')
                        result.append(source_record(collection, item, mappings[collection]))
                    if len(items) < 100:
                        break
                    offset += len(items)
                else:
                    raise RuntimeError('Wix pagination cap reached; sync held to prevent truncation')
        return result


class GoogleSheet:
    def __init__(self):
        self.token = setting('GOOGLE_SHEETS_ACCESS_TOKEN')
        keys = ('GOOGLE_SHEETS_CLIENT_ID', 'GOOGLE_SHEETS_CLIENT_SECRET', 'GOOGLE_SHEETS_REFRESH_TOKEN')
        if all(setting(k) for k in keys):
            with httpx.Client(timeout=30) as client:
                r = client.post('https://oauth2.googleapis.com/token', data={
                    'client_id': setting(keys[0]), 'client_secret': setting(keys[1]),
                    'refresh_token': setting(keys[2]), 'grant_type': 'refresh_token'})
                r.raise_for_status()
                self.token = r.json()['access_token']
        if not self.token:
            raise RuntimeError('Google Sheets runtime credentials are missing')

    def request(self, method, range_name, **kwargs):
        url = f'https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/' + quote(range_name, safe='')
        with httpx.Client(timeout=30) as client:
            r = client.request(method, url, headers={'Authorization': 'Bearer ' + self.token}, **kwargs)
            r.raise_for_status()
            return r.json()

    def read_ids(self):
        header = self.request('GET', f"'{TAB}'!A1:AA1").get('values', [])
        if header != [HEADERS]:
            raise RuntimeError('Existing sheet headers changed; writes blocked')
        # Read only the stable ID column; preserve all prior rows and follow-up cells.
        rows = self.request('GET', f"'{TAB}'!J2:J").get('values', [])
        ids = [str(row[0]) for row in rows if row and row[0]]
        if len(ids) != len(set(ids)):
            raise RuntimeError('Duplicate submission IDs already exist in the Sheet; review required')
        return set(ids)

    def append(self, row):
        if len(row) != len(HEADERS):
            raise ValueError('Complete registration row required')
        # RAW keeps phones, timestamps, and any formula-like source text literal.
        url = f'https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/' + quote(f"'{TAB}'!A:AA", safe='') + ':append'
        with httpx.Client(timeout=30) as client:
            r = client.post(url, headers={'Authorization': 'Bearer ' + self.token},
                params={'valueInputOption': 'RAW', 'insertDataOption': 'INSERT_ROWS'},
                json={'majorDimension': 'ROWS', 'values': [row]})
            r.raise_for_status()
            if r.json().get('updates', {}).get('updatedRows') != 1:
                raise RuntimeError('Sheet append was not acknowledged')
