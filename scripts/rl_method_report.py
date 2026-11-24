"""Summarize diagnostic validation and export convergence and sensitivity curves."""
import sys
sys.path.insert(0,"/app")
import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean
import numpy as np
import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
from agents49_experiment import read,write,digest,config
from rl_method_study import tasks, Policy
from app.offloading.agents49.dqn import DQN
from app.offloading.agents49.ddqn import DDQN
from app.offloading.agents49.adapter import load_agent
from app.offloading.agents49.normalizer import normalize,FEATURE_NAMES
from app.offloading.integration_contract import run_policy
from app.offloading.profiles import root,load
from app.offloading.estimators import load_registered


def csvout(path,rows):
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main(out,input_contract_index=None):
    assert read(out/"complete.json")["new_test_runs"]==0
    curves=read(out/"validation-curves.json")
    csvout(out/"validation-curves.csv",[{k:v for k,v in r.items() if k not in ("placement","placement_ratio","components_ms")} for r in curves])
    groups=defaultdict(list)
    for r in curves:
        groups[r["mode"],r["steps"],r["length"],r["burst"]].append(r)
    summary=[dict(mode=k[0],steps=k[1],length=k[2],burst=k[3],mean_reward=mean(r["reward"] for r in v),
                  avg_latency_ms=mean(r["avg_latency_ms"] for r in v),
                  deadline_met_rate=mean(r["deadline_met_rate"] for r in v)) for k,v in groups.items()]
    write(out/"validation-summary.json",summary)
    csvout(out/"validation-summary.csv",summary)
    fig,axes=plt.subplots(1,3,figsize=(16,4),layout="constrained")
    for mode_index,mode in enumerate(read(out/"feature-design.json")["modes"]):
        color=plt.get_cmap("tab10")(mode_index)
        for seed in (42,43,44):
            episode=[__import__("json").loads(line) for line in (out/mode/str(seed)/"episodes.jsonl").read_text().splitlines()]
            losses=[mean(s["loss"] for s in e["records"] if s["loss"] is not None) if any(s["loss"] is not None for s in e["records"]) else float("nan") for e in episode]
            xx=np.arange(1,len(losses)+1)*(20 if mode=="global20" else 100)
            axes[0].plot(xx,losses,alpha=.4,color=color,label=mode if seed==42 else None)
            axes[2].plot(xx,[sum(s["reward"] for s in e["records"])/(20 if mode=="global20" else 100) for e in episode],alpha=.4,color=color,label=mode if seed==42 else None)
        pts=[r for r in summary if r["mode"]==mode and r["length"]==100 and not r["burst"]]
        axes[1].plot([r["steps"] for r in pts],[r["mean_reward"] for r in pts],marker="o",label=mode)
    axes[0].set(xlabel="Dispatches",ylabel="Clipped TD loss",title="Training loss; 3 seeds")
    axes[1].set(xlabel="Dispatches",ylabel="Mean per-task reward",title="Validation; 100 tasks / steady")
    axes[0].legend(fontsize=8)
    axes[2].legend(fontsize=8)
    axes[1].legend()
    axes[2].set(xlabel="Dispatches",ylabel="Mean reward per dispatch",title="Exploratory training reward")
    fig.savefig(out/"learning-curves.png",dpi=150)
    plt.close(fig)
    # Actual validation states collected by the historical frozen policies.
    ids=read(root()/"formal-evaluation/profile-ids.json")
    scenes=read(root()/"ai-comparison/scenario_manifest.json")["scenarios"]
    estimator=load_registered(scenes[0]["estimator_id"])
    sensitivity=[]
    clock_results=[]
    for name,ctor in (("dqn",DQN),("ddqn",DDQN)):
        checkpoint=root()/"agents49/training"/name/"42"/f"{name}_simpy49.npz"
        a=load_agent(name,checkpoint,digest(checkpoint),contract_index=input_contract_index)
        states=[]
        class Trace:
            def select_node(self,task,state):
                from app.offloading.integration_contract import feature_vector
                f=feature_vector(task,state)
                states.append(f)
                return ("local","edge","cloud")[a.act(f)]
        for scene in scenes:
            _,train=load(ids[scene["dataset"]+"/training"])
            _,val=load(ids[scene["dataset"]+"/validation"])
            interval=mean(r["workload_ms"] for r in train)/(3*scene["reference_offered_cpu_load"])
            work=tasks(val,100,interval,701,estimator)
            run_policy(work,Trace(),include_decision_overhead=False,**config(scene))
        x=np.array([normalize(f) for f in states])
        q=a._forward(x,a.online)[2]
        raw=np.array(states)
        shifted=raw.copy()
        shifted[:,[3,20,34,48]]+=100000
        sq=a._forward(np.array([normalize(f) for f in shifted]),a.online)[2]
        clock_results.append({"model":name,"clock_shift_ms":100000,
                              "action_flip_fraction":float((sq.argmax(axis=1)!=q.argmax(axis=1)).mean()),
                              "q_abs_change":float(abs(sq-q).mean())})
        rng=np.random.default_rng(73)
        for i,field in enumerate(FEATURE_NAMES):
            perm=x.copy()
            perm[:,i]=rng.permutation(perm[:,i])
            pq=a._forward(perm,a.online)[2]
            sensitivity.append(dict(model=name,feature=field,q_abs_change=float(abs(q-pq).mean()),
                                    action_flip_fraction=float((pq.argmax(axis=1)!=q.argmax(axis=1)).mean())))
    write(out/"clock-translation-probe.json",clock_results)
    write(out/"q-sensitivity-both.json",sensitivity)
    csvout(out/"q-sensitivity-both.csv",sensitivity)
    # Training-selected ablation transform, no test-dependent tuning.
    f=read(out/"feature-design.json")
    feature=read(out/"feature-analysis.json")
    csvout(out/"feature-analysis.csv",feature)
    write(out/"evidence-summary.json",{"training_models":12,"training_dispatches":28800,"validation_runs":len(curves),
          "raw_constant_names":[FEATURE_NAMES[i] for i in f["constant_indices"]],
          "pruned_active_dimensions":49-len(f["dropped_indices"]),"test_runs":0,
          "checkpoints":{p.relative_to(out).as_posix():digest(p) for p in out.glob("*/*/method-checkpoint.npz")}})
    print("Report complete",len(curves),"validation runs")


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("out",type=Path)
    p.add_argument('--input-contract-index',required=True,type=Path)
    a=p.parse_args()
    main(a.out,a.input_contract_index)

