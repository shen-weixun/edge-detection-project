"""Thin HTTP adapter for the actual ConvAI Innovations Laya Router."""
import os
import json
import uuid
from pathlib import Path
from datetime import datetime, timezone
from time import perf_counter
from threading import Lock
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Literal

app = FastAPI(title="Laya Offloading Worker")
_router = None
_lock = Lock()  # protect first model load and concurrent inference


class DecisionRequest(BaseModel):
    task: dict
    nodes: list[dict]
    context: dict = {}
    variant: Literal["legacy", "v2"] = "legacy"


@app.get("/health")
def health():
    return {"service": "laya", "model_loaded": _router is not None}


@app.post("/decide")
def decide(data: DecisionRequest):
    global _router
    if {n.get("name") for n in data.nodes} != {"local", "edge", "cloud"}:
        raise HTTPException(422, "Expected local, edge and cloud")
    state = {"task": data.task, "nodes": data.nodes}
    original_state = state
    if data.variant == 'v2':
        state = compact_state(data.task, data.nodes)
    audit_id = uuid.uuid4().hex
    started = perf_counter()
    audit = {'audit_id': audit_id, 'timestamp': datetime.now(timezone.utc).isoformat(),
             'context': data.context, 'state': state, 'fallback_used': False,
             'variant': data.variant, 'input_state': original_state}
    questions = {"offload_target": {
        "type": "choice",
        "instructions": "Select the node likely to minimize total completion latency given network transfer, queueing, computation and deadline. Choose one node.",
        "criteria": {
            "local": "Run on local device: no network transfer but lower compute capability; consider queue workload.",
            "edge": "Offload to edge: moderate uplink RTT, capacity, bandwidth and queue.",
            "cloud": "Offload to cloud: faster compute but possibly higher RTT and upload latency.",
        },
    }}
    if data.variant == 'v2':
        questions = neutral_questions(data.nodes)
    try:
        with _lock:
            if _router is None:
                from laya import Router
                _router = Router(device=os.getenv("LAYA_DEVICE", "cpu"))
            if data.variant == 'legacy':
                result = _router.predict(state, questions)
            else:
                import torch
                previous_threads = torch.get_num_threads()
                v2_threads = int(os.getenv('LAYA_V2_THREADS', '1'))
                try:
                    torch.set_num_threads(v2_threads)
                    result = _router.predict(state, questions, model='multilingual')
                finally:
                    torch.set_num_threads(previous_threads)
                audit['threads'] = v2_threads
        audit['raw_output'] = result
        answer = result['answers']['offload_target']
        node = answer['choice']
        if node not in ('local', 'edge', 'cloud'):
            raise ValueError('Invalid Laya decision')
        audit['final_choice'] = node
    except Exception as exc:
        audit['error'] = f'{type(exc).__name__}: {exc}'
        raise HTTPException(503, f"Laya inference failed: {type(exc).__name__}") from exc
    finally:
        audit.update(questions=questions, elapsed_ms=(perf_counter()-started)*1000)
        directory = Path(os.getenv('LAYA_AUDIT_ROOT', '/audit'))
        directory.mkdir(parents=True, exist_ok=True)
        def encode(value):
            if hasattr(value, 'tolist'): return value.tolist()
            if hasattr(value, 'item'): return value.item()
            raise TypeError(type(value).__name__)
        with _lock:
            with (directory/'decisions.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(audit, ensure_ascii=False, default=encode, allow_nan=False)+'\n')
    return {"node": node, "confidence": answer.get("confidence"),
            "audit_id": audit_id,
            "model": result.get("routing", {}).get("model", "laya")}


def compact_state(task, nodes):
    """Preserve candidate order. Only algebra on observable inputs; no ranking."""
    candidates = []
    for n in nodes:
        remote = n['name'] != 'local'
        bw, speed = n['bandwidth_mbps'], n['compute_speed']
        candidates.append(dict(node=n['name'],
            input_transfer_ms=(task['image_size_mb']*8000/bw+n['rtt_ms']/2) if remote else 0,
            output_transfer_ms=(task['result_size_kb']*8/bw+n['rtt_ms']/2) if remote else 0,
            cpu_queue_ms=n['queue_work_ms']/speed,
            in_transit_cpu_ms=n.get('committed_work_ms',0)/speed,
            compute_ms=task['estimated_workload_ms']/speed,
            upload_backlog_ms=n.get('upload_backlog_ms',0) if remote else 0,
            download_backlog_ms=n.get('download_backlog_ms',0) if remote else 0,
            available=n.get('available',True)))
    now=max(n.get('observed_at_ms',0) for n in nodes)
    return dict(units='milliseconds', remaining_deadline_ms=task['deadline_ms']-max(0,now-task.get('arrival_ms',0)), candidates=candidates)


def neutral_questions(nodes):
    return {'offload_target':dict(type='choice',
        instructions='Choose an available candidate with the lowest expected completion time. Account for transfer, pending CPU work, compute time and the remaining deadline. All durations are milliseconds. CPU work can progress during transfer.',
        criteria={n['name']:'Execute on the candidate named '+n['name']+'.' for n in nodes})}
