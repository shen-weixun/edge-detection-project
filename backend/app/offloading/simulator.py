"""FCFS discrete-event model; policies receive estimates, never scheduled finishes."""
from dataclasses import asdict
from time import perf_counter
from math import isfinite
import simpy
from .models import NodeConfig, NodeState, SystemState, DecisionTask

DEFAULT_NODES = {
    'local': NodeConfig(1, 0, 1000),
    'edge': NodeConfig(3, 20, 120),
    'cloud': NodeConfig(8, 100, 55),
}


class _SerializedLink:
    def __init__(self, env):
        self.resource = simpy.Resource(env, capacity=1)
        self.pending = {}

    def backlog(self, now):
        return sum(max(0, duration - (now - start)) if start is not None else duration
                   for duration, start in self.pending.values())


class _Node:
    def __init__(self, env, cfg):
        self.env, self.cfg = env, cfg
        self.cpu = simpy.Resource(env, capacity=1)
        self.upload, self.download = _SerializedLink(env), _SerializedLink(env)
        self.jobs = {}
        self.queue_area = self.last_update = self.busy_ms = 0.0
        self.max_queue = 0

    def stage(self, task_id, stage=None, estimate=0):
        now = self.env.now
        waiting = sum(j['stage'] == 'cpu_wait' for j in self.jobs.values())
        self.queue_area += waiting * (now - self.last_update)
        self.last_update = now
        if stage is None:
            self.jobs.pop(task_id, None)
        else:
            self.jobs[task_id] = dict(stage=stage, estimate=estimate, since=now)
        self.max_queue = max(self.max_queue, sum(j['stage'] == 'cpu_wait' for j in self.jobs.values()))

    def state(self, name, now):
        jobs = list(self.jobs.values())
        def count(stage): return sum(j['stage'] == stage for j in jobs)
        cpu_work = sum(max(0, j['estimate'] - (now-j['since'])*self.cfg.speed)
                       if j['stage']=='cpu_run' else j['estimate']
                       for j in jobs if j['stage'] in ('cpu_wait', 'cpu_run'))
        committed = [j for j in jobs if j['stage'] in ('committed', 'upload')]
        return NodeState(name, self.cfg.speed, count('cpu_wait'), cpu_work,
                         self.cfg.rtt_ms, self.cfg.bandwidth_mbps,
                         self.upload.backlog(now), self.download.backlog(now), True,
                         count('cpu_run'), len(committed), count('upload'), count('return'),
                         sum(j['estimate'] for j in committed), now)


class Simulator:
    def __init__(self, tasks, strategy, nodes=None, include_decision_overhead=True,
                 information_mode='realistic', network_mode='independent',
                 shared_bandwidth_mbps=120.0, deadline_policy='complete_all'):
        if information_mode not in ('realistic', 'oracle'):
            raise ValueError('invalid information mode')
        if network_mode not in ('independent', 'shared'):
            raise ValueError('invalid network mode')
        if deadline_policy not in ('complete_all', 'drop_if_expired'):
            raise ValueError('invalid deadline policy')
        if not isfinite(shared_bandwidth_mbps) or shared_bandwidth_mbps <= 0:
            raise ValueError('invalid shared bandwidth')
        self.env = simpy.Environment()
        self.tasks = sorted(tasks, key=lambda t: (t.arrival_ms, t.task_id))
        self.strategy = strategy
        self.information_mode, self.network_mode = information_mode, network_mode
        self.shared_bandwidth_mbps, self.deadline_policy = shared_bandwidth_mbps, deadline_policy
        self.decision_engine = simpy.Resource(self.env, capacity=1)
        self.include_decision_overhead = include_decision_overhead
        self.nodes = {name: _Node(self.env, cfg) for name, cfg in (nodes or DEFAULT_NODES).items()}
        if set(self.nodes) != {'local', 'edge', 'cloud'}:
            raise ValueError('must configure local, edge and cloud')
        if len({t.task_id for t in self.tasks}) != len(self.tasks):
            raise ValueError('duplicate task ID')
        if network_mode == 'shared':
            up, down = _SerializedLink(self.env), _SerializedLink(self.env)
            for name in ('edge', 'cloud'):
                self.nodes[name].upload, self.nodes[name].download = up, down
        self.results, self.queue_samples, self.events = [], [], []
        self._ran = False

    def get_state(self):
        states = {}
        for name, node in self.nodes.items():
            state = node.state(name, self.env.now)
            if self.network_mode == 'shared' and name != 'local':
                from dataclasses import replace
                state = replace(state, bandwidth_mbps=min(state.bandwidth_mbps, self.shared_bandwidth_mbps))
            states[name] = state
        return SystemState(**states)

    def _expired(self, task):
        return self.deadline_policy == 'drop_if_expired' and self.env.now > task.arrival_ms + task.deadline_ms

    def _stage(self, task, selected, stage, estimate):
        self.nodes[selected].stage(task.task_id, stage, estimate)
        self.events.append(dict(time_ms=self.env.now, task_id=task.task_id, node=selected, stage=stage))

    def _transfer(self, task, link, duration):
        # Atomic, non-preemptive transmission. Expired waiters consume no service.
        link.pending[task.task_id] = (duration, None)
        try:
            with link.resource.request() as request:
                yield request
                if not self._expired(task):
                    link.pending[task.task_id] = (duration, self.env.now)
                    yield self.env.timeout(duration)
        finally:
            link.pending.pop(task.task_id, None)

    def _process(self, task):
        if task.arrival_ms > self.env.now:
            yield self.env.timeout(task.arrival_ms - self.env.now)
        row = dict(task_id=task.task_id, selected_node=None, arrival_ms=task.arrival_ms,
                   network_ms=0., queue_ms=0., compute_ms=0., decision_ms=0.,
                   decision_wall_ms=0., decision_queue_ms=0., cpu_started_at_ms=None,
                   cpu_completed_at_ms=None, decision_model=None, decision_confidence=None,
                   decision_audit_id=None, task=asdict(task))
        observation = DecisionTask.observe(task, self.information_mode)
        row['decision_input'] = asdict(observation)
        start_wait = self.env.now
        with self.decision_engine.request() as request:
            yield request
            row['decision_queue_ms'] = self.env.now - start_wait
            if self._expired(task):
                self._finish(task, row, False)
                return
            state = self.get_state()
            self.queue_samples.append(dict(time_ms=self.env.now, **{
                key: value for n in state.nodes() for key, value in
                ((n.name+'_queue', n.queue_length), (n.name+'_work_ms', n.queue_work_ms+n.committed_work_ms))}))
            if hasattr(self.strategy, 'request_action'):
                if self.include_decision_overhead:
                    raise ValueError('Interactive RL is a selection-quality ablation; evaluate trained policies via select_node')
                selected = yield self.strategy.request_action(observation, state, self.env)
                wall_ms = 0.0
            else:
                start = perf_counter()
                selected = self.strategy.select_node(observation, state)
                wall_ms = (perf_counter()-start)*1000
            if selected not in self.nodes or not isfinite(wall_ms) or wall_ms < 0:
                raise ValueError('invalid strategy decision')
            row.update(selected_node=selected, decision_wall_ms=wall_ms)
            for key, attr in [('decision_model','last_model'), ('decision_confidence','last_confidence'), ('decision_audit_id','last_audit_id')]:
                row[key] = getattr(self.strategy, attr, None)
            if self.include_decision_overhead:
                row['decision_ms'] = wall_ms
                yield self.env.timeout(wall_ms)
        node = self.nodes[selected]
        estimate = observation.estimated_workload_ms
        self._stage(task, selected, 'committed', estimate)
        if self._expired(task):
            self._finish(task, row, False)
            return
        if selected != 'local':
            self._stage(task, selected, 'upload', estimate)
            before = self.env.now
            yield self.env.timeout(node.cfg.rtt_ms/2)
            if not self._expired(task):
                bw = getattr(self.get_state(), selected).bandwidth_mbps
                yield self.env.process(self._transfer(task, node.upload, task.image_size_mb*8000/bw))
            row['network_ms'] += self.env.now-before
            if self._expired(task):
                self._finish(task, row, False)
                return
        self._stage(task, selected, 'cpu_wait', estimate)
        before = self.env.now
        with node.cpu.request() as request:
            yield request
            row['queue_ms'] = self.env.now-before
            if self._expired(task):
                self._finish(task, row, False)
                return
            self._stage(task, selected, 'cpu_run', estimate)
            row['cpu_started_at_ms'] = self.env.now
            row['compute_ms'] = task.workload_ms/node.cfg.speed
            yield self.env.timeout(row['compute_ms'])
            node.busy_ms += row['compute_ms']
            row['cpu_completed_at_ms'] = self.env.now
        self._stage(task, selected, 'return', 0)
        if selected != 'local':
            if self._expired(task):
                self._finish(task, row, False)
                return
            before = self.env.now
            yield self.env.timeout(node.cfg.rtt_ms/2)
            if not self._expired(task):
                bw = getattr(self.get_state(), selected).bandwidth_mbps
                yield self.env.process(self._transfer(task, node.download, task.result_size_kb*8/bw))
            row['network_ms'] += self.env.now-before
            # A result crossing the deadline is rejected at this stage boundary.
            delivered = not self._expired(task)
            if not delivered:
                self._finish(task, row, False)
                return
        self._finish(task, row, self.deadline_policy == 'complete_all' or not self._expired(task))

    def _finish(self, task, row, completed):
        if row['selected_node'] is not None:
            self._stage(task, row['selected_node'], None, 0)
        row.update(completed_at_ms=self.env.now, total_latency_ms=self.env.now-task.arrival_ms,
                   completed=completed, dropped=not completed,
                   deadline_met=completed and self.env.now-task.arrival_ms <= task.deadline_ms,
                   drop_reason=None if completed else 'expired_at_stage_boundary')
        self.results.append(row)

    def start(self):
        if self._ran:
            raise RuntimeError('Simulator is single-use; create a new episode')
        self._ran = True
        for task in self.tasks:
            self.env.process(self._process(task))

    def run(self):
        self.start()
        self.env.run()
        return sorted(self.results, key=lambda r: r['task_id'])

    def node_statistics(self):
        horizon = max((r['completed_at_ms'] for r in self.results), default=0)
        result = {}
        for name, node in self.nodes.items():
            samples = self.queue_samples
            result[name] = dict(
                mean_queue_time_weighted=node.queue_area/horizon if horizon else 0,
                max_queue=node.max_queue,
                mean_queue_at_decisions=sum(s[name+'_queue'] for s in samples)/len(samples) if samples else 0,
                max_queue_at_decisions=max((s[name+'_queue'] for s in samples), default=0),
                max_work_ms_at_decisions=max((s[name+'_work_ms'] for s in samples), default=0),
                cpu_utilization=node.busy_ms/horizon if horizon else 0)
        return result
