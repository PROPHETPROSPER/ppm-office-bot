import json, re, httpx
from app.settings import setting
from app.storage import connect,now_iso

SYSTEM='''You are a sermon production assistant for Prophet Prosper Ministries. Produce source-grounded content only.
Return ONLY valid JSON: {"slides":[{"title":"...","quote":"...","explanation":"..."} EXACTLY 3],
"reels":[{"hook":"...","exact_excerpt":"...","note":"..."} ONE OR TWO],"scriptures_referenced":[],"verification_notes":[]}.
Rules: Quotes and exact_excerpt MUST be character-for-character substrings of input transcript. Do not invent or fix quotes.
Do not fabricate testimonies, scriptures, timing marks, viewers, or prophecy. Preserve nuanced theological statements.
Avoid coercive donation or private mentorship promotion. If sources unavailable, leave quote/excerpt blank and note why.
If no timestamps exist, do not invent them. These are review drafts, NEVER auto-publish.'''

def parse_json_response(raw):
    txt=raw.strip()
    if txt.startswith('```'):
        txt=re.sub(r'^```(?:json)?\s*','',txt)
        txt=re.sub(r'\s*```$','',txt)
    return json.loads(txt)

def ai_generate(transcript,provider,model):
    if provider=='openai':
        key=setting('OPENAI_API_KEY')
        if not key or not model:raise RuntimeError('OpenAI API key/model missing')
        with httpx.Client(timeout=80) as cli:
            r=cli.post('https://api.openai.com/v1/responses',headers={'Authorization':f'Bearer {key}'},
               json={'model':model,'instructions':SYSTEM,'input':transcript})
            r.raise_for_status();out=r.json()
        raw='\n'.join(item.get('text','') for x in out.get('output',[]) for item in x.get('content',[]) if item.get('type')=='output_text')
        return parse_json_response(raw)
    if provider=='anthropic':
        key=setting('ANTHROPIC_API_KEY')
        if not key or not model:raise RuntimeError('Anthropic API key/model missing')
        with httpx.Client(timeout=80) as cli:
            r=cli.post('https://api.anthropic.com/v1/messages',headers={'x-api-key':key,'anthropic-version':'2023-06-01'},
               json={'model':model,'max_tokens':2200,'system':SYSTEM,'messages':[{'role':'user','content':transcript}]})
            r.raise_for_status();out=r.json()
        raw='\n'.join(x.get('text','') for x in out.get('content',[]) if x.get('type')=='text')
        return parse_json_response(raw)
    if provider=='offline':
        # Demonstrates the pipeline without requiring a paid API key.
        sentences=re.split(r'(?<=[.!?])\s+',transcript.strip())
        snippet=next((s for s in sentences if len(s)>=18),sentences[0] if sentences else '')[:220]
        return {'slides':[{'title':'Teaching insight '+str(i),'quote':snippet,'explanation':'Editorial summary required.'} for i in range(1,4)],
                'reels':[{'hook':'Select the strongest introduction','exact_excerpt':snippet,'note':'Editorial selection required; locate in video manually'}],
                'scriptures_referenced':[],'verification_notes':['Offline demonstration; does not infer teaching content.']}
    raise ValueError('provider must be openai, anthropic or offline')

def check_exact_quotes(transcript,data):
    problems=[]
    slides=data.get('slides',[])
    reels=data.get('reels',[])
    if len(slides)!=3: problems.append('Exactly three slides required')
    if len(reels) not in (1,2): problems.append('One or two reel selections required')
    for i,s in enumerate(slides):
        q=s.get('quote','')
        if not q or q not in transcript:problems.append(f'slide {i+1}: quote missing or not verbatim')
    for i,r in enumerate(reels):
        q=r.get('exact_excerpt','')
        if not q or q not in transcript:problems.append(f'reel {i+1}: excerpt missing or not verbatim')
    return problems

def draft_teaching(transcript,reference,provider='offline',model=''):
    if not transcript or len(transcript)<20:raise ValueError('Supply an actual teaching transcript')
    if len(transcript)>100000:raise ValueError('Transcript too long for this endpoint; split it')
    data=ai_generate(transcript,provider,model)
    problems=check_exact_quotes(transcript,data)
    status='REVIEW_REQUIRED' if problems else 'READY_FOR_HUMAN_REVIEW'
    with connect() as db:
        cur=db.execute('''INSERT INTO ai_assets(created_at,teaching_ref,asset_json,quote_check,status) VALUES(?,?,?,?,?)''',
            (now_iso(),reference,json.dumps(data,ensure_ascii=False),json.dumps(problems),status))
        asset_id=cur.lastrowid
    return {'asset_id':asset_id,'asset':data,'quote_verification_issues':problems,'status':status}
