"""Dry-run-first scheduling helpers; no external messages until approved + enabled."""
import asyncio,sys,json
from datetime import datetime,date,time,timedelta
from zoneinfo import ZoneInfo
from app.settings import setting,CONFIDENTIAL_TERMS
from app.storage import init_db,connect,now_iso,audit
from app.integrations import youtube_active_broadcasts
from app.campaigns import plan_campaign,public_url_ok
from app.wix_sync import sync_preview_only
from app.dispatch import send_approved_due
ET=ZoneInfo('America/New_York')


def live_topic(title,now):
    """Only confidently classifiable streams qualify for owner-preapproved auto alerts."""
    s=title.casefold()
    if any(x in s for x in CONFIDENTIAL_TERMS):return None
    if ('morning' in s or 'hour of prayer' in s) and 'prayer' in s and now.weekday() in (0,2,4) and 7<=now.hour<=12:
        return 'morning_prayer'
    during_fast=date(2026,10,11)<=now.date()<=date(2026,11,9)
    if during_fast and now.weekday()<6 and 17<=now.hour<=23 and any(x in s for x in ('divine visitation','encounter','bible teaching')):
        return 'evening_teaching'
    if date(2026,10,21)<=now.date()<=date(2026,10,24) and 13<=now.hour<=18 and any(x in s for x in ('watchman','authority over resistance')):
        return 'schools'
    return None

async def live_check(now=None):
    broadcasts=await youtube_active_broadcasts()
    now=now or datetime.now(ET)
    count=0;held=0;auto=0
    for item in broadcasts:
        video_id=item.get('id')
        if not video_id:continue
        title=str((item.get('snippet') or {}).get('title','')).strip()
        if not title or any(t in title.casefold() for t in CONFIDENTIAL_TERMS):
            held+=1;continue
        topic=live_topic(title,now)
        if topic is None:
            # Unknown content may be reviewed manually but never auto-announced.
            held+=1;continue
        text=f"LIVE NOW: {title}\nWatch here: https://www.youtube.com/watch?v={video_id}"
        approved=setting('AUTO_APPROVE_LIVE_ALERTS','false').lower()=='true'
        for dest in ('official','free','telegram_personal'):
            with connect() as db:
                st='APPROVED' if approved else 'DRAFT'
                key=f'live:{video_id}:{dest}'
                cur=db.execute('''INSERT OR IGNORE INTO drafts
                  (dedupe_key,audience,topic,text,scheduled_at,status,created_at,approved_by,approved_at,metadata_json)
                  VALUES (?,?,?,?,?,?,?,?,?,?)''',
                  (key,dest,topic,text,now.isoformat(),st,now_iso(),
                   'owner_preapproved_live_policy' if approved else None,now_iso() if approved else None,
                   json.dumps({'video_id':video_id,'verified_active':True,'approved_by_policy':approved})))
                count+=cur.rowcount
                if approved and cur.rowcount:auto+=1
    return {'active_streams':len(broadcasts),'drafts_created':count,'auto_approved_for_dispatch':auto,
            'unrecognized_held':held,'note':'Actual sending still requires LIVE_SENDING_ENABLED and valid destination IDs.'}


def routine_reminders(target_day=None):
    """Generate the correct daily reminders. Never hallucinate meeting links."""
    d=target_day or datetime.now(ET).date()
    created=0;skipped=[]
    plans=[]
    # Morning prayer continues each M/W/F outside fast as well.
    if d.weekday() in (0,2,4):
        plans.append(('official','morning_prayer',8,40,'Morning Prayer begins at 9 AM Eastern. Join our official YouTube channel for the confirmed live link.'))
    active=date(2026,10,11)<=d<=date(2026,11,9)
    if active:
        zoom=setting('ZOOM_PRAYER_URL','')
        if public_url_ok(zoom):
            plans.append(('official','gatherings',17,30,f'Divine Visitation corporate prayer begins at 6 PM ET on Zoom. Join: {zoom}'))
            plans.append(('free','gatherings',17,30,f'Join us for Divine Visitation corporate prayer at 6 PM ET: {zoom}'))
        else:skipped.append('Zoom URL not confirmed; no reminder with an invented link.')
        if d.weekday()<6:
            plans.append(('official','evening_teaching',18,50,'Divine Visitation teaching begins at 7 PM ET on YouTube. Our bot shares the confirmed link when the broadcast is live.'))
    if d.weekday()==5 and d!=date(2026,10,24):
        mentorship=setting('PAID_MENTORSHIP_URL','')
        if public_url_ok(mentorship):
            plans.append(('paid','schools',13,30,f'Private Spiritual Foundation mentorship begins at 2 PM ET. Your class link: {mentorship}'))
        else:skipped.append('Paid class link not configured; mentorship reminder withheld.')
    with connect() as db:
        for dest,topic,hour,minute,text in plans:
            dt=datetime.combine(d,time(hour,minute),tzinfo=ET)
            if dt<datetime.now(ET)-timedelta(hours=1) and target_day is None:
                continue
            key=f'routine:{d.isoformat()}:{topic}:{dest}:{hour:02}:{minute:02}'
            auto=setting('AUTO_APPROVE_ROUTINE_REMINDERS','false').lower()=='true'
            status='APPROVED' if auto else 'DRAFT'
            cur=db.execute('''INSERT OR IGNORE INTO drafts
               (dedupe_key,audience,topic,text,scheduled_at,status,created_at,approved_by,approved_at)
               VALUES(?,?,?,?,?,?,?,?,?)''',(key,dest,topic,text,dt.isoformat(),status,now_iso(),
                 'owner_preapproved_routine_policy' if auto else None,now_iso() if auto else None))
            created+=cur.rowcount
    return {'created':created,'missing_links_or_held':skipped}

def main():
    init_db();mode=sys.argv[1] if len(sys.argv)>1 else 'schedule'
    if mode=='schedule':print({'events':plan_campaign(),'routines':routine_reminders()})
    elif mode=='live':print(asyncio.run(live_check()))
    elif mode=='wix':print(sync_preview_only())
    elif mode=='dispatch':print(asyncio.run(send_approved_due()))
    else:raise SystemExit('Use schedule, live, wix or dispatch')
if __name__=='__main__':main()
