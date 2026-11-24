"""Seal final evidence and keep the previous delivery intact."""
import argparse
import json
from pathlib import Path
import shutil
import zipfile

from agents49_evidence import read, require, sha

ROOT = Path(__file__).resolve().parents[1]
NEW = ROOT / "profiles/agents49-final"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("out", type=Path)
    parser.add_argument("historical", type=Path, help="Unpacked previous delivery")
    args = parser.parse_args()
    out = args.out.resolve()
    archive = out.with_suffix(".zip")
    require(not out.exists() and not archive.exists(), "output already exists")
    for stage, count in (("expanded", 57600), ("laya-subset", 2400)):
        check = read(NEW / stage / "independent-validation.json")
        require(check["status"] == "PASS" and check["tasks"] == count, stage)
    require(read(NEW / "reproduction-check.json")["status"] == "PASS", "reproduction")
    shutil.copytree(NEW, out, ignore=shutil.ignore_patterns("*.tmp"))
    def copy(source, relative):
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    for path in (ROOT / "work/agents49-final").glob("*.log"):
        copy(path, "logs/" + path.name)
    for name in ("DQN_DDQN_FINAL_ACCEPTANCE.md", "DQN_DDQN_REPRODUCIBILITY.md", "AI_STRATIFIED_COMPARISON.md", "CODEX_PROGRESS.md"):
        copy(ROOT / name, name)
    historical = args.historical
    previous = read(historical / "SHA256SUMS.json")
    for name in ("study.json", "selected-checkpoints.json", "clean-validation/selection.json",
                 "evidence/agents49_experiment_as_executed.py", "DQN_DDQN_GOLDEN_FIXTURES.json",
                 "formal/laya-audit.json", "source-snapshot.zip"):
        require(sha(historical / name) == previous[name], name)
        copy(historical / name, "historical/" + name)
    for name in previous:
        if name.startswith("frozen-profiles/") or name == "member-original/DQN_DDQN.zip":
            require(sha(historical / name) == previous[name], name)
            copy(historical / name, name)
    copy(ROOT / "backend/tests/test_agents49.py", "source/backend/tests/test_agents49.py")
    for path in (ROOT / "scripts").glob("agents49*.py"):
        copy(path, "source/scripts/" + path.name)
    copy(Path(__file__), "source/scripts/" + Path(__file__).name)
    for path in (ROOT / "backend/app/offloading/agents49").glob("*.py"):
        copy(path, "source/backend/app/offloading/agents49/" + path.name)
    files = {p.relative_to(out).as_posix(): sha(p) for p in sorted(out.rglob("*")) if p.is_file()}
    (out / "SHA256SUMS.json").write_text(json.dumps(files, indent=2), encoding="utf-8")
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as bundle:
        for name in (*files, "SHA256SUMS.json"):
            bundle.write(out / name, name)
    with zipfile.ZipFile(archive) as bundle:
        from hashlib import sha256
        require(set(bundle.namelist()) == {*files, "SHA256SUMS.json"}, "ZIP membership")
        for name, expected in files.items():
            require(sha256(bundle.read(name)).hexdigest() == expected, name)
    print(f"{len(files)} SHA-256 entries; {archive.stat().st_size} ZIP bytes")

