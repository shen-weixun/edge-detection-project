"""Recompute metrics and dispatch choices from every saved validation run."""
import argparse
import csv
import json
from math import ceil,isfinite,isclose
from pathlib import Path
from statistics import mean


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("out",type=Path)
    out=p.parse_args().out
    def read(path):
        return json.loads(path.read_text(encoding="utf-8-sig"))
    design=read(out/"design.json")
    inputs={(c["scene"]["id"],c["seed"],c["burst"]):c["tasks"] for c in design["validation"]}
    maximum=0.
    tasks_seen=0
    paths=list((out/"runs").glob("*/validation-*.json"))
    assert len(paths)==48*3*32
    for path in paths:
        payload=read(path)
        summary=payload["summary"]
        tasks=payload["tasks"]
        qrows=payload["q_values"]
        expected=inputs[summary["scene"],summary["validation_seed"],summary["burst"]]
        assert [r["task"] for r in tasks]==expected
        assert len(tasks)==len(qrows)==100
        for row,q in zip(tasks,qrows):
            assert row["completed"] and not row["dropped"] and row["decision_ms"]==0
            assert "workload_ms" not in row["decision_input"] and "face_count" not in row["decision_input"]
            assert len(q["q_values"])==3 and all(isfinite(v) for v in q["q_values"])
            assert q["action"]==max(range(3),key=q["q_values"].__getitem__)
            assert row["selected_node"]==("local","edge","cloud")[q["action"]]
            assert row["task_id"]==q["task_id"]
            error=max(abs(row["completed_at_ms"]-row["arrival_ms"]-row["total_latency_ms"]),
                      abs(sum(row[k] for k in ("decision_ms","decision_queue_ms","network_ms","queue_ms","compute_ms"))-row["total_latency_ms"]))
            assert error<1e-6
            maximum=max(maximum,error)
        times=sorted(r["total_latency_ms"] for r in tasks)
        assert isclose(mean(times),summary["avg_latency_ms"],abs_tol=.000051,rel_tol=0)
        assert isclose(times[ceil(.95*len(tasks))-1],summary["p95_latency_ms"],abs_tol=1e-6,rel_tol=0)
        assert isclose(mean(r["deadline_met"] for r in tasks),summary["deadline_met_rate"],abs_tol=1e-6,rel_tol=0)
        assert isclose(mean(-r["total_latency_ms"]/1000-(not r["deadline_met"]) for r in tasks),
                       summary["mean_task_reward"],abs_tol=1e-8,rel_tol=0)
        tasks_seen+=len(tasks)
    result=dict(status="PASS",validation_runs=len(paths),tasks=tasks_seen,
                finite_q_and_action_match=True,paired_inputs=True,max_conservation_error_ms=maximum)
    (out/"validation-independent-audit.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(result)

