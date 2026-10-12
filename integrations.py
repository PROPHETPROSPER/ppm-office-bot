"""Read-only retrieval; outbound integrations are not invoked without explicit operator approval."""
import httpx
from app.settings import setting

def _post(url,**kwargs):
    with httpx.Client(timeout=30) as client:
        r=client.post(url,**kwargs);r.raise_for_status();return r.json()

def wix_events_readonly():
    token=setting('WIX_API_TOKEN')
    if not token:raise RuntimeError('WIX_API_TOKEN missing')
    headers={'Authorization':token,'Content-Type':'application/json'}
    site=setting('WIX_SITE_ID')
    if site:headers['wix-site-id']=site
    return _post('https://www.wixapis.com/events/v3/events/query',headers=headers,
       json={'query':{'paging':{'limit':100}},'includeDrafts':False})

async def youtube_active_broadcasts():
    token=setting('YOUTUBE_OAUTH_ACCESS_TOKEN')
    async with httpx.AsyncClient(timeout=20) as cli:
        # A refresh token avoids expiration during the 30-day fast.
        if all(setting(x) for x in ('YOUTUBE_OAUTH_CLIENT_ID','YOUTUBE_OAUTH_CLIENT_SECRET','YOUTUBE_OAUTH_REFRESH_TOKEN')):
            auth=await cli.post('https://oauth2.googleapis.com/token',data={
                'client_id':setting('YOUTUBE_OAUTH_CLIENT_ID'),
                'client_secret':setting('YOUTUBE_OAUTH_CLIENT_SECRET'),
                'refresh_token':setting('YOUTUBE_OAUTH_REFRESH_TOKEN'),
                'grant_type':'refresh_token'})
            auth.raise_for_status()
            token=auth.json()['access_token']
        if not token:raise RuntimeError('Authenticated YouTube OAuth access/refresh token required')
        res=await cli.get('https://www.googleapis.com/youtube/v3/liveBroadcasts',
          params={'part':'id,snippet,status','broadcastStatus':'active','mine':'true','maxResults':15},
          headers={'Authorization':f'Bearer {token}'})
        res.raise_for_status();return res.json().get('items',[])

# Intentionally no order, refill, or cancel actions anywhere in this module.
def morethanpanel_readonly(action='services'):
    if action not in ('services','balance'):
        raise ValueError('The system permits ONLY services and balance reads')
    key=setting('MORETHANPANEL_API_KEY')
    if not key:raise RuntimeError('MoreThanPanel API key not configured')
    return _post('https://morethanpanel.com/api/v2',data={'key':key,'action':action})

async def clearstream_account_readonly():
    key=setting('CLEARSTREAM_API_KEY')
    if not key:raise RuntimeError('Clearstream API key missing')
    async with httpx.AsyncClient(timeout=20) as cli:
        r=await cli.get('https://api.getclearstream.com/v1/account',headers={'X-Api-Key':key})
        r.raise_for_status()
        return {'connected':True,'verified':True}
