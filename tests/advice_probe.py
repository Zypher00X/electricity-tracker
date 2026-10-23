"""Explicit developer-only model discovery. Never prints the API key or error body."""
import json
import os
from pathlib import Path
from urllib import request, error

def load_env():
    for line in Path('.env').read_text(encoding='utf-8-sig').splitlines():
        if '=' not in line or line.lstrip().startswith('#'): continue
        key,value=line.split('=',1)
        os.environ.setdefault(key.strip(),value.strip().strip('"').strip("'"))

def call(path, payload=None, timeout=45):
    req=request.Request('https://generativelanguage.googleapis.com/v1beta/'+path,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={'x-goog-api-key':os.environ['GEMINI_API_KEY'],'Content-Type':'application/json'})
    try:
        with request.urlopen(req,timeout=timeout) as res:return res.status,json.load(res)
    except error.HTTPError as exc:return exc.code,{}
    except Exception as exc:return type(exc).__name__,{}

if __name__=='__main__':
    load_env()
    assert os.environ.get('GEMINI_API_KEY'),'GEMINI_API_KEY missing'
    status,data=call('models?pageSize=1000')
    names=[m['name'].split('/')[-1] for m in data.get('models',[]) if 'generateContent' in m.get('supportedGenerationMethods',[])]
    candidates=[name for name in ['gemini-2.5-flash-lite','gemini-3.1-flash-lite','gemini-3.5-flash-lite','gemini-2.5-flash','gemini-3.6-flash','gemini-3.8-flash','gemini-2.0-flash'] if name in names]
    print(json.dumps({'list_status':status,'eligible_candidates':candidates}))
    for model in candidates:
        code,result=call('models/'+model+':generateContent',{'contents':[{'parts':[{'text':'Return JSON {"ok":true} only.'}]}], 'generationConfig':{'responseMimeType':'application/json','maxOutputTokens':128}})
        ok=code==200 and bool(result.get('candidates'))
        print(json.dumps({'model':model,'status':code,'generated':ok}))
        if ok:
            Path('tmp').mkdir(exist_ok=True)
            Path('tmp/advice-model.json').write_text(json.dumps({'model':model,'usage':result.get('usageMetadata',{})}),encoding='utf-8')
            break
