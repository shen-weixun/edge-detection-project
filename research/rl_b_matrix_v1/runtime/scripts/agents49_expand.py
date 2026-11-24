"""Freeze and execute matched eight-policy holdout and ten-policy Laya subset."""
import argparse
from dataclasses import asdict
import csv
from math import ceil, isclose
from pathlib import Path
from statistics import mean

from agents49_experiment import (Study, read, write, digest, config, tasks_from,
    Agent49Policy, EstimatedPolicy, STRATEGY_FACTORIES, load_agent, run_policy, Task, workload_digest)

SEEDS = (211, 307, 401)
STRATEGIES = ("local_only", "edge_only", "cloud_only", "load_threshold",
              "latency_aware", "latency_aware_v2", "dqn", "ddqn")
LAYA = ("laya", "laya_v2")


def describe(values):
    return {"n": len(values), "mean_ms": mean(values), "p95_ms": sorted(values)[ceil(.95*len(values))-1]}


def laya_budget(old):
    audit = {r["audit_id"]: r for r in read(old / "formal/laya-audit.json")}
    stats = {}
    for name in LAYA:
        rows = [t for path in (old / "formal/raw").glob(f"*/{name}.json")
                for t in read(path)["result"]["tasks"]]
        stats[name] = {"worker": describe([audit[r["decision_audit_id"]]["elapsed_ms"] for r in rows]),
                       "client": describe([r["decision_wall_ms"] for r in rows]),
                       "decision_queue": describe([r["decision_queue_ms"] for r in rows])}
    total = 24*len(SEEDS)*100
    return {"previous_run": stats, "full_calls_per_variant": total, "full_calls_total": total*2,
            "estimated_serial_client_hours": sum(total*r["client"]["mean_ms"] for r in stats.values())/3600000,
            "new_calls": 0, "archived_live_decisions": 480,
            "reason": "Reuse full archived SimPy runs on exact frozen historical subset and time schedule; rerun eight comparators. No decisions replayed."}


def freeze(study, old, out, selected):
    manifests = {"expanded": [], "laya-subset": []}
    for scene in study.pilot["scenarios"]:
        dataset = scene["dataset"]
        pool = study.data[dataset, "testing"][1]
        interval = study.training_interval(scene)
        for seed in SEEDS:
            tasks = tasks_from(pool, 100, interval, seed, 1000, study.estimator)
            if len({t.source_path for t in tasks}) != 100:
                raise ValueError("100 unique images required in every seed")
            new_scene = dict(scene, id=f'{dataset}-{scene["load"]}-{scene["network"]}-n100-s{seed}',
                             count=100, seed=seed, interval_ms=interval, arrival_rate_per_second=1000/interval,
                             design_basis="Training-profile mean service at reference Edge speed 3")
            for key in ("per_node_compute_demand", "reference_mean_service_ms", "reference_service_rate_per_second"):
                new_scene.pop(key, None)
            manifests["expanded"].append((new_scene, tasks, None))
        for seed in (23, 37):
            old_id = f'{dataset}-{scene["load"]}-{scene["network"]}-n5-s{seed}'
            frozen = read(old / "formal/raw" / old_id / "laya.json")
            manifests["laya-subset"].append((frozen["scene"], [Task(**r) for r in frozen["workload"]], old_id))

    frozen = {}
    for stage, cases in manifests.items():
        frozen[stage] = []
        for scene, tasks, old_id in cases:
            rows = [asdict(t) for t in tasks]
            interval = scene["interval_ms"]
            avg_work = mean(t.workload_ms for t in tasks)
            frozen[stage].append({"scene": scene, "workload": rows, "workload_sha256": workload_digest(rows),
                                  "archived_run": old_id, "realized_reference_rho": avg_work / (3*interval),
                                  "offered_cpu_rho_by_node_if_all_tasks": {
                                      name: avg_work/(cfg["speed"]*interval) for name, cfg in scene["nodes"].items()}})
    manifest = {"schema": "agents49-final-design-v1", "expanded_seeds": SEEDS,
                "laya_subset_seeds": [23, 37], "checkpoints": selected,
                "seed_note": "Same 100 independent images per dataset; each expanded seed permutes order.",
                "runner_sha256": digest(Path(__file__)), "laya_budget": laya_budget(old), **frozen}
    path = out / "design.json"
    if path.exists():
        raise ValueError("Design already frozen")
    write(path, manifest)
    print("DESIGN FROZEN", digest(path), len(frozen["expanded"]), len(frozen["laya-subset"]), flush=True)


def evaluate(old, out, stage, study):
    design = read(out / "design.json")
    if design["runner_sha256"] != digest(Path(__file__)):
        raise ValueError("Runner changed after design freeze")
    selected = design["checkpoints"]
    agents = {name: study.load_model(name, old / spec["path"], spec["sha256"]) for name, spec in selected.items()}
    strategies = STRATEGIES + (LAYA if stage == "laya-subset" else ())
    records = []
    for case in design[stage]:
        scene = case["scene"]
        inputs = case["workload"]
        tasks = [Task(**row) for row in inputs]
        if workload_digest(inputs) != case["workload_sha256"]:
            raise ValueError("Invalid workload hash")
        for name in strategies:
            path = out / stage / "raw" / scene["id"] / (name + ".json")
            if path.exists():
                payload = read(path)
            elif name in LAYA:
                source = old / "formal/raw" / case["archived_run"] / (name + ".json")
                payload = read(source)
                payload.update(decision_provenance="archived_live_complete_run", archived_sha256=digest(source))
            else:
                policy = Agent49Policy(agents[name]) if name in agents else STRATEGY_FACTORIES[name]()
                result = run_policy(tasks, EstimatedPolicy(policy, study.estimator),
                                    include_decision_overhead=True, **config(scene))
                payload = {"status": "PASS", "scene": scene, "strategy": name, "workload": inputs,
                           "workload_sha256": case["workload_sha256"], "checkpoint": selected.get(name),
                           "result": result, "decision_provenance": "new_local_wall_time"}
                if name in agents:
                    payload["agent_decisions"] = policy.decisions
            if not (payload["status"] == "PASS" and payload["scene"] == scene
                    and payload["workload"] == inputs and payload["workload_sha256"] == case["workload_sha256"]
                    and payload["strategy"] == name
                    and (payload.get("checkpoint") or {}).get("sha256") == (selected.get(name) or {}).get("sha256")):
                raise ValueError(f"Unmatched run {path}")
            rows = payload["result"]["tasks"]
            if [r["task"] for r in rows] != inputs or not all(
                r["completed"] and r["decision_ms"] > 0 and isclose(
                    r["total_latency_ms"], sum(r[k] for k in
                    ("decision_ms", "decision_queue_ms", "network_ms", "queue_ms", "compute_ms")),
                    abs_tol=1e-6, rel_tol=0) for r in rows):
                raise ValueError(f"Inconsistent events {path}")
            if not path.exists():
                write(path, payload)
            stats = payload["result"]["summary"]
            records.append({"dataset": scene["dataset"], "load": scene["load"], "network": scene["network"],
                            "scene_id": scene["id"], "seed": scene["seed"], "strategy": name, "count": len(rows),
                            "interval_ms": scene["interval_ms"], "realized_reference_rho": case["realized_reference_rho"],
                            "workload_sha256": case["workload_sha256"], "decision_provenance": payload["decision_provenance"],
                            **{f: stats[f] for f in ("avg_latency_ms", "p95_latency_ms", "deadline_met_rate", "completion_rate")},
                            **stats["components_ms"], **{n+"_ratio": v for n, v in stats["placement_ratio"].items()}})
        print(stage, scene["id"], len(strategies), flush=True)
    with (out / stage / "comparison.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    write(out / stage / "comparison.json", records)
    write(out / stage / "complete.json", {"status": "PASS", "strategy_runs": len(records),
          "tasks": sum(r["count"] for r in records), "design_sha256": digest(out / "design.json")})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("freeze", "expanded", "laya-subset"))
    for key in ("old", "out", "member", "archive"):
        parser.add_argument(f"--{key}", required=True, type=Path)
    parser.add_argument('--input-contract-index', required=True, type=Path)
    args = parser.parse_args()
    study = Study(args.out / "reproduction", args.member, args.archive, args.input_contract_index)
    selected = read(args.out / "selected-checkpoints.json")
    for name, model in selected.items():
        reproduced = read(study.output / "selected-checkpoints.json")[name]
        if model["sha256"] != reproduced["sha256"] or model["validation_mean_reward"] != reproduced["validation_mean_reward"]:
            raise ValueError("Phase 2 reproduction selection differs")
    if args.stage == "freeze":
        freeze(study, args.old, args.out, selected)
    else:
        evaluate(args.old, args.out, args.stage, study)

