"""Observable cost diagnostics and real-event fixtures; no simulator modification."""
from dataclasses import asdict,replace
import numpy as np
from app.offloading.models import Task,DecisionTask
from app.offloading.simulator import Simulator
from app.offloading.latency_v2 import estimate_v2,LatencyAwareV2Strategy
from app.offloading.strategies import LatencyAwareStrategy
from app.offloading.integration_contract import feature_vector
from app.offloading.agents49.integral_env import IntegralEnv
from common import write
from design import B,config

NAMES=('local','edge','cloud')
def costs(task,state):return [estimate_v2(task,n)['total_ms'] for n in state.nodes()]
def reduced_cost(task,n,remove_cpu=False,remove_network=False):
    # Mathematical component ablation ONLY. This is not a fabricated DTO fed to
    # an agent, nor a claim that this counterfactual is a reachable system state.
    cpu=0. if remove_cpu else n.queue_work_ms/n.compute_speed
    committed=n.committed_work_ms/n.compute_speed
    compute=task.estimated_workload_ms/n.compute_speed
    if n.name=='local':return cpu+committed+compute
    up=task.image_size_mb*8000/n.bandwidth_mbps;down=task.result_size_kb*8/n.bandwidth_mbps
    upload_backlog=0. if remove_network else n.upload_backlog_ms
    download_backlog=0. if remove_network else n.download_backlog_ms
    ready=max(n.rtt_ms/2,upload_backlog)+up
    return max(max(ready,cpu+committed)+compute+n.rtt_ms/2,download_backlog)+down
def adaptation(task,state):
    c=costs(task,state);a=int(np.argmin(c))
    no_cpu=[reduced_cost(task,n,remove_cpu=True) for n in state.nodes()]
    no_link=[reduced_cost(task,n,remove_network=True) for n in state.nodes()]
    ordered=sorted(c)
    return dict(estimated_costs_ms=dict(zip(NAMES,c)),estimated_best=NAMES[a],
        best_second_gap_ms=ordered[1]-ordered[0],
        cpu_component_reversal=a!=int(np.argmin(no_cpu)),network_component_reversal=a!=int(np.argmin(no_link)),
        counterfactual_scope='cost-component ablation only; never used as agent input')

def conservation(rows):
    max_error=0.
    for row in rows:
        stages=sum(row[k] for k in ('decision_queue_ms','decision_ms','network_ms','queue_ms','compute_ms'))
        err=max(abs(stages-row['total_latency_ms']),abs(row['completed_at_ms']-row['arrival_ms']-row['total_latency_ms']))
        max_error=max(max_error,err)
        assert err<1e-6
        assert all(row[k]>=-1e-9 for k in ('decision_queue_ms','decision_ms','network_ms','queue_ms','compute_ms'))
    assert len({r['task_id'] for r in rows})==len(rows)
    for name in NAMES:
        times=[]
        for r in rows:
            if r['selected_node']==name:
                assert r['cpu_started_at_ms']<=r['cpu_completed_at_ms']<=r['completed_at_ms']+1e-9
                times.extend([(r['cpu_started_at_ms'],1),(r['cpu_completed_at_ms'],-1)])
        busy=0
        for _,delta in sorted(times):
            busy+=delta;assert 0<=busy<=1
        assert busy==0
    return max_error

class CapacityAudit:
    def __init__(self,sim):self.sim=sim;self.steps=0;self.maxima={}
    def record(self):
        self.steps+=1
        for name,node in self.sim.nodes.items():
            for label,res in [('cpu',node.cpu),('upload',node.upload.resource),('download',node.download.resource)]:
                assert res.count<=res.capacity==1
                key=name+'.'+label;self.maxima[key]=max(self.maxima.get(key,0),res.count)
class AuditedIntegralEnv(IntegralEnv):
    def _advance(self):
        if not hasattr(self,'capacity_audit') or self.capacity_audit.sim is not self.sim:self.capacity_audit=CapacityAudit(self.sim)
        env=self.sim.env;original=env.step
        def step():
            value=original();self.capacity_audit.record();return value
        env.step=step
        try:return super()._advance()
        finally:env.step=original

W=470.3018125055678
def task(i,at=0,size=.1,actual=W):return Task(i,size,1,actual,at,1000,width=1024,height=768,estimated_workload_ms=W,source_path='controlled/probe.jpg')

def fixture(network,prefix,probe_at,actual_override=None):
    probe=task(99,probe_at)
    work=[task(i,at,size,actual if actual_override is None else actual_override) for i,at,size,actual,node in prefix]+[probe]
    forced={i:node for i,at,size,actual,node in prefix};observed={}
    class Policy:
        def select_node(self,t,s):
            if t.task_id!=99:return forced[t.task_id]
            observed.update(task=asdict(t),state=asdict(s),features=feature_vector(t,s),diagnostic=adaptation(t,s),
                            V1=LatencyAwareStrategy().select_node(t,s),V2=LatencyAwareV2Strategy().select_node(t,s))
            return observed['V2']
    sim=Simulator(work,Policy(),include_decision_overhead=False,**config(dict(nodes=B[network])))
    audit=CapacityAudit(sim);sim.start()
    while sim.env.peek()!=float('inf'):sim.env.step();audit.record()
    rows=sorted(sim.results,key=lambda r:r['task_id']);error=conservation(rows)
    return dict(observation=observed,tasks=rows,events=sim.events,capacity_maxima=audit.maxima,time_error_ms=error)

def event_evidence(out):
    cases={}
    cases['cpu_idle']=fixture('ec_boundary',[],200)
    cases['cpu_busy']=fixture('ec_boundary',[(i,float(i),.1,W,'edge') for i in range(3)],200)
    assert cases['cpu_idle']['observation']['V2']=='edge'
    assert cases['cpu_busy']['observation']['V2']=='cloud'
    edge=cases['cpu_busy']['observation']['state']['edge']
    assert edge['queue_work_ms']>0 and edge['upload_backlog_ms']==0 and edge['committed_work_ms']==0
    cases['link_idle']=fixture('network_4',[],100)
    cases['link_busy']=fixture('network_4',[(0,0.,1.,W,'cloud')],100)
    assert cases['link_idle']['observation']['V2']=='cloud'
    assert cases['link_busy']['observation']['V2']=='edge'
    cloud=cases['link_busy']['observation']['state']['cloud']
    assert cloud['queue_work_ms']==0 and cloud['cpu_running']==0 and cloud['upload_backlog_ms']>0
    assert cases['link_busy']['observation']['diagnostic']['network_component_reversal']
    cases['remote_idle']=fixture('local_entry',[],500)
    prefix=[(i,float(i),.1,W,'edge' if i<6 else 'cloud') for i in range(18)]
    cases['remote_busy']=fixture('local_entry',prefix,500)
    assert cases['remote_idle']['observation']['V2']=='edge'
    assert cases['remote_busy']['observation']['V2']=='local'
    assert all(cases['remote_busy']['observation']['state'][n]['queue_work_ms']>0 for n in ('edge','cloud'))
    cases['hidden_actual_short']=fixture('ec_boundary',[(0,0.,.1,W,'edge')],100)
    cases['hidden_actual_long']=fixture('ec_boundary',[(0,0.,.1,W,'edge')],100,actual_override=1470.)
    assert cases['hidden_actual_short']['observation']==cases['hidden_actual_long']['observation']
    for a,b in [('cpu_idle','cpu_busy'),('link_idle','link_busy'),('remote_idle','remote_busy')]:
        assert cases[a]['observation']['task']==cases[b]['observation']['task']
    write(out/'event-reversals.json',cases)
    return cases
