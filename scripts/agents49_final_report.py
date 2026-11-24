"""Independently audit expanded results and publish matched stratum summaries."""
import argparse
from collections import Counter, defaultdict
import csv
from math import ceil, isclose
from pathlib import Path
from statistics import mean

from agents49_report import LABELS, NODES, PHASES, figure, table, reference, NodeConfig
from agents49_experiment import Task, read, write, digest, workload_digest, np
from agents49_expand import STRATEGIES, LAYA
from agents49_evidence import require, split_evidence


FIELDS = ("avg_latency_ms", "p95_latency_ms", "deadline_met_rate", "completion_rate",
          *PHASES, *(f"{node}_ratio" for node in NODES))


def summarize(rows):
    latencies = sorted(r["total_latency_ms"] for r in rows)
    return {"avg_latency_ms": mean(latencies), "p95_latency_ms": latencies[ceil(.95*len(rows))-1],
            "deadline_met_rate": mean(r["deadline_met"] for r in rows),
            "completion_rate": mean(r["completed"] for r in rows),
            **{key: mean(r[key] for r in rows) for key in PHASES},
            **{f"{n}_ratio": mean(r["selected_node"] == n for r in rows) for n in NODES}}


def csv_output(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def audit_model(raw, rows, weights, features):
    decisions = raw["agent_decisions"]
    require(len(decisions) == len(rows), "decision count")
    matrix = np.array([d["raw_features"] for d in decisions])
    scales = np.array([f["scale"] for f in features])
    mask = np.array([f["binary"] for f in features])
    normal = np.where(mask, matrix, np.log1p(matrix/scales))
    require(np.allclose(normal, [d["normalized_features"] for d in decisions], rtol=1e-12, atol=1e-12), "normalization")
    q = normal
    for i in range(0, 6, 2):
        q = q @ weights[i] + weights[i+1]
        if i < 4:
            q = np.maximum(q, 0)
    require(np.isfinite(q).all() and np.allclose(q, [d["q_values"] for d in decisions], rtol=1e-10, atol=1e-10), "Q values")
    actions = np.argmax(np.where(matrix[:, mask] == 1, q, -np.inf), axis=1)
    for i, (row, d, action) in enumerate(zip(rows, decisions, actions)):
        require(np.array_equal(matrix[i, :7], [row["decision_input"][f["name"]] for f in features[:7]]), "decision features")
        require(row["task_id"] == d["task_id"] and d["action"] == action
                and d["node"] == row["selected_node"] == NODES[action], "action")


def audit_events(rows, case):
    scene = case["scene"]
    nodes = {n: NodeConfig(**cfg) for n, cfg in scene["nodes"].items()}
    shifted = [Task(**dict(r["task"], arrival_ms=r["arrival_ms"]+r["decision_queue_ms"]+r["decision_ms"]))
               for r in rows]
    ref, calendars = reference(shifted, {r["task_id"]: r["selected_node"] for r in rows}, nodes,
                               scene["network_mode"], scene["shared_bandwidth_mbps"])
    max_error = 0
    decision = []
    for row, task in zip(rows, shifted):
        original = row["arrival_ms"]
        total = row["completed_at_ms"] - original
        require(row["completed"] and not row["dropped"] and row["decision_ms"] == row["decision_wall_ms"] > 0
                and row["deadline_met"] == (total <= row["task"]["deadline_ms"]), "completion and deadline")
        require(all(row[key] >= 0 for key in PHASES)
                and "workload_ms" not in row["decision_input"] and "face_count" not in row["decision_input"], "decision observation")
        errors = [abs(total-row["total_latency_ms"]), abs(total-sum(row[k] for k in PHASES))]
        errors += [abs(row[key]-ref[row["task_id"]][key]) for key in
                   ("network_ms", "queue_ms", "compute_ms", "cpu_started_at_ms", "cpu_completed_at_ms", "completed_at_ms")]
        max_error = max(max_error, *errors)
        require(max(errors) < 1e-6, (scene["id"], row["task_id"], errors))
        decision.append((task.arrival_ms-row["decision_ms"], task.arrival_ms))
    for calendar in [sorted(decision), *calendars.values()]:
        require(all(b[0] >= a[1]-1e-6 for a, b in zip(calendar, calendar[1:])), "resource overlap")
    return max_error


def run(stage, out, profiles):
    old = profiles / "agents49"
    sources, _ = split_evidence(old, profiles)
    design = read(out / "design.json")
    folder = out / stage
    gate = read(folder / "complete.json")
    require(gate["design_sha256"] == digest(out / "design.json"), "design digest")
    archive = {r["audit_id"]: r for r in read(old / "formal/laya-audit.json")}
    features = read(old / "DQN_DDQN_GOLDEN_FIXTURES.json")["features"]
    weights = {}
    for name, checkpoint in design["checkpoints"].items():
        path = old / checkpoint["path"]
        require(digest(path) == checkpoint["sha256"], "checkpoint SHA")
        with np.load(path, allow_pickle=False) as model:
            weights[name] = [model[f"w{i}"] for i in range(6)]
    strategies = STRATEGIES + (LAYA if stage == "laya-subset" else ())
    summaries = {(r["scene_id"], r["strategy"]): r for r in read(folder / "comparison.json")}
    groups = defaultdict(lambda: defaultdict(list))
    seed_deltas = []
    count = 0
    maximum = 0
    audited = set()
    for case in design[stage]:
        scene, tasks = case["scene"], case["workload"]
        key = (scene["dataset"], scene["load"], scene["network"])
        paths = {r["source_path"] for r in tasks}
        require(len(paths) == len(tasks) and paths <= sources[key[0], "testing"], "held-out split")
        if stage == "expanded":
            require(paths == sources[key[0], "testing"], "full test coverage")
        seed_stats = {}
        for name in strategies:
            raw = read(folder / "raw" / scene["id"] / f"{name}.json")
            rows = raw["result"]["tasks"]
            require(raw["scene"] == scene and raw["workload"] == tasks and [r["task"] for r in rows] == tasks
                    and raw["workload_sha256"] == workload_digest(tasks), "paired workload")
            maximum = max(maximum, audit_events(rows, case))
            if name in weights:
                require(raw["checkpoint"] == design["checkpoints"][name], "selected checkpoint")
                audit_model(raw, rows, weights[name], features)
            if name in LAYA:
                original = old / "formal/raw" / case["archived_run"] / f"{name}.json"
                require(digest(original) == raw["archived_sha256"] and read(original)["result"] == raw["result"],
                        "full archived result")
                for row in rows:
                    aid = row["decision_audit_id"]
                    audit = archive[aid]
                    require(aid not in audited and not audit["fallback_used"]
                            and audit["raw_output"]["answers"]["offload_target"]["choice"]
                            == audit["final_choice"] == row["selected_node"]
                            and audit["input_state"]["task"] == row["decision_input"]
                            and 0 < audit["elapsed_ms"] <= row["decision_wall_ms"], "real Laya audit")
                    audited.add(aid)
            groups[key][name].extend(rows)
            actual = summarize(rows)
            for field in FIELDS:
                require(isclose(actual[field], summaries[scene["id"], name][field], rel_tol=0,
                                abs_tol=5.1e-5 if field == "avg_latency_ms" else 1e-8), field)
            seed_stats[name] = actual
            count += len(rows)
        for candidate, reference_name in (("dqn", "latency_aware"), ("ddqn", "latency_aware"),
                                          ("dqn", "latency_aware_v2"), ("ddqn", "latency_aware_v2"), ("ddqn", "dqn")):
            seed_deltas.append({"dataset": key[0], "load": key[1], "network": key[2], "seed": scene["seed"],
                                "candidate": candidate, "reference": reference_name,
                                **{f"delta_{f}": seed_stats[candidate][f]-seed_stats[reference_name][f]
                                   for f in FIELDS}})
    require(len(groups) == 24 and count == gate["tasks"] and len(summaries) == gate["strategy_runs"]
            and len(audited) == (480 if stage == "laya-subset" else 0), "coverage")
    charts = folder / "charts"
    charts.mkdir(exist_ok=True)
    aggregate = []
    markdown = [f"# {stage}", ""]
    for key, policies in groups.items():
        rows = [{"dataset": key[0], "load": key[1], "network": key[2], "strategy": name,
                 "count": len(tasks), **summarize(tasks)} for name, tasks in policies.items()]
        aggregate.extend(rows)
        chart = figure(charts, key, rows, "100 images / 3 orderings" if stage == "expanded" else "Laya common subset")
        markdown.extend(["### " + " / ".join(key), "", f"[圖表](charts/{chart})", "",
            *table(("策略", "平均 ms", "P95 ms", "Deadline", "完成率", "決策 ms", "決策排隊 ms", "網路 ms",
                    "CPU 排隊 ms", "計算 ms", "Local / Edge / Cloud"),
                   ([LABELS[r["strategy"]], f"{r['avg_latency_ms']:.2f}", f"{r['p95_latency_ms']:.2f}",
                     f"{r['deadline_met_rate']:.1%}", f"{r['completion_rate']:.1%}",
                     *(f"{r[f]:.3f}" for f in PHASES), " / ".join(f"{r[f'{n}_ratio']:.1%}" for n in NODES)]
                    for r in rows)), ""])
    csv_output(folder / "stratified.csv", aggregate)
    csv_output(folder / "paired-seed-deltas.csv", seed_deltas)
    write(folder / "stratified.json", aggregate)
    (folder / "STRATIFIED.md").write_text("\n".join(markdown), encoding="utf-8")
    result = {"status": "PASS", "tasks": count, "strategy_runs": len(summaries), "strata": 24,
              "max_fcfs_and_conservation_error_ms": maximum, "archived_live_audits": len(audited)}
    write(folder / "independent-validation.json", result)
    print(result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("expanded", "laya-subset"))
    parser.add_argument("out", type=Path)
    parser.add_argument("profiles", type=Path)
    args = parser.parse_args()
    run(args.stage, args.out, args.profiles)

