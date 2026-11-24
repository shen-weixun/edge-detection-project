"""Run the original 49D weights through native SimPy on three synthetic tasks."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

sys.path.insert(0, "/app")

from app.offloading.agents49.adapter import AGENTS, Agent49Policy, load_agent
from app.offloading.integration_contract import run_policy
from app.offloading.models import Task


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("member", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument('--input-contract-index',required=True,type=Path)
    args = p.parse_args()
    manifest = {path: sha for sha, path in (line.split(maxsplit=1)
                for line in (args.member / "SHA256_MANIFEST.txt").read_text().splitlines())}
    tasks = [Task(i, size, 1, work, i*80., 1000, width=512, height=512, estimated_workload_ms=estimate)
             for i, (size, work, estimate) in enumerate(((.025, 350, 300), (.04, 120, 200), (.08, 300, 250)))]
    evidence = {}
    for name in AGENTS:
        relative = f"models/{name}_49d.npz"
        path = args.member / relative
        sha = manifest[relative]
        policy = Agent49Policy(load_agent(name, path, sha,contract_index=args.input_contract_index))
        result = run_policy(tasks, policy, include_decision_overhead=True)
        assert len(result["tasks"]) == len(policy.decisions) == 3
        for row, decision in zip(result["tasks"], policy.decisions):
            assert row["completed"] and row["decision_ms"] > 0
            assert row["task_id"] == decision["task_id"] and row["selected_node"] == decision["node"]
        assert sha256(path.read_bytes()).hexdigest() == sha
        evidence[name] = {"prototype_sha256": sha, "result": result, "agent_decisions": policy.decisions}
    args.output.write_text(json.dumps(evidence, indent=2, allow_nan=False), encoding="utf-8")
    print("Original weights: 2 x 3 native SimPy tasks completed; Q/action and measured decision cost recorded.")

