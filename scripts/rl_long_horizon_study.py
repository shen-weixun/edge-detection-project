"""Predeclared small factorial study with RNG-isolated validation."""
import sys
sys.path.insert(0,"/app")
import argparse
from dataclasses import asdict
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
from statistics import mean
import zipfile
import numpy as np

from agents49_experiment import read,write,digest,config
from rl_method_study import tasks
from app.offloading.agents49.dqn import DQN
from app.offloading.agents49.ddqn import DDQN
from app.offloading.agents49.input_contract import InputSpec, export_agent_contract, write_contract_index
from app.offloading.agents49.adapter import Agent49Policy
from app.offloading.agents49.evaluation import evaluation_snapshot
from app.offloading.agents49.integral_env import IntegralEnv
from app.offloading.integration_contract import feature_vector,run_policy,validate_manifest_split
from app.offloading.profiles import load,root
from app.offloading.estimators import load_registered
from app.offloading.rl import OffloadingEnv
from app.offloading.strategies import STRATEGY_FACTORIES

SEEDS=(42,43,44)
VAL_SEEDS=(701,709)
BUDGET=800
ALGORITHMS={"dqn":DQN,"ddqn":DDQN}


class Policy:
    def __init__(self,agent):
        self.agent=agent
        self.policy=Agent49Policy(agent)
        self.q=[]
    def select_node(self,task,state):
        node=self.policy.select_node(task,state)
        trace=self.policy.decisions[-1]
        self.q.append(dict(task_id=task.task_id,q_values=trace['q_values'],action=trace['action']))
        return node


def rollout(agent,work,scene,reward_mode,dropped,start):
    if tuple(dropped) != agent.input_spec.zeroed_feature_indices:
        raise ValueError('Rollout mask differs from agent input contract')
    env=(IntegralEnv if reward_mode=="integral" else OffloadingEnv)(work,**config(scene))
    obs=env.reset()
    log=[]
    while obs is not None:
        f=feature_vector(*obs)
        action=agent.act(f,epsilon=max(.05,1-.95*(start+len(log))/(BUDGET-1)))
        nxt,reward,done,info=env.step(action)
        nf=f if done else feature_vector(*nxt)
        agent.remember(f,action,reward,nf,done)
        loss=agent.train_step()
        log.append(dict(task_id=obs[0].task_id,action=action,reward=reward,episode_done=done,
                        next_task_id=None if done else nxt[0].task_id,info=info,loss=loss))
        obs=nxt
    rows=env.sim.results
    expected=sum(r["total_latency_ms"]/1000+(not r["deadline_met"]) for r in rows)
    assert abs(sum(r["reward"] for r in log)+expected)<1e-6
    # Separate arithmetic sweep over observed arrivals and terminal timestamps.
    points=sorted([(r["arrival_ms"],1) for r in rows]+[(r["completed_at_ms"],-1) for r in rows])
    active=0
    area=0.
    prior=0.
    for at,delta in points:
        area+=active*(at-prior)
        prior=at
        active+=delta
    assert active==0 and abs(area-sum(r["total_latency_ms"] for r in rows))<1e-6
    if reward_mode=="integral":
        assert abs(area-env.sim.area_ms)<1e-6
    return dict(transitions=log,tasks=rows,independent_area_ms=area,
                cost_events=env.sim.cost_events if reward_mode=="integral" else [])


def main(out,archive):
    if out.exists():
        raise ValueError("Choose a new output")
    out.mkdir(parents=True)
    with zipfile.ZipFile(archive) as z:
        manifest=json.loads(z.read("SHA256SUMS.json"))
        for name,expected in manifest.items():
            assert sha256(z.read(name)).hexdigest()==expected
        write(out/"previous-archive.json",{"sha256":digest(archive),"verified_members":len(manifest)})
    plan=read(root()/"formal-evaluation/plan.json")["selected"]
    validate_manifest_split(plan)
    ids=read(root()/"formal-evaluation/profile-ids.json")
    pools={}
    specs={}
    for ds in ("lfw","wider_train"):
        for role in ("training","validation"):
            meta,rows=load(ids[ds+"/"+role])
            assert {r["source_path"] for r in rows}=={r["source_path"] for r in plan if r["dataset"]==ds and r["role"]==role}
            pools[ds,role]=rows
            specs[ds+"/"+role]=meta["csv_sha256"]
    all_scenes=read(root()/"ai-comparison/scenario_manifest.json")["scenarios"]
    cases={("Low","local_advantage"),("Medium","edge_advantage"),("High","cloud_advantage"),("High","reference")}
    scenes=[s for s in all_scenes if (s["load"],s["network"]) in cases]
    assert len(scenes)==8
    estimator=load_registered(scenes[0]["estimator_id"])
    dropped=read(root()/"rl-method-v1/feature-design.json")["dropped_indices"]
    schedules={}
    for seed in SEEDS:
        blocks=[]
        for block in range(BUDGET//100):
            scene=scenes[block%8]
            ds=scene["dataset"]
            interval=mean(r["workload_ms"] for r in pools[ds,"training"])/(3*scene["reference_offered_cpu_load"])
            work=tasks(pools[ds,"training"],100,interval,seed*10000+block,estimator,block%2==1)
            blocks.append(dict(scene=scene,burst=block%2==1,tasks=[asdict(t) for t in work]))
        schedules[f"{seed}/100"]=blocks
        split=[]
        for block,case in enumerate(blocks):
            for start in range(0,100,20):
                chunk=case["tasks"][start:start+20]
                offset=chunk[0]["arrival_ms"]
                rows=[dict(t,task_id=i,arrival_ms=t["arrival_ms"]-offset) for i,t in enumerate(chunk)]
                split.append(dict(scene=case["scene"],burst=case["burst"],tasks=rows,
                                  parent_block=block,offset_ms=offset,start_index=start))
        schedules[f"{seed}/20"]=split
    val=[]
    for scene,seed,burst in product(scenes,VAL_SEEDS,(False,True)):
        ds=scene["dataset"]
        interval=mean(r["workload_ms"] for r in pools[ds,"training"])/(3*scene["reference_offered_cpu_load"])
        val.append(dict(scene=scene,seed=seed,burst=burst,
                        tasks=[asdict(t) for t in tasks(pools[ds,"validation"],100,interval,seed,estimator,burst)]))
    from app.offloading.models import Task
    write(out/"design.json",dict(seeds=SEEDS,validation_seeds=VAL_SEEDS,budget=BUDGET,
         reward_modes=["completion","integral"],gamma=1,feature_modes=["full","pruned"],algorithms=list(ALGORITHMS),
         dropped=dropped,profiles=specs,training=schedules,validation=val,
         source_sha256={str(p):digest(p) for p in [Path(__file__),*Path("/app/app/offloading/agents49").glob("*.py")]},
         historical_note="Completion control uses gamma=1 to isolate reward timing; historical gamma=.99 is not rerun."))
    results=[]
    exported_contracts=[]
    for algorithm,reward_mode,length,feature,seed in product(ALGORITHMS,("completion","integral"),(20,100),("full","pruned"),SEEDS):
        name=f"{algorithm}-{reward_mode}-n{length}-{feature}-s{seed}"
        folder=out/"runs"/name
        folder.mkdir(parents=True)
        drop=dropped if feature=="pruned" else []
        agent=ALGORITHMS[algorithm](seed=seed,gamma=1,
                                  input_spec=InputSpec(feature,tuple(drop)))
        steps=0
        def evaluate():
            frozen=evaluation_snapshot(agent,991)
            rng_before=json.dumps(agent.rng.bit_generator.state,sort_keys=True)
            for case in val:
                work=[Task(**r) for r in case["tasks"]]
                policy=Policy(frozen)
                result=run_policy(work,policy,include_decision_overhead=False,**config(case["scene"]))
                expected=mean(-r["total_latency_ms"]/1000-(not r["deadline_met"]) for r in result["tasks"])
                row=dict(run=name,algorithm=algorithm,reward_mode=reward_mode,train_length=length,
                         feature=feature,seed=seed,steps=steps,scene=case["scene"]["id"],
                         validation_seed=case["seed"],burst=case["burst"],mean_task_reward=expected,**result["summary"])
                results.append(row)
                write(folder/f'validation-{steps}-{case["scene"]["id"]}-{case["seed"]}-{int(case["burst"])}.json',
                      dict(summary=row,q_values=policy.q,tasks=result["tasks"]))
            assert rng_before==json.dumps(agent.rng.bit_generator.state,sort_keys=True)
        evaluate()
        with (folder/"training.jsonl").open("w") as f:
            for ep,case in enumerate(schedules[f"{seed}/{length}"]):
                work=[Task(**r) for r in case["tasks"]]
                episode=rollout(agent,work,case["scene"],reward_mode,drop,steps)
                f.write(json.dumps(dict(episode=ep,**episode),allow_nan=False)+"\n")
                steps+=length
                if steps in (400,800):
                    evaluate()
        agent.save(folder/"checkpoint.npz")
        write(folder/"checkpoint.json",dict(sha256=digest(folder/"checkpoint.npz"),updates=agent.updates,
              gamma=1,algorithm=algorithm,objective=reward_mode,feature_mask=drop,training_seed=seed))
        exported_contracts.append(export_agent_contract(agent,folder/'checkpoint.npz',folder/'input-contracts',[Path(__file__)]))
        write(out/"validation-summary.json",results)
        print(name,"complete",flush=True)
    write_contract_index(out/'input-contract-index.json',exported_contracts)
    # Exactly matched comparator suite, inference-cost exclusion diagnostic.
    for strategy in ("latency_aware","latency_aware_v2"):
        for case in val:
            result=run_policy([Task(**r) for r in case["tasks"]],STRATEGY_FACTORIES[strategy](),
                              include_decision_overhead=False,**config(case["scene"]))
            results.append(dict(run=strategy,algorithm=strategy,reward_mode="baseline",train_length=0,
                 feature="full",seed=0,steps=800,scene=case["scene"]["id"],validation_seed=case["seed"],burst=case["burst"],
                 mean_task_reward=mean(-r["total_latency_ms"]/1000-(not r["deadline_met"]) for r in result["tasks"]),
                 **result["summary"]))
    write(out/"validation-summary.json",results)
    write(out/"complete.json",dict(status="PASS",models=48,training_dispatches=38400,validation_runs=len(results),
                                  test_runs=0,updates_each=agent.updates))


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("out",type=Path)
    p.add_argument("archive",type=Path)
    a=p.parse_args()
    main(a.out,a.archive)

