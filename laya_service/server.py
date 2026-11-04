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

app = FastAPI(title="Laya Offloading Worker")
_router = None
_lock = Lock()  # protect first model load and concurrent inference


class DecisionRequest(BaseModel):
    task: dict
    nodes: list[dict]
    context: dict = {}


@app.get("/health")
def health():
    return {"service": "laya", "model_loaded": _router is not None}


@app.post("/decide")
def decide(data: DecisionRequest):
    global _router
    if {n.get("name") for n in data.nodes} != {"local", "edge", "cloud"}:
        raise HTTPException(422, "Expected local, edge and cloud")
    state = {"task": data.task, "nodes": data.nodes}
    audit_id = uuid.uuid4().hex
    started = perf_counter()
    audit = {'audit_id': audit_id, 'timestamp': datetime.now(timezone.utc).isoformat(),
             'context': data.context, 'state': state, 'fallback_used': False}
    questions = {"offload_target": {
        "type": "choice",
        "instructions": "Select the node likely to minimize total completion latency given network transfer, queueing, computation and deadline. Choose one node.",
        "criteria": {
            "local": "Run on local device: no network transfer but lower compute capability; consider queue workload.",
            "edge": "Offload to edge: moderate uplink RTT, capacity, bandwidth and queue.",
            "cloud": "Offload to cloud: faster compute but possibly higher RTT and upload latency.",
        },
    }}
    try:
        with _lock:
            if _router is None:
                from laya import Router
                _router = Router(device=os.getenv("LAYA_DEVICE", "cpu"))
            result = _router.predict(state, questions)
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
