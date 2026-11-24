"""Native SimPy event wrapper with observable unfinished-job holding cost."""
from ..simulator import Simulator
from ..rl import OffloadingEnv, _Bridge


class IntegralSimulator(Simulator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.active_ids = set()
        self.settled_ids = set()
        self.last_cost_time = 0.
        self.area_ms = 0.
        self.misses = 0
        self.cost_events = []

    def accrue(self):
        now = self.env.now
        self.area_ms += len(self.active_ids) * (now-self.last_cost_time)
        self.last_cost_time = now

    def _process(self, task):
        if task.arrival_ms > self.env.now:
            yield self.env.timeout(task.arrival_ms-self.env.now)
        self.accrue()
        self.active_ids.add(task.task_id)
        self.cost_events.append(dict(time_ms=self.env.now, kind="arrival", task_id=task.task_id,
                                     unfinished=len(self.active_ids), area_ms=self.area_ms))
        yield from super()._process(task)

    def _finish(self, task, row, completed):
        self.accrue()
        if task.task_id not in self.active_ids or task.task_id in self.settled_ids:
            raise ValueError("Invalid terminal settlement")
        super()._finish(task, row, completed)
        self.active_ids.remove(task.task_id)
        self.settled_ids.add(task.task_id)
        self.misses += int(not self.results[-1]["deadline_met"])
        self.cost_events.append(dict(time_ms=self.env.now, kind="terminal", task_id=task.task_id,
                                     unfinished=len(self.active_ids), area_ms=self.area_ms,
                                     deadline_met=self.results[-1]["deadline_met"]))


class IntegralEnv(OffloadingEnv):
    """Reward = -(integral unfinished dt / 1000 + newly settled misses).

    Decision transitions stop at the next real decision observation. Final drain
    has no decisions and therefore is charged to the last transition. Gamma=1
    gives exact undiscounted full-stream delay plus one penalty per miss.
    """
    def reset(self):
        if self.config.get("deadline_policy","complete_all") != "complete_all":
            raise ValueError("This objective requires complete_all")
        self.bridge = _Bridge()
        self.sim = IntegralSimulator(self._tasks, self.bridge,
                                     **{**self.config, "include_decision_overhead": False})
        self.bridge.ready = self.sim.env.event()
        self.cursor = 0
        self.done = False
        self.charged_area = 0.
        self.charged_misses = 0
        self.sim.start()
        self._advance()
        return None if self.done else self.bridge.observation

    def step(self, action):
        observation, _, done, info = super().step(action)
        self.sim.accrue()
        delta_area = self.sim.area_ms-self.charged_area
        new_misses = self.sim.misses-self.charged_misses
        self.charged_area = self.sim.area_ms
        self.charged_misses = self.sim.misses
        reward = -delta_area/1000-new_misses
        info.update(area_ms=self.sim.area_ms, delta_area_ms=delta_area,
                    new_misses=new_misses, episode_done=done,
                    task_done_ids=[r["task_id"] for r in info["terminal_rewards"]])
        return observation,reward,done,info

