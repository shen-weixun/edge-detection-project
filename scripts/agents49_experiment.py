"""Train and evaluate the member 49D architectures with the approved SimPy."""
import argparse
import csv
from dataclasses import asdict, replace
from hashlib import sha256
import json
import math
from pathlib import Path
import random
from statistics import mean
import sys

sys.path.insert(0, "/app")

import numpy as np

from app.offloading.agents49.adapter import AGENTS, Agent49Policy, load_agent
from app.offloading.agents49.input_contract import export_agent_contract, write_contract_index
from app.offloading.agents49.normalizer import FEATURE_NAMES, SCALES, BINARY_INDICES, CONTRACT_VERSION
from app.offloading.agents49.training import train_episode
from app.offloading.estimators import EstimatedPolicy, load_registered
from app.offloading.integration_contract import ACTIONS, run_policy, validate_manifest_split
from app.offloading.laya_client import LayaStrategy, LayaV2Strategy
from app.offloading.models import DecisionTask, NodeConfig, NodeState, SystemState, Task
from app.offloading.profiles import load, root
from app.offloading.rl import EpisodeSplit
from app.offloading.strategies import STRATEGY_FACTORIES
from app.offloading.workload import generate_tasks, source_identity

TRAIN_SEEDS = (42, 43, 44)
VALIDATION_SEEDS = (101, 103)
TEST_SEEDS = (23, 37)
EPISODES_PER_SCENE = 8
TRAIN_TASKS = 20
FORMAL_TASKS = 5
REWARD = "-total_latency_ms/1000 - (0 if deadline_met else 1)"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def workload_digest(rows):
    return sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


def config(scene):
    return {
        "nodes": {name: NodeConfig(**node) for name, node in scene["nodes"].items()},
        "information_mode": "realistic",
        "network_mode": scene["network_mode"],
        "shared_bandwidth_mbps": scene["shared_bandwidth_mbps"],
        "deadline_policy": "complete_all",
    }


def tasks_from(rows, count, interval, seed, deadline, estimator):
    tasks = generate_tasks(count, interval, seed, deadline, rows)
    return [replace(task, estimated_workload_ms=estimator.predict(task)) for task in tasks]


class Study:
    def __init__(self, output, member, archive, input_contract_index=None):
        self.output, self.member, self.archive = output, member, archive
        self.input_contract_index = input_contract_index
        self.new_contracts = {}
        self.pilot = read(archive / "scenario_manifest.json")
        self.subsets = read(archive / "task_subset_manifest.json")
        formal = root() / "formal-evaluation"
        ids = read(formal / "profile-ids.json")
        split = read(formal / "plan.json")["selected"]
        canonical = [dict(row, source_path=source_identity(row["source_path"])) for row in split]
        validate_manifest_split(canonical)
        self.data = {}
        for key, identifier in ids.items():
            dataset, role = key.split("/")
            meta, rows = load(identifier)
            expected = {row["source_path"] for row in canonical
                        if row["dataset"] == dataset and row["role"] == role}
            actual = {source_identity(row["source_path"]) for row in rows}
            if actual != expected or len(rows) != len(expected):
                raise ValueError(f"Profile/split mismatch: {key}")
            self.data[dataset, role] = (meta, rows)
        estimator_id = read(formal / "evaluation/fit-complete.json")["models"]["median"]
        self.estimator = load_registered(estimator_id)
        for scene in self.pilot["scenarios"]:
            if scene["estimator_id"] != estimator_id or scene["deadline_policy"] != "complete_all":
                raise ValueError("Pilot configuration mismatch")
        for dataset in self.subsets:
            training = self.tasks(dataset, "training", 40, 1000, 11)
            testing = self.tasks(dataset, "testing", 100, 1000, 11)
            EpisodeSplit(tuple(training), tuple(testing))
            test_meta, test_rows = self.data[dataset, "testing"]
            if self.subsets[dataset]["profile_csv_sha256"] != test_meta["csv_sha256"]:
                raise ValueError("Pilot test profile digest differs")
            self.estimator.validate_test(test_rows)
        provenance = {
            "training_seeds": TRAIN_SEEDS, "validation_seeds": VALIDATION_SEEDS,
            "evaluation_seeds": TEST_SEEDS, "episodes_per_scene": EPISODES_PER_SCENE,
            "training_tasks_per_episode": TRAIN_TASKS, "formal_tasks_per_scene_seed": FORMAL_TASKS,
            "normalizer": CONTRACT_VERSION, "feature_names": FEATURE_NAMES,
            "action_map": ACTIONS, "reward": REWARD, "gamma_per_decision": .99,
            "validation_intervals": "training profile mean / (reference Edge speed 3 * offered rho)",
            "estimator_id": estimator_id, "split_sha256": digest(formal / "plan.json"),
            "pilot_manifest_sha256": digest(archive / "scenario_manifest.json"),
            "profiles": {"/".join(k): {"id": v[0]["id"], "csv_sha256": v[0]["csv_sha256"],
                                      "count": len(v[1])} for k, v in self.data.items()},
            "implementation_sha256": {str(path.relative_to("/app")): digest(path)
                                      for path in [Path(__file__), *Path("/app/app/offloading/agents49").glob("*.py"),
                                                   Path("/app/app/offloading/rl.py"), Path("/app/app/offloading/simulator.py")]},
            "numpy": np.__version__,
        }
        manifest = output / "study.json"
        if manifest.exists() and read(manifest) != json.loads(json.dumps(provenance)):
            raise ValueError("Study provenance changed. Use a new output directory.")
        write(manifest, provenance)

    def tasks(self, dataset, role, count, interval, seed):
        return tasks_from(self.data[dataset, role][1], count, interval, seed, 1000, self.estimator)

    def training_interval(self, scene):
        rows = self.data[scene["dataset"], "training"][1]
        return mean(row["workload_ms"] for row in rows) / (3 * scene["reference_offered_cpu_load"])

    def load_model(self, algorithm, checkpoint, sha):
        ref = self.new_contracts.get((algorithm, sha))
        return load_agent(algorithm, checkpoint, sha, contract_ref=ref,
                          contract_index=None if ref else self.input_contract_index)

    def train(self):
        selected_file = self.output / "selected-checkpoints.json"
        if selected_file.exists():
            return read(selected_file)
        selected = {}
        for algorithm, constructor in AGENTS.items():
            candidates = []
            for seed in TRAIN_SEEDS:
                rng = random.Random(seed)
                agent = constructor(seed=seed)
                folder = self.output / "training" / algorithm / str(seed)
                folder.mkdir(parents=True, exist_ok=True)
                scenes = self.pilot["scenarios"] * EPISODES_PER_SCENE
                rng.shuffle(scenes)
                completed_steps = 0
                total_steps = len(scenes) * TRAIN_TASKS
                rewards = []
                with (folder / "transitions.jsonl").open("w", encoding="utf-8") as log:
                    for episode, scene in enumerate(scenes):
                        dataset = scene["dataset"]
                        interval = self.training_interval(scene)
                        episode_seed = rng.randrange(2**32)
                        tasks = self.tasks(dataset, "training", TRAIN_TASKS, interval, episode_seed)
                        steps = train_episode(
                            agent, tasks, config=config(scene),
                            epsilon_for_step=lambda step: max(.05, 1 - .95 * (completed_steps + step) / (total_steps - 1)),
                        )
                        rewards.append(sum(step["reward"] for step in steps))
                        log.write(json.dumps({
                            "episode": episode, "scene": scene["id"], "sample_seed": episode_seed,
                            "interval_ms": interval, "sources": [task.source_path for task in tasks],
                            "transitions": steps, "episode_reward": rewards[-1],
                        }, allow_nan=False) + "\n")
                        completed_steps += len(steps)
                checkpoint = folder / f"{algorithm}_simpy49.npz"
                agent.save(checkpoint)
                sha = digest(checkpoint)
                self.new_contracts[algorithm, sha] = export_agent_contract(
                    agent, checkpoint, folder/'input-contracts', [Path(__file__)])
                frozen = self.load_model(algorithm, checkpoint, sha)
                validation = []
                for scene in self.pilot["scenarios"]:
                    interval = self.training_interval(scene)
                    for val_seed in VALIDATION_SEEDS:
                        tasks = self.tasks(scene["dataset"], "validation", 10, interval, val_seed)
                        result = run_policy(tasks, Agent49Policy(frozen), include_decision_overhead=False,
                                            **config(scene))
                        score = mean(-r["total_latency_ms"]/1000 - (not r["deadline_met"]) for r in result["tasks"])
                        validation.append({"scene": scene["id"], "seed": val_seed, "mean_reward": score,
                                           "interval_ms": interval, "sources": [t.source_path for t in tasks],
                                           "summary": result["summary"]})
                write(folder / "validation.json", validation)
                candidate = {"path": str(checkpoint.relative_to(self.output)), "sha256": sha, "seed": seed,
                             "updates": agent.updates, "steps": completed_steps,
                             "mean_training_episode_reward": mean(rewards),
                             "validation_mean_reward": mean(row["mean_reward"] for row in validation)}
                write(folder / "checkpoint.json", candidate)
                candidates.append(candidate)
                print("TRAIN", algorithm, seed, candidate["validation_mean_reward"], flush=True)
            winner = max(candidates, key=lambda item: (item["validation_mean_reward"], -item["seed"]))
            selected[algorithm] = dict(winner, selection="highest mean validation reward, ties by smaller seed")
        write_contract_index(self.output/'input-contract-index.json',self.new_contracts.values())
        write(selected_file, selected)
        return selected

    def golden(self, selected=None):
        feature_doc = read(self.member / "examples/feature_names.json")
        features = feature_doc["features"]
        if (tuple(f["name"] for f in features) != FEATURE_NAMES
                or feature_doc["contract_version"] != CONTRACT_VERSION
                or [f["scale"] for f in features] != SCALES.tolist()
                or tuple(i for i, f in enumerate(features) if f["binary"]) != BINARY_INDICES
                or feature_doc["action_map"] != {str(i): node for i, node in enumerate(ACTIONS)}):
            raise ValueError("Member manifest differs from runtime contract")
        signatures = dict(line.split(maxsplit=1)[::-1] for line in
                          (self.member / "SHA256_MANIFEST.txt").read_text().splitlines())
        examples = []
        # Distinct values per column detect order regressions. A second fixture masks the best action.
        for masked in (False, True):
            task = DecisionTask(7, .23, 641, 479, 123, 999, 321, 15)
            nodes = {
                node: NodeState(node, 1.5+i, 2+i, 233+i, 35+i, 71+i, 123+i, 343+i,
                                not masked or i == 1, 1, 4+i, 5+i, 6+i, 543+i, 137)
                for i, node in enumerate(ACTIONS)
            }
            state = SystemState(**nodes)
            fields = asdict(task)
            for name, values in asdict(state).items():
                fields.update({f"{name}.{key}": value for key, value in values.items()})
            raw = [float(fields[f["name"]]) for f in features]
            normalized = [value if f["binary"] else math.log1p(value/f["scale"])
                          for f, value in zip(features, raw)]
            outputs = {}
            for name in AGENTS:
                cases = [("prototype", self.member / "models" / f"{name}_49d.npz",
                          signatures[f"models/{name}_49d.npz"])]
                if selected:
                    cases.append(("simpy", self.output / selected[name]["path"], selected[name]["sha256"]))
                for version, checkpoint, sha in cases:
                    agent = self.load_model(name, checkpoint, sha)
                    with np.load(checkpoint, allow_pickle=False) as weights:
                        expected = normalized
                        for layer in range(3):
                            matrix, bias = weights[f"w{2*layer}"], weights[f"w{2*layer+1}"]
                            expected = [math.fsum(value * float(w) for value, w in zip(expected, column)) + float(b)
                                        for column, b in zip(matrix.T, bias)]
                            if layer < 2:
                                expected = [max(0, value) for value in expected]
                    allowed = [i for i, index in enumerate(BINARY_INDICES) if raw[index] == 1]
                    action = max(allowed, key=expected.__getitem__)
                    policy = Agent49Policy(agent)
                    if policy.select_node(task, state) != ACTIONS[action] or agent.act(raw, epsilon=0) != action:
                        raise ValueError("Golden action mismatch")
                    trace = policy.decisions[0]
                    np.testing.assert_array_equal(trace["raw_features"], raw)
                    np.testing.assert_allclose(trace["normalized_features"], normalized, atol=1e-12, rtol=1e-12)
                    np.testing.assert_allclose(trace["q_values"], expected, atol=1e-10, rtol=1e-10)
                    outputs[f"{name}_{version}"] = {"q_values": expected, "action": action, "node": ACTIONS[action],
                                                   "checkpoint_sha256": sha}
            examples.append({"task": asdict(task), "state": asdict(state), "raw_features": raw,
                             "normalized_features": normalized, "models": outputs})
        for name in AGENTS:
            versions = ("prototype", "simpy") if selected else ("prototype",)
            for version in versions:
                key = f"{name}_{version}"
                if np.allclose(examples[0]["models"][key]["q_values"], examples[1]["models"][key]["q_values"]):
                    raise ValueError(f"Q values invariant across fixtures: {key}")
        write(self.output / "DQN_DDQN_GOLDEN_FIXTURES.json",
              {"contract": CONTRACT_VERSION, "features": features, "fixtures": examples,
               "oracle": "Independent scalar log1p and dense layer dot products from frozen NPZ tensors"})
        print("GOLDEN PASS", "prototype and SimPy" if selected else "prototype", flush=True)

    def evaluate(self, mode, selected):
        models = {name: self.load_model(name, self.output / spec["path"], spec["sha256"])
                  for name, spec in selected.items()}
        audit_path = self.archive / "raw/model-audit.jsonl"
        archived = {row["audit_id"]: row for row in map(json.loads, audit_path.read_text(encoding="utf-8").splitlines())}
        if len(archived) != 482:
            raise ValueError("Pilot audit is incomplete")
        rows = []
        for old_scene in self.pilot["scenarios"]:
            seeds = (11,) if mode == "pilot" else TEST_SEEDS
            for seed in seeds:
                scene = dict(old_scene)
                if mode == "pilot":
                    old = read(self.archive / "raw/runs" / scene["id"] / "local_only.json")
                    tasks = [Task(**row) for row in old["workload"]]
                    sources = [item["source_path"] for item in self.subsets[scene["dataset"]]["images"]]
                    if [task.source_path for task in tasks] != sources:
                        raise ValueError("Pilot source order changed")
                    regenerated = self.tasks(scene["dataset"], "testing", 10, scene["interval_ms"], 11)
                    if tasks != regenerated:
                        raise ValueError("Pilot task inputs differ from frozen profiles")
                else:
                    scene.update(seed=seed, count=FORMAL_TASKS,
                                 id=f'{scene["dataset"]}-{scene["load"]}-{scene["network"]}-n{FORMAL_TASKS}-s{seed}')
                    excluded = {item["source_path"] for item in self.subsets[scene["dataset"]]["images"]}
                    pool = [row for row in self.data[scene["dataset"], "testing"][1] if row["source_path"] not in excluded]
                    tasks = tasks_from(pool, FORMAL_TASKS, scene["interval_ms"], seed, 1000, self.estimator)
                manifest = [asdict(task) for task in tasks]
                sha = workload_digest(manifest)
                for strategy in self.pilot["strategy_order"]:
                    path = self.output / mode / "raw" / scene["id"] / f"{strategy}.json"
                    laya = strategy in ("laya", "laya_v2")
                    if path.exists():
                        payload = read(path)
                        if (payload["workload_sha256"] != sha or payload["scene"] != scene
                                or payload.get("checkpoint") != selected.get(strategy)):
                            raise ValueError("Existing evaluation belongs to another experiment")
                    elif mode == "pilot" and laya:
                        src = self.archive / "raw/runs" / scene["id"] / f"{strategy}.json"
                        payload = read(src)
                        if payload["status"] != "PASS" or payload["scene"] != scene or payload["workload"] != manifest:
                            raise ValueError("Archived Laya run differs from common inputs")
                        payload.update(decision_provenance="archived_live_full_run_no_replay",
                                       archive_sha256=digest(src))
                    else:
                        if laya:
                            attempt = path.with_suffix(".started.json")
                            if attempt.exists():
                                raise RuntimeError(f"Interrupted live attempt retained: {attempt}")
                            write(attempt, {"scene": scene, "strategy": strategy, "workload_sha256": sha})
                        policy = (Agent49Policy(models[strategy]) if strategy in models else
                                  LayaStrategy() if strategy == "laya" else
                                  LayaV2Strategy() if strategy == "laya_v2" else STRATEGY_FACTORIES[strategy]())
                        try:
                            result = run_policy(tasks, EstimatedPolicy(policy, self.estimator),
                                                include_decision_overhead=True, **config(scene))
                        except Exception as error:
                            write(path.with_suffix(".failure.json"),
                                  {"scene": scene, "strategy": strategy, "error": repr(error)})
                            raise
                        payload = {"status": "PASS", "scene": scene, "strategy": strategy, "workload": manifest,
                                   "workload_sha256": sha, "result": result, "checkpoint": selected.get(strategy),
                                   "decision_provenance": "live_this_run" if laya else "local_wall_time_this_run"}
                        if strategy in models:
                            payload["agent_decisions"] = policy.decisions
                    if payload["workload_sha256"] != sha or payload["workload"] != manifest:
                        raise ValueError("Policy workload mismatch")
                    result = payload["result"]
                    raw_rows = result["tasks"]
                    if len(raw_rows) != len(tasks) or [r["task"] for r in raw_rows] != manifest:
                        raise ValueError("Unexpected task stream")
                    decisions = {entry["task_id"]: entry for entry in payload.get("agent_decisions", [])}
                    for row in raw_rows:
                        total = sum(row[key] for key in ("decision_ms", "decision_queue_ms", "queue_ms", "network_ms", "compute_ms"))
                        if not (row["completed"] and not row["dropped"] and row["decision_ms"] > 0
                                and math.isclose(total, row["total_latency_ms"], abs_tol=1e-6, rel_tol=0)):
                            raise ValueError("Incomplete result or invalid latency decomposition")
                        if strategy in models and decisions[row["task_id"]]["node"] != row["selected_node"]:
                            raise ValueError("Q action does not match task dispatch")
                        if mode == "pilot" and laya:
                            audit = archived[row["decision_audit_id"]]
                            if (audit["fallback_used"] or audit["final_choice"] != row["selected_node"]
                                    or audit["input_state"]["task"] != row["decision_input"]):
                                raise ValueError("Archived Laya audit mismatch")
                    if not path.exists():
                        write(path, payload)
                    summary = result["summary"]
                    rows.append({
                        "dataset": scene["dataset"], "load": scene["load"], "network": scene["network"],
                        "scene_id": scene["id"], "seed": seed, "count": len(tasks), "strategy": strategy,
                        "workload_sha256": sha, "decision_provenance": payload["decision_provenance"],
                        "avg_latency_ms": summary["avg_latency_ms"], "p95_latency_ms": summary["p95_latency_ms"],
                        "deadline_met_rate": summary["deadline_met_rate"], **summary["components_ms"],
                        **{f"{node}_ratio": value for node, value in summary["placement_ratio"].items()},
                    })
                print(mode.upper(), scene["id"], "10/10", flush=True)
        if mode == "formal":
            self.audit_live(rows)
        with (self.output / mode / "comparison.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        write(self.output / mode / "complete.json", {
            "status": "PASS", "strategy_runs": len(rows), "tasks": sum(row["count"] for row in rows),
            "laya_live_calls": sum(row["count"] for row in rows if row["decision_provenance"] == "live_this_run"),
        })

    def audit_live(self, rows):
        audit_path = root() / "laya_audit/decisions.jsonl"
        audit = {row["audit_id"]: row for row in map(json.loads, audit_path.read_text(encoding="utf-8").splitlines())}
        selected = {}
        for case in rows:
            if case["decision_provenance"] != "live_this_run":
                continue
            path = self.output / "formal/raw" / case["scene_id"] / f'{case["strategy"]}.json'
            for row in read(path)["result"]["tasks"]:
                key = row["decision_audit_id"]
                record = audit[key]
                if (key in selected or record["fallback_used"] or record["final_choice"] != row["selected_node"]
                        or record["raw_output"]["answers"]["offload_target"]["choice"] != row["selected_node"]
                        or record["input_state"]["task"] != row["decision_input"]):
                    raise ValueError("Live Laya audit mismatch")
                selected[key] = record
        write(self.output / "formal/laya-audit.json", list(selected.values()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("prototype", "train", "pilot", "formal"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--member", required=True, type=Path)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument('--input-contract-index', required=True, type=Path)
    args = parser.parse_args()
    study = Study(args.output, args.member, args.archive, args.input_contract_index)
    if args.stage == "prototype":
        study.golden()
    elif args.stage == "train":
        study.golden(study.train())
    else:
        selected = read(args.output / "selected-checkpoints.json")
        if args.stage == "formal" and read(args.output / "pilot/complete.json")["status"] != "PASS":
            raise ValueError("Pilot gate is not satisfied")
        study.evaluate(args.stage, selected)

