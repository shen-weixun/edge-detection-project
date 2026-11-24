"""Independently verify a completed stage; publish figures and metrics per stratum."""
import argparse
from collections import Counter, defaultdict
import csv
from hashlib import sha256
import json
from math import ceil, isclose
from pathlib import Path
from statistics import mean
import sys

import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend" if (ROOT / "backend").is_dir() else ROOT
sys.path[:0] = [str(BACKEND), str(BACKEND / "tests")]
from acceptance_reference import reference
from app.offloading.models import Task, NodeConfig

PHASES = ("decision_ms", "decision_queue_ms", "network_ms", "queue_ms", "compute_ms")
NODES = ("local", "edge", "cloud")
LABELS = dict(local_only="Local-only", edge_only="Edge-only", cloud_only="Cloud-only",
              load_threshold="Load threshold", latency_aware="Latency-aware",
              latency_aware_v2="Latency-aware V2", laya="Laya Original", laya_v2="Laya V2",
              dqn="DQN", ddqn="DDQN")
FIELDS = ("avg_latency_ms", "p95_latency_ms", "deadline_met_rate", *PHASES,
          *(f"{node}_ratio" for node in NODES))


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def close(a, b, tolerance=1e-6):
    return isclose(a, b, rel_tol=0, abs_tol=tolerance)


def table(header, rows):
    return ["|" + "|".join(header) + "|", "|" + "|".join("---" for _ in header) + "|",
            *["|" + "|".join(str(x) for x in row) + "|" for row in rows]]


def figure(folder, key, rows, stage):
    labels = [LABELS[row["strategy"]] for row in rows]
    y = np.arange(len(rows))
    fig, axes = plt.subplots(2, 2, figsize=(13.5, 9), layout="constrained")
    avg = [r["avg_latency_ms"] for r in rows]
    p95 = [r["p95_latency_ms"] for r in rows]
    ax = axes[0, 0]
    ax.scatter(avg, y-.15, label="Mean", color="#227c9d", s=34, zorder=3)
    ax.scatter(p95, y+.15, label="P95", color="#bd651c", marker="D", s=31, zorder=3)
    ax.set(xscale="log", xlabel="Milliseconds (log scale)", title="End-to-end latency")
    ax.legend()
    ax = axes[0, 1]
    ax.barh(y, [100*r["deadline_met_rate"] for r in rows], color="#2a9d8f")
    ax.set(xlim=(0, 100), xlabel="Percent", title="Deadline met (1,000 ms)")
    ax = axes[1, 0]
    left = np.zeros(len(rows))
    for field, label, color in zip(PHASES, ("Decision", "Decision wait", "Network", "CPU wait", "Compute"),
                                    ("#6d597a", "#e56b6f", "#227c9d", "#f4a261", "#2a9d8f")):
        vals = [r[field] for r in rows]
        ax.barh(y, vals, left=left, label=label, color=color)
        left += vals
    ax.set(xlabel="Milliseconds", title="Mean latency by phase")
    ax.legend(ncols=2, fontsize=8)
    ax = axes[1, 1]
    left = np.zeros(len(rows))
    for node, color in zip(NODES, ("#40798c", "#f29e4c", "#6d597a")):
        vals = [100*r[f"{node}_ratio"] for r in rows]
        ax.barh(y, vals, left=left, label=node.title(), color=color)
        left += vals
    ax.set(xlim=(0, 100), xlabel="Percent", title="Node placement")
    ax.legend(ncols=3)
    for ax in axes.flat:
        ax.set_yticks(y, labels)
        ax.set_ylim(len(rows)-.5, -.5)
        ax.set_axisbelow(True)
        ax.grid(axis="x", alpha=.2)
    dataset = "LFW" if key[0] == "lfw" else "WIDER FACE"
    fig.suptitle(f"{dataset} / {key[1]} / {key[2].replace('_', ' ').title()} — {stage.title()}"
                 f" ({rows[0]['count']} tasks per policy)", fontsize=15)
    name = "-".join(key) + ".png"
    fig.savefig(folder / name, dpi=125)
    plt.close(fig)
    return name


def run(folder, stage):
    src = folder / stage
    gate = read(src / "complete.json")
    with (src / "comparison.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    seeds = {11} if stage == "pilot" else {23, 37}
    expected_count = 10 if stage == "pilot" else 5
    require(gate["status"] == "PASS" and gate["strategy_runs"] == len(rows) == 240*len(seeds), "incomplete")
    all_keys = set()
    workloads = defaultdict(set)
    groups = defaultdict(lambda: defaultdict(list))
    samples = defaultdict(set)
    max_error = 0
    max_reference_error = 0
    total = 0
    for line in rows:
        raw = read(src / "raw" / line["scene_id"] / (line["strategy"] + ".json"))
        scene, tasks, results = raw["scene"], raw["workload"], raw["result"]["tasks"]
        key = (line["dataset"], line["load"], line["network"])
        seed, strategy = int(line["seed"]), line["strategy"]
        run_key = (*key, seed, strategy)
        require(run_key not in all_keys and seed in seeds and strategy in LABELS, run_key)
        all_keys.add(run_key)
        require(tuple(scene[field] for field in ("dataset", "load", "network")) == key, run_key)
        require(len(results) == len(tasks) == int(line["count"]) == expected_count, run_key)
        signature = sha256(json.dumps(tasks, sort_keys=True).encode()).hexdigest()
        require(signature == raw["workload_sha256"] == line["workload_sha256"], run_key)
        workloads[(*key, seed)].add(signature)
        samples[(key[0], seed)].add(tuple(task["source_path"] for task in tasks))
        ports = defaultdict(list)
        phases = {field: [] for field in PHASES}
        placement = Counter()
        latencies = []
        deadlines = []
        clock = []
        for idx, task in enumerate(results):
            require(task["task"] == tasks[idx] and task["completed"] and not task["dropped"], run_key)
            require(task["task_id"] == idx, run_key)
            require("workload_ms" not in task["decision_input"] and "face_count" not in task["decision_input"], run_key)
            node = task["selected_node"]
            cfg = scene["nodes"][node]
            require(close(task["compute_ms"], tasks[idx]["workload_ms"]/cfg["speed"]), run_key)
            require(all(task[field] >= 0 for field in PHASES), run_key)
            require(task["decision_ms"] > 0 and task["decision_ms"] == task["decision_wall_ms"], run_key)
            sum_phases = sum(task[field] for field in PHASES)
            actual = task["completed_at_ms"]-task["arrival_ms"]
            require(close(actual, task["total_latency_ms"]) and close(actual, sum_phases), run_key)
            max_error = max(max_error, abs(actual-sum_phases))
            start, end = task["cpu_started_at_ms"], task["cpu_completed_at_ms"]
            require(task["arrival_ms"] <= start <= end <= task["completed_at_ms"], run_key)
            require(close(end-start, task["compute_ms"]), run_key)
            release = task["arrival_ms"]+task["decision_queue_ms"]+task["decision_ms"]
            clock.append((release-task["decision_ms"], release))
            ports[node].append((start, end))
            require(task["deadline_met"] == (actual <= tasks[idx]["deadline_ms"]), run_key)
            if node == "local":
                require(task["network_ms"] == 0, run_key)
            for field in PHASES:
                phases[field].append(task[field])
            placement[node] += 1
            latencies.append(actual)
            deadlines.append(task["deadline_met"])
        # Arithmetic FCFS oracle consumes only observed post-decision releases.
        shifted = [Task(**dict(row["task"], arrival_ms=row["arrival_ms"] + row["decision_queue_ms"]
                              + row["decision_ms"])) for row in results]
        placements = {row["task_id"]: row["selected_node"] for row in results}
        nodes = {name: NodeConfig(**cfg) for name, cfg in scene["nodes"].items()}
        oracle, links = reference(shifted, placements, nodes, scene["network_mode"],
                                  scene["shared_bandwidth_mbps"])
        for task in results:
            for field in ("cpu_started_at_ms", "cpu_completed_at_ms", "completed_at_ms",
                          "network_ms", "queue_ms", "compute_ms"):
                error = abs(task[field] - oracle[task["task_id"]][field])
                require(error < 1e-6, (run_key, task["task_id"], field, error))
                max_reference_error = max(max_reference_error, error)
        for calendar in links.values():
            for earlier, later in zip(calendar, calendar[1:]):
                require(later[0] >= earlier[1]-1e-6, run_key)
        for calendar in [clock, *ports.values()]:
            ordered = sorted(calendar)
            for earlier, later in zip(ordered, ordered[1:]):
                require(later[0] >= earlier[1]-1e-6, run_key)
        values = {
            "avg_latency_ms": mean(latencies),
            "p95_latency_ms": sorted(latencies)[ceil(.95*len(latencies))-1],
            "deadline_met_rate": mean(deadlines), **{f: mean(v) for f, v in phases.items()},
            **{f"{node}_ratio": placement[node]/len(tasks) for node in NODES},
        }
        for field in FIELDS:
            require(close(values[field], float(line[field]), 5.1e-5 if field == "avg_latency_ms" else 1e-6),
                    f"{run_key}: {field}")
        groups[key][strategy].extend(results)
        total += len(tasks)
    require(len(groups) == 24 and len(workloads) == 24*len(seeds)
            and all(len(x) == 1 for x in workloads.values()) and all(len(x) == 1 for x in samples.values())
            and total == gate["tasks"], "workload pairing")
    require(len(samples) == 2*len(seeds), "seed samples")

    graphs = src / "charts"
    graphs.mkdir(exist_ok=True)
    aggregate = []
    display = []
    for key, data in groups.items():
        require(set(data) == set(LABELS), key)
        display_rows = []
        for strategy, tasks in data.items():
            times = sorted(task["total_latency_ms"] for task in tasks)
            values = {"dataset": key[0], "load": key[1], "network": key[2], "strategy": strategy,
                      "count": len(tasks), "avg_latency_ms": mean(times),
                      "p95_latency_ms": times[ceil(.95*len(tasks))-1],
                      "deadline_met_rate": mean(t["deadline_met"] for t in tasks)}
            values.update({f: mean(t[f] for t in tasks) for f in PHASES})
            values.update({f"{n}_ratio": mean(t["selected_node"] == n for t in tasks) for n in NODES})
            aggregate.append(values)
            display_rows.append(values)
        image = figure(graphs, key, display_rows, stage)
        display.extend(["### " + " / ".join(key), "", f"[四面板圖](charts/{image})", "",
                        *table(("策略", "平均 ms", "P95 ms", "Deadline", "決策 ms", "決策排隊 ms", "網路 ms",
                                "CPU 排隊 ms", "運算 ms", "Local / Edge / Cloud"),
                               ([LABELS[r["strategy"]], f"{r['avg_latency_ms']:.2f}", f"{r['p95_latency_ms']:.2f}",
                                 f"{r['deadline_met_rate']:.0%}", *(f"{r[f]:.3f}" for f in PHASES),
                                 " / ".join(f"{r[f'{n}_ratio']:.0%}" for n in NODES)] for r in display_rows)), ""])
    with (src / "stratified.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(aggregate[0]))
        writer.writeheader()
        writer.writerows(aggregate)
    (src / "stratified.json").write_text(json.dumps(aggregate, indent=2), encoding="utf-8")
    (src / "STRATIFIED.md").write_text(f"# {stage.title()} — 分層結果\n\n" + "\n".join(display), encoding="utf-8")
    result = {"stage": stage, "strategy_runs": len(rows), "tasks": total, "strata": len(groups),
              "max_latency_decomposition_error_ms": max_error, "max_fcfs_reference_error_ms": max_reference_error,
              "matched_workloads": len(workloads),
              "sample_sources": {f"{k[0]}/{k[1]}": list(next(iter(v))) for k, v in samples.items()},
              "charts": len(groups)}
    (src / "independent-validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "sample_sources"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("pilot", "formal"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run(args.output, args.stage)

