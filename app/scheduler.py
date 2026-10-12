"""Run this as a single process on your server, not in ChatGPT.
All content is review-held. Only explicitly approved items dispatch with LIVE_SENDING_ENABLED=true.
"""
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from app.worker import live_check,routine_reminders
from app.wix_sync import sync_preview_only
from app.campaigns import plan_campaign
from app.storage import init_db
from app.dispatch import send_approved_due

async def scheduler():
    init_db()
    last_wix=None;last_campaign=None
    while True:
        now=datetime.now(ZoneInfo('America/New_York'))
        if now.hour>=7 and now.date()!=last_wix:
            try:print('wix_sync',sync_preview_only(),flush=True)
            except Exception as e:print('wix_sync_skipped',str(e)[:120],flush=True)
            last_wix=now.date()
        if now.hour>=7 and now.date()!=last_campaign:
            try:print('campaign_draft',plan_campaign(),flush=True);print('routines',routine_reminders(),flush=True)
            except Exception as e:print('campaign_error',str(e)[:120],flush=True)
            last_campaign=now.date()
        try:print('live_check',await live_check(),flush=True)
        except Exception as e:print('live_skipped',str(e)[:120],flush=True)
        try:print('dispatch',await send_approved_due(),flush=True)
        except Exception as e:print('dispatch_error',str(e)[:120],flush=True)
        await asyncio.sleep(300)

if __name__=='__main__':asyncio.run(scheduler())
