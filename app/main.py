import os,json, hmac
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import FastAPI,Header,HTTPException,Depends,Request
from fastapi.security import HTTPBearer,HTTPAuthorizationCredentials
from pydantic import BaseModel,Field
from app.settings import setting,TOPICS,CONFIDENTIAL_TERMS
from app.storage import init_db,connect,rows,now_iso,audit
from app.telegram import handle_update,tg,audience_chat_id
from app.campaigns import add_event,approve_event,plan_campaign,create_draft
from app.integrations import wix_events_readonly, youtube_active_broadcasts, morethanpanel_readonly, clearstream_account_readonly
from app.ai_content import draft_teaching
from app.comparison import compare_scenarios
from app.wix_sync import sync_preview_only

app=FastAPI(title='PPM Ministry Automation — Approval First',version='1.0.0',
 description='Private Telegram automation and ministry draft-review API. Does NOT buy followers, run ads, or send SMS/WhatsApp.')
security=HTTPBearer(auto_error=False)
@app.on_event('startup')
def startup():init_db()

def admin(auth: HTTPAuthorizationCredentials=Depends(security)):
    token=setting('APP_ADMIN_TOKEN')
    if not token or token.startswith('REPLACE_'):
        raise HTTPException(503,'Configure a real APP_ADMIN_TOKEN first')
    if not auth or not hmac.compare_digest(auth.credentials,token):
        raise HTTPException(401,'Admin authorization required')
    return 'authorized_admin'

class EventInput(BaseModel):
    event_id:str;name:str;start_date:str;end_date:str|None=None
    time_label:str='';url:str;topic:str;is_private:bool=False;review_reason:str='Requires schedule and link review'
class DraftInput(BaseModel):
    audience:str;topic:str;text:str;scheduled_at:str|None=None;dedupe_key:str|None=None
class SermonInput(BaseModel):
    reference:str;transcript:str;provider:str='offline';model:str=''
class CompareInput(BaseModel):
    scenarios:list[dict]

@app.get('/health')
def health():return {'healthy':True,'status':'DRAFT_MODE' if setting('LIVE_SENDING_ENABLED','false').lower()!='true' else 'SENDING_ENABLED','purchasing':'NEVER_SUPPORTED'}

@app.get('/admin/1on1/status')
def oneonone_status(_:str=Depends(admin)):
    from app.oneonone import queue_summary
    return queue_summary()

@app.post('/admin/1on1/baseline')
def oneonone_baseline(_:str=Depends(admin)):
    from app.oneonone import sync
    from app.oneonone_providers import WixSource,GoogleSheet
    try:return sync(WixSource(),GoogleSheet(),baseline=True)
    except (RuntimeError,ValueError):
        raise HTTPException(409,'Baseline held; check credentials, source mapping, sheet reconciliation and existing baseline state') from None

@app.post('/admin/1on1/sync')
def oneonone_sync(_:str=Depends(admin)):
    from app.oneonone import sync
    from app.oneonone_providers import WixSource,GoogleSheet
    try:return sync(WixSource(),GoogleSheet())
    except (RuntimeError,ValueError):
        raise HTTPException(409,'Sync held; review source mapping, baseline, staff configuration or uncertain Sheet writes') from None

@app.post('/admin/1on1/deliver-staff-notices')
async def oneonone_delivery(_:str=Depends(admin)):
    from app.oneonone import deliver
    try:return await deliver(tg)
    except (RuntimeError,ValueError):
        raise HTTPException(409,'Delivery held; verify bot identity, staff access and dedicated activation settings') from None
@app.get('/admin/readiness')
def readiness(_:str=Depends(admin)):
    """Deployment checks without ever returning secret values."""
    from app.storage import db_file
    from app.settings import AUDIENCES
    import os
    storage_path=db_file()
    parent=os.path.dirname(os.path.abspath(storage_path))
    required=['TELEGRAM_BOT_TOKEN','TELEGRAM_WEBHOOK_SECRET','TELEGRAM_OWNER_USER_IDS',
              'TELEGRAM_OFFICIAL_CHANNEL_ID','TELEGRAM_FREE_GROUP_ID','TELEGRAM_PAID_GROUP_ID']
    missing=[key for key in required if not setting(key)]
    return {
      'test_environment_ready':not missing and os.access(parent,os.W_OK),
      'missing_required_settings':missing,
      'db_storage_directory_writable':os.access(parent,os.W_OK),
      'persistent_storage_configured': bool(setting('PPM_DATA_DIR') or setting('DB_PATH')),
      'scheduler_enabled':setting('PPM_SCHEDULER_ENABLED','false').lower()=='true',
      'telegram_outbound_enabled':setting('LIVE_SENDING_ENABLED','false').lower()=='true',
      'ai_provider_configured':setting('AI_PROVIDER','none') not in ('','none'),
      'youtube_oauth_configured':bool(setting('YOUTUBE_OAUTH_ACCESS_TOKEN') or setting('YOUTUBE_OAUTH_REFRESH_TOKEN')),
      'wix_events_configured':bool(setting('WIX_API_TOKEN')),
      'note':'Readiness is configuration only. Real delivery requires private end-to-end tests.'
    }

@app.get('/admin/telegram/identity')
async def verify_telegram_identity(_:str=Depends(admin)):
    # Validate the owner-selected @username against Telegram's actual bot identity.
    # Do not enable webhooks or sending if the token belongs to a different bot.
    from app.telegram import tg
    from app.settings import setting
    import httpx
    try:
        me = await tg('getMe', {})
    except (httpx.HTTPError,RuntimeError):
        raise HTTPException(502,'Telegram token validation failed; check token and connectivity')
    got=(me.get('username') or '').casefold().lstrip('@')
    expected=setting('PPM_EXPECTED_BOT_USERNAME','').casefold().lstrip('@')
    if not expected:
        raise HTTPException(503,'Expected bot username is not configured')
    if got!=expected:
        raise HTTPException(409,'Telegram token belongs to a different bot; launch blocked')
    return {'username':'@'+me['username'],'verified':True,'bot_mode':setting('PPM_BOT_MODE','public'),'note':'Identity verified; this does not mean public sending is enabled'}

@app.get('/info')
def info(_:str=Depends(admin)):
    return {'topics':TOPICS,'audiences':['official','free','paid','telegram_personal','clearstream','whatsapp'],
            'publishing_enabled':setting('LIVE_SENDING_ENABLED','false').lower()=='true',
            'restricted_owner_only':'PPP Dallas excluded from campaigns and exports',
            'note':'No SMS/WhatsApp sending routes; no MoreThanPanel order routes.'}
@app.post('/telegram/webhook')
async def telegram_webhook(req:Request,x_telegram_bot_api_secret_token:str|None=Header(None)):
    secret=setting('TELEGRAM_WEBHOOK_SECRET')
    if not secret or secret.startswith('REPLACE_') or not x_telegram_bot_api_secret_token or not hmac.compare_digest(secret,x_telegram_bot_api_secret_token):
        raise HTTPException(403,'Invalid Telegram webhook secret')
    update=await req.json()
    await handle_update(update)
    return {'ok':True}

@app.post('/admin/events')
def admin_add_event(e:EventInput,actor:str=Depends(admin)):
    try:out=add_event(e.model_dump());audit(actor,'import_event',out);return out
    except ValueError as ex:raise HTTPException(400,str(ex))
@app.get('/admin/events')
def admin_list_events(_:str=Depends(admin)):return rows('SELECT * FROM events ORDER BY start_date')
@app.post('/admin/events/{event_id}/approve')
def admin_approve_event(event_id:str,actor:str=Depends(admin)):
    try:approve_event(event_id,actor);return {'approved':True,'event_id':event_id}
    except ValueError as e:raise HTTPException(400,str(e))
@app.post('/admin/campaigns/plan')
def admin_plan_campaign(_:str=Depends(admin)):
    result=plan_campaign();audit('admin','plan_campaign',{'created':result['new_drafts']});return result
@app.get('/admin/drafts')
def get_drafts(status:str|None=None,limit:int=100,_:str=Depends(admin)):
    if limit<1 or limit>500:raise HTTPException(400,'limit must be 1..500')
    if status:return rows('SELECT * FROM drafts WHERE status=? ORDER BY scheduled_at LIMIT ?',(status,limit))
    return rows('SELECT * FROM drafts ORDER BY scheduled_at LIMIT ?',(limit,))
@app.post('/admin/drafts')
def admin_create_draft(p:DraftInput,_:str=Depends(admin)):
    try:return {'draft_id':create_draft(p.model_dump(exclude_none=True))}
    except ValueError as e:raise HTTPException(400,str(e))
@app.post('/admin/drafts/{draft_id}/approve')
def approve_draft(draft_id:int,actor:str=Depends(admin)):
    with connect() as db:
        d=db.execute('SELECT * FROM drafts WHERE draft_id=?',(draft_id,)).fetchone()
        if not d:raise HTTPException(404,'Draft not found')
        if d['status'] not in ('DRAFT','EXPORT_ONLY'):
            raise HTTPException(400,'Draft is not awaiting approval')
        # SMS and WhatsApp remain export-only, no sending via this API.
        new_status='APPROVED_EXPORT' if d['audience'] in ('clearstream','whatsapp') else 'APPROVED'
        db.execute('UPDATE drafts SET status=?,approved_by=?,approved_at=? WHERE draft_id=?',
                    (new_status,actor,now_iso(),draft_id))
    audit(actor,'approve_draft',{'draft_id':draft_id,'status':new_status})
    return {'draft_id':draft_id,'status':new_status}
@app.post('/admin/drafts/{draft_id}/send')
async def send_draft(draft_id:int,actor:str=Depends(admin)):
    from app.dispatch import send_one
    try:return await send_one(draft_id,actor)
    except PermissionError as e:raise HTTPException(403,str(e))
    except ValueError as e:raise HTTPException(400,str(e))
    except RuntimeError as e:raise HTTPException(502,str(e))

@app.get('/admin/export/{channel}')
def approved_exports(channel:str,_:str=Depends(admin)):
    if channel not in ('clearstream','whatsapp'):
        raise HTTPException(400,'Only Clearstream and WhatsApp are supported for consent-review exports')
    return {'channel':channel,'rows':rows('SELECT * FROM drafts WHERE audience=? AND status=?',(channel,'APPROVED_EXPORT')),
      'requirement':'Verify specific channel opt-in and suppress unsubscribed subscribers before sending manually. No recipients are auto imported.'}
@app.get('/admin/telegram/members')
def member_summary(_:str=Depends(admin)):
    return rows('''SELECT p.topic, COUNT(*) AS opted_in FROM preferences p JOIN members m ON m.telegram_id=p.telegram_id
       WHERE p.enabled=1 AND m.stopped_at IS NULL GROUP BY p.topic''')

@app.post('/admin/integrations/wix/preview')
def wix_preview(_:str=Depends(admin)):
    try:
        raw=wix_events_readonly()
        preview=[{'id':e.get('id'),'title':e.get('title'),
             'start':(e.get('dateAndTimeSettings') or {}).get('startDate'),
             'status':e.get('status'), 'slug':e.get('slug')}
            for e in raw.get('events',[])]
        return {'events':preview,'imported':0,'approval':'Required before event import and marketing'}
    except Exception as e:raise HTTPException(502,f'Wix read failed: {str(e)[:150]}')
@app.post('/admin/integrations/wix/import-on-hold')
def wix_import_on_hold(_:str=Depends(admin)):
    try:return sync_preview_only()
    except Exception as e:raise HTTPException(502,f'Wix import failed: {str(e)[:150]}')
@app.post('/admin/integrations/youtube/check-active')
async def check_live(_:str=Depends(admin)):
    try:
        active=await youtube_active_broadcasts()
        return {'active_broadcasts':[{'id':x.get('id'),'title':(x.get('snippet') or {}).get('title'),
              'url':'https://www.youtube.com/watch?v='+x['id']}
                for x in active if x.get('id')],
               'action':'PREVIEW ONLY. Moderator chooses Morning Prayer or Evening Teaching before generating announcement.'}
    except Exception as e:raise HTTPException(502,f'YouTube read failed: {str(e)[:150]}')
@app.post('/admin/integrations/clearstream/check')
async def clearstream_check(_:str=Depends(admin)):
    try:return await clearstream_account_readonly()
    except Exception as e:raise HTTPException(502,f'Clearstream read failed: {str(e)[:150]}')
@app.post('/admin/integrations/morethanpanel/preview')
def morethanpanel_preview(_:str=Depends(admin)):
    try:
        raw=morethanpanel_readonly('services')
        services=raw if isinstance(raw,list) else []
        return {'catalog_count':len(services),'sample':[{'name':x.get('name'),'category':x.get('category'),'rate':x.get('rate')} for x in services[:30]],
                'mode':'READ_ONLY; NO ORDER ROUTES EXIST'}
    except Exception as e:raise HTTPException(502,f'Panel read failed: {str(e)[:150]}')
@app.post('/admin/ai/create')
def generate_assets(p:SermonInput,actor:str=Depends(admin)):
    try:
        output=draft_teaching(p.transcript,p.reference,p.provider,p.model)
        audit(actor,'generate_sermon_draft',{'reference':p.reference,'asset_id':output['asset_id'],'provider':p.provider})
        return output
    except (ValueError,RuntimeError) as e:raise HTTPException(400,str(e))
    except Exception as e:raise HTTPException(502,'AI provider could not produce valid draft; check keys/model and provider response')
@app.get('/admin/ai/assets')
def list_ai_assets(_:str=Depends(admin)):
    return rows('SELECT * FROM ai_assets ORDER BY asset_id DESC LIMIT 100')
@app.post('/admin/comparison')
def compare(data:CompareInput,_:str=Depends(admin)):
    try:return compare_scenarios(data.scenarios)
    except ValueError as e:raise HTTPException(400,str(e))
@app.get('/admin/audit')
def get_audit(_:str=Depends(admin)):
    return rows('SELECT * FROM audits ORDER BY audit_id DESC LIMIT 100')
