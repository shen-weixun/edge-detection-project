"""Final SimPy acceptance: controlled arithmetic, measured load, sensitivity,
independent FCFS reference, held-out estimation errors. No Laya dependency.
"""
import sys,os,json,csv,hashlib,math
from pathlib import Path
from dataclasses import asdict,replace
from statistics import mean,median
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from acceptance_reference import scenarios,single_cost,check_run
from app.offloading.models import Task,DecisionTask
from app.offloading.simulator import Simulator,DEFAULT_NODES
from app.offloading.strategies import FixedStrategy,LatencyAwareStrategy,STRATEGY_FACTORIES,estimate_latency
from app.offloading.workload import generate_tasks,calibration_estimate,source_identity
from app.offloading.profiles import load
from app.offloading.experiment import metrics

out=Path(os.environ.get('ACCEPTANCE_OUTPUT','/tmp/final-acceptance'));out.mkdir(parents=True,exist_ok=True)
def save(name,data):
    (out/(name+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
def table(name,rows):
    with (out/(name+'.csv')).open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
checks=[];max_error=0.;terminal_count=0

def validate(sim,rows,label):
    global max_error,terminal_count
    reference=check_run(sim,rows);max_error=max(max_error,reference['max_reference_error_ms']);terminal_count+=len(rows)
    checks.append(dict(check=label,status='PASS',tasks=len(rows),maximum_reference_error_ms=reference['max_reference_error_ms']))
    return reference

# 1. Three controlled scenarios: same prior, actual internal work independent.
t,sets=scenarios();controlled=[];case_data={}
for case,nodes in sets.items():
    sim=Simulator([t],LatencyAwareStrategy(),nodes,False)
    state=sim.get_state();obs=DecisionTask.observe(t)
    estimates={n:single_cost(t,cfg,n,True)['total_latency_ms'] for n,cfg in nodes.items()}
    for n in state.nodes():assert abs(estimate_latency(obs,n)-estimates[n.name])<1e-9
    selected=min(estimates,key=estimates.get);rows=sim.run();assert rows[0]['selected_node']==selected
    validate(sim,rows,case+'/latency_aware')
    case_data[case]=dict(config={n:asdict(c) for n,c in nodes.items()},decision_input=asdict(obs),actual_workload_ms=t.workload_ms,selected=selected,estimated_latencies_ms=estimates,rows=rows)
    for node,cfg in nodes.items():
        fixed=Simulator([t],FixedStrategy(node),nodes,False);r=fixed.run()[0];validate(fixed,[r],case+'/'+node)
        manual=single_cost(t,cfg,node)
        assert abs(r['total_latency_ms']-manual['total_latency_ms'])<1e-9
        controlled.append(dict(scenario=case,node=node,selected=node==selected,estimated_latency_ms=estimates[node],manual_actual_latency_ms=manual['total_latency_ms'],simulated_latency_ms=r['total_latency_ms'],network_ms=r['network_ms'],cpu_queue_ms=r['queue_ms'],compute_ms=r['compute_ms'],status='PASS'))
save('controlled-scenarios',case_data);table('controlled-scenarios',controlled)

# 2. Single-task network/compute parameter sweeps.
sensitivity=[]
for node in ('edge','cloud'):
    for field,values in [('rtt_ms',[0,20,200,1000]),('bandwidth_mbps',[1,8,80,1000]),('speed',[1,3,8,20])]:
        observed=[]
        for value in values:
            nodes=dict(DEFAULT_NODES);nodes[node]=replace(nodes[node],**{field:value})
            fixed=Simulator([t],FixedStrategy(node),nodes,False);r=fixed.run()[0]
            validate(fixed,[r],'sensitivity/'+node+'/'+field+'/'+str(value))
            manual=single_cost(t,nodes[node],node)
            assert abs(manual['total_latency_ms']-r['total_latency_ms'])<1e-9
            adaptive=Simulator([t],LatencyAwareStrategy(),nodes,False)
            s=adaptive.get_state();est={n:single_cost(t,cfg,n,True)['total_latency_ms'] for n,cfg in nodes.items()}
            ar=adaptive.run();validate(adaptive,ar,'adaptive/'+node+'/'+field+'/'+str(value))
            assert ar[0]['selected_node']==min(est,key=est.get)
            observed.append(r['compute_ms'] if field=='speed' else r['network_ms'])
            sensitivity.append(dict(node=node,parameter=field,value=value,manual_total_ms=manual['total_latency_ms'],simulated_total_ms=r['total_latency_ms'],network_ms=r['network_ms'],compute_ms=r['compute_ms'],latency_aware_choice=ar[0]['selected_node'],status='PASS'))
        assert all((b>=a if field=='rtt_ms' else b<=a) for a,b in zip(observed,observed[1:]))
table('sensitivity',sensitivity)

# 3. Same measured LFW thirty images at low/near-Edge-capacity/severe overload.
profile_id=os.getenv('WORKLOAD_PROFILE_ID','6ddb0a187ba44065a5beaf0450ad259e')
calibration_id=os.getenv('CALIBRATION_PROFILE_ID','a057ded0f08c4837beff2ffd02f390ee')
meta,profile=load(profile_id);cal_meta,cal=load(calibration_id)
estimate=calibration_estimate(cal,profile)
arrivals={'low':max(x['workload_ms'] for x in profile)*1.25,
          'medium':mean(x['workload_ms'] for x in profile)/DEFAULT_NODES['edge'].speed,
          'high':mean(x['workload_ms'] for x in profile)/(DEFAULT_NODES['cloud'].speed*4)}
load_rows=[];experiments={};batch=None
for level,gap in arrivals.items():
    tasks=[replace(x,estimated_workload_ms=estimate) for x in generate_tasks(30,gap,42,1000,profile)]
    identity=[{k:v for k,v in asdict(x).items() if k not in ('arrival_ms','deadline_ms')} for x in tasks]
    digest=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    if batch is None:batch=digest
    assert digest==batch
    for name,factory in STRATEGY_FACTORIES.items():
        sim=Simulator(tasks,factory(),include_decision_overhead=False)
        rows=sim.run();ref=validate(sim,rows,'measured_load/'+level+'/'+name);summary=metrics(rows)
        again=Simulator(tasks,factory(),include_decision_overhead=False);replay=again.run()
        assert [{k:v for k,v in r.items() if k!='decision_wall_ms'} for r in rows]==[{k:v for k,v in r.items() if k!='decision_wall_ms'} for r in replay]
        placements={r['task_id']:r['selected_node'] for r in rows}
        upload_queue=mean(ref['reference'][r['task_id']]['upload_queue_ms'] for r in rows)
        download_queue=mean(ref['reference'][r['task_id']]['download_queue_ms'] for r in rows)
        load_rows.append(dict(load=level,interval_ms=gap,strategy=name,avg_latency_ms=summary['avg_latency_ms'],p95_ms=summary['p95_latency_ms'],cpu_queue_ms=mean(r['queue_ms'] for r in rows),upload_queue_ms=upload_queue,download_queue_ms=download_queue,deadline_met_rate=summary['deadline_met_rate'],**{n+'_mean_queue':sim.node_statistics()[n]['mean_queue_time_weighted'] for n in DEFAULT_NODES},**{n+'_utilization':sim.node_statistics()[n]['cpu_utilization'] for n in DEFAULT_NODES}))
        experiments[level+'/'+name]=dict(summary=summary,node_statistics=sim.node_statistics(),tasks=rows,events=sim.events,reference=ref)
        if name.endswith('_only') and level=='high':
            node=name.split('_')[0];values=[r['queue_ms'] for r in rows]
            assert all(b>=a-1e-7 for a,b in zip(values,values[1:])),(level,name,values)
            assert values[-1]>values[0]
for name in ('local_only','edge_only','cloud_only'):
    by={r['load']:r for r in load_rows if r['strategy']==name}
    assert by['low']['cpu_queue_ms']<1e-7
    assert by['low']['cpu_queue_ms']<=by['medium']['cpu_queue_ms']+1e-7<=by['high']['cpu_queue_ms']+2e-7
    assert by['low']['avg_latency_ms']<=by['medium']['avg_latency_ms']+1e-3<=by['high']['avg_latency_ms']+2e-3
table('measured-load',load_rows);save('measured-load-details',experiments)

# 4. Deliberately saturate the network; same input, isolated vs common uplink.
shared=[];shared_details={}
class Alternating:
    def select_node(self,task,state):return ('edge','cloud')[task.task_id%2]
from app.offloading.models import NodeConfig
configs={n:NodeConfig(2,0 if n=='local' else 20,80) for n in DEFAULT_NODES}
for mode in ('independent','shared'):
    ts=[replace(t,task_id=i,arrival_ms=0) for i in range(4)]
    sim=Simulator(ts,Alternating(),configs,False,network_mode=mode,shared_bandwidth_mbps=80)
    rows=sim.run();ref=validate(sim,rows,'network_contention/'+mode)
    shared_details[mode]=dict(rows=rows,reference=ref)
    for r in rows:
        rr=ref['reference'][r['task_id']]
        shared.append(dict(mode=mode,task_id=r['task_id'],node=r['selected_node'],upload_started_ms=rr['upload_started'],upload_completed_ms=rr['upload_completed'],upload_queue_ms=rr['upload_queue_ms'],cpu_started_ms=r['cpu_started_at_ms'],cpu_completed_ms=r['cpu_completed_at_ms'],download_queue_ms=rr['download_queue_ms'],total_latency_ms=r['total_latency_ms']))
table('network-contention',shared);save('network-contention-details',shared_details)

# 5. Strictly held-out forecast errors. WIDER_train is evaluation for the LFW prior,
# but is used as calibration only in the separately labelled WIDER-median comparison.
error_rows=[];predictions=[];split_evidence=[]
for ident in [profile_id,'dd2acc74347847fabc9199bbf204a5b5','adacfbcf078045d89dd8fc8718ed538f']:
    test_meta,test=load(ident)
    e=calibration_estimate(cal,test)
    altered=[dict(r,workload_ms=r['workload_ms']*100,face_count=999) for r in test]
    assert calibration_estimate(cal,altered)==e
    actual=[r['workload_ms'] for r in test];errors=[e-y for y in actual]
    error_rows.append(dict(estimator='production_LFW_historical_median',test_dataset=test_meta['dataset'],test_profile=ident,training_profile=calibration_id,n=len(test),estimate_ms=e,actual_mean_ms=mean(actual),mae_ms=mean(abs(v) for v in errors),rmse_ms=math.sqrt(mean(v*v for v in errors)),bias_ms=mean(errors)))
    for r in test:predictions.append(dict(dataset=test_meta['dataset'],source_path=r['source_path'],estimated_workload_ms=e,actual_workload_ms=r['workload_ms'],error_ms=e-r['workload_ms']))
    root=Path(os.getenv('DATASET_ROOT','/datasets'))
    def content_hashes(rows):return {hashlib.sha256((root/r['source_path']).read_bytes()).hexdigest() for r in rows}
    overlap=content_hashes(cal)&content_hashes(test)
    assert not overlap
    split_evidence.append(dict(test_profile=ident,training_profile=calibration_id,source_overlap=0,content_sha256_overlap=len(overlap),test_label_mutation_does_not_change_estimate=True))
wm,wt=load('dd2acc74347847fabc9199bbf204a5b5');vm,vt=load('adacfbcf078045d89dd8fc8718ed538f')
assert not content_hashes(wt).intersection(content_hashes(vt))
split_evidence.append(dict(test_profile=vm['id'],training_profile=wm['id'],source_overlap=0,content_sha256_overlap=0,test_label_mutation_does_not_change_estimate=calibration_estimate(wt,[dict(r,workload_ms=r['workload_ms']*100) for r in vt])==calibration_estimate(wt,vt)))
e=calibration_estimate(wt,vt);err=[e-r['workload_ms'] for r in vt]
error_rows.append(dict(estimator='diagnostic_WIDER_training_median',test_dataset='wider_val',test_profile=vm['id'],training_profile=wm['id'],n=len(vt),estimate_ms=e,actual_mean_ms=mean(r['workload_ms'] for r in vt),mae_ms=mean(abs(v) for v in err),rmse_ms=math.sqrt(mean(v*v for v in err)),bias_ms=mean(err)))
table('estimation-errors',error_rows);table('estimation-predictions',predictions);save('split-evidence',split_evidence)
save('measured-manifest',dict(test_profile=meta,calibration_profile=cal_meta,estimate_ms=estimate,intervals_ms=arrivals,image_batch_sha256=batch,decision_cost_scope='zero virtual decision cost; deterministic simulator acceptance, NOT end-to-end algorithm ranking'))
save('core-checks',checks)
save('core-summary',dict(status='PASS',run_checks=len(checks),terminal_results_checked=terminal_count,max_reference_error_ms=max_error,scenario_choices={k:v['selected'] for k,v in case_data.items()},load_intervals_ms=arrivals,information_mode='realistic',load_profile_id=profile_id,calibration_profile_id=calibration_id))
print(json.dumps(dict(status='PASS',checks=len(checks),results=terminal_count,max_reference_error_ms=max_error,scenarios={k:v['selected'] for k,v in case_data.items()})),flush=True)
