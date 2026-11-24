"""B-v1 frozen exogenous design. Generates manifests; never trains any model."""
from collections import Counter
from dataclasses import asdict
from itertools import product
from statistics import mean
import csv,json,random
import numpy as np
from common import ROOT,canonical,digest,file_sha,write,table
from app.offloading.models import Task,NodeConfig
from app.offloading.estimators import WorkloadEstimator

DATASETS=('lfw','wider_train');LOADS=('Low','Medium','High');PATTERNS=('steady','burst')
RHO=dict(zip(LOADS,(.3,.9,1.5)));SEEDS=(42,43,44);VAL_SEEDS=(701,709)
def nodes(e,c):return dict(local=dict(speed=1,rtt_ms=0,bandwidth_mbps=1000),edge=dict(zip(('speed','rtt_ms','bandwidth_mbps'),e)),cloud=dict(zip(('speed','rtt_ms','bandwidth_mbps'),c)))
B={
 'reference':nodes((3,20,120),(8,100,55)),
 'ec_boundary':nodes((3,20,120),(8,112,55)),
 'network_4':nodes((3,20,4),(8,100,4)),
 'local_entry':nodes((3,300,120),(8,400,55)),
}
A={'reference':B['reference'],'local_advantage':nodes((3,1000,1),(8,2000,.5)),
   'edge_advantage':nodes((6,4,1000),(8,2000,1)),'cloud_advantage':nodes((2,30,80),(20,2,1000))}
# Prespecified interpolation combinations. Validation-only; never selected from Test.
UNSEEN={'unseen_ec_116':nodes((3,20,120),(8,116,55)),
        'unseen_network_6':nodes((3,20,6),(8,100,6)),
        'unseen_local_310_390':nodes((3,310,120),(8,390,55))}
def rng(seed,round,stream):return np.random.default_rng(np.random.SeedSequence([20261124,seed,round,stream]))
def cell(ds,load,network,pattern):return f'{ds}/{load}/{network}/{pattern}'
def config(case):return dict(nodes={k:NodeConfig(**v) for k,v in case['nodes'].items()},network_mode='independent',information_mode='realistic',deadline_policy='complete_all')

def load_data():
    ids=json.loads((ROOT/'data/profile-ids.json').read_text());pools={};metadata={}
    for key,id in ids.items():
        path=ROOT/'data'/f'{id}.csv';meta=json.loads(path.with_suffix('.json').read_text())
        assert file_sha(path)==meta['csv_sha256']
        rows=[]
        for row in csv.DictReader(path.open(encoding='utf-8-sig')):
            assert row['success']=='True' and row['device']=='CPUExecutionProvider' and int(row['repeats'])>=3
            rows.append(dict(source_path=row['source_path'],sample_id=row['sample_id'],dataset=row['dataset'],
                image_size_mb=float(row['image_size_mb']),width=int(row['width']),height=int(row['height']),
                face_count=int(row['face_count']),workload_ms=float(row['inference_ms'])))
        pools[key]=rows;metadata[key]=dict(profile_id=id,csv_sha256=file_sha(path),unique_images=len(rows))
    plan=json.loads((ROOT/'data/original-split-plan.json').read_text())['selected']
    selected=[r for r in plan if r['role'] in ('training','validation')]
    for field in ('source_path','group','image_sha256'):
        left={r[field] for r in selected if r['role']=='training'};right={r[field] for r in selected if r['role']=='validation'}
        assert not left&right
    estimator=WorkloadEstimator.from_dict(json.loads((ROOT/'data/estimator.json').read_text()))
    assert estimator.kind=='median' and abs(estimator.value_ms-470.3018125055678)<1e-10
    return pools,metadata,estimator

def make_tasks(pool,interval,seed_components,estimator,pattern):
    r=np.random.default_rng(np.random.SeedSequence(seed_components))
    weights=np.array([.15 if i%20<10 else 1.85 for i in range(99)]) if pattern=='burst' else np.ones(99)
    gaps=weights*(99*interval/weights.sum());arrivals=np.r_[0.,np.cumsum(gaps)]
    result=[]
    for i,at in enumerate(arrivals):
        row=pool[int(r.integers(len(pool)))];t=Task(task_id=i,arrival_ms=float(at),deadline_ms=1000,**row)
        from dataclasses import replace
        result.append(replace(t,estimated_workload_ms=estimator.predict(t)))
    return result

def balanced_order(seed,round):
    groups=[];r=rng(seed,round,1)
    for k in range(4):
        group=[(d,l,(2*d+b+l+k)%4,b) for d,l,b in product(range(2),range(3),range(2))]
        r.shuffle(group);groups.append(group)
    r.shuffle(groups)
    return [entry for g in groups for entry in g]

def build(out):
    pools,meta,estimator=load_data();est_sha=file_sha(ROOT/'data/estimator.json')
    union={**A,**B,**UNSEEN};validation=[]
    for ds,load,network,pattern,seed in product(DATASETS,LOADS,union,PATTERNS,VAL_SEEDS):
        d=DATASETS.index(ds);l=LOADS.index(load);p=PATTERNS.index(pattern)
        interval=mean(x['workload_ms'] for x in pools[ds+'/training'])/(3*RHO[load])
        work=make_tasks(pools[ds+'/validation'],interval,[20261124,seed,d,l,80],estimator,pattern)
        layer=('extreme_sanity' if network in ('local_advantage','edge_advantage','cloud_advantage') else 'common_reference' if network=='reference' else 'unseen_parameters' if network in UNSEEN else 'B_boundary_or_congestion')
        row=dict(cell=cell(ds,load,network,pattern),dataset=ds,load=load,network=network,pattern=pattern,seed=seed,
                 layer=layer,nodes=union[network],nominal_interval_ms=interval,estimator_sha256=est_sha,
                 arrival_span_ms=work[-1].arrival_ms,tasks=task_rows(work))
        row['exogenous_sha256']=digest(row);validation.append(row)
    training=[];coverage=[]
    for seed,round in product(SEEDS,range(2)):
        order=balanced_order(seed,round)
        for pos,(d,l,n,p) in enumerate(order):
            ds,load,network,pattern=DATASETS[d],LOADS[l],tuple(B)[n],PATTERNS[p]
            interval=mean(x['workload_ms'] for x in pools[ds+'/training'])/(3*RHO[load])
            work=make_tasks(pools[ds+'/training'],interval,[20261124,seed,round,d,l,20],estimator,pattern)
            row=dict(cell=cell(ds,load,network,pattern),dataset=ds,load=load,network=network,pattern=pattern,
                seed=seed,round=round,position=pos,quarter=pos//12,epsilon=.8 if round==0 else .1,
                nodes=B[network],nominal_interval_ms=interval,arrival_span_ms=work[-1].arrival_ms,
                estimator_sha256=est_sha,tasks=task_rows(work))
            row['exogenous_sha256']=digest({k:v for k,v in row.items() if k!='epsilon'})
            training.append(row)
            coverage.append({k:row[k] for k in ('seed','round','position','quarter','cell','dataset','load','network','pattern','epsilon','arrival_span_ms','exogenous_sha256')})
    manifest=dict(schema='rl-b-matrix-v1',phase='DESIGN_ONLY_NOT_EXECUTED',training_seeds=SEEDS,validation_seeds=VAL_SEEDS,
        profile_sources=meta,estimator_sha256=est_sha,estimator_value_ms=estimator.value_ms,
        training=training,validation=validation,A_reference=A,B=B,unseen_validation=UNSEEN,
        historical_test_loaded=False,independent_training_images=sum(len(pools[ds+'/training']) for ds in DATASETS))
    write(out/'training-manifest.json',{k:v for k,v in manifest.items() if k!='validation'})
    write(out/'validation-manifest.json',dict(schema='rl-b-validation-v1',cases=validation,profiles=meta,estimator_sha256=est_sha,test_used=False))
    table(out/'schedule-coverage.csv',coverage)
    report=dict(cells_per_seed_round=48,planned_training_episodes=len(training),planned_dispatches=len(training)*100,
        planned_dispatches_per_seed=9600,unique_training_images=80,validation_environments=len(union),
        validation_cells=2*3*len(union)*2,validation_cases=len(validation),validation_task_records=len(validation)*100,
        unseen_parameters=UNSEEN,training_manifest_sha256=file_sha(out/'training-manifest.json'),
        validation_manifest_sha256=file_sha(out/'validation-manifest.json'),all_training_execution_authorized=False)
    write(out/'design-summary.json',report)
    return manifest

def task_rows(work):return [asdict(t) for t in work]
def smoke_cells():
    return [('lfw','Medium','ec_boundary','steady'),('wider_train','High','network_4','burst'),
            ('lfw','High','local_entry','burst'),('wider_train','Medium','ec_boundary','steady'),
            ('lfw','High','network_4','steady'),('wider_train','High','local_entry','burst')]
def smoke_subset(manifest):
    result=[]
    for keys in smoke_cells():
        result.append(next(c for c in manifest['training'] if c['seed']==42 and c['round']==0 and c['cell']==cell(*keys)))
    return result
def validation_subset(manifest):
    cells=[cell(*x) for x in smoke_cells()]+[cell(ds,'Medium','reference','steady') for ds in DATASETS]
    return [next(c for c in manifest['validation'] if c['seed']==701 and c['cell']==key) for key in cells]
