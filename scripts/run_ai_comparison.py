"""Fixed common 10-image pilot; live Laya, blocked unknown DQN contract.
Durable policy-level checkpoints; per-decision writes happen after policy timer.
"""
import sys,os,json,csv,hashlib,time,random,traceback
from pathlib import Path
from dataclasses import asdict,replace
from statistics import mean
from urllib.request import urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.offloading import profiles
from app.offloading.models import Task,DecisionTask,NodeConfig
from app.offloading.workload import generate_tasks
from app.offloading.estimators import load_registered,EstimatedPolicy
from app.offloading.strategies import STRATEGY_FACTORIES,FixedStrategy
from app.offloading.laya_client import LayaStrategy,LayaV2Strategy
from app.offloading.simulator import Simulator
from app.offloading.experiment import metrics
from formal_design import ENVIRONMENTS
O=profiles.root()/'ai-comparison';O.mkdir(exist_ok=True);SEED=11;COUNT=10;DEADLINE=1000
ORDER=['local_only','edge_only','cloud_only','load_threshold','latency_aware','latency_aware_v2','dqn','ddqn','laya','laya_v2'];AVAILABLE=[n for n in ORDER if n not in ('dqn','ddqn')]
ENV_KEYS=['local_advantage','edge_advantage','cloud_advantage','reference'];RHOS={'Low':.3,'Medium':.9,'High':1.5}
FORMAL=profiles.root()/'formal-evaluation'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');tmp.replace(p)
def csvout(p,rows):
 with p.open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def make_plan():
 ids=read(FORMAL/'profile-ids.json');fit=read(FORMAL/'evaluation/fit-complete.json');model=load_registered(fit['models']['median']);sets={};scenes=[];testplan=read(FORMAL/'plan.json');lookup={r['source_path']:r for r in testplan['selected'] if r['role']=='testing'}
 for dataset in ('lfw','wider_train'):
  meta,rows=profiles.load(ids[dataset+'/testing']);model.validate_test(rows);subset=generate_tasks(COUNT,70,SEED,DEADLINE,rows);avg=mean(t.workload_ms for t in subset);reference_mean_ms=avg/3
  sets[dataset]=dict(profile_id=meta['id'],profile_csv_sha256=meta['csv_sha256'],full_test_count=len(rows),subset_count=COUNT,seed=SEED,selection='random.Random(11).sample(frozen_profile,10), no replacement; same order in every scenario',images=[dict(task_id=t.task_id,source_path=t.source_path,sample_id=t.sample_id,image_sha256=lookup[t.source_path]['image_sha256'],actual_workload_ms_posthoc=t.workload_ms,face_count_posthoc=t.face_count) for t in subset],mean_actual_workload_ms=avg,reference_edge_mean_compute_ms=reference_mean_ms)
  for level,rho in RHOS.items():
   interval=reference_mean_ms/rho
   for env in ENV_KEYS:
    cfg=ENVIRONMENTS[env];scenes.append(dict(id=f'{dataset}-{level}-{env}-n10-s11',dataset=dataset,load=level,network=env,interval_ms=interval,arrival_rate_per_second=1000/interval,reference_node='Reference Edge CPU: speed=3, FCFS capacity=1',reference_mean_service_ms=reference_mean_ms,reference_service_rate_per_second=1000/reference_mean_ms,reference_offered_cpu_load=rho,classification='Low rho=0.3; Medium rho=0.9; High rho=1.5 relative to fixed reference Edge CPU, not whole-system utilization',design_basis='Aggregate measured service of the predetermined common subset, fixed before any policy output; used only for arrival schedule, never fitted into predictor or supplied per-image to policy',per_node_compute_demand={n:dict(mean_service_ms=avg/v['speed'],all_to_this_node_cpu_rho=avg/v['speed']/interval) for n,v in cfg['nodes'].items()},count=COUNT,seed=SEED,deadline_ms=DEADLINE,estimator_id=fit['models']['median'],include_decision_overhead=True,deadline_policy='complete_all',information_mode='realistic',**cfg))
 plan=dict(schema='ai-comparison-pilot-v1',scenarios=scenes,strategy_order=ORDER,available=AVAILABLE,blocked=['dqn','ddqn'],stage='COMMON_10_IMAGE_LIVE_INTEGRATION_PILOT',planned_laya_model_calls=480,planned_warmup_calls=2,max_automatic_model_calls=482,estimated_cpu_seconds_from_previous_means=24*10*(1.096+1.729),expansion_gate='DQN feature contract BLOCKED and Laya reliability FAIL: no 30-image expansion in this run',model_initialization='First warmup call excluded from every task; initial health and aggregate cold-load-plus-warmup time recorded; pure load time NOT SEPARATELY MEASURED if Router lazy-loads',scope='InsightFace workloads measured earlier; only SimPy execution simulated; live policy cost measured on this host; no replay used')
 for filename,payload in [('scenario_manifest.json',plan),('task_subset_manifest.json',sets)]:
  p=O/filename
  if p.exists():assert read(p)==payload,'Frozen plan changed'
  else:save(p,payload)
 return plan,sets,model

class Observed:
 def __init__(self,inner,scene,name):self.inner=inner;self.scene=scene;self.name=name;self.records=[];self.sim=None
 def __getattr__(self,n):return getattr(self.inner,n)
 def select_node(self,t,state):
  started=time.perf_counter();record=dict(task=t,state=state,task_id=t.task_id,started_at_sim_ms=self.sim.env.now,success=False)
  try:
   selected=self.inner.select_node(t,state);record.update(success=True,selected_node=selected);return selected
  except Exception as e:record.update(error=type(e).__name__+': '+str(e));raise
  finally:
   record.update(client_inference_ms=(time.perf_counter()-started)*1000,audit_id=getattr(self.inner,'last_audit_id',None) if record['success'] else None,model=getattr(self.inner,'last_model',None));self.records.append(record);self.sim.env.process(self.flush(record))
 def serialize(self,r):return dict(r,task=asdict(r['task']),state=asdict(r['state']))
 def write(self,r):
  p=O/'raw/decisions'/self.scene['id']/self.name/(str(r['task_id'])+'.json')
  if p.exists():assert read(p)==self.serialize(r),'No overwrite of prior decision'
  else:save(p,self.serialize(r))
 def flush(self,r):
  yield self.sim.env.timeout(0)
  self.write(r)

def warmup(model):
 path=O/'warmup.json'
 if path.exists():return read(path)
 try:
  with urlopen('http://laya:8001/health',timeout=10) as f:before=json.load(f)
 except Exception as e:before=dict(error=repr(e))
 state=Simulator([],FixedStrategy('local')).get_state();t=DecisionTask(0,.1,250,250,0,1000,model.value_ms,16);warm=[]
 for name,cls in [('laya',LayaStrategy),('laya_v2',LayaV2Strategy)]:
  p=cls();start=time.perf_counter()
  try:node=p.select_node(t,state);warm.append(dict(strategy=name,status='PASS',audit_id=p.last_audit_id,node=node,model=p.last_model,elapsed_ms=(time.perf_counter()-start)*1000,excluded_from_all_task_metrics=True))
  except Exception as e:warm.append(dict(strategy=name,status='FAILED',error=repr(e),elapsed_ms=(time.perf_counter()-start)*1000,excluded_from_all_task_metrics=True))
 result=dict(health_before=before,calls=warm,policy='One identical neutral warmup per variant; cached weights permitted, no result cache',pure_model_load_ms=None,load_limit='Cold-load+warmup aggregate observed only if health_before.model_loaded=false; no pure load separation claimed')
 save(path,result);return result

def run():
 assert read(O/'feature_contract_check.json')['status']=='DQN/DDQN FORMAL INTEGRATION: BLOCKED'
 plan,sets,model=make_plan()
 config=dict(script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),scenario_sha256=hashlib.sha256((O/'scenario_manifest.json').read_bytes()).hexdigest(),implementation={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path('/app/app/offloading')/(n+'.py') for n in ('simulator','models','strategies','latency_v2','estimators','laya_client'))})
 if (O/'run-config.json').exists():assert read(O/'run-config.json')==config,'Frozen runtime changed'
 else:save(O/'run-config.json',config)
 warm=warmup(model);unavailable={r['strategy']:r.get('error') for r in warm['calls'] if r['status']!='PASS'}
 for scene in plan['scenarios']:
  _,profile=profiles.load(sets[scene['dataset']]['profile_id']);tasks=[replace(t,estimated_workload_ms=model.predict(t)) for t in generate_tasks(COUNT,scene['interval_ms'],SEED,DEADLINE,profile)]
  manifest=[asdict(t) for t in tasks];sha=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest();names=list(AVAILABLE);random.Random(scene['id']).shuffle(names)
  for name in names:
   out=O/'raw/runs'/scene['id']/(name+'.json')
   if out.exists():continue
   old=O/'raw/decisions'/scene['id']/name
   if name in ('laya','laya_v2') and (name in unavailable or (old.exists() and list(old.glob('*.json')))):
    save(out,dict(status='SERVICE_UNAVAILABLE' if name in unavailable else 'INTERRUPTED_NO_LIVE_REPLAY',reason=unavailable.get(name,'Partial decisions retained; no repeated calls or replay masquerading as live'),scene=scene,strategy=name,workload=manifest,workload_sha256=sha));continue
   policy=LayaStrategy() if name=='laya' else LayaV2Strategy() if name=='laya_v2' else STRATEGY_FACTORIES[name]();obs=Observed(policy,scene,name);sim=Simulator(tasks,EstimatedPolicy(obs,model),nodes={k:NodeConfig(**v) for k,v in scene['nodes'].items()},include_decision_overhead=True,network_mode=scene['network_mode'],shared_bandwidth_mbps=scene['shared_bandwidth_mbps']);obs.sim=sim
   try:
    rows=sim.run();assert len(rows)==COUNT and [r['task'] for r in rows]==manifest
    for r in rows:
     assert r['completed'] and not r['dropped'];assert abs(r['total_latency_ms']-sum(r[k] for k in ('decision_queue_ms','decision_ms','network_ms','queue_ms','compute_ms')))<1e-6;assert abs(r['total_latency_ms']-r['completed_at_ms']+r['arrival_ms'])<1e-6
     assert not {'workload_ms','face_count','source_path'} & r['decision_input'].keys();assert r['decision_ms']>0;assert abs(r['compute_ms']-r['task']['workload_ms']/scene['nodes'][r['selected_node']]['speed'])<1e-6
    for node in sim.nodes:
     intervals=sorted((r['cpu_started_at_ms'],r['cpu_completed_at_ms']) for r in rows if r['selected_node']==node);assert all(a[1]<=b[0]+1e-7 for a,b in zip(intervals,intervals[1:]))
    result=dict(status='PASS',scope='LIVE_DECISION_COST_SIMULATED_EXECUTION_NO_REPLAY',scene=scene,strategy=name,workload_sha256=sha,workload=manifest,result=dict(summary=metrics(rows),tasks=rows,events=sim.events,node_statistics=sim.node_statistics(),queue_samples=sim.queue_samples))
   except Exception as e:
    for r in obs.records:obs.write(r)
    result=dict(status='FAILED',scene=scene,strategy=name,workload_sha256=sha,workload=manifest,error=repr(e),traceback=traceback.format_exc(),partial_tasks=sim.results,events=sim.events)
    if name in ('laya','laya_v2'):unavailable[name]=repr(e)
   save(out,result);print('RUN',scene['id'],name,result['status'],flush=True)
  print('SCENE COMPLETE',scene['id'],flush=True)
 save(O/'run-complete.json',dict(scenes=24,available_runs=192,expected_live_laya_decisions=480,warmup_calls=2,blocked_models=['dqn','ddqn'],scope='10-image pilot only; no larger expansion'))
if __name__=='__main__':
 if '--plan' in sys.argv:print(json.dumps(make_plan()[0],ensure_ascii=False))
 else:run()
