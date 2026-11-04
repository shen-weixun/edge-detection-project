"""Real Laya decision model integration via the optional isolated Docker service."""
import json
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from dataclasses import asdict
from .models import DecisionTask as Task, SystemState


class LayaStrategy:
    def __init__(self, endpoint=None, timeout=120.0):
        self.endpoint = endpoint or os.getenv("LAYA_URL", "http://laya:8001/decide")
        self.timeout = timeout
        self.last_confidence = None
        self.last_model = None
        self.last_audit_id = None

    def select_node(self, task: Task, state: SystemState) -> str:
        if not isinstance(task, Task):
            raise TypeError('Laya requires DecisionTask; internal Task is not a policy input')
        data = {
            'context': {'task_id': task.task_id},
            "task": asdict(task),
            "nodes": [vars(n) for n in state.nodes()],
        }
        payload = json.dumps(data, allow_nan=False).encode("utf-8")
        request = Request(self.endpoint, data=payload,
                          headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                result = json.load(response)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise RuntimeError("Laya service unavailable; start Docker profile 'ai' and check logs") from exc
        node = result.get("node")
        if node not in {"local", "edge", "cloud"}:
            raise RuntimeError("Laya returned an invalid node (no silent fallback)")
        self.last_confidence = result.get("confidence")
        self.last_model = result.get('model')
        self.last_audit_id = result.get('audit_id')
        return node
