"""Seal the bounded long-horizon method study without touching past results."""
from pathlib import Path
from hashlib import sha256
import argparse
import json
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"profiles/rl-long-horizon-v1"
REPORTS=("RL_RNG_ISOLATION_TEST.md","RL_LONG_HORIZON_OBJECTIVE.md","RL_REWARD_TIMING_TESTS.md",
         "RL_DQN_DDQN_COMPARISON.md","RL_TRAINING_DIAGNOSTICS.md","CODEX_PROGRESS.md")


def sha(path):
    return sha256(path.read_bytes()).hexdigest()


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("out",type=Path)
    a=p.parse_args()
    out=a.out.resolve()
    archive=out.with_suffix(".zip")
    if out.exists() or archive.exists():
        raise ValueError("Choose a new delivery")
    assert json.loads((DATA/"independent-audit.json").read_text())["status"]=="PASS"
    shutil.copytree(DATA,out)
    shutil.copytree(ROOT/"profiles/rl-long-horizon-evidence",out/"evidence")
    shutil.copytree(ROOT/"work/rl-long-horizon",out/"logs")
    for name in REPORTS:
        shutil.copy2(ROOT/name,out/name)
    source=out/"source"
    for file in (ROOT/"backend/app/offloading/agents49").glob("*.py"):
        dest=source/"backend/app/offloading/agents49"/file.name
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(file,dest)
    for name in ("scripts/rl_long_horizon_study.py","scripts/rl_long_horizon_evidence.py",
                 "scripts/rl_long_horizon_report.py","scripts/rl_long_horizon_validation_audit.py","scripts/rl_method_study.py","scripts/agents49_experiment.py",
                 "backend/tests/test_integral_rl.py","backend/tests/test_task_credit.py",
                 "backend/app/offloading/simulator.py","backend/app/offloading/rl.py",
                 "backend/app/offloading/models.py","backend/app/offloading/integration_contract.py"):
        dest=source/name
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/name,dest)
    shutil.copy2(Path(__file__),source/"scripts"/Path(__file__).name)
    previous=ROOT/"profiles/rl-method-v1"
    shutil.copy2(previous/"feature-design.json",out/"training-selected-feature-design.json")
    specs=json.loads((ROOT/"profiles/formal-evaluation/profile-ids.json").read_text())
    for key,identifier in specs.items():
        if not key.endswith(("/training","/validation")):
            continue
        for ext in (".csv",".json"):
            dest=out/"profiles"/(identifier+ext)
            dest.parent.mkdir(exist_ok=True)
            shutil.copy2(ROOT/"profiles"/(identifier+ext),dest)
    plan=ROOT/"profiles/formal-evaluation/plan.json"
    shutil.copy2(plan,out/"profiles/split-plan.json")
    estimator=json.loads((previous/"feature-design.json").read_text())["estimator"]
    shutil.copy2(ROOT/"profiles/estimators"/(estimator+".json"),out/"profiles"/(estimator+".json"))
    files={p.relative_to(out).as_posix():sha(p) for p in sorted(out.rglob("*")) if p.is_file()}
    (out/"SHA256SUMS.json").write_text(json.dumps(files,ensure_ascii=False,indent=2),encoding="utf-8")
    with zipfile.ZipFile(archive,"x",zipfile.ZIP_DEFLATED) as z:
        for name in (*files,"SHA256SUMS.json"):
            z.write(out/name,name)
    with zipfile.ZipFile(archive) as z:
        assert set(z.namelist())=={*files,"SHA256SUMS.json"}
        for name,expected in files.items():
            assert sha256(z.read(name)).hexdigest()==expected,name
    print(len(files),"files rehashed;",archive.stat().st_size,"ZIP bytes")

