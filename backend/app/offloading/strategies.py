"""Decision policies observe only the current state; no access to future outcomes."""
from .models import DecisionTask as Task, SystemState, NodeState


def estimate_latency(task: Task, node: NodeState) -> float:
    if not node.available:
        return float("inf")
    compute = task.estimated_workload_ms / node.compute_speed
    queue = (node.queue_work_ms + node.committed_work_ms) / node.compute_speed
    if node.name == "local":
        return queue + compute
    upload = task.image_size_mb * 8_000 / node.bandwidth_mbps
    download = task.result_size_kb * 8 / node.bandwidth_mbps
    return (queue + compute + node.rtt_ms + upload + download
            + node.upload_backlog_ms + node.download_backlog_ms)


class FixedStrategy:
    def __init__(self, name):
        if name not in ("local", "edge", "cloud"):
            raise ValueError("unknown node")
        self.name = name

    def select_node(self, task: Task, state: SystemState) -> str:
        node = getattr(state, self.name)
        if not node.available:
            raise ValueError(f"{self.name} unavailable")
        return self.name


class LoadThresholdStrategy:
    """Original fourth baseline: use edge under its queue threshold, else cloud."""
    def __init__(self, threshold=2):
        self.threshold = threshold

    def select_node(self, task: Task, state: SystemState) -> str:
        if state.edge.available and state.edge.queue_length + state.edge.committed_count < self.threshold:
            return "edge"
        if state.cloud.available:
            return "cloud"
        return "local"


class LatencyAwareStrategy:
    def select_node(self, task: Task, state: SystemState) -> str:
        return min(state.nodes(), key=lambda node: estimate_latency(task, node)).name


STRATEGY_FACTORIES = {
    "local_only": lambda: FixedStrategy("local"),
    "edge_only": lambda: FixedStrategy("edge"),
    "cloud_only": lambda: FixedStrategy("cloud"),
    "load_threshold": LoadThresholdStrategy,
    "latency_aware": LatencyAwareStrategy,
}
