"""Bind historical and corrected artifacts to the exact sources in the sealed ZIP."""
import argparse
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import zipfile

from agents49_evidence import read, require, sha, split_evidence, check_training, check_evaluation


def digest(data):
    return sha256(data).hexdigest()


def finalize(repo, archive, out):
    import json

    profiles = repo / "profiles"
    old = profiles / "agents49"
    sources, study = split_evidence(old, profiles)
    corrected = read(old / "clean-validation/selection.json")
    proof = read(old / "evidence/corrected-reproduction.json")
    def put(name, data):
        (out / name).write_text(json.dumps(data, indent=2, allow_nan=False), encoding="utf-8")

    with zipfile.ZipFile(archive) as bundle:
        checks = json.loads(bundle.read("SHA256SUMS.json"))
        require(set(bundle.namelist()) == {*checks, "SHA256SUMS.json"}, "ZIP membership")
        for path, expected in checks.items():
            require(digest(bundle.read(path)) == expected, path)
        with zipfile.ZipFile(BytesIO(bundle.read("source-snapshot.zip"))) as snapshot:
            runner = "scripts/agents49_experiment.py"
            validator = "scripts/agents49_revalidate.py"
            executed = "evidence/agents49_experiment_as_executed.py"
            require(checks[executed] == study["implementation_sha256"][runner], "executed runner")
            require(digest(snapshot.read(runner)) == proof["corrected_runner_sha256"] == sha(repo / runner),
                    "corrected runner")
            require(digest(snapshot.read(validator)) == sha(repo / validator), "corrected validator")
            core = {}
            for name in ("simulator", "rl", "models", "integration_contract", "strategies", "latency_v2"):
                path = f"backend/app/offloading/{name}.py"
                core[path] = sha(repo / path)
                require(core[path] == digest(snapshot.read(path)), path)
            for path, expected in study["implementation_sha256"].items():
                if path != runner:
                    require(expected == sha(repo / "backend" / path) == digest(snapshot.read("backend/" + path)), path)
        historical = read(old / "selected-checkpoints.json")
        selected = {name: entry["selected"] for name, entry in corrected["models"].items()}
        for name, model in selected.items():
            require(model["sha256"] == historical[name]["sha256"] == sha(old / model["path"]), name)
        bound = ["study.json", "selected-checkpoints.json", executed, "clean-validation/selection.json",
                 "evidence/corrected-reproduction.json", "DQN_DDQN_GOLDEN_FIXTURES.json", "formal/laya-audit.json"]
        bound.extend(path for path in checks if path.startswith(("clean-validation/", "training/", "pilot/raw/", "formal/raw/")))
        for path in set(bound):
            require(sha(old / path) == checks[path], path)
        put("study.json", {
            "schema": "agents49-version-ledger-v2",
            "source_archive_sha256": sha(archive),
            "verified_archive_members": len(checks),
            "historical_run": {"study_sha256": checks["study.json"], "runner_artifact": executed,
                               "runner_sha256": checks[executed], "selection_sha256": checks["selected-checkpoints.json"],
                               "training_schedule": "training mean / (3 * rho)",
                               "historical_validation_schedule": "pilot held-out aggregate / (3 * rho)",
                               "checkpoints": historical},
            "corrected_validation": {
                "validator_path": validator, "validator_sha256": sha(repo / validator),
                "reproduction_runner_path": runner, "reproduction_runner_sha256": proof["corrected_runner_sha256"],
                "selection_sha256": checks["clean-validation/selection.json"],
                "schedule": corrected["validation_intervals"], "seeds": corrected["seeds"],
                "dataset_role": "validation", "tasks_per_scenario_seed": 10,
                "input_profile_specs": {k: v for k, v in study["profiles"].items() if k.endswith("/validation")},
                "schedule_profile_specs": {k: v for k, v in study["profiles"].items() if k.endswith("/training")},
                "runs": {name: {str(c["seed"]): {"checkpoint": c, "trace_sha256":
                         checks[f'clean-validation/{name}/{c["seed"]}/validation.json']}
                         for c in item["candidates"]} for name, item in corrected["models"].items()},
                "deadline_ms": 1000, "decision_overhead": False, "same_checkpoint_bytes": True,
                "scene_manifest_sha256": study["pilot_manifest_sha256"]},
            "profiles": study["profiles"], "split_sha256": study["split_sha256"],
            "estimator_id": study["estimator_id"], "protected_source_sha256": core,
        })
        put("selected-checkpoints.json", selected)

    training = check_training(old, sources, study)
    put("historical-evidence.json", {"training": training, **{
        stage: check_evaluation(old, profiles, sources, stage) for stage in ("pilot", "formal")}})
    print(f"PASS: {len(checks)} archived members, source versions, corrected selection and historical AI audit")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for field in ("repo", "archive", "out"):
        parser.add_argument(field, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    finalize(args.repo, args.archive, args.out)

