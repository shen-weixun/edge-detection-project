"""Check new training reproduction against sealed artifacts before evaluation."""
import argparse
from math import isclose
from pathlib import Path

from agents49_evidence import check_training, read, require, sha, split_evidence
from agents49_experiment import write

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for name in ("old", "out", "profiles"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    new = args.out / "reproduction"
    sources, study = split_evidence(new, args.profiles)
    proof = check_training(new, sources, study)
    manifest = read(args.out / "study.json")
    require(study["implementation_sha256"]["scripts/agents49_experiment.py"]
            == manifest["corrected_validation"]["reproduction_runner_sha256"], "reproduction runner")
    for name, runs in manifest["corrected_validation"]["runs"].items():
        for seed, record in runs.items():
            folder = Path("training") / name / seed
            entry = read(new / folder / "checkpoint.json")
            expected = record["checkpoint"]
            require(entry["sha256"] == expected["sha256"], "checkpoint SHA")
            require(isclose(entry["validation_mean_reward"], expected["validation_mean_reward"],
                            rel_tol=0, abs_tol=1e-12), "validation reward")
            previous = read(args.old / "clean-validation" / name / seed / "validation.json")
            current = read(new / folder / "validation.json")
            for case in previous + current:
                # Runtime wall time is measured but excluded from validation events.
                case["summary"].pop("avg_decision_wall_ms")
            require(previous == current, "exact validation inputs and simulated outcomes")
            require(sha(new / folder / "transitions.jsonl") == sha(args.old / folder / "transitions.jsonl"),
                    "transition SHA")
    require(read(new / "DQN_DDQN_GOLDEN_FIXTURES.json") == read(args.old / "DQN_DDQN_GOLDEN_FIXTURES.json"),
            "golden fixtures changed")
    write(args.out / "reproduction-check.json", {"status": "PASS", "checkpoint_checks": proof,
          "golden_equal": True, "training_log_sha_equal": True, "validation_cases_equal": True})
    print("PASS: six weights, six transition logs, 288 validation runs and golden outputs reproduced.")

