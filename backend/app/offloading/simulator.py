"""SimPy FCFS discrete-event simulation. No remote image inference is performed."""
from dataclasses import asdict
from time import perf_counter
from math import isfinite
import simpy
from .models import NodeConfig, NodeState, SystemState


DEFAULT_NODES = {
    "local": NodeConfig(speed=1, rtt_ms=0, bandwidth_mbps=1000),
    "edge": NodeConfig(speed=3, rtt_ms=20, bandwidth_mbps=120),
    "cloud": NodeConfig(speed=8, rtt_ms=100, bandwidth_mbps=55),
}


class _SerializedLink:
    def __init__(self, env):
        self.resource = simpy.Resource(env, capacity=1)
        self.work_until = 0.0

    def transfer(self, env, duration):
        self.work_until = max(self.work_until, env.now) + duration
        with self.resource.request() as request:
            yield request
            yield env.timeout(duration)

    def backlog(self, now):
        return max(0.0, self.work_until - now)


class _Node:
    def __init__(self, env, cfg):
        self.cfg = cfg
        self.cpu = simpy.Resource(env, capacity=1)
        self.work_until = 0.0
        self.outstanding = 0
        self.upload = _SerializedLink(env)
        self.download = _SerializedLink(env)

    def state(self, name, now):
        return NodeState(
            name=name, compute_speed=self.cfg.speed,
            queue_length=max(0, self.outstanding - int(self.cpu.count)),
            queue_work_ms=max(0.0, self.work_until - now) * self.cfg.speed,
            rtt_ms=self.cfg.rtt_ms,
            bandwidth_mbps=self.cfg.bandwidth_mbps,
            upload_backlog_ms=self.upload.backlog(now),
            download_backlog_ms=self.download.backlog(now),
        )


class Simulator:
    def __init__(self, tasks, strategy, nodes=None, include_decision_overhead=True):
        self.env = simpy.Environment()
        self.tasks = sorted(tasks, key=lambda t: (t.arrival_ms, t.task_id))
        self.strategy = strategy
        self.decision_engine = simpy.Resource(self.env, capacity=1)
        self.include_decision_overhead = include_decision_overhead
        self.nodes = {name: _Node(self.env, cfg)
                      for name, cfg in (nodes or DEFAULT_NODES).items()}
        if set(self.nodes) != {"local", "edge", "cloud"}:
            raise ValueError("must configure local, edge and cloud")
        if len({t.task_id for t in self.tasks}) != len(self.tasks):
            raise ValueError("duplicate task ID")
        self.results = []
        self.queue_samples = []

    def get_state(self):
        return SystemState(**{name: n.state(name, self.env.now)
                              for name, n in self.nodes.items()})

    def _process(self, task):
        if task.arrival_ms > self.env.now:
            yield self.env.timeout(task.arrival_ms - self.env.now)
        # One shared policy executor: AI inference cannot run infinitely in parallel.
        decision_wait_started = self.env.now
        with self.decision_engine.request() as decision_request:
            yield decision_request
            decision_queue_ms = self.env.now - decision_wait_started
            state = self.get_state()
            self.queue_samples.append({
                "time_ms": round(self.env.now, 4),
                "local_queue": state.local.queue_length,
                "edge_queue": state.edge.queue_length,
                "cloud_queue": state.cloud.queue_length,
                "local_work_ms": round(state.local.queue_work_ms, 4),
                "edge_work_ms": round(state.edge.queue_work_ms, 4),
                "cloud_work_ms": round(state.cloud.queue_work_ms, 4),
                "edge_rtt_ms": state.edge.rtt_ms,
                "cloud_rtt_ms": state.cloud.rtt_ms,
            })
            start = perf_counter()
            selected = self.strategy.select_node(task, state)
            decision_ms = (perf_counter() - start) * 1000
            decision_metadata = {key: getattr(self.strategy, attr, None) for key, attr in
                                 [('decision_model', 'last_model'), ('decision_confidence', 'last_confidence'), ('decision_audit_id', 'last_audit_id')]}
            if selected not in self.nodes:
                raise ValueError(f"Invalid strategy node: {selected}")
            if not isfinite(decision_ms) or decision_ms < 0:
                raise ValueError("invalid decision time")
            if self.include_decision_overhead and decision_ms:
                yield self.env.timeout(decision_ms)
        node = self.nodes[selected]
        cfg = node.cfg
        network_ms = 0.0
        if selected != "local":
            yield self.env.timeout(cfg.rtt_ms / 2)
            network_ms += cfg.rtt_ms / 2
            before = self.env.now
            yield self.env.process(node.upload.transfer(
                self.env, task.image_size_mb * 8_000 / cfg.bandwidth_mbps))
            network_ms += self.env.now - before
        # CPU service begins only after full input has arrived.
        queue_enter = self.env.now
        processing_ms = task.workload_ms / cfg.speed
        node.outstanding += 1
        node.work_until = max(node.work_until, queue_enter) + processing_ms
        with node.cpu.request() as request:
            yield request
            queue_ms = self.env.now - queue_enter
            yield self.env.timeout(processing_ms)
        node.outstanding -= 1
        if selected != "local":
            yield self.env.timeout(cfg.rtt_ms / 2)
            network_ms += cfg.rtt_ms / 2
            before = self.env.now
            yield self.env.process(node.download.transfer(
                self.env, task.result_size_kb * 8 / cfg.bandwidth_mbps))
            network_ms += self.env.now - before
        total_latency_ms = self.env.now - task.arrival_ms
        self.results.append({
            "task_id": task.task_id,
            "selected_node": selected,
            "arrival_ms": round(task.arrival_ms, 4),
            "completed_at_ms": round(self.env.now, 4),
            "network_ms": round(network_ms, 4),
            "queue_ms": round(queue_ms, 4),
            "compute_ms": round(processing_ms, 4),
            "decision_ms": round(decision_ms, 4),
            **decision_metadata,
            "decision_queue_ms": round(decision_queue_ms, 4),
            "total_latency_ms": round(total_latency_ms, 4),
            "deadline_met": total_latency_ms <= task.deadline_ms,
            "task": asdict(task),
        })

    def run(self):
        for task in self.tasks:
            self.env.process(self._process(task))
        self.env.run()
        return sorted(self.results, key=lambda r: r["task_id"])
