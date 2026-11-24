"""Training/validation-only reward-method experiment. Never evaluates testing."""
import sys
sys.path.insert(0,"/app")
import argparse
from app.offloading.agents49.evaluation import evaluation_snapshot
from dataclasses import asdict, replace
import json
from math import ceil
from pathlib import Path
import random
from statistics import mean
import numpy as np
from agents49_experiment import config, read, write, digest
from app.offloading.profiles import load, root
from app.offloading.estimators import load_registered
from app.offloading.integration_contract import feature_vector, validate_manifest_split, run_policy
from app.offloading.models import Task
from app.offloading.rl import OffloadingEnv
from app.offloading.agents49.training import train_episode
from app.offloading.agents49.task_credit import train_task_episode
from app.offloading.agents49.dqn import DQN
from app.offloading.agents49.adapter import load_agent
from app.offloading.agents49.input_contract import InputSpec, export_agent_contract, write_contract_index
from app.offloading.agents49.normalizer import normalize, FEATURE_NAMES
from app.offloading.strategies import STRATEGY_FACTORIES

SEEDS=(42,43,44)
MODES=("global20","global100","task100","task100_pruned")


class Agent(DQN):
    def __init__(self, seed, mode, dropped):
        self.dropped = dropped if mode.endswith("pruned") else []
        super().__init__(seed=seed,gamma=0 if mode.startswith("task") else .99,
                         input_spec=InputSpec('pruned' if self.dropped else 'full',tuple(self.dropped)))
        self.traces=[]
    def act(self, features, epsilon=0):
        self.traces.append(list(features))
        return super().act(features,epsilon)


class Policy:
    def __init__(self,agent):
        self.agent=agent
    def select_node(self,task,state):
        return ("local","edge","cloud")[self.agent.act(feature_vector(task,state),0)]


def tasks(pool, n, interval, seed, estimator, burst=False):
    rng=random.Random(seed)
    schedule=[]
    now=0.
    for i in range(n):
        row=pool[rng.randrange(len(pool))]
        t=Task(task_id=i,arrival_ms=now,deadline_ms=1000,**row)
        schedule.append(replace(t,estimated_workload_ms=estimator.predict(t)))
        now+=interval*(.15 if burst and i%20<10 else 1.85 if burst else 1)
    return schedule


def historical(out):
    stats={}
    for algorithm in ("dqn","ddqn"):
        log=root()/"agents49/training"/algorithm/"42/transitions.jsonl"
        eps=[json.loads(line) for line in log.read_text().splitlines()]
        terminals=[(s,t) for e in eps for s in e["transitions"] for t in s["terminal_rewards"]]
        total=-sum(t["reward"] for _,t in terminals)
        stats[algorithm]={"completed_rewards":len(terminals),
          "same_task_ratio":mean(s["task_id"]==t["task_id"] for s,t in terminals),
          "final_step_cost_fraction":-sum(t["reward"] for s,t in terminals if s["done"])/total,
          "source_sha256":digest(log)}
    write(out/"historical-reward.json",stats)
    # A slow local job, a later fast Edge job, then a Cloud probe.
    a=Task(0,.001,1,300,0,1000)
    work=[a,replace(a,task_id=1,arrival_ms=1,workload_ms=1),replace(a,task_id=2,arrival_ms=50,workload_ms=1)]
    counter={}
    for mode in ("global","task"):
        agent=Agent(42,"task100" if mode=="task" else "global100",[])
        actions=iter((0,1,2))
        agent.act=lambda features,epsilon:next(actions)
        fn=train_task_episode if mode=="task" else train_episode
        counter[mode]=fn(agent,work,epsilon_for_step=lambda _:0,config={})
    write(out/"minimal-counterexample.json",counter)


def main(out,input_contract_index=None):
    if out.exists():
        raise ValueError("Choose a new output directory")
    out.mkdir(parents=True)
    scenes=read(root()/"ai-comparison/scenario_manifest.json")["scenarios"]
    ids=read(root()/"formal-evaluation/profile-ids.json")
    plan=read(root()/"formal-evaluation/plan.json")["selected"]
    validate_manifest_split(plan)
    data={}
    specs={}
    for ds in ("lfw","wider_train"):
        for role in ("training","validation"):
            meta,rows=load(ids[ds+"/"+role])
            assert {r["source_path"] for r in rows}=={r["source_path"] for r in plan if r["dataset"]==ds and r["role"]==role}
            data[ds,role]=rows
            specs[ds+"/"+role]={"id":meta["id"],"csv_sha256":meta["csv_sha256"]}
    estimator=load_registered(read(root()/"formal-evaluation/evaluation/fit-complete.json")["models"]["median"])
    def make(scene,role,n,seed,burst=False):
        pool=data[scene["dataset"],role]
        interval=mean(r["workload_ms"] for r in data[scene["dataset"],"training"])/(3*scene["reference_offered_cpu_load"])
        return tasks(pool,n,interval,seed,estimator,burst)
    historical(out)
    collector=Agent(17,"global100",[])
    for scene in scenes:
        train_episode(collector,make(scene,"training",40,17),epsilon_for_step=lambda _:1,config=config(scene))
    matrix=np.array(collector.traces)
    constants=np.flatnonzero(np.ptp(matrix,axis=0)<1e-12).tolist()
    duplicates=[(i,j) for i in range(49) for j in range(i) if np.array_equal(matrix[:,i],matrix[:,j])]
    dropped=sorted((set(constants)|{i for i,j in duplicates}|{FEATURE_NAMES.index("arrival_ms"),
                     *[FEATURE_NAMES.index(n+".observed_at_ms") for n in ("local","edge","cloud")]})-{14,28,42})
    write(out/"feature-design.json",{"analysis_role":"training","names":FEATURE_NAMES,"constant_indices":constants,
          "equal_column_pairs":duplicates,"dropped_indices":dropped,"seeds":SEEDS,"modes":MODES,
          "episodes_100":24,"steps_per_model":2400,"profiles":specs,"estimator":estimator.model_id if hasattr(estimator,"model_id") else scenes[0]["estimator_id"],
          "script_sha256":digest(Path(__file__)),"task_objective":"terminal task contextual cost, gamma=0",
          "gamma_global":.99,"episode_task_counts":[20,100],"checkpoints":[0,800,1600,2400]})
    np.savez_compressed(out/"training-observations.npz",raw=matrix,normalized=np.array([normalize(x) for x in matrix]))
    # Fixed validation suite: all 24 scenarios, two task lengths and burst/steady.
    suite=[(s,n,b,make(s,"validation",n,701,b)) for s in scenes for n in (20,100) for b in (False,True)]
    curve=[]
    validation_raw=[]
    exported_contracts=[]
    for seed in SEEDS:
        for mode in MODES:
            agent=Agent(seed,mode,dropped)
            folder=out/mode/str(seed)
            folder.mkdir(parents=True)
            n=20 if mode=="global20" else 100
            num_episodes=2400//n
            rng=random.Random(seed)
            episode_scenes=[scenes[i%24] for i in range(num_episodes)]
            rng.shuffle(episode_scenes)
            steps=0
            def evaluate():
                evaluation_agent = evaluation_snapshot(agent, 701)
                evaluation_agent.traces = []
                for scene,length,burst,work in suite:
                    result=run_policy(work,Policy(evaluation_agent),include_decision_overhead=False,**config(scene))
                    score=mean(-r["total_latency_ms"]/1000-(not r["deadline_met"]) for r in result["tasks"])
                    curve.append({"seed":seed,"mode":mode,"steps":steps,"scene":scene["id"],"length":length,
                                  "burst":burst,"reward":score,**result["summary"]})
                if steps==2400:
                    validation_raw.extend(evaluation_agent.traces)
                agent.traces.clear()
            evaluate()
            with (folder/"episodes.jsonl").open("w") as stream:
                for i,scene in enumerate(episode_scenes):
                    # Fixed seed sequence uses identical schedules for 100-task methods.
                    sample_seed=rng.randrange(2**32)
                    work=make(scene,"training",n,sample_seed,i%2==1)
                    fn=train_task_episode if mode.startswith("task") else train_episode
                    records=fn(agent,work,epsilon_for_step=lambda k:max(.05,1-.95*(steps+k)/2399),config=config(scene))
                    steps+=n
                    stream.write(json.dumps({"episode":i,"scene":scene["id"],"seed":sample_seed,"burst":i%2==1,
                                  "sources":[t.source_path for t in work],"records":records})+"\n")
                    agent.traces.clear()
                    if steps%800==0:
                        evaluate()
            agent.save(folder/"method-checkpoint.npz")
            write(folder/"checkpoint.json",{"sha256":digest(folder/"method-checkpoint.npz"),
                  "mode":mode,"gamma":agent.gamma,"active_dimensions":49-len(agent.dropped),
                  "contract":"method-task-terminal-v1" if mode.startswith("task") else "historical-global-v1",
                  "transform":agent.dropped,"seed":seed,"updates":agent.updates})
            exported_contracts.append(export_agent_contract(agent,folder/'method-checkpoint.npz',folder/'input-contracts',[Path(__file__)]))
            print(seed,mode,"complete",flush=True)
    write_contract_index(out/'input-contract-index.json',exported_contracts)
    write(out/"validation-curves.json",curve)
    # Sensitivity on validation observations; no testing data loaded.
    val=np.array(validation_raw[:5000])
    features=[]
    original=root()/"agents49/training/dqn/42/dqn_simpy49.npz"
    old=load_agent('dqn',original,digest(original),contract_index=input_contract_index)
    z=np.array([normalize(x) for x in val])
    q=old._forward(z,old.online)[2]
    rng=np.random.default_rng(73)
    for i,name in enumerate(FEATURE_NAMES):
        perturbed=z.copy()
        perturbed[:,i]=rng.permutation(perturbed[:,i])
        pq=old._forward(perturbed,old.online)[2]
        features.append({"name":name,"training_min":float(matrix[:,i].min()),"training_max":float(matrix[:,i].max()),
                         "validation_min":float(val[:,i].min()),"validation_max":float(val[:,i].max()),
                         "normalized_training_min":float(normalize(matrix.min(axis=0))[i]),
                         "normalized_training_max":float(normalize(matrix.max(axis=0))[i]),
                         "q_mean_abs_permutation_change":float(abs(pq-q).mean()),
                         "action_flip_fraction":float((pq.argmax(axis=1)!=q.argmax(axis=1)).mean())})
    write(out/"feature-analysis.json",features)
    # Baselines use identical validation inputs.
    baselines=[]
    for name in ("latency_aware","latency_aware_v2"):
        for scene,n,burst,work in suite:
            result=run_policy(work,STRATEGY_FACTORIES[name](),include_decision_overhead=False,**config(scene))
            baselines.append({"strategy":name,"scene":scene["id"],"length":n,"burst":burst,
                              "reward":mean(-r["total_latency_ms"]/1000-(not r["deadline_met"]) for r in result["tasks"]),
                              **result["summary"]})
    write(out/"validation-baselines.json",baselines)
    write(out/"complete.json",{"status":"PASS","validation_runs":len(curve),"new_test_runs":0,
                               "claim":"method diagnostics only; no convergence or superiority certification"})


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("out",type=Path)
    p.add_argument('--input-contract-index',required=True,type=Path)
    a=p.parse_args()
    main(a.out,a.input_contract_index)

