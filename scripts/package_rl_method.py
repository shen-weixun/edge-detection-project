"""Seal method diagnostics, source, training metadata and reports."""
from pathlib import Path
from hashlib import sha256
import argparse
import json
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[1]
REPORTS=("RL_REWARD_AUDIT.md","RL_STATE_ABLATION.md","RL_PAPER_COMPARISON.md","RL_TRAINING_REDESIGN.md","CODEX_PROGRESS.md")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("out",type=Path)
    args=p.parse_args()
    out=args.out.resolve()
    target=out.with_suffix(".zip")
    if out.exists() or target.exists():
        raise ValueError("Choose a new delivery path")
    data=ROOT/"profiles/rl-method-v1"
    assert json.loads((data/"complete.json").read_text())["new_test_runs"]==0
    shutil.copytree(data,out)
    for name in REPORTS:
        shutil.copy2(ROOT/name,out/name)
    shutil.copytree(ROOT/"work/rl-method",out/"logs")
    source=out/"source"
    for name in ("scripts/rl_method_study.py","scripts/rl_method_report.py","scripts/agents49_experiment.py",
                 "backend/app/offloading/agents49/task_credit.py","backend/tests/test_task_credit.py",
                 "backend/app/offloading/rl.py","backend/app/offloading/models.py",
                 "backend/app/offloading/integration_contract.py"):
        dst=source/name
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/name,dst)
    for n in ("dqn.py","ddqn.py","normalizer.py","training.py"):
        shutil.copy2(ROOT/"backend/app/offloading/agents49"/n,source/"backend/app/offloading/agents49"/n)
    sums={f.relative_to(out).as_posix():sha256(f.read_bytes()).hexdigest()
          for f in sorted(out.rglob("*")) if f.is_file()}
    (out/"SHA256SUMS.json").write_text(json.dumps(sums,ensure_ascii=False,indent=2),encoding="utf-8")
    with zipfile.ZipFile(target,"x",zipfile.ZIP_DEFLATED) as z:
        for name in (*sums,"SHA256SUMS.json"):
            z.write(out/name,name)
    with zipfile.ZipFile(target) as z:
        for name,expected in sums.items():
            assert sha256(z.read(name)).hexdigest()==expected
    print(len(sums),"SHA-256 matches;",target.stat().st_size,"ZIP bytes")

