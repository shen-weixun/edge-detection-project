"""Check frozen artifacts, split membership, training ledger and policy audit."""
import argparse
from collections import Counter
import csv
from hashlib import sha256
import json
from math import isclose, isfinite
from pathlib import Path
from statistics import mean

import numpy as np


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    return sha256(path.read_bytes()).hexdigest()


def require(test, description):
    if not test:
        raise ValueError(description)


def split_evidence(out, profiles):
    study = read(out / "study.json")
    plan_path = profiles / "formal-evaluation/plan.json"
    require(sha(plan_path) == study["split_sha256"], "split plan checksum")
    plan = read(plan_path)["selected"]
    for field in ("source_path", "image_sha256", "group"):
        roles = {}
        for row in plan:
            value = row[field].casefold().replace("\\", "/")
            require(roles.setdefault(value, row["role"]) == row["role"], f"split overlap: {field}/{value}")
    sources = {(dataset, role): {r["source_path"] for r in plan if (r["dataset"], r["role"]) == (dataset, role)}
               for dataset in ("lfw", "wider_train") for role in ("training", "validation", "testing")}
    for key, spec in study["profiles"].items():
        require(sha(profiles / f"{spec['id']}.csv") == spec["csv_sha256"], "profile checksum " + key)
    return sources, study


def check_training(out, sources, study):
    selected = read(out / "selected-checkpoints.json")
    initial_audit = out / "clean-validation/selection.json"
    corrected = read(initial_audit)["models"] if initial_audit.exists() else None
    if corrected is None:
        require(study.get("validation_intervals", "").startswith("training profile mean"), "selection schedule")
    evidence = {}
    for path in sorted((out / "training").glob("*/*/transitions.jsonl")):
        parent = path.parent
        candidate = read(parent / "checkpoint.json")
        algorithm, seed = parent.parent.name, int(parent.name)
        case = f"{algorithm}/{seed}"
        require(sha(out / candidate["path"]) == candidate["sha256"], case)
        episodes = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        require(len(episodes) == 192 and len(Counter(e["scene"] for e in episodes)) == 24, case)
        all_losses = []
        tasks = 0
        term_rewards = []
        for index, episode in enumerate(episodes):
            steps = episode["transitions"]
            dataset = episode["scene"].split("-")[0]
            require(episode["episode"] == index and len(steps) == len(episode["sources"]) == 20
                    and set(episode["sources"]) <= sources[dataset, "training"], case)
            already_dispatched = set()
            terminals = set()
            last_time = 0
            for i, step in enumerate(steps):
                task_id = step["task_id"]
                require(step["done"] == (i == len(steps)-1)
                        and step["next_task_id"] == (None if step["done"] else steps[i+1]["task_id"])
                        and task_id not in already_dispatched and step["time_ms"] >= last_time, case)
                last_time = step["time_ms"]
                already_dispatched.add(task_id)
                for terminal in step["terminal_rewards"]:
                    tid = terminal["task_id"]
                    require(tid in already_dispatched and tid not in terminals
                            and isfinite(terminal["reward"]) and not terminal["dropped"], case)
                    terminals.add(tid)
                    term_rewards.append(terminal["reward"])
                require(isclose(step["reward"], sum(t["reward"] for t in step["terminal_rewards"]),
                                rel_tol=0, abs_tol=1e-9), case)
                if step["loss"] is not None:
                    require(isfinite(step["loss"]) and step["loss"] >= 0, case)
                    all_losses.append(step["loss"])
            require(terminals == already_dispatched and len(terminals) == 20, case)
            require(isclose(episode["episode_reward"], sum(s["reward"] for s in steps), abs_tol=1e-9), case)
            tasks += len(steps)
        require(tasks == candidate["steps"] == 3840 and len(all_losses) == candidate["updates"] == 3777, case)
        validation_path = out / "clean-validation" / algorithm / str(seed) if corrected else parent
        validation = read(validation_path / "validation.json")
        require(len(validation) == 48 and {v["seed"] for v in validation} == set(study["validation_seeds"]), case)
        for row in validation:
            require(set(row["sources"]) <= sources[row["scene"].split("-")[0], "validation"], case)
        if corrected:
            record = corrected[algorithm]
            require(record["same_weights"] and record["selected"]["sha256"] == selected[algorithm]["sha256"], case)
        else:
            require(isclose(candidate["validation_mean_reward"], mean(row["mean_reward"] for row in validation)),
                    case)
        evidence[case] = {"episodes": len(episodes), "tasks": tasks, "updates": len(all_losses),
                          "loss_mean": mean(all_losses), "loss_max": max(all_losses),
                          "terminal_reward_mean": mean(term_rewards), "weight_sha256": candidate["sha256"]}
    require(len(evidence) == 6, "candidate count")
    if corrected is None:
        for algorithm, checkpoint in selected.items():
            candidates = [read(path) for path in (out / "training" / algorithm).glob("*/checkpoint.json")]
            winner = max(candidates, key=lambda c: (c["validation_mean_reward"], -c["seed"]))
            require(winner["sha256"] == checkpoint["sha256"], "clean selection winner")
    return evidence


def check_evaluation(out, profiles, sources, stage):
    selected = read(out / "selected-checkpoints.json")
    feat = read(out / "DQN_DDQN_GOLDEN_FIXTURES.json")["features"]
    scales = np.array([feature["scale"] for feature in feat])
    mask = np.array([feature["binary"] for feature in feat])
    weights = {}
    for name, model in selected.items():
        with np.load(out / model["path"], allow_pickle=False) as archive:
            weights[name] = [archive[f"w{i}"] for i in range(6)]
    archive = profiles / "ai-comparison"
    prior_audit = {r["audit_id"]: r for r in map(json.loads, (archive / "raw/model-audit.jsonl").read_text(encoding="utf-8").splitlines())}
    if stage == "pilot":
        audit = prior_audit
    else:
        records = read(out / "formal/laya-audit.json")
        audit = {r["audit_id"]: r for r in records}
        require(len(records) == len(audit) == 480 and not set(audit) & set(prior_audit), "live audit identity")
    subsets = read(archive / "task_subset_manifest.json")
    audit_seen = set()
    counters = Counter()
    usage = Counter()
    with (out / stage / "comparison.csv").open(encoding="utf-8-sig", newline="") as file:
        for line in csv.DictReader(file):
            dataset, scene, strategy = line["dataset"], line["scene_id"], line["strategy"]
            raw = read(out / stage / "raw" / scene / f"{strategy}.json")
            paths = {t["source_path"] for t in raw["workload"]}
            require(paths <= sources[dataset, "testing"], "task test isolation")
            pilot_paths = {item["source_path"] for item in subsets[dataset]["images"]}
            require(paths == pilot_paths if stage == "pilot" else not paths & pilot_paths, "pilot test isolation")
            rows = raw["result"]["tasks"]
            if strategy in weights:
                require(raw["checkpoint"]["sha256"] == selected[strategy]["sha256"], "evaluation checkpoint")
                decisions = raw["agent_decisions"]
                require(len(decisions) == len(rows), "decision count")
                matrix = np.array([d["raw_features"] for d in decisions])
                normal = np.where(mask, matrix, np.log1p(matrix/scales))
                require(np.allclose(normal, [d["normalized_features"] for d in decisions],
                                    rtol=1e-12, atol=1e-12), "recorded normalization")
                q = normal
                for i in range(0, 6, 2):
                    q = q @ weights[strategy][i] + weights[strategy][i+1]
                    if i < 4:
                        q = np.maximum(0, q)
                require(np.isfinite(q).all() and np.allclose(q, [d["q_values"] for d in decisions],
                        rtol=1e-10, atol=1e-10), "recorded Q")
                actions = np.argmax(np.where(matrix[:, mask] == 1, q, -np.inf), axis=1)
                for i, (row, decision, action) in enumerate(zip(rows, decisions, actions)):
                    features = row["decision_input"]
                    require(np.array_equal(matrix[i, :7], [features[f["name"]] for f in feat[:7]]), "model task features")
                    require(row["task_id"] == decision["task_id"] and decision["action"] == action
                            and row["selected_node"] == decision["node"] == ("local", "edge", "cloud")[action], "Q dispatch")
                counters[strategy] += len(rows)
            if strategy in ("laya", "laya_v2"):
                if stage == "pilot":
                    source = archive / "raw/runs" / scene / f"{strategy}.json"
                    require(sha(source) == raw["archive_sha256"], "archived strategy checksum")
                    require(raw["decision_provenance"] == "archived_live_full_run_no_replay", "archived provenance")
                else:
                    require(raw["decision_provenance"] == "live_this_run", "live provenance")
                for row in rows:
                    key = row["decision_audit_id"]
                    record = audit[key]
                    usage[f"{strategy}_truncated"] += bool(record["raw_output"].get("usage", {}).get("truncated"))
                    require(key not in audit_seen and not record["fallback_used"]
                            and record["input_state"]["task"] == row["decision_input"]
                            and record["raw_output"]["answers"]["offload_target"]["choice"]
                            == record["final_choice"] == row["selected_node"], "Laya dispatch")
                    require(0 < record["elapsed_ms"] <= row["decision_wall_ms"], "wall-time measurement")
                    audit_seen.add(key)
                counters[strategy] += len(rows)
    require(len(audit_seen) == 480 and set(counters.values()) == {240}, "AI task count")
    return {"decision_counts": dict(counters), "laya_distinct_audits": len(audit_seen),
            "fallback_count": 0, "usage": dict(usage)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("pilot", "formal"))
    parser.add_argument("out", type=Path)
    parser.add_argument("profiles", type=Path)
    args = parser.parse_args()
    sources, study = split_evidence(args.out, args.profiles)
    evidence = {"training": check_training(args.out, sources, study),
                "evaluation": check_evaluation(args.out, args.profiles, sources, args.stage)}
    (args.out / args.stage / "policy-evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence["evaluation"]))

