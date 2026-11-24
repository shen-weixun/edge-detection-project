"""HTTP and original homepage regression; no extra Laya inference."""
from pathlib import Path
import requests,json,hashlib
ROOT=Path(__file__).resolve().parents[1];O=ROOT/'work/ai-comparison/tests';O.mkdir(parents=True,exist_ok=True);DATA=ROOT/'profiles/ai-comparison';BASE='http://127.0.0.1:8080';checks=[]
def check(name,condition):assert condition,name;checks.append(name);print('PASS',name,flush=True)
def get(url):r=requests.get(BASE+url,timeout=30);r.raise_for_status();return r
for page in ('/','/simulator.html','/ai-comparison.html','/api/health'):check('HTTP '+page,get(page).status_code==200)
for module in ('ai-comparison.js','ai-comparison-data.js'):check('module MIME '+module,'javascript' in get('/'+module).headers['Content-Type'])
catalog=get('/ai-comparison/catalog.json').json();check('catalog 24 scenes',len(catalog['scenarios'])==24)
for s in catalog['scenarios']:
 x=get('/ai-comparison/'+s['results_file']).json();check('same-scene rows '+s['id'],len(x['rows'])==10 and all(r['scenario_id']==s['id'] and r['dataset']==s['dataset'] and r['load']==s['load'] and r['network']==s['network'] and r['count']==10 and r['seed']==11 for r in x['rows']));check('no fake DQN performance '+s['id'],all(r['status']=='BLOCKED' and r['avg_latency_ms'] is None for r in x['rows'] if r['strategy'] in ('dqn','ddqn')))
for dataset in ('lfw','wider_train'):
 file='charts/'+dataset+'/Low/reference.png';content=get('/ai-comparison/'+file).content;check('actual published PNG '+dataset,hashlib.sha256(content).hexdigest()==hashlib.sha256((DATA/file).read_bytes()).hexdigest())
for key in ('dqn','ddqn'):
 r=requests.post(BASE+'/api/offloading/experiments',json=dict(workload_mode='synthetic',count=1,strategies=[key]),timeout=30);check('unknown contract API not enabled '+key,r.status_code==422)
r=requests.post(BASE+'/api/offloading/experiments',json=dict(workload_mode='synthetic',count=2),timeout=60);r.raise_for_status();x=r.json();check('legacy default five',len(x['strategies'])==5);check('legacy API conservation',all(abs(t['total_latency_ms']-sum(t[k] for k in ('network_ms','queue_ms','compute_ms','decision_ms','decision_queue_ms')))<1e-6 for s in x['strategies'].values() for t in s['tasks']))
subset=json.loads((DATA/'task_subset_manifest.json').read_text());sample=next(r['sample_id'] for r in subset['lfw']['images'] if r['face_count_posthoc']==1)
r=requests.post(BASE+f'/api/samples/{sample}/detect',timeout=300);check('original real InsightFace detection',r.status_code==200 and r.json()['execution_mode']=='local_baseline');image=get(f'/api/samples/{sample}/image').content;r=requests.post(BASE+'/api/verify',files={'first':('a.jpg',image,'image/jpeg'),'second':('b.jpg',image,'image/jpeg')},timeout=300);check('original real same-image verification',r.status_code==200 and r.json()['match'])
(O/'http-results.json').write_text(json.dumps(dict(passed=len(checks),checks=checks,extra_laya_calls=0),ensure_ascii=False,indent=2),encoding='utf-8');print('TOTAL',len(checks),'PASSED')
