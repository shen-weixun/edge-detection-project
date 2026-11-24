"""Compare the corrected runner with the independently revalidated training."""
import argparse
import json
from pathlib import Path
from math import isclose

from agents49_evidence import check_training, read, require, sha, split_evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for name in ("old", "new", "profiles"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    sources, study = split_evidence(args.new, args.profiles)
    verification = check_training(args.new, sources, study)
    selection = read(args.old / "clean-validation/selection.json")["models"]
    for algorithm, item in selection.items():
        for record in item["candidates"]:
            seed = record["seed"]
            folder = Path("training") / algorithm / str(seed)
            reproduced = read(args.new / folder / "checkpoint.json")
            require(reproduced["sha256"] == record["sha256"], f"{algorithm}/{seed} weights changed")
            require(isclose(reproduced["validation_mean_reward"], record["validation_mean_reward"],
                            rel_tol=0, abs_tol=1e-12), f"{algorithm}/{seed} validation changed")
            before = sha(args.old / folder / "transitions.jsonl")
            after = sha(args.new / folder / "transitions.jsonl")
            require(before == after, f"{algorithm}/{seed} transitions changed")
            verification[f"{algorithm}/{seed}"]["transition_log_sha256"] = after
        selected = read(args.new / "selected-checkpoints.json")[algorithm]
        require(selected["sha256"] == item["selected"]["sha256"], f"{algorithm} selected weights changed")
    output = {"status": "PASS", "checkpoints": verification,
              "corrected_runner_sha256": study["implementation_sha256"]["scripts/agents49_experiment.py"]}
    (args.old / "evidence/corrected-reproduction.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"PASS: {len(verification)} identical checkpoint and training transition SHA-256 pairs; clean scores reproduced")

