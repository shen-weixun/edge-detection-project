"""Frozen split evaluation and fair full-image policy matrix; no algorithm edits."""
import sys,os,json,csv,hashlib,gzip,random,itertools
from pathlib import Path
from dataclasses import replace,asdict
from collections import defaultdict,Counter
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from app.offloading import profiles
from app.offloading.estimators import WorkloadEstimator,identities,register
from app.offloading.integration_contract import validate_manifest_split
from app.offloading.experiment import experiment
from app.offloading.models import Task,NodeConfig
from app.offloading.simulator import Simulator
from app.offloading.strategies import FixedStrategy,LatencyAwareStrategy
from app.offloading.latency_v2 import LatencyAwareV2Strategy
from acceptance_reference import check_run
from formal_design import write_design,scenarios,POLICIES
OUT=profiles.root()/'formal-evaluation';E=OUT/'evaluation';E.mkdir(exist_ok=True)
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def writecsv(p,rows):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def measure(model,rows):
 y=np.array([r['workload_ms'] for r in rows]);pred=np.array([model.predict(r) for r in rows]);e=pred-y
 return dict(n=len(rows),mae_ms=float(np.abs(e).mean()),rmse_ms=float(np.sqrt(np.mean(e**2))),mean_bias_ms=float(e.mean()),absolute_error_p50_ms=float(np.quantile(abs(e),.5)),absolute_error_p95_ms=float(np.quantile(abs(e),.95)))
def load_data():
 plan=read(OUT/'plan.json');validate_manifest_split(plan['selected']);data=defaultdict(dict);measurements=[]
 ids=read(OUT/'profile-ids.json')
 for dataset in ('lfw','wider_train'):
  for role in ('training','validation','testing'):
   meta,rows=profiles.load(ids[dataset+'/'+role]);assert len(rows)==plan['counts'][role]
   lookup={r['source_path']:r for r in rows};enriched=[]
   for r in plan['selected']:
    if r['dataset']!=dataset or r['role']!=role:continue
    path=Path(os.getenv('DATASET_ROOT','/datasets'))/r['source_path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==r['image_sha256']
    m=read(OUT/'measurements'/(r['image_sha256']+'.json'));assert str(m['row']['success'])=='True' and len(json.loads(m['row']['inference_samples_ms']))>=3
    row=dict(lookup[r['source_path']],group=r['group'],image_sha256=r['image_sha256'],role=role);enriched.append(row);measurements.append(m)
   data[dataset][role]=enriched
 # Independently exclude historical registered measurements from the new test.
 old=set()
 for m in profiles.listing():
  if m.get('split_role') or m.get('derived_from'):continue
  p=profiles.path_for(m['id'],'.csv')
  if p.exists():old.update(r['source_path'] for r in csv.DictReader(p.open(encoding='utf-8-sig')))
 assert not old.intersection(r['source_path'] for d in data.values() for r in d['testing'])
 writecsv(OUT/'train_val_test_split.csv',plan['selected'])
 manifest=dict(schema='formal-dataset-v1',seed=plan['seed'],plan_sha256=hashlib.sha256((OUT/'plan.json').read_bytes()).hexdigest(),profiles=ids,
   counts={d:{role:len(rows) for role,rows in parts.items()} for d,parts in data.items()},group_counts={d:{role:len({r['group'] for r in rows}) for role,rows in parts.items()} for d,parts in data.items()},
   exact_cross_split_duplicates=0,group_cross_split_overlap=0,dhash_le4_cross_split=0,new_test_history_path_overlap=0,measurements=measurements,
   limits='WIDER event-folder is a conservative proxy for scene group, not verified person identity. dHash<=4 screen does not prove absence of every semantic/near duplicate. Timing batches differ for reused training rows; provenance is per-image.')
 save(OUT/'dataset_manifest.json',manifest);return data

def fit():
 if (E/'fit-complete.json').exists():print('FIT REUSE',flush=True);return
 data=load_data();train=sum((p['training'] for p in data.values()),[]);val=sum((p['validation'] for p in data.values()),[]);test=sum((p['testing'] for p in data.values()),[])
 models={}
 for kind,alphas in [('median',[1]),('ridge_raw',[.1,1,10]),('ridge_log',[.1,1,10])]:
  for alpha in alphas:
   name=kind if kind=='median' else kind+'-'+str(alpha);models[name]=replace(WorkloadEstimator.fit(train,kind,alpha),validation_identities=tuple(identities(val)))
   models[name].validate_test(test);models[name].save(E/'models'/(name+'.json'))
 validation={k:measure(m,val) for k,m in models.items()};ridge=min((k for k in models if k!='median'),key=lambda k:(validation[k]['mae_ms'],k));selected=min(models,key=lambda k:(validation[k]['mae_ms'],k))
 ids={k:register(models[k]) for k in ('median',ridge)}
 save(E/'validation-selection.json',dict(objective='pooled_validation_MAE_only',validation=validation,ridge=ridge,best_overall=selected,model_ids=ids,test_labels_used=False))
 results=[];predictions=[];subgroups=[];confidence=[]
 for dataset,part in data.items():
  rows=part['testing']
  for name,model in models.items():
   results.append(dict(dataset=dataset,model=name,**measure(model,rows)))
   for r in rows:
    p=model.predict(r);predictions.append(dict(dataset=dataset,model=name,source_path=r['source_path'],group=r['group'],image_sha256=r['image_sha256'],width=r['width'],height=r['height'],image_size_mb=r['image_size_mb'],actual_face_count_posthoc_only=r['face_count'],actual_ms=r['workload_ms'],predicted_ms=p,error_ms=p-r['workload_ms']))
   for label,predicate in [('high_resolution_ge1MP',lambda r:r['width']*r['height']>=1e6),('long_actual_ge1000ms',lambda r:r['workload_ms']>=1000),('multiple_faces_ge2',lambda r:r['face_count']>=2)]:
    rs=[r for r in rows if predicate(r)]
    subgroups.append(dict(dataset=dataset,model=name,subgroup=label,status='EVALUATED' if rs else 'NO_SAMPLES',**(measure(model,rs) if rs else dict(n=0,mae_ms='',rmse_ms='',mean_bias_ms='',absolute_error_p50_ms='',absolute_error_p95_ms=''))))
  diffs=np.array([abs(models[ridge].predict(r)-r['workload_ms'])-abs(models['median'].predict(r)-r['workload_ms']) for r in rows]);groups=sorted({r['group'] for r in rows});indices={g:np.array([i for i,r in enumerate(rows) if r['group']==g]) for g in groups};rng=np.random.default_rng(424242)
  boot=[float(diffs[np.concatenate([indices[g] for g in rng.choice(groups,len(groups),replace=True)])].mean()) for _ in range(2000)]
  confidence.append(dict(dataset=dataset,quantity='Ridge_MAE_minus_Median_MAE',delta_ms=float(diffs.mean()),ci95_low_ms=float(np.quantile(boot,.025)),ci95_high_ms=float(np.quantile(boot,.975)),bootstrap='cluster_by_group',groups=len(groups),n=len(rows),repeats=2000,seed=424242))
 cross=[];cross_selection={}
 for source,target in [('lfw','wider_train'),('wider_train','lfw')]:
  choices={k:WorkloadEstimator.fit(data[source]['training'],m.kind,m.ridge_alpha) for k,m in models.items()};v={k:measure(m,data[source]['validation']) for k,m in choices.items()};k=min(v,key=lambda k:(v[k]['mae_ms'],k));cross_selection[source]=dict(validation=v,selected=k)
  save(E/'cross-validation-selection.json',cross_selection)
  for name in ('median',k):
   if any(r['source_dataset']==source and r['model']==name for r in cross):continue
   cross.append(dict(source_dataset=source,target_dataset=target,model=name,source_validation_selected=k,**measure(choices[name],data[target]['testing'])))
 writecsv(OUT/'workload_estimator_results.csv',results);writecsv(E/'estimator_predictions.csv',predictions);writecsv(E/'estimator_subgroups.csv',subgroups);writecsv(E/'estimator_paired_ci.csv',confidence);writecsv(E/'cross_dataset.csv',cross)
 save(E/'fit-complete.json',dict(ridge=ridge,models=ids,test_images=200,confidence=confidence));print('FIT COMPLETE',ridge,confidence,flush=True)

def matrix():
 fit();data=load_data();selection=read(E/'validation-selection.json');ridge=selection['ridge'];models={k:WorkloadEstimator.load(E/'models'/(k+'.json')) for k in ('median',ridge)};design=write_design(OUT)
 config=dict(design_sha256=hashlib.sha256((OUT/'preregistered-design.json').read_bytes()).hexdigest(),dataset_sha256=hashlib.sha256((OUT/'plan.json').read_bytes()).hexdigest(),selection=selection,implementation={p:hashlib.sha256((Path('/app')/p).read_bytes()).hexdigest() for p in ('app/offloading/simulator.py','app/offloading/strategies.py','app/offloading/latency_v2.py','app/offloading/estimators.py','app/offloading/experiment.py','app/offloading/integration_contract.py')})
 p=E/'run-config.json'
 if p.exists():assert read(p)==config,'Frozen implementation/config changed'
 else:save(p,config)
 raw=E/'raw';raw.mkdir(exist_ok=True);summary=[];truths={}
 for i,s in enumerate(scenarios()):
  path=raw/(s['id']+'.json.gz')
  if path.exists():
   with gzip.open(path,'rt',encoding='utf-8') as f:x=json.load(f)
   assert x['scenario']==s
  else:
   profile=[{k:v for k,v in r.items() if k not in ('group','role','image_sha256')} for r in data[s['dataset']]['testing']]
   groups=[('median',POLICIES),(ridge,['latency_aware','latency_aware_v2'])];random.Random(s['id']).shuffle(groups);x=dict(scenario=s,results={})
   for estimator,names in groups:
    names=list(names);random.Random(s['id']+estimator).shuffle(names)
    result=experiment(strategies=names,count=100,profile=profile,seed=s['seed'],interval_ms=s['interval_ms'],deadline_ms=s['deadline_ms'],include_decision_overhead=True,nodes={k:NodeConfig(**v) for k,v in s['nodes'].items()},network_mode=s['network_mode'],shared_bandwidth_mbps=s['shared_bandwidth_mbps'],deadline_policy='complete_all',information_mode='realistic',estimator_model=models[estimator]);x['results'][estimator]=result
   temporary=path.with_suffix('.tmp')
   with gzip.open(temporary,'wt',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,allow_nan=False)
   temporary.replace(path)
  for estimator,result in x['results'].items():
   truth=[{k:v for k,v in t.items() if k!='estimated_workload_ms'} for t in result['workload']];sha=hashlib.sha256(json.dumps(truth,sort_keys=True).encode()).hexdigest()
   if s['id'] in truths:assert truths[s['id']]==sha
   truths[s['id']]=sha
   for strategy,v in result['strategies'].items():
    assert [r['task'] for r in v['tasks']]==result['workload'];assert len({r['task_id'] for r in v['tasks']})==100
    for t in v['tasks']:
     assert t['completed'] and not t['dropped'];assert abs(t['total_latency_ms']-sum(t[k] for k in ('network_ms','queue_ms','compute_ms','decision_ms','decision_queue_ms')))<1e-6
     assert abs(t['total_latency_ms']-t['completed_at_ms']+t['arrival_ms'])<1e-6
     assert not {'workload_ms','face_count','source_path'} & t['decision_input'].keys()
     assert t['arrival_ms']<=t['cpu_started_at_ms']<=t['cpu_completed_at_ms']<=t['completed_at_ms']
     assert abs(t['compute_ms']-t['task']['workload_ms']/s['nodes'][t['selected_node']]['speed'])<1e-6
    for node,stats in v['node_statistics'].items():
     assert 0<=stats['cpu_utilization']<=1+1e-9
     intervals=sorted((t['cpu_started_at_ms'],t['cpu_completed_at_ms']) for t in v['tasks'] if t['selected_node']==node)
     assert all(a[1]<=b[0]+1e-7 for a,b in zip(intervals,intervals[1:]))
    q=v['summary'];summary.append(dict(scenario_id=s['id'],dataset=s['dataset'],environment=s['environment'],interval_ms=s['interval_ms'],deadline_ms=s['deadline_ms'],seed=s['seed'],estimator='median' if estimator=='median' else 'ridge',estimator_model=estimator,strategy=strategy,count=100,actual_workload_sha256=sha,average_latency_ms=q['avg_latency_ms'],p95_latency_ms=q['p95_latency_ms'],deadline_met_rate=q['deadline_met_rate'],completion_rate=q['completion_rate'],drop_rate=q['drop_rate'],decision_wall_ms=q['avg_decision_wall_ms'],**q['components_ms'],**{n+'_ratio':q['placement_ratio'][n] for n in ('local','edge','cloud')},**{n+'_time_weighted_queue':v['node_statistics'][n]['mean_queue_time_weighted'] for n in ('local','edge','cloud')},**{n+'_utilization':v['node_statistics'][n]['cpu_utilization'] for n in ('local','edge','cloud')}))
  writecsv(OUT/'strategy_comparison.csv',summary);print('MATRIX',i+1,'/',len(scenarios()),s['id'],'PASS',flush=True)
 save(E/'matrix-complete.json',dict(scenarios=len(scenarios()),strategy_runs=len(summary),task_results=100*len(summary),laya_model_calls=0,validations='time conservation, unique tasks, exact same hidden truth, CPU intervals/capacity, original actual compute, hidden DTO fields'))
 # Independent outcome reference and deterministic replay are diagnostic only.
 verification=[]
 for dataset in ('lfw','wider_train'):
  for mode in ('independent','shared'):
   rs=data[dataset]['testing'];tasks=[Task(i,arrival_ms=i*70,deadline_ms=1000,estimated_workload_ms=models['median'].predict(r),**{k:v for k,v in r.items() if k not in ('group','role','image_sha256')}) for i,r in enumerate(rs)]
   for key,cls in [('v1',LatencyAwareStrategy),('v2',LatencyAwareV2Strategy),('edge',lambda:FixedStrategy('edge'))]:
    sim=Simulator(tasks,cls(),include_decision_overhead=False,network_mode=mode,shared_bandwidth_mbps=8);rows=sim.run();ref=check_run(sim,rows);again=Simulator(tasks,cls(),include_decision_overhead=False,network_mode=mode,shared_bandwidth_mbps=8).run()
    for a,b in zip(rows,again):
     for field in ('selected_node','completed_at_ms','cpu_started_at_ms','cpu_completed_at_ms','total_latency_ms','network_ms','queue_ms','compute_ms','deadline_met'):assert a[field]==b[field]
    verification.append(dict(dataset=dataset,network=mode,policy=key,n=len(rows),max_reference_error_ms=ref['max_reference_error_ms'],deterministic_replay=True))
 save(E/'independent-validation.json',verification);print('MATRIX COMPLETE',len(summary),flush=True)
if __name__=='__main__':
 write_design(OUT)
 if '--fit' in sys.argv:fit()
 else:matrix()
