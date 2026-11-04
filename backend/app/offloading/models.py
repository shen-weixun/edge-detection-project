"""Shared, serializable task and observable node-state contracts."""
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class Task:
    task_id: int
    image_size_mb: float
    face_count: int
    workload_ms: float  # measured reference-device inference duration
    arrival_ms: float
    deadline_ms: float  # relative to arrival
    result_size_kb: float = 16.0
    source_path: str = ''
    dataset: str = ''
    sample_id: str = ''

    def __post_init__(self):
        if self.task_id < 0 or self.face_count < 0:
            raise ValueError("task_id and face_count cannot be negative")
        for name in ("image_size_mb", "workload_ms", "deadline_ms", "result_size_kb"):
            value = getattr(self, name)
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and > 0")
        if not isfinite(self.arrival_ms) or self.arrival_ms < 0:
            raise ValueError("arrival_ms must be finite and >= 0")


@dataclass(frozen=True)
class NodeState:
    name: str
    compute_speed: float  # relative to reference device
    queue_length: int
    queue_work_ms: float  # outstanding reference work, including executing job
    rtt_ms: float
    bandwidth_mbps: float
    upload_backlog_ms: float = 0.0
    download_backlog_ms: float = 0.0
    available: bool = True


@dataclass(frozen=True)
class SystemState:
    local: NodeState
    edge: NodeState
    cloud: NodeState

    def nodes(self):
        return (self.local, self.edge, self.cloud)


@dataclass(frozen=True)
class NodeConfig:
    speed: float
    rtt_ms: float
    bandwidth_mbps: float

    def __post_init__(self):
        if any(not isfinite(v) or v <= 0 for v in (self.speed, self.bandwidth_mbps)):
            raise ValueError("speed and bandwidth_mbps must be finite and > 0")
        if not isfinite(self.rtt_ms) or self.rtt_ms < 0:
            raise ValueError("rtt_ms must be finite and >= 0")
