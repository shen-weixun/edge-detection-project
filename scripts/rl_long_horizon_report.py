"""Audit all training ledgers and export per-seed diagnostics."""
import sys
sys.path.insert(0,"/app")
import argparse
from collections import defaultdict
import csv
import json
from math import ceil,isfinite,isclose
from pathlib import Path
from statistics import mean
import numpy as np
import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
from agents49_experiment import read,write,digest


def csvout(path,rows):
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main(out):
    complete=read(out/"complete.json")
    design=read(out/"design.json")
    rows=read(out/"validation-summary.json")
    seedrows=[]
    for r in rows:
        copy={k:v for k,v in r.items() if k not in ("placement","placement_ratio","components_ms")}
        copy.update(r["components_ms"])
        copy.update({n+"_ratio":v for n,v in r["placement_ratio"].items()})
        seedrows.append(copy)
    csvout(out/"validation-all-seeds.csv",seedrows)
    training=[]
    maximum=0.
    nlogs=0
    returns=defaultdict(list)
    for folder in sorted((out/"runs").iterdir()):
        spec=read(folder/"checkpoint.json")
        assert digest(folder/"checkpoint.npz")==spec["sha256"]
        assert spec["updates"]==737 and spec["gamma"]==1
        algorithm,objective,length,feature,seed=folder.name.split("-")
        length=int(length[1:])
        seed=int(seed[1:])
        schedule=design["training"][f"{seed}/{length}"]
        episodes=[json.loads(line) for line in (folder/"training.jsonl").read_text().splitlines()]
        assert len(episodes)==len(schedule)
        steps=0
        for e,case in zip(episodes,schedule):
            tasks=e["tasks"]
            trans=e["transitions"]
            assert len(tasks)==len(trans)==length and {t["task_id"] for t in tasks}==set(range(length))
            assert [r["task"] for r in sorted(tasks,key=lambda r:r["task_id"])]==case["tasks"]
            lat=sum(t["total_latency_ms"] for t in tasks)
            cost=lat/1000+sum(not t["deadline_met"] for t in tasks)
            err=max(abs(cost+sum(t["reward"] for t in trans)),abs(lat-e["independent_area_ms"]))
            maximum=max(maximum,err)
            assert err<1e-6 and all(isfinite(t["reward"]) and (t["loss"] is None or isfinite(t["loss"])) for t in trans)
            for i,t in enumerate(trans):
                assert t["episode_done"]==(i==length-1)
                assert t["next_task_id"]==(None if i==length-1 else i+1)
            steps+=length
            losses=[t["loss"] for t in trans if t["loss"] is not None]
            record=dict(run=folder.name,algorithm=algorithm,objective=objective,length=length,feature=feature,seed=seed,
                        steps=steps,reward_per_task=-cost/length,mean_loss=mean(losses) if losses else None,
                        avg_latency_ms=lat/length,p95_latency_ms=sorted(t["total_latency_ms"] for t in tasks)[ceil(.95*length)-1],
                        deadline_met_rate=mean(t["deadline_met"] for t in tasks),
                        **{n+"_ratio":mean(t["selected_node"]==n for t in tasks) for n in ("local","edge","cloud")})
            training.append(record)
        assert steps==800
        nlogs+=1
    assert nlogs==48
    # Cross-length task/content/relative-time matching before each reset.
    for seed in design["seeds"]:
        blocks=design["training"][f"{seed}/100"]
        chunks=design["training"][f"{seed}/20"]
        for chunk in chunks:
            original=blocks[chunk["parent_block"]]["tasks"][chunk["start_index"]:chunk["start_index"]+20]
            for old,new in zip(original,chunk["tasks"]):
                assert old["source_path"]==new["source_path"] and old["workload_ms"]==new["workload_ms"]
                assert abs(old["arrival_ms"]-new["arrival_ms"]-chunk["offset_ms"])<1e-6
    csvout(out/"training-all-seeds.csv",training)
    curves=defaultdict(list)
    for r in rows:
        if r["reward_mode"]!="baseline":
            curves[r["run"],r["steps"]].append(r)
    reduced=[dict(run=k[0],steps=k[1],algorithm=v[0]["algorithm"],objective=v[0]["reward_mode"],
                  length=v[0]["train_length"],feature=v[0]["feature"],seed=v[0]["seed"],
                  reward=mean(r["mean_task_reward"] for r in v),latency_ms=mean(r["avg_latency_ms"] for r in v),
                  deadline=mean(r["deadline_met_rate"] for r in v)) for k,v in curves.items()]
    csvout(out/"validation-seed-curves.csv",reduced)
    # Plot each seed, with fixed colors and labels in every panel.
    fig,axes=plt.subplots(2,4,figsize=(16,7),layout="constrained",sharex=True)
    for ai,algorithm in enumerate(("dqn","ddqn")):
        for col,(length,feature) in enumerate(((20,"full"),(20,"pruned"),(100,"full"),(100,"pruned"))):
            ax=axes[ai,col]
            for objective,color in (("completion","#bf5b17"),("integral","#187b80")):
                for seed,style in zip((42,43,44),("-","--",":")):
                    pts=[r for r in reduced if r["algorithm"]==algorithm and r["objective"]==objective
                         and r["length"]==length and r["feature"]==feature and r["seed"]==seed]
                    pts.sort(key=lambda r:r["steps"])
                    ax.plot([r["steps"] for r in pts],[r["reward"] for r in pts],style,color=color,
                            label=f"{objective} s{seed}",marker=".",alpha=.85)
            ax.set(title=f"{algorithm.upper()} / {length} / {feature}",xlabel="Dispatches",ylabel="Validation reward / task")
            ax.legend(fontsize=6,ncol=2)
    fig.savefig(out/"validation-every-seed.png",dpi=135)
    plt.close(fig)
    # Tables show all seeds, including deterioration.
    text=["# 每個訓練種子的固定驗證結果","",
          "|模型／回合／特徵／Seed|Completion 0→400→800|Integral 0→400→800|",
          "|---|---|---|"]
    for algorithm in ("dqn","ddqn"):
        for length in (20,100):
            for feature in ("full","pruned"):
                for seed in (42,43,44):
                    sequences=[]
                    for obj in ("completion","integral"):
                        pts=sorted([r for r in reduced if r["algorithm"]==algorithm and r["length"]==length
                                    and r["feature"]==feature and r["seed"]==seed and r["objective"]==obj],
                                   key=lambda r:r["steps"])
                        sequences.append(" → ".join(f'{r["reward"]:.3f}' for r in pts))
                    text.append("|"+f"{algorithm} / {length} / {feature} / {seed}|"+ "|".join(sequences)+"|")
    (out/"PER_SEED.md").write_text("\n".join(text),encoding="utf-8")
    fig,axes=plt.subplots(2,4,figsize=(16,7),layout="constrained",sharex=True)
    for ai,algorithm in enumerate(("dqn","ddqn")):
        for col,(length,feature) in enumerate(((20,"full"),(20,"pruned"),(100,"full"),(100,"pruned"))):
            ax=axes[ai,col]
            for objective,color in (("completion","#bf5b17"),("integral","#187b80")):
                for seed,style in zip((42,43,44),("-","--",":")):
                    pts=[r for r in training if r["algorithm"]==algorithm and r["objective"]==objective
                         and r["length"]==length and r["feature"]==feature and r["seed"]==seed]
                    pts.sort(key=lambda r:r["steps"])
                    ax.plot([r["steps"] for r in pts],[r["reward_per_task"] for r in pts],style,color=color,
                            label=f"{objective} s{seed}",alpha=.65)
            ax.set(title=f"{algorithm.upper()} / {length} / {feature}",xlabel="Dispatches",ylabel="Training reward / task")
            ax.legend(fontsize=6,ncol=2)
    fig.savefig(out/"training-every-seed.png",dpi=135)
    plt.close(fig)
    indexed={(r["algorithm"],r["train_length"],r["feature"],r["seed"],r["steps"],
              r["scene"],r["validation_seed"],r["burst"],r["reward_mode"]):r
             for r in rows if r["reward_mode"]!="baseline"}
    deltas=[]
    for key,a in indexed.items():
        if key[-1]!="completion":
            continue
        b=indexed[key[:-1]+("integral",)]
        deltas.append(dict(algorithm=key[0],length=key[1],feature=key[2],seed=key[3],steps=key[4],
                      scene=key[5],validation_seed=key[6],burst=key[7],
                      integral_minus_completion_reward=b["mean_task_reward"]-a["mean_task_reward"],
                      integral_minus_completion_latency_ms=b["avg_latency_ms"]-a["avg_latency_ms"],
                      integral_minus_completion_deadline=b["deadline_met_rate"]-a["deadline_met_rate"]))
    csvout(out/"paired-reward-deltas.csv",deltas)
    empirical=[]
    for objective in ("completion","integral"):
        for length in (20,100):
            for feature in ("full","pruned"):
                for seed in (42,43,44):
                    paths=[out/"runs"/f"{name}-{objective}-n{length}-{feature}-s{seed}"/"checkpoint.npz"
                           for name in ("dqn","ddqn")]
                    with np.load(paths[0]) as d,np.load(paths[1]) as q:
                        difference=max(float(abs(d[f"w{i}"]-q[f"w{i}"]).max()) for i in range(6))
                    empirical.append(dict(objective=objective,length=length,feature=feature,seed=seed,
                                          maximum_weight_difference=difference))
    write(out/"empirical-dqn-ddqn-differences.json",empirical)
    write(out/"independent-audit.json",dict(status="PASS",models=nlogs,max_cost_identity_error=maximum,
                                          verified_training_dispatches=sum(r["length"] for r in training),
                                          shared_update_budget=737,test_runs=0))
    print(nlogs,"models audited; max identity error",maximum)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("out",type=Path)
    main(p.parse_args().out)

