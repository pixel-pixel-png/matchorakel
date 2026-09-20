"""Execute explicit oracles, record every outcome. No implicit live AI usage."""
import argparse
import io
import json
import math
import re
import sys
import time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from qa.support import Sandbox
from fixtures import fixture_public,display_fixture_date
from goal_model import GoalModel
from language_chat import _candidate,clean_ai_answer,validate_answer,general_answer,_cache,build_payload
from urllib.error import HTTPError

def strings(v):
 if isinstance(v,str):yield v
 elif isinstance(v,dict):
  for k,x in v.items():
   if k not in ('created_at','analysis_id','context','source','source_note','scoreline','as_of','venue_source'):yield from strings(x)
 elif isinstance(v,list):
  for x in v:yield from strings(x)
def check(case,env):
 mode=case['mode']
 if mode=='chat':
  r=env.client.post('/chat',json={k:case[k] for k in ('message','context','history') if k in case});d=r.get_json()
  assert r.status_code==case.get('status',200),(r.status_code,d)
  assert d.get('kind')==case['kind'],d
  if case.get('pair'):
   code,h,a=case['pair'];assert d.get('context')=={'league':code,'home':h,'away':a},d
  if case.get('fixture_status'):assert all(f['status']==case['fixture_status'] for f in d.get('fixtures',[])),d
  if case.get('language'):assert d.get('language')==case['language'],d
  if case.get('contains'):assert case['contains'].casefold() in json.dumps(d,ensure_ascii=False).casefold(),d
  visible=' '.join(strings(d))
  assert not re.search(r'\b(undefined|nan|null)\b|\{team\}|\{home\}',visible,re.I),visible
  assert not re.search(r'Bra fråga|Hoppas det hjälper|Säg till om du vill veta mer',visible,re.I),visible
  if d['kind']=='prediction':
   assert d['response'].startswith('Prediction:'),d
   assert abs(sum(d['probabilities'].values())-100)<=1,d
   assert all(math.isfinite(v) and 0<=v<=100 for v in d['probabilities'].values()),d
   assert all(isinstance(d['scoreline'][k],int) and 0<=d['scoreline'][k]<=7 for k in ('home','away')),d
   second=env.client.post('/chat',json={k:case[k] for k in ('message','context','history') if k in case}).get_json()
   assert d['scoreline']==second.get('scoreline') and d['probabilities']==second.get('probabilities'),d
  return {'kind':d['kind'],'context':d.get('context'),'response':d.get('response',d.get('summary',''))}
 if mode=='http':
  r=env.client.post('/chat',json=case['body']);assert r.status_code==case['status'],(r.status_code,r.get_json());return {'status':r.status_code}
 if mode=='corrupt_fixture':
  path=env.root/'data/fixtures.json';old=path.read_bytes()
  try:
   path.write_text(case['value']);r=env.client.get('/api/fixtures');assert r.status_code==200;assert r.get_json()==[]
  finally:path.write_bytes(old)
  return {'handled':True}
 if mode=='payload':
  _,p=build_payload('Offside?',{},case['history']);roles=[x['role'] for x in p['contents']]
  assert len(roles)<=17 and roles[-1]=='user' and all(x==('user' if i%2==0 else 'model') for i,x in enumerate(roles)),roles
  assert 'systemInstruction' in p;return {'roles':roles}
 if mode=='invalid_matrix':
  try:GoalModel.matrix(*case['rates'])
  except ValueError:return {'rejected':True}
  raise AssertionError('Invalid rate accepted')
 if mode=='invalid_answer':
  assert not validate_answer(case['value'],{},'Fotbollsfråga'),case['value'];return {'rejected':True}
 if mode=='http_error':
  _cache.clear()
  def fail(*a,**k):raise HTTPError('url',case['code'],'test',{},io.BytesIO(b'{}'))
  with patch.dict('os.environ',{'GEMINI_API_KEY':'test-secret'}),patch('language_chat.urlopen',side_effect=fail),patch('language_chat.time.sleep'):
   assert general_answer('Offside?',{}) is None
  return {'handled':case['code']}
 if mode=='matrix':
  m=GoalModel.matrix(*case['rates']);assert math.isclose(float(m.sum()),1,abs_tol=1e-9) and (m>=0).all() and (m<=1).all();return {'sum':float(m.sum())}
 if mode=='fixture':
  f=fixture_public({'home':'Barcelona','away':'Sevilla','league':'LL','utc_date':'2099-10-21T00:00:00Z','status':case['status']})
  value=display_fixture_date(f);assert ('avspark inte fastställd' in value)==(case['status']=='SCHEDULED'),value;return {'date':value}
 if mode=='gemini':
  result,reason=_candidate(case['payload']);assert result==case['expected'],(result,reason);return {'reason':reason}
 if mode=='clean':
  result=clean_ai_answer(case['value']);assert result==case['expected'],result;return {'text':result}
 raise AssertionError('Unknown test mode')
def run(round_id):
 cases=json.loads(Path('qa/cases.json').read_text());results=[]
 with Sandbox() as env,patch.dict('os.environ',{'GEMINI_API_KEY':''}):
  for c in cases:
   started=time.monotonic()
   try:detail=check(c,env);ok=True
   except Exception as e:detail={'error':str(e)[:1600]};ok=False
   results.append({'id':c['id'],'class':c['class'],'passed':ok,'seconds':round(time.monotonic()-started,4),**detail})
 report={'round':round_id,'cases':len(results),'passed':sum(x['passed'] for x in results),'failed':[x for x in results if not x['passed']],'results':results}
 Path('qa/results').mkdir(exist_ok=True);Path(f'qa/results/round-{round_id}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
 print(json.dumps({k:v for k,v in report.items() if k!='results'},ensure_ascii=False,indent=2));return len(report['failed'])
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--round',default='initial');args=p.parse_args();sys.exit(bool(run(args.round)))
