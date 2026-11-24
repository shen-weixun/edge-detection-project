"""Diagnose first policy divergence on shared causal state; no result correction."""
from pathlib import Path
from dataclasses import asdict
from statistics import mean
import sys,json,csv,gzip
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from app.offloading import profiles
from app.offloading.models import Task,NodeConfig
from app.offloading.simulator import Simulator
from app.offloading.strategies import LatencyAwareStrategy,estimate_latency
from app.offloading.latency_v2 import LatencyAwareV2Strategy,estimate_v2
from acceptance_reference import check_run
O=profiles.root()/'formal-evaluation';E=O/'evaluation'
rs=list(csv.DictReader((O/'paired_differences.csv').open(encoding='utf-8-sig')));worst=max((r for r in rs if r['comparison']=='policy_effect'),key=lambda r:float(r['delta_ms']));out=[]
for seed in (11,23,37):
 sid=f"{worst['dataset']}-{worst['environment']}-i{worst['interval_ms']}-d{worst['deadline_ms']}-s{seed}"
 with gzip.open(E/'raw'/(sid+'.json.gz'),'rt',encoding='utf-8') as f:raw=json.load(f)
 original=raw['results']['median'];s=raw['scenario'];tasks=[Task(**r) for r in original['workload']];runs={}
 for name,base in [('v1',LatencyAwareStrategy()),('v2',LatencyAwareV2Strategy())]:
  snapshots={}
  class Capture:
   def select_node(self,t,state):
    snapshots[t.task_id]=dict(task=asdict(t),state=asdict(state),v1_costs_ms={n.name:estimate_latency(t,n) for n in state.nodes()},v2_costs_ms={n.name:estimate_v2(t,n)['total_ms'] for n in state.nodes()});return base.select_node(t,state)
  sim=Simulator(tasks,Capture(),nodes={k:NodeConfig(**v) for k,v in s['nodes'].items()},include_decision_overhead=False,network_mode=s['network_mode'],shared_bandwidth_mbps=s['shared_bandwidth_mbps']);rows=sim.run();validation=check_run(sim,rows)
  runs[name]=dict(rows=rows,snapshots=snapshots,max_reference_error_ms=validation['max_reference_error_ms'])
 a={r['task_id']:r for r in runs['v1']['rows']};b={r['task_id']:r for r in runs['v2']['rows']};tid=next((i for i in sorted(a) if a[i]['selected_node']!=b[i]['selected_node']),None)
 if tid is not None:assert runs['v1']['snapshots'][tid]['state']==runs['v2']['snapshots'][tid]['state']
 out.append(dict(scenario_id=sid,scope='ZERO_DECISION_COST_DIAGNOSTIC_RECONSTRUCTION_NOT_FORMAL_REPLACEMENT',first_divergence_task=tid,first_shared_observation=runs['v1']['snapshots'][tid] if tid is not None else None,v1_choice=a[tid]['selected_node'] if tid is not None else None,v2_choice=b[tid]['selected_node'] if tid is not None else None,actual_workload_posthoc_only=a[tid]['task']['workload_ms'] if tid is not None else None,mean_stage_differences={k:mean(r[k] for r in runs['v2']['rows'])-mean(r[k] for r in runs['v1']['rows']) for k in ('network_ms','queue_ms','compute_ms','total_latency_ms')},runs=runs))
(E/'regression-case-study.json').write_text(json.dumps(dict(formal_worst_condition=worst,diagnostic_runs=out),ensure_ascii=False,indent=2),encoding='utf-8');print('CASE DIAG COMPLETE',[(r['scenario_id'],r['first_divergence_task'],r['v1_choice'],r['v2_choice']) for r in out])
