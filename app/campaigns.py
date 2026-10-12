from datetime import date,timedelta,datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
import hashlib
from app.storage import connect,now_iso,audit
from app.settings import PROMO_STAGES,CONFIDENTIAL_TERMS

DAY_TO_CHANNELS={
  'official':{14,7,3,2,1,0},
  'free':{14,7,3,0},
  'paid':{7,1,0},
  'clearstream':{7,1,0},
  'whatsapp':{7,1,0},
  'telegram_personal':{3,2,1,0}
}

def public_url_ok(url):
    try:
        u=urlparse(url)
        return u.scheme=='https' and bool(u.netloc) and not u.username
    except Exception:return False

def add_event(event):
    required=('event_id','name','start_date','url','topic')
    for k in required:
        if not event.get(k): raise ValueError(f'Missing {k}')
    start=date.fromisoformat(event['start_date'])
    end=date.fromisoformat(event.get('end_date') or event['start_date'])
    if end<start:raise ValueError('End date before start')
    if not public_url_ok(event['url']):raise ValueError('Event URL must be HTTPS')
    if event['topic'] not in ('prayer_chain','schools','gatherings','evening_teaching','morning_prayer'):
        raise ValueError('Unknown event topic')
    # Prevent confidential owner-only planning from leaking into a public system.
    private=bool(event.get('is_private',False)) or any(s.lower() in (event['name']+' '+event.get('time_label','')+' '+event['url']).lower() for s in CONFIDENTIAL_TERMS)
    # Private plans never enter this app's general campaign database.
    if private:
        return {'event_id':event['event_id'],'status':'PRIVATE_SKIPPED_OWNER_ONLY'}
    # No new or changed event becomes promotable from a website sync alone.
    with connect() as db:
        old=db.execute('SELECT * FROM events WHERE event_id=?',(event['event_id'],)).fetchone()
        unchanged=bool(old) and all([old['name']==event['name'],old['start_date']==start.isoformat(),
          old['end_date']==end.isoformat(),old['url']==event['url'],old['time_label']==event.get('time_label','')])
        new_approval=int(bool(old['public_ok'])) if unchanged else 0
        if old and not unchanged:
            db.execute('''UPDATE drafts SET status='STALE_HOLD'
              WHERE event_id=? AND status IN ('DRAFT','APPROVED','EXPORT_ONLY','APPROVED_EXPORT')''',(event['event_id'],))
        db.execute('''INSERT INTO events(event_id,name,start_date,end_date,time_label,url,topic,public_ok,is_private,review_reason,created_at)
         VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(event_id) DO UPDATE SET
         name=excluded.name,start_date=excluded.start_date,end_date=excluded.end_date,
         time_label=excluded.time_label,url=excluded.url,topic=excluded.topic,
         public_ok=excluded.public_ok,is_private=excluded.is_private,review_reason=excluded.review_reason''',
         (event['event_id'],event['name'],start.isoformat(),end.isoformat(),event.get('time_label',''),
          event['url'],event['topic'],new_approval,int(private),event.get('review_reason','Requires editorial approval'),now_iso()))
    return {'event_id':event['event_id'],'status':'APPROVAL_PRESERVED' if new_approval else 'HOLD_REVIEW'}

def approve_event(event_id, reviewer):
    with connect() as db:
        r=db.execute('SELECT * FROM events WHERE event_id=?',(event_id,)).fetchone()
        if not r:raise ValueError('Unknown event')
        if r['is_private']:raise ValueError('Owner-only/private events cannot be made public here')
        db.execute('UPDATE events SET public_ok=1, review_reason=NULL WHERE event_id=?',(event_id,))
    audit(reviewer,'approve_event',{'event_id':event_id})

def make_message(ev, days):
    labels={14:'Save the date',10:'Program preview',7:'One week away',5:'What to expect',3:'Three days away',2:'Two days away',1:'Tomorrow',0:'Today'}
    return f"{labels[days]}: {ev['name']} — {ev['time_label']}. Details: {ev['url']}"

def plan_campaign(start_day=None):
    today=start_day or datetime.now(ZoneInfo('America/New_York')).date()
    events=[];created=[];suppressed=[]
    with connect() as db:
        events=[dict(e) for e in db.execute('SELECT * FROM events WHERE public_ok=1 AND is_private=0')]
    planned=[]
    for ev in events:
        ev_day=date.fromisoformat(ev['start_date'])
        end_day=date.fromisoformat(ev['end_date'])
        for day in PROMO_STAGES:
            dt=ev_day-timedelta(days=day)
            if dt>=today:
                for channel,allowed in DAY_TO_CHANNELS.items():
                    if day not in allowed:continue
                    planned.append((dt,channel,day,ev))
        # daily event-day reminders for people actively attending a multi-day event.
        for i in range(1,(end_day-ev_day).days+1):
            dt=ev_day+timedelta(days=i)
            if dt>=today:
                for channel in ('official','free'):
                    planned.append((dt,channel,-i,ev))
    planned.sort(key=lambda r:(r[0],r[1],r[2]))
    daily=set();weekly={}
    for dt,ch,day,ev in planned:
        dk=(dt.isoformat(),ch)
        wk=(dt.isocalendar().year,dt.isocalendar().week,ch)
        if dk in daily:
            suppressed.append({'channel':ch,'date':str(dt),'event':ev['event_id'],'reason':'another event notice on same day'})
            continue
        if ch in ('official','free') and weekly.get(wk,0)>=3 and day>=0:
            suppressed.append({'channel':ch,'date':str(dt),'event':ev['event_id'],'reason':'max three promotional notices per week'})
            continue
        if ch=='clearstream' or ch=='whatsapp':
            # Export for human review ONLY; neither channel sends from this application.
            status='EXPORT_ONLY'
        else:status='DRAFT'
        msg=make_message(ev,day) if day>=0 else f"Day {1-day} continues: {ev['name']}. Details: {ev['url']}"
        fingerprint=hashlib.sha256((ev['name']+ev['start_date']+ev['end_date']+ev['url']+ev['time_label']).encode()).hexdigest()[:12]
        key=f"event:{ev['event_id']}:{fingerprint}:{ch}:{dt}:stage{day}"
        with connect() as db:
            cur=db.execute('''INSERT OR IGNORE INTO drafts(dedupe_key,event_id,audience,topic,text,scheduled_at,status,created_at)
                              VALUES(?,?,?,?,?,?,?,?)''',(key,ev['event_id'],ch,ev['topic'],msg,dt.isoformat()+'T12:00:00',status,now_iso()))
            if cur.rowcount:created.append({'key':key,'audience':ch,'scheduled':str(dt)})
        daily.add(dk);weekly[wk]=weekly.get(wk,0)+1
    return {'new_drafts':len(created),'suppressed':suppressed,'note':'No messages sent; SMS/WhatsApp are export-only'}

def create_draft(payload):
    aud=payload['audience']
    if aud not in (*DAY_TO_CHANNELS.keys(),'telegram_personal'):
        raise ValueError('Invalid destination')
    from app.settings import TOPICS
    if payload['topic'] not in TOPICS:raise ValueError('Unknown topic')
    text=payload['text'].strip()
    if not text or len(text)>3500:raise ValueError('Text must be 1-3500 chars')
    if any(s.lower() in text.lower() for s in CONFIDENTIAL_TERMS):raise ValueError('Owner-only event terms cannot appear in drafts')
    key=payload.get('dedupe_key') or f'manual:{now_iso()}:{aud}'
    with connect() as db:
        cur=db.execute('''INSERT INTO drafts(dedupe_key,audience,topic,text,scheduled_at,status,created_at)
              VALUES(?,?,?,?,?,?,?)''',(key,aud,payload['topic'],text,payload.get('scheduled_at',now_iso()),'DRAFT',now_iso()))
        return cur.lastrowid
