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
from .workload import generate_tasks


def metrics(rows):
    if not rows:
        raise ValueError("no results")
    latencies = sorted(r["total_latency_ms"] for r in rows)
    counts = Counter(r["selected_node"] for r in rows)
    return {
        "task_count": len(rows),
        "completed_count": len(rows),
        "completion_rate": 1.0,
        "dropped_count": 0,
        "drop_rate": 0.0,
        "drop_policy": "none; late tasks finish and count as deadline misses",
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
               nodes=None):
    names = strategies or ["local_only", "edge_only", "cloud_only",
                           "load_threshold", "latency_aware"]
    if len(names) != len(set(names)):
        raise ValueError("strategy names must be unique")
    unknown = set(names) - set(STRATEGY_FACTORIES) - {"laya"}
    if unknown:
        raise ValueError(f"Strategies not implemented: {sorted(unknown)}")
    tasks = generate_tasks(count, interval_ms, seed, deadline_ms, profile)
    output = {}
    for name in names:
        policy = LayaStrategy() if name == "laya" else STRATEGY_FACTORIES[name]()
        sim = Simulator(tasks, policy, nodes or DEFAULT_NODES,
                        include_decision_overhead)
        rows = sim.run()
        output[name] = {"summary": metrics(rows), "tasks": rows,
                        "queue_samples": sim.queue_samples}
    for result in output.values():
        snapshots = result['queue_samples']
        result['node_statistics'] = {name: {
            'max_queue_at_decisions': max(s[name+'_queue'] for s in snapshots),
            'mean_queue_at_decisions': mean(s[name+'_queue'] for s in snapshots),
            'max_work_ms_at_decisions': max(s[name+'_work_ms'] for s in snapshots),
            'cpu_utilization': sum(r['compute_ms'] for r in result['tasks'] if r['selected_node']==name) / max(r['completed_at_ms'] for r in result['tasks'])
        } for name in ('local','edge','cloud')}
    manifest = [asdict(t) for t in tasks]
    return {"workload_sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(),
            "workload": manifest,
            "measurement_scope": "Local reference inference is measured only for measured_csv; network, queue and relative node speeds are simulated. Decision wall time is measured on this host.",
            "profile_source": "measured_csv" if profile is not None else "synthetic_demo_NOT_measured",
            "decision_overhead_in_latency": include_decision_overhead,
            "config": {"count": count, "interval_ms": interval_ms,
                       "seed": seed, "deadline_ms": deadline_ms,
                       "nodes": {k: asdict(v) for k, v in (nodes or DEFAULT_NODES).items()}},
            "strategies": output}
