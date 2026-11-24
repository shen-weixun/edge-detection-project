import unittest
from dataclasses import replace
from app.offloading.models import Task, NodeConfig
from app.offloading.agents49.task_credit import train_task_episode
from app.offloading.agents49.dqn import DQN
from app.offloading.agents49.ddqn import DDQN


class Recorder:
    gamma = 0
    def __init__(self, actions):
        self.actions = iter(actions)
        self.memory = []
    def act(self, features, epsilon):
        return next(self.actions)
    def remember(self, *args):
        self.memory.append(args)
    def train_step(self):
        return None


class TaskCreditTests(unittest.TestCase):
    def test_reverse_completion_and_final_drain(self):
        a = Task(0, .001, 1, 300, 0, 1000)
        b = replace(a, task_id=1, arrival_ms=1, workload_ms=1)
        c = replace(b, task_id=2, arrival_ms=50)
        agent = Recorder([0, 1, 2])
        log = train_task_episode(agent, [a,b,c], epsilon_for_step=lambda _:0, config={})
        self.assertEqual([(r["task_id"],r["action"]) for r in log], [(1,1),(2,2),(0,0)])
        self.assertAlmostEqual(log[-1]["reward"], -.3)
        self.assertEqual([r["episode_done"] for r in log], [False,True,True])
        for sample in agent.memory:
            self.assertTrue(sample[-1])
            self.assertEqual(sample[0],sample[3])

    def test_simultaneous_completions(self):
        a = Task(0,.001,1,100,0,1000)
        tasks = [replace(a,task_id=i,workload_ms=100 if i==0 else 99.984,result_size_kb=1) for i in range(3)]
        nodes = {n:NodeConfig(1,0,1000) for n in ("local","edge","cloud")}
        log = train_task_episode(Recorder([0,1,2]), tasks,
                                 epsilon_for_step=lambda _:0,config={"nodes":nodes})
        self.assertEqual({r["task_id"] for r in log},{0,1,2})
        self.assertTrue(all(abs(r["reward"]+.1)<1e-9 for r in log))

    def test_gamma_zero_removes_dqn_ddqn_target_difference(self):
        import numpy as np
        from app.offloading.models import DecisionTask, SystemState, NodeState
        from app.offloading.integration_contract import feature_vector
        nodes = [NodeState(n,1,0,0,0,1000) for n in ("local","edge","cloud")]
        f = feature_vector(DecisionTask(0,.1,10,10,0,1000,150,16),SystemState(*nodes))
        a,b = DQN(seed=7,gamma=0), DDQN(seed=7,gamma=0)
        for _ in range(64):
            for agent in (a,b):
                agent.remember(f,0,-.1,f,True)
        self.assertEqual(a.train_step(),b.train_step())
        for x,y in zip(a.online,b.online):
            np.testing.assert_array_equal(x,y)

