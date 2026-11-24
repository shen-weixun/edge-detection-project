"""Actual HTTP regression for formal profiles; deliberately zero Laya model calls."""
from pathlib import Path
import requests,json,csv,io,hashlib,statistics,gzip
ROOT=Path(__file__).resolve().parents[1];O=ROOT/'work/formal-evaluation/tests';O.mkdir(parents=True,exist_ok=True);P=ROOT/'profiles/formal-evaluation';ids=json.loads((P/'profile-ids.json').read_text());model=json.loads((P/'evaluation/fit-complete.json').read_text())['models'];base='http://127.0.0.1:8080';checks=[];raw=[]
def check(name,condition):
 assert condition,name
 checks.append(name);print('PASS',name,flush=True)
def get(url):r=requests.get(base+url,timeout=60);r.raise_for_status();return r

def post(body,expected=200):
 r=requests.post(base+'/api/offloading/experiments',json=body,timeout=300);check('HTTP '+str(body.get('strategies','default'))+' expected '+str(expected),r.status_code==expected)
 if r.status_code==200:raw.append(dict(request=body,response=r.json()));return r.json()
 return r.json()
for page in ('/','/simulator.html','/simulator.js','/api/health'):check('page '+page,get(page).status_code==200)
ms=get('/api/offloading/estimators').json();check('formal models discoverable',set(model.values()) <= {m['id'] for m in ms})
for key,identifier in ids.items():
 meta=get('/api/offloading/profiles/'+identifier).json();content=get('/api/offloading/profiles/'+identifier+'/csv').content;rows=list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))));check('profile count '+key,len(rows)==(100 if key.endswith('testing') else 40 if key.endswith('training') else 20));check('profile checksum '+key,hashlib.sha256(content).hexdigest()==meta['csv_sha256']);check('actual repeated medians '+key,all(r['success']=='True' and int(r['repeats'])>=3 and abs(float(r['inference_ms'])-statistics.median(json.loads(r['inference_samples_ms'])))<1e-6 for r in rows))
for dataset in ('lfw','wider_train'):
 truths=[]
 for name,identifier in model.items():
  b=dict(workload_mode='measured',profile_id=ids[dataset+'/testing'],count=100,seed=11,interval_ms=70,deadline_ms=1000,estimator_id=identifier,strategies=['local_only','edge_only','cloud_only','load_threshold','latency_aware','latency_aware_v2'] if name=='median' else ['latency_aware','latency_aware_v2']);x=post(b);truths.append([{k:v for k,v in t.items() if k!='estimated_workload_ms'} for t in x['workload']]);check('100 unique '+dataset+'/'+name,len({t['source_path'] for t in x['workload']})==100)
  for strategy,v in x['strategies'].items():
   check('same tasks '+dataset+'/'+name+'/'+strategy,[r['task'] for r in v['tasks']]==x['workload']);check('conservation '+dataset+'/'+name+'/'+strategy,all(abs(t['total_latency_ms']-sum(t[k] for k in ('network_ms','queue_ms','compute_ms','decision_ms','decision_queue_ms')))<1e-6 for t in v['tasks']));check('DTO privacy '+dataset+'/'+name+'/'+strategy,all(not {'workload_ms','face_count','source_path'} & t['decision_input'].keys() for t in v['tasks']))
 check('same hidden truth across estimators '+dataset,truths[0]==truths[1])
b=dict(workload_mode='measured',profile_id=ids['lfw/testing'],count=3,estimator_id=model['median'],strategies=['latency_aware','latency_aware_v2'])
for label,extra in [('missing model',dict(estimator_id='0'*64)),('two estimators',dict(calibration_profile_id=ids['lfw/training'])),('training overlap',dict(profile_id=ids['lfw/training'])),('validation overlap',dict(profile_id=ids['lfw/validation'])),('oracle',dict(information_mode='oracle')),('synthetic',dict(workload_mode='synthetic',profile_id=None)),('dqn',dict(strategies=['dqn'])),('ddqn',dict(strategies=['ddqn'])),('too many AI tasks',dict(strategies=['laya'],count=51)),('invalid policy',dict(strategies=['unknown']))]:
 r=requests.post(base+'/api/offloading/experiments',json=dict(b,**extra),timeout=60);check('reject '+label,r.status_code==422)
for network in ('independent','shared'):
 for policy in ('complete_all','drop_if_expired'):
  x=post(dict(b,network_mode=network,deadline_policy=policy,deadline_ms=1))
  for v in x['strategies'].values():check('terminal accounting '+network+'/'+policy,v['summary']['completed_count']+v['summary']['dropped_count']==3)
x=post(dict(b,estimator_id=None,calibration_profile_id=ids['lfw/training'],strategies=None) | {'strategies':['local_only','edge_only','cloud_only','load_threshold','latency_aware']});check('legacy calibration entry',x['estimator']['kind']=='disjoint_historical_median')
s=post(dict(workload_mode='synthetic',count=3));check('legacy defaults five',len(s['strategies'])==5)
# Real homepage inference, after all formal measurement and timing runs ended.
rows=list(csv.DictReader(io.StringIO(get('/api/offloading/profiles/'+ids['lfw/testing']+'/csv').text)));sample=next(r['sample_id'] for r in rows if int(r['face_count'])==1)
r=requests.post(base+f'/api/samples/{sample}/detect',timeout=300);check('homepage actual detection',r.status_code==200 and r.json()['execution_mode']=='local_baseline')
image=get(f'/api/samples/{sample}/image').content;r=requests.post(base+'/api/verify',files={'first':('a.jpg',image,'image/jpeg'),'second':('b.jpg',image,'image/jpeg')},timeout=300);check('homepage actual verification',r.status_code==200 and r.json()['match'])
with gzip.open(O/'api-raw.json.gz','wt',encoding='utf-8') as f:json.dump(raw,f,ensure_ascii=False)
(O/'api-results.json').write_text(json.dumps(dict(passed=len(checks),new_laya_calls=0,checks=checks),ensure_ascii=False,indent=2),encoding='utf-8');print('TOTAL',len(checks),'PASSED, Laya calls=0',flush=True)
