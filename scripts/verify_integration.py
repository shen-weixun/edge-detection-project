import requests,time,csv,io,json,hashlib,sys
from pathlib import Path
BASE='http://127.0.0.1:8080'
out=Path(__file__).resolve().parents[1]/'work'/'verification';out.mkdir(parents=True,exist_ok=True)
checks=[]
def check(name,cond):
    assert cond,name
    checks.append(name);print('PASS',name,flush=True)
def get(p):
    r=requests.get(BASE+p,timeout=60);r.raise_for_status();return r.json()
def post(p,b,timeout=600):
    r=requests.post(BASE+p,json=b,timeout=timeout);r.raise_for_status();return r.json()
def profile(dataset,count):
    existing=get('/api/offloading/profiles') if '--reuse-profiles' in sys.argv else []
    p=next((x for x in existing if x['dataset']==dataset and x['count']==count and x['status']=='completed' and x['succeeded']==count),None)
    if p is None: p=post('/api/offloading/profiles',dict(dataset=dataset,count=count,seed=42,repeats=3))
    deadline=time.monotonic()+1800
    while p['status']=='running':
        assert time.monotonic()<deadline,'profile timeout'
        time.sleep(2);p=get('/api/offloading/profiles/'+p['id'])
        print('PROFILE',dataset,p['completed'],p['status'],flush=True)
    check(dataset+' real measurement completed',p['status']=='completed' and p['succeeded']==count and p['failed']==0)
    r=requests.get(BASE+'/api/offloading/profiles/'+p['id']+'/csv');r.raise_for_status()
    check(dataset+' CSV checksum',hashlib.sha256(r.content).hexdigest()==p['csv_sha256'])
    rows=list(csv.DictReader(io.StringIO(r.text)))
    check(dataset+' real CSV schema',all(float(x['inference_ms'])>0 and len(json.loads(x['inference_samples_ms']))==3 and int(x['width'])>0 and x['success']=='True' for x in rows))
    (out/(dataset+'-profile.csv')).write_bytes(r.content)
    return p,rows
for page in ['/','/simulator.html','/simulator.js','/api/health']:
    check(page+' HTTP',requests.get(BASE+page,timeout=30).status_code==200)
for body in [dict(workload_mode='measured',count=1),dict(workload_mode='measured',profile_id='0'*32,count=1),dict(workload_mode='synthetic',profile_id='0'*32),dict(strategies=['dqn'])]:
    check('invalid measured/mode/strategy '+str(body),requests.post(BASE+'/api/offloading/experiments',json=body).status_code==422)
for body in [dict(dataset='invalid'),dict(dataset='lfw',repeats=2),dict(dataset='lfw',count=501)]:
    check('profile validation '+str(body),requests.post(BASE+'/api/offloading/profiles',json=body).status_code==422)
p,rows=profile('lfw',30)
w,wr=profile('wider_val',3)
body=dict(workload_mode='measured',profile_id=p['id'],count=30,seed=42,include_decision_overhead=True)
a=post('/api/offloading/experiments',body)
check('CSV actually reaches SimPy',a['profile_source']=='measured_csv' and a['profile']['id']==p['id'])
lookup={x['source_path']:x for x in rows}
check('CSV inference times unchanged in tasks',all(t['workload_ms']==float(lookup[t['source_path']]['inference_ms']) for t in a['workload']))
check('five policies same tasks',all([t['task'] for t in s['tasks']]==a['workload'] for s in a['strategies'].values()))
check('delay decomposition',all(abs(t['total_latency_ms']-sum(t[k] for k in ['network_ms','queue_ms','compute_ms','decision_ms','decision_queue_ms']))<.002 for s in a['strategies'].values() for t in s['tasks']))
check('explicit no-drop completion',all(s['summary']['completion_rate']==1 and s['summary']['drop_rate']==0 for s in a['strategies'].values()))
b=post('/api/offloading/experiments',body)
check('repeat experiment identical workload hash',a['workload_sha256']==b['workload_sha256'])
s=post('/api/offloading/experiments',dict(workload_mode='synthetic',count=3))
check('explicit synthetic label',s['profile_source']=='synthetic_demo_NOT_measured' and s['profile'] is None)
v=post('/api/offloading/experiments',dict(workload_mode='measured',profile_id=w['id'],count=3))
check('WIDER real profile reaches SimPy',all(t['dataset']=='wider_val' for t in v['workload']))
sample=next(x['sample_id'] for x in rows if int(x['face_count'])==1)
r=requests.post(BASE+f'/api/samples/{sample}/detect',timeout=300);r.raise_for_status();check('homepage real sample detection',r.json()['execution_mode']=='local_baseline')
image=requests.get(BASE+f'/api/samples/{sample}/image').content
r=requests.post(BASE+'/api/verify',files={'first':('a.jpg',image,'image/jpeg'),'second':('b.jpg',image,'image/jpeg')},timeout=300)
check('homepage real same-image verification',r.status_code==200 and r.json()['match'])
laya=post('/api/offloading/experiments',dict(workload_mode='measured',profile_id=p['id'],strategies=['laya'],count=1,deadline_ms=1))
t=laya['strategies']['laya']['tasks'][0]
check('real Laya model decision',t['selected_node'] in ['local','edge','cloud'] and t['decision_model'] is not None)
check('Laya decision deadline miss reflected',not t['deadline_met'] and t['decision_ms']>1)
(out/'integration-results.json').write_text(json.dumps(dict(passed=len(checks),failed=0,checks=checks,profiles=[p,w],measured_experiment=a,laya_experiment=laya),ensure_ascii=False,indent=2),encoding='utf-8')
print('TOTAL',len(checks),'PASSED',flush=True)
