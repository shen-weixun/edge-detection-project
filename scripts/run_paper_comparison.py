"""Frozen multi-seed fair comparison; restart-safe and keeps every raw outcome.
Laya V2 failed reliability diagnostics and is labelled exploratory, not ranked.
"""
from pathlib import Path
from dataclasses import asdict
import json,csv,hashlib,itertools,random,time,requests
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'work/paper-improvements';CELLS=OUT/'matrix';CELLS.mkdir(exist_ok=True)
selection=json.loads((OUT/'results/estimator-evaluation.json').read_text(encoding='utf-8'))
MODELS=selection['model_ids'];FEATURE=selection['best_feature'];PROFILES=selection['test_profile_ids']
BASE={'local':dict(speed=1,rtt_ms=0,bandwidth_mbps=1000),'edge':dict(speed=3,rtt_ms=20,bandwidth_mbps=120),'cloud':dict(speed=8,rtt_ms=100,bandwidth_mbps=55)}
ENVIRONMENTS={'reference':dict(nodes=BASE,network_mode='independent',shared_bandwidth_mbps=120),
 'network_constrained':dict(nodes={**BASE,'edge':dict(speed=3,rtt_ms=100,bandwidth_mbps=8),'cloud':dict(speed=8,rtt_ms=300,bandwidth_mbps=4)},network_mode='shared',shared_bandwidth_mbps=8),
 'fast_compute':dict(nodes={**BASE,'edge':dict(BASE['edge'],speed=6),'cloud':dict(BASE['cloud'],speed=16)},network_mode='independent',shared_bandwidth_mbps=120)}
POLICIES=['local_only','edge_only','cloud_only','load_threshold','latency_aware','latency_aware_v2']
LOADS={'low':10000,'medium':200,'high':25};SEEDS=[11,23,37]
sourcefiles=['backend/app/offloading/'+n+'.py' for n in ['estimators','latency_v2','strategies','experiment','laya_client']]+['laya_service/server.py']
implementation={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sourcefiles}
config=dict(task_count=6,deadline_ms=1000,seeds=SEEDS,loads_ms=LOADS,environments=ENVIRONMENTS,models=MODELS,profiles=PROFILES,implementation_sha256=implementation,
            scope='policy end-to-end includes saved-model prediction and policy wall time; engine/image read/decode assumptions unchanged',laya_v2_scope='exploratory_only_failed_reliability')
manifest=OUT/'matrix-config.json'
if manifest.exists():assert json.loads(manifest.read_text())==config,'Frozen matrix configuration changed'
else:manifest.write_text(json.dumps(config,indent=2),encoding='utf-8')
truths={};summaries=[];raw_ids=[]
def run(dataset,environment,load,seed,estimator,scope,policies):
    label='-'.join(map(str,[dataset,environment,load,seed,estimator,scope]));path=CELLS/(label+'.json')
    names=list(policies);random.Random(int(hashlib.sha256(label.encode()).hexdigest()[:8],16)).shuffle(names)
    body=dict(workload_mode='measured',profile_id=PROFILES[dataset],count=6,seed=seed,interval_ms=LOADS[load],deadline_ms=1000,strategies=names,
              include_decision_overhead=scope not in ('ablation','exploratory_ablation'),information_mode='oracle' if scope=='oracle' else 'realistic',**ENVIRONMENTS[environment])
    if scope!='oracle':body['estimator_id']=MODELS[estimator]
    if path.exists():
        x=json.loads(path.read_text(encoding='utf-8'));assert x['request']==body
    else:
        response=requests.post('http://127.0.0.1:8080/api/offloading/experiments',json=body,timeout=600)
        response.raise_for_status();x=response.json();x['request']=body
        path.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
    true=[{k:v for k,v in t.items() if k!='estimated_workload_ms'} for t in x['workload']]
    digest=hashlib.sha256(json.dumps(true,sort_keys=True).encode()).hexdigest();key=(dataset,environment,load,seed)
    if key in truths:assert truths[key]==digest,'Different actual workload across methods'
    truths[key]=digest
    for name,result in x['strategies'].items():
        assert [r['task'] for r in result['tasks']]==x['workload']
        for r in result['tasks']:
            assert abs(r['total_latency_ms']-sum(r[k] for k in ['network_ms','queue_ms','compute_ms','decision_ms','decision_queue_ms']))<1e-6
            assert abs(r['total_latency_ms']-r['completed_at_ms']+r['arrival_ms'])<1e-6
            assert 'workload_ms' not in r['decision_input'] and 'face_count' not in r['decision_input']
            if scope in ('ablation','exploratory_ablation'):assert r['decision_ms']==0 and r['decision_queue_ms']==0
            if name.startswith('laya'):assert r['decision_audit_id'];raw_ids.append(r['decision_audit_id'])
        s=result['summary'];c=s['components_ms']
        summaries.append(dict(dataset=dataset,environment=environment,load=load,seed=seed,estimator=estimator,scope=scope,strategy=name,actual_workload_sha256=digest,
             avg_latency_ms=s['avg_latency_ms'],p95_ms=s['p95_latency_ms'],deadline_met_rate=s['deadline_met_rate'],decision_ms=c['decision_ms'],decision_queue_ms=c['decision_queue_ms'],network_ms=c['network_ms'],cpu_queue_ms=c['queue_ms'],compute_ms=c['compute_ms'],
             **{n+'_ratio':s['placement_ratio'][n] for n in BASE},**{n+'_time_weighted_queue':result['node_statistics'][n]['mean_queue_time_weighted'] for n in BASE}))
    with (OUT/'matrix-summary.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=list(summaries[0]));writer.writeheader();writer.writerows(summaries)
    (OUT/'matrix-audit-ids.json').write_text(json.dumps(raw_ids),encoding='utf-8')
    print('CELL',label,'PASS',len(x['strategies']),flush=True)

# Primary formal and prediction-isolation comparison, separately labelled oracle.
for dataset,env,load,seed in itertools.product(PROFILES,ENVIRONMENTS,LOADS,SEEDS):
    run(dataset,env,load,seed,'median','formal',POLICIES+['laya'])
    run(dataset,env,load,seed,FEATURE,'formal',POLICIES)
    run(dataset,env,load,seed,'oracle','oracle',['latency_aware_v2'])
# Decision cost ablation only in the unchanged reference environment.
for dataset,load,seed in itertools.product(PROFILES,LOADS,SEEDS):
    run(dataset,'reference',load,seed,'median','ablation',POLICIES+['laya'])
# Unreliable V2 is retained for honest, bounded exploratory comparison.
for dataset,load,scope in itertools.product(PROFILES,LOADS,['exploratory','exploratory_ablation']):
    run(dataset,'reference',load,11,'median',scope,['laya_v2'])
(OUT/'matrix-complete.json').write_text(json.dumps(dict(cells=len(list(CELLS.glob('*.json'))),summary_rows=len(summaries),true_workload_cells=len(truths),laya_audit_ids=len(raw_ids),status='COMPLETE'),indent=2),encoding='utf-8')
print('MATRIX COMPLETE',len(summaries),flush=True)
