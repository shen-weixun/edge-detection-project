"""Preregistered formal design: independent of inference labels and outcomes."""
from dataclasses import replace
from pathlib import Path
import json,csv,itertools,hashlib
BASE={'local':dict(speed=1,rtt_ms=0,bandwidth_mbps=1000),'edge':dict(speed=3,rtt_ms=20,bandwidth_mbps=120),'cloud':dict(speed=8,rtt_ms=100,bandwidth_mbps=55)}
ENVIRONMENTS={
 'reference':dict(nodes=BASE,network_mode='independent',shared_bandwidth_mbps=120),
 'local_advantage':dict(nodes={**BASE,'edge':dict(speed=3,rtt_ms=1000,bandwidth_mbps=1),'cloud':dict(speed=8,rtt_ms=2000,bandwidth_mbps=.5)},network_mode='independent',shared_bandwidth_mbps=120),
 'edge_advantage':dict(nodes={**BASE,'edge':dict(speed=6,rtt_ms=4,bandwidth_mbps=1000),'cloud':dict(speed=8,rtt_ms=2000,bandwidth_mbps=1)},network_mode='independent',shared_bandwidth_mbps=120),
 'cloud_advantage':dict(nodes={**BASE,'edge':dict(speed=2,rtt_ms=30,bandwidth_mbps=80),'cloud':dict(speed=20,rtt_ms=2,bandwidth_mbps=1000)},network_mode='independent',shared_bandwidth_mbps=120),
 'edge_rtt_400':dict(nodes={**BASE,'edge':dict(BASE['edge'],rtt_ms=400)},network_mode='independent',shared_bandwidth_mbps=120),
 'cloud_bandwidth_4':dict(nodes={**BASE,'cloud':dict(BASE['cloud'],bandwidth_mbps=4)},network_mode='independent',shared_bandwidth_mbps=120),
 'remote_compute_2x':dict(nodes={**BASE,'edge':dict(BASE['edge'],speed=6),'cloud':dict(BASE['cloud'],speed=16)},network_mode='independent',shared_bandwidth_mbps=120),
 'shared_8':dict(nodes=BASE,network_mode='shared',shared_bandwidth_mbps=8)}
SEEDS=[11,23,37];GAPS=[70,300,1000];DEADLINES=[500,1000,2000]
POLICIES=['local_only','edge_only','cloud_only','load_threshold','latency_aware','latency_aware_v2']
def scenarios():
 return [dict(id=f'{d}-{env}-i{gap}-d{deadline}-s{seed}',dataset=d,environment=env,interval_ms=gap,deadline_ms=deadline,seed=seed,count=100,**config) for d,(env,config),gap,deadline,seed in itertools.product(('lfw','wider_train'),ENVIRONMENTS.items(),GAPS,DEADLINES,SEEDS)]
def write_design(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=True)
 config=dict(schema='formal-design-v1',scenarios=scenarios(),algorithms=['four_fixed_baselines_with_median','V1_Median','V2_Median','V1_Ridge','V2_Ridge'],include_decision_overhead=True,deadline_policy='complete_all',information_mode='realistic',estimator_candidates=dict(median=[1],ridge_raw=[.1,1,10],ridge_log=[.1,1,10]),selection='lowest pooled validation MAE; test never selection input',subgroups=dict(high_resolution_min_pixels=1000000,long_actual_min_ms=1000,multiple_faces_min=2),bootstrap_seed=424242,bootstrap_repeats=2000,laya_additional_model_calls=0,warning='Seeds permute the same 100 held-out images; seed variation is ordering variation, not independent image populations.')
 p=out/'preregistered-design.json';payload=json.dumps(config,sort_keys=True,ensure_ascii=False,indent=2)
 if p.exists():assert p.read_text(encoding='utf-8')==payload,'Frozen design differs'
 else:p.write_text(payload,encoding='utf-8')
 with (out/'scenario_matrix.csv').open('w',newline='',encoding='utf-8-sig') as f:
  rows=[dict(**{k:v for k,v in s.items() if k!='nodes'},nodes_json=json.dumps(s['nodes'],sort_keys=True)) for s in scenarios()];w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 return config
if __name__=='__main__':
 import argparse
 a=argparse.ArgumentParser();a.add_argument('--output',required=True);args=a.parse_args();print('DESIGN',len(write_design(args.output)['scenarios']),'frozen')
