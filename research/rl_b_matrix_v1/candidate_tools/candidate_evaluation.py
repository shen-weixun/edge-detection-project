"""Frozen Validation and post-hoc observable-cost diagnostics, no training."""
from dataclasses import fields
from statistics import mean
import numpy as np
from common import digest
from design import DATASETS,LOADS,B,config,load_data
from evidence import conservation,adaptation
from app.offloading.models import Task,DecisionTask,NodeState,SystemState
from app.offloading.agents49.adapter import Agent49Policy
from app.offloading.agents49.evaluation import evaluation_snapshot
from app.offloading.estimators import EstimatedPolicy
from app.offloading.integration_contract import run_policy
from app.offloading.strategies import STRATEGY_FACTORIES

def intermediate_cases(cases):
    selected=[]
    for d,ds in enumerate(DATASETS):
        for l,load in enumerate(LOADS):
            for n,network in enumerate(B):
                pattern=('steady','burst')[(d+l+n)%2]
                selected.append(next(c for c in cases if c['dataset']==ds and c['load']==load and c['network']==network and c['pattern']==pattern and c['seed']==701))
    assert len(selected)==24
    return selected

def observed_dto(trace):
    raw=trace['raw_features'];task_fields=[f.name for f in fields(DecisionTask) if f.name!='task_id']
    task=DecisionTask(task_id=trace['task_id'],**dict(zip(task_fields,raw[:7])))
    node_fields=[f.name for f in fields(NodeState) if f.name!='name']
    nodes=[NodeState(name=name,**dict(zip(node_fields,raw[7+i*14:21+i*14]))) for i,name in enumerate(('local','edge','cloud'))]
    return task,SystemState(*nodes)

def evaluate_case(case,estimator,overhead,agent=None,baseline=None,checkpoint=None):
    policy=Agent49Policy(agent) if agent is not None else STRATEGY_FACTORIES[baseline]()
    result=run_policy([Task(**r) for r in case['tasks']],EstimatedPolicy(policy,estimator),
                      include_decision_overhead=overhead,**config(case))
    error=conservation(result['tasks']);q=policy.decisions if agent is not None else []
    diag=[dict(task_id=t['task_id'],action=t['action'],q_values=t['q_values'],**adaptation(*observed_dto(t))) for t in q]
    cost=sum(r['total_latency_ms']/1000+int(not r['deadline_met']) for r in result['tasks'])
    sigfields=('task_id','selected_node','total_latency_ms','deadline_met','network_ms','queue_ms','compute_ms','decision_ms','decision_queue_ms')
    summary=result['summary'];components=summary['components_ms']
    row=dict(policy=baseline or agent.algorithm,train_seed=None if agent is None else checkpoint['seed'],
        checkpoint=None if agent is None else checkpoint['step'],cell=case['cell'],dataset=case['dataset'],load=case['load'],
        network=case['network'],pattern=case['pattern'],layer=case['layer'],validation_seed=case['seed'],
        overhead=overhead,task_count=len(result['tasks']),exogenous_sha256=case['exogenous_sha256'],
        mean_ms=summary['avg_latency_ms'],p95_ms=summary['p95_latency_ms'],deadline_rate=summary['deadline_met_rate'],completion_rate=summary['completion_rate'],
        episode_reward=-cost,mean_task_reward=-cost/len(result['tasks']),decision_wall_ms=summary['avg_decision_wall_ms'],
        decision_ms=components['decision_ms'],decision_queue_ms=components['decision_queue_ms'],network_ms=components['network_ms'],
        cpu_queue_ms=components['queue_ms'],compute_ms=components['compute_ms'],
        local_ratio=summary['placement_ratio']['local'],edge_ratio=summary['placement_ratio']['edge'],cloud_ratio=summary['placement_ratio']['cloud'],
        cpu_reversals=None if not diag else sum(x['cpu_component_reversal'] for x in diag),
        network_reversals=None if not diag else sum(x['network_component_reversal'] for x in diag),
        median_cost_gap_ms=None if not diag else float(np.median([x['best_second_gap_ms'] for x in diag])),
        max_time_error_ms=error)
    signature=digest(dict(tasks=[{k:r[k] for k in sigfields} for r in result['tasks']],decisions=q))
    return dict(summary=row,tasks=result['tasks'],events=result['events'],node_statistics=result['node_statistics'],
                decisions=q,adaptation=diag,signature=signature)
