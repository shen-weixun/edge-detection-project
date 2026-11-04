"""Comparable strategy runs: identical tasks and environment for every policy."""
from collections import Counter
from statistics import mean
from math import ceil
import hashlib
import json
from .simulator import Simulator, DEFAULT_NODES
from dataclasses import asdict
from .strategies import STRATEGY_FACTORIES
from .laya_client import LayaStrategy
from .workload import generate_tasks, calibration_estimate
from dataclasses import replace


def metrics(rows):
    if not rows:
        raise ValueError("no results")
    latencies = sorted(r["total_latency_ms"] for r in rows)
    counts = Counter(r["selected_node"] for r in rows)
    return {
        "task_count": len(rows),
        "completed_count": sum(r["completed"] for r in rows),
        "completion_rate": sum(r["completed"] for r in rows)/len(rows),
        "dropped_count": sum(r["dropped"] for r in rows),
        "drop_rate": sum(r["dropped"] for r in rows)/len(rows),
        "latency_scope": "all terminal tasks, including time consumed before dropping",
        "avg_decision_wall_ms": mean(r["decision_wall_ms"] for r in rows),
        "avg_latency_ms": round(mean(latencies), 4),
        "p95_latency_ms": latencies[max(0, ceil(0.95 * len(latencies)) - 1)],
        "deadline_met_rate": round(sum(r["deadline_met"] for r in rows) / len(rows), 4),
        "avg_decision_ms": round(mean(r["decision_ms"] for r in rows), 4),
        "placement": {name: counts.get(name, 0) for name in ("local", "edge", "cloud")},
        "placement_ratio": {name: counts.get(name, 0)/len(rows) for name in ("local", "edge", "cloud")},
        "components_ms": {key: mean(r[key] for r in rows) for key in
                          ('network_ms', 'queue_ms', 'compute_ms', 'decision_ms', 'decision_queue_ms')},
    }


def experiment(strategies=None, count=30, interval_ms=70.0, seed=42,
               deadline_ms=500.0, profile=None, include_decision_overhead=True,
               nodes=None, calibration_profile=None, information_mode="realistic",
               network_mode="independent", shared_bandwidth_mbps=120.0,
               deadline_policy="complete_all"):
    names = strategies or ["local_only", "edge_only", "cloud_only",
                           "load_threshold", "latency_aware"]
    if len(names) != len(set(names)):
        raise ValueError("strategy names must be unique")
    unknown = set(names) - set(STRATEGY_FACTORIES) - {"laya"}
    if unknown:
        raise ValueError(f"Strategies not implemented: {sorted(unknown)}")
    tasks = generate_tasks(count, interval_ms, seed, deadline_ms, profile)
    estimate = 150.0
    if information_mode == "realistic" and profile is not None:
        estimate = calibration_estimate(calibration_profile, profile)
    tasks = [replace(t, estimated_workload_ms=estimate) for t in tasks]
    output = {}
    for name in names:
        policy = LayaStrategy() if name == "laya" else STRATEGY_FACTORIES[name]()
        sim = Simulator(tasks, policy, nodes or DEFAULT_NODES,
                        include_decision_overhead, information_mode, network_mode,
                        shared_bandwidth_mbps, deadline_policy)
        rows = sim.run()
        output[name] = {"summary": metrics(rows), "tasks": rows,
                        "queue_samples": sim.queue_samples, "events": sim.events,
                        "node_statistics": sim.node_statistics()}
    manifest = [asdict(t) for t in tasks]
    return {"workload_sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(),
            "workload": manifest,
            "measurement_scope": "Local reference inference is measured only for measured_csv; network, queue and relative node speeds are simulated. Decision wall time is measured on this host.",
            "profile_source": "measured_csv" if profile is not None else "synthetic_demo_NOT_measured",
            "decision_overhead_in_latency": include_decision_overhead,
            "model_version": "audit-v2",
            "information_mode": information_mode,
            "estimator": {"kind": "disjoint_historical_median" if calibration_profile else "synthetic_prior",
                          "estimate_ms": estimate,
                          "training_identities": sorted((r["dataset"], r["source_path"]) for r in (calibration_profile or []))},
            "comparison_scope": "end_to_end" if include_decision_overhead else "selection_quality_ablation",
            "decision_executor": "single_serial_nonpreemptive",
            "config": {"network_mode": network_mode, "shared_bandwidth_mbps": shared_bandwidth_mbps,
                       "deadline_policy": deadline_policy, "information_mode": information_mode, "count": count, "interval_ms": interval_ms,
                       "seed": seed, "deadline_ms": deadline_ms,
                       "nodes": {k: asdict(v) for k, v in (nodes or DEFAULT_NODES).items()}},
            "strategies": output}
