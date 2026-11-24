"""Independent frozen Validation-only entry point; never calls train_step."""
import argparse,json
from copy import deepcopy
from pathlib import Path
from statistics import mean
from common import ROOT,digest,rng_state,weight_sha,write
from design import config,load_data,validation_subset
from evidence import conservation
from app.offloading.models import Task
from app.offloading.agents49.evaluation import evaluation_snapshot
from app.offloading.agents49.adapter import Agent49Policy,load_agent
from app.offloading.estimators import EstimatedPolicy
from app.offloading.integration_contract import run_policy
from app.offloading.strategies import STRATEGY_FACTORIES

def signature(result,q):
    fields=('task_id','selected_node','total_latency_ms','completed_at_ms','deadline_met','network_ms','queue_ms','compute_ms','decision_ms','decision_queue_ms')
    return digest(dict(tasks=[{k:r[k] for k in fields} for r in result['tasks']],q=q))

def evaluate(agent,cases,overhead=False,baseline=None):
    _,_,estimator=load_data();before=(rng_state(agent),weight_sha(agent),agent.updates,len(agent.memory)) if agent is not None else None
    frozen=evaluation_snapshot(agent,991) if agent is not None else None
    results=[]
    for case in cases:
        policy=Agent49Policy(frozen) if frozen is not None else STRATEGY_FACTORIES[baseline]()
        result=run_policy([Task(**r) for r in case['tasks']],EstimatedPolicy(policy,estimator),
                          include_decision_overhead=overhead,**config(case))
        conservation(result['tasks'])
        q=policy.decisions if frozen is not None else []
        cost=sum(r['total_latency_ms']/1000+int(not r['deadline_met']) for r in result['tasks'])
        results.append(dict(cell=case['cell'],layer=case['layer'],exogenous_sha256=case['exogenous_sha256'],
             overhead_in_latency=overhead,episode_reward=-cost,summary=result['summary'],
             node_statistics=result['node_statistics'],tasks=result['tasks'],q_values=q,
             events=result['events'],signature=signature(result,q)))
    if agent is not None:assert before==(rng_state(agent),weight_sha(agent),agent.updates,len(agent.memory))
    return results

def read_manifest():
    t=json.loads((ROOT/'results/design/training-manifest.json').read_text())
    v=json.loads((ROOT/'results/design/validation-manifest.json').read_text())
    return dict(training=t['training'],validation=v['cases'])

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--model',required=True);p.add_argument('--out',required=True)
    args=p.parse_args();folder=Path(args.model);meta=json.loads((folder/'checkpoint-metadata.json').read_text())
    agent=load_agent(meta['algorithm'],folder/'smoke-only.npz',meta['sha256'],contract_index=folder/'input-contract-index.json')
    agent.gamma=meta['gamma']
    # Explicitly fixed small Validation subset; full 240-case manifest is NOT run.
    write(Path(args.out),evaluate(agent,validation_subset(read_manifest()),False))
