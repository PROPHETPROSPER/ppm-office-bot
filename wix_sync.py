"""Read-only Wix event sync, always holding new/changed events for editorial approval."""
import hashlib,json
from datetime import datetime
from urllib.parse import urljoin
from app.integrations import wix_events_readonly
from app.campaigns import add_event, public_url_ok
from app.settings import setting,CONFIDENTIAL_TERMS
from app.storage import connect,now_iso

def verified_page_url(event):
    page=event.get('eventPageUrl') or {}
    if isinstance(page,str) and public_url_ok(page):return page
    if isinstance(page,dict):
        for k in ('url','fullUrl','absoluteUrl'):
            candidate=page.get(k)
            if isinstance(candidate,str) and public_url_ok(candidate):return candidate
        root=setting('WIX_SITE_BASE_URL')
        path=page.get('path') or page.get('relativeUrl')
        if root and public_url_ok(root) and isinstance(path,str):
            candidate=urljoin(root,path)
            if public_url_ok(candidate):return candidate
    return None

def normalize_event(raw):
    title=str(raw.get('title','')).strip()
    if not title or any(t.lower() in title.lower() for t in CONFIDENTIAL_TERMS):return None
    if raw.get('status') in ('DRAFT','CANCELED','ENDED'):return None
    url=verified_page_url(raw)
    if not url:return None
    dt=raw.get('dateAndTimeSettings') or {}
    start=dt.get('startDate') or ''
    end=dt.get('endDate') or start
    if not start:return None
    start=start[:10];end=end[:10]
    datetime.fromisoformat(start);datetime.fromisoformat(end)
    low=title.lower()
    topic='prayer_chain' if 'prayer chain' in low else 'schools' if 'school' in low or 'watchman' in low else 'gatherings'
    return {'event_id':'wix:'+str(raw.get('id')),'name':title,
        'start_date':start,'end_date':end,'time_label':'Verify start time in Wix before promotion',
        'url':url,'topic':topic,'review_reason':'Needs schedule, timezone, URL and ministry approval'}

def sync_preview_only():
    response=wix_events_readonly()
    total=0;skipped=0;results=[]
    for item in response.get('events',[]):
        normalized=normalize_event(item)
        if not normalized:
            skipped+=1;continue
        source=hashlib.sha256(json.dumps({
          'name':item.get('title'),
          'start':(item.get('dateAndTimeSettings') or {}).get('startDate'),
          'end':(item.get('dateAndTimeSettings') or {}).get('endDate'),
          'status':item.get('status'), 'page':item.get('eventPageUrl')},
          sort_keys=True,default=str).encode()).hexdigest()
        with connect() as db:
            old=db.execute('SELECT source_fingerprint FROM wix_sources WHERE event_id=?',
                           (normalized['event_id'],)).fetchone()
        if old and old['source_fingerprint']==source:
            skipped+=1;continue
        results.append(add_event(normalized));total+=1
        with connect() as db:
            db.execute('''INSERT INTO wix_sources(event_id,source_fingerprint,checked_at)
                VALUES(?,?,?) ON CONFLICT(event_id) DO UPDATE SET
                source_fingerprint=excluded.source_fingerprint,checked_at=excluded.checked_at''',
                (normalized['event_id'],source,now_iso()))
    return {'imported_or_checked':total,'skipped_missing_or_unchanged':skipped,
            'results':results,'note':'New or changed events remain on hold; no messages sent.'}
