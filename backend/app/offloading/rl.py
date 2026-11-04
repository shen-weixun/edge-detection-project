"""Minimal event-stepped RL adapter. No DQN/DDQN weights or training claim.

Rewards are emitted when jobs terminate, potentially several decisions after
their action. task_id in info provides delayed-credit attribution. An agent
can use these rewards directly as a continuing semi-Markov episode.
"""
from .simulator import Simulator

ACTIONS = ('local', 'edge', 'cloud')


class _Bridge:
    def request_action(self, task, state, env):
        self.action = env.event()
        self.observation = (task, state)
        self.ready.succeed(self.observation)
        return self.action


class OffloadingEnv:
    def __init__(self, tasks, **config):
        self._tasks, self.config = tuple(tasks), config
        if config.get('include_decision_overhead', False):
            raise ValueError('RL training adapter excludes decision wall time')
        self.sim = None

    def reset(self):
        self.bridge = _Bridge()
        self.sim = Simulator(self._tasks, self.bridge, **{
            **self.config, 'include_decision_overhead': False})
        self.bridge.ready = self.sim.env.event()
        self.cursor = 0
        self.done = False
        self.sim.start()
        self._advance()
        return None if self.done else self.bridge.observation

    def _advance(self):
        env = self.sim.env
        while env.peek() != float('inf') and not self.bridge.ready.triggered:
            env.step()
        self.done = not self.bridge.ready.triggered

    def step(self, action):
        if self.sim is None or self.done:
            raise RuntimeError('reset required or episode done')
        if type(action) is not int or not 0 <= action < len(ACTIONS):
            raise ValueError('action must be 0/1/2')
        env = self.sim.env
        self.bridge.ready = env.event()
        self.bridge.action.succeed(ACTIONS[action])
        self._advance()
        terminals = self.sim.results[self.cursor:]
        self.cursor = len(self.sim.results)
        # Dimensionless negative latency in seconds, plus one for each miss.
        rewards = [dict(task_id=r['task_id'], reward=-r['total_latency_ms']/1000
                        - (0 if r['deadline_met'] else 1), dropped=r['dropped'])
                   for r in terminals]
        return (None if self.done else self.bridge.observation,
                sum(r['reward'] for r in rewards), self.done,
                {'terminal_rewards': rewards, 'time_ms': env.now})
