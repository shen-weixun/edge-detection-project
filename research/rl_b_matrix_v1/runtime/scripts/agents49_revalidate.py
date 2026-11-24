"""Recheck candidate ranking with arrival intervals derived only from training."""
import argparse
from pathlib import Path
from statistics import mean

from agents49_experiment import (
    AGENTS, Agent49Policy, Study, TRAIN_SEEDS, VALIDATION_SEEDS, config,
    load_agent, read, run_policy, write,
)


def training_interval(study, scene):
    rows = study.data[scene["dataset"], "training"][1]
    return mean(row["workload_ms"] for row in rows) / (3 * scene["reference_offered_cpu_load"])


def validate_candidate(study, agent):
    rows = []
    for scene in study.pilot["scenarios"]:
        interval = training_interval(study, scene)
        for seed in VALIDATION_SEEDS:
            tasks = study.tasks(scene["dataset"], "validation", 10, interval, seed)
            result = run_policy(tasks, Agent49Policy(agent), include_decision_overhead=False, **config(scene))
            reward = mean(-task["total_latency_ms"]/1000 - (not task["deadline_met"]) for task in result["tasks"])
            rows.append({"scene": scene["id"], "seed": seed, "interval_ms": interval, "mean_reward": reward,
                         "sources": [task.source_path for task in tasks], "summary": result["summary"]})
    return rows


def revalidate(study, output):
    selected = read(study.output / "selected-checkpoints.json")
    corrected = {}
    for algorithm in AGENTS:
        candidates = []
        for seed in TRAIN_SEEDS:
            folder = study.output / "training" / algorithm / str(seed)
            candidate = read(folder / "checkpoint.json")
            agent = study.load_model(algorithm, study.output / candidate["path"], candidate["sha256"])
            validation = validate_candidate(study, agent)
            write(output / algorithm / str(seed) / "validation.json", validation)
            candidates.append(dict(candidate, validation_mean_reward=mean(r["mean_reward"] for r in validation)))
        winner = max(candidates, key=lambda item: (item["validation_mean_reward"], -item["seed"]))
        corrected[algorithm] = {"candidates": candidates, "selected": winner,
                                "previous_sha256": selected[algorithm]["sha256"],
                                "same_weights": winner["sha256"] == selected[algorithm]["sha256"]}
        print("CLEAN VALIDATION", algorithm, [(c["seed"], c["validation_mean_reward"]) for c in candidates],
              "selected", winner["seed"], flush=True)
    write(output / "selection.json", {"validation_intervals": "mean training work / (reference Edge speed 3 * offered rho)",
                                      "seeds": VALIDATION_SEEDS, "models": corrected})
    if not all(record["same_weights"] for record in corrected.values()):
        raise RuntimeError("Candidate ranking changed: re-evaluate affected RL rows before publishing")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for name in ("study", "output", "member", "archive"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument('--input-contract-index', required=True, type=Path)
    args = parser.parse_args()
    revalidate(Study(args.study, args.member, args.archive, args.input_contract_index), args.output)

