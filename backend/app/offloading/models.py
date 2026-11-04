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
    width: int = 0
    height: int = 0
    estimated_workload_ms: float = 150.0

    def __post_init__(self):
        if self.task_id < 0 or self.face_count < 0:
            raise ValueError("task_id and face_count cannot be negative")
        for name in ("image_size_mb", "workload_ms", "deadline_ms", "result_size_kb", "estimated_workload_ms"):
            value = getattr(self, name)
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and > 0")
        if not isfinite(self.arrival_ms) or self.arrival_ms < 0:
            raise ValueError("arrival_ms must be finite and >= 0")


@dataclass(frozen=True)
class DecisionTask:
    """Only decision-time observables. No identity/path or post-inference labels."""
    task_id: int
    image_size_mb: float
    width: int
    height: int
    arrival_ms: float
    deadline_ms: float
    estimated_workload_ms: float
    result_size_kb: float

    @classmethod
    def observe(cls, task, information_mode='realistic'):
        return cls(task.task_id, task.image_size_mb, task.width, task.height,
                   task.arrival_ms, task.deadline_ms,
                   task.workload_ms if information_mode == 'oracle' else task.estimated_workload_ms,
                   task.result_size_kb)


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
    cpu_running: int = 0
    committed_count: int = 0
    transmitting_count: int = 0
    returning_count: int = 0
    committed_work_ms: float = 0.0
    observed_at_ms: float = 0.0


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
