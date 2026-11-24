"""Build a sealed experiment delivery without altering either historical run."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "profiles"
STUDY = PROFILES / "agents49"
REPORTS = (
    "DQN_DDQN_49D_AUDIT.md", "DQN_DDQN_SIMPY_ADAPTER.md", "DQN_DDQN_TRAINING_REPORT.md",
    "DQN_DDQN_GOLDEN_FIXTURES.json", "AI_10_STRATEGY_COMPARISON.md", "CODEX_PROGRESS.md",
)


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def copy(src, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def package(out, original):
    archive = out.with_suffix(".zip")
    if out.exists() or archive.exists():
        raise ValueError("Existing delivery preserved; choose a new output path")
    for stage, expected in (("pilot", 240), ("formal", 480)):
        folder = STUDY / stage
        if (read(folder / "complete.json")["status"] != "PASS"
                or read(folder / "independent-validation.json")["strategy_runs"] != expected
                or read(folder / "policy-evidence.json")["evaluation"]["laya_distinct_audits"] != 480):
            raise ValueError("Cannot publish incomplete experiment")
    if digest(original) != read(STUDY / "prototype-audit.json")["zip_sha256"]:
        raise ValueError("Original ZIP changed")
    shutil.copytree(STUDY, out)
    for name in REPORTS:
        copy(ROOT / name, out / name)
    copy(original, out / "member-original/DQN_DDQN.zip")
    work = ROOT / "work/agents49"
    for path in work.glob("*.log"):
        copy(path, out / "evidence" / path.name)
    shutil.copytree(work / "prototype-reproduction", out / "evidence/prototype-reproduction")
    frozen = out / "frozen-profiles"
    settings = read(STUDY / "study.json")
    for spec in settings["profiles"].values():
        for suffix in (".csv", ".json"):
            name = spec["id"] + suffix
            copy(PROFILES / name, frozen / name)
    for path in ("formal-evaluation/plan.json", "formal-evaluation/profile-ids.json",
                 "formal-evaluation/evaluation/fit-complete.json",
                 "ai-comparison/scenario_manifest.json", "ai-comparison/task_subset_manifest.json",
                 "ai-comparison/raw/model-audit.jsonl"):
        copy(PROFILES / path, frozen / path)
    model = "estimators/" + settings["estimator_id"] + ".json"
    copy(PROFILES / model, frozen / model)
    for scene in read(frozen / "ai-comparison/scenario_manifest.json")["scenarios"]:
        for strategy in ("local_only", "laya", "laya_v2"):
            path = f"ai-comparison/raw/runs/{scene['id']}/{strategy}.json"
            copy(PROFILES / path, frozen / path)
    source_files = subprocess.check_output(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                                           cwd=ROOT).decode("utf-8").split("\0")
    with zipfile.ZipFile(out / "source-snapshot.zip", "w", zipfile.ZIP_DEFLATED) as bundle:
        for name in source_files:
            if name and (ROOT / name).is_file():
                bundle.write(ROOT / name, name)
    (out / "README.md").write_text(
        "# SimPy 49D 交付\n\n"
        "先讀 [十策略比較](AI_10_STRATEGY_COMPARISON.md)、[訓練報告](DQN_DDQN_TRAINING_REPORT.md) 與 "
        "[Golden fixtures](DQN_DDQN_GOLDEN_FIXTURES.json)。\n\n"
        "- [Pilot 分層](pilot/STRATIFIED.md) ／ [正式分層](formal/STRATIFIED.md) 連到 48 張圖；各有逐種子 CSV 與原始 JSON。\n"
        "- frozen-profiles 包含重現需要的量測 CSV、資料分割、估計器及 Pilot 的既有完整 Laya 執行。"
        "不包含照片、資料庫或 InsightFace/Laya 大模型。\n"
        "- evidence 是執行日誌、校驗及實際執行版 runner；source-snapshot.zip 含現行修正程式。\n"
        "- 正式 Laya 稽核是本次真實呼叫；離線驗證不會觸發模型。\n",
        encoding="utf-8",
    )
    checks = {p.relative_to(out).as_posix(): digest(p) for p in sorted(out.rglob("*")) if p.is_file()}
    (out / "SHA256SUMS.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(out.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(out).as_posix())
    with zipfile.ZipFile(archive) as bundle:
        require = set(bundle.namelist()) == {*checks, "SHA256SUMS.json"}
        if not require or any(sha256(bundle.read(name)).hexdigest() != sha for name, sha in checks.items()):
            raise ValueError("Delivery checksum verification failed")
    print(json.dumps({"output": str(out), "zip": str(archive), "verified_files": len(checks),
                      "zip_bytes": archive.stat().st_size}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("out", type=Path)
    parser.add_argument("original", type=Path)
    args = parser.parse_args()
    package(args.out.resolve(), args.original.resolve())

