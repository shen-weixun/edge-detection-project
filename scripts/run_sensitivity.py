from pathlib import Path
import requests,json,hashlib,csv,time,os
base='http://127.0.0.1:8080/api/offloading'
out=Path(os.getenv('EXPERIMENT_OUTPUT',str(Path(__file__).resolve().parents[1]/'work'/'sensitivity')));out.mkdir(parents=True,exist_ok=True)
profiles=requests.get(base+'/profiles').json()
p=next(x for x in profiles if x['dataset']=='lfw' and x['count']==30 and x['status']=='completed' and (not os.getenv('WORKLOAD_PROFILE_ID') or x['id']==os.getenv('WORKLOAD_PROFILE_ID')))
print('PROFILE',p['id'],flush=True)
nodes={'local':{'speed':1,'rtt_ms':0,'bandwidth_mbps':1000},'edge':{'speed':3,'rtt_ms':20,'bandwidth_mbps':120},'cloud':{'speed':8,'rtt_ms':100,'bandwidth_mbps':55}}
common=dict(workload_mode='measured',profile_id=p['id'],count=30,seed=42,include_decision_overhead=True,nodes=nodes)
def run(body):
 r=requests.post(base+'/experiments',json=body,timeout=900);r.raise_for_status();return r.json()
warm=run(dict(common,count=1,strategies=['laya'],deadline_ms=1000,interval_ms=1000))
(out/'warmup.json').write_text(json.dumps(warm,ensure_ascii=False,indent=2),encoding='utf-8')
print('WARMED',warm['strategies']['laya']['summary']['avg_decision_ms'],flush=True)
rows=[];runs=[];imagehash=None
for interval in [70,300,1000]:
 for deadline in [500,1000,2000]:
  result=run(dict(common,strategies=['local_only','edge_only','cloud_only','load_threshold','latency_aware','laya'],interval_ms=interval,deadline_ms=deadline))
  manifest=[{k:v for k,v in t.items() if k not in ['arrival_ms','deadline_ms']} for t in result['workload']]
  digest=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()
  if imagehash is None:imagehash=digest
  assert digest==imagehash,'image batch/order changed'
  for strategy,v in result['strategies'].items():
   assert [t['task'] for t in v['tasks']]==result['workload']
   s=v['summary'];c=s['components_ms']
   rows.append(dict(interval_ms=interval,deadline_ms=deadline,strategy=strategy,avg_latency_ms=s['avg_latency_ms'],p95_latency_ms=s['p95_latency_ms'],deadline_met_rate=s['deadline_met_rate'],avg_decision_ms=s['avg_decision_ms'],decision_queue_ms=c['decision_queue_ms'],cpu_queue_ms=c['queue_ms'],network_ms=c['network_ms'],compute_ms=c['compute_ms'],**{n+'_count':s['placement'][n] for n in ['local','edge','cloud']}))
  path=out/f'interval-{interval}-deadline-{deadline}.json';path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');runs.append(result)
  with (out/'summary.csv').open('w',newline='',encoding='utf-8-sig') as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
  s=result['strategies']['laya']['summary'];print('DONE',interval,deadline,s['placement'], 'decision',s['avg_decision_ms'],'latency',s['avg_latency_ms'],'deadline',s['deadline_met_rate'],flush=True)
(out/'manifest.json').write_text(json.dumps(dict(profile=p,image_batch_sha256=imagehash,nodes=nodes,grid_runs=9,policies=6,tasks_per_policy=30,warmup_excluded=True),ensure_ascii=False,indent=2),encoding='utf-8')
print('GRID COMPLETE',flush=True)
