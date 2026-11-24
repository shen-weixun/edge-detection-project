import unittest
from dataclasses import replace

from app.offloading.agents49.normalizer import FEATURE_NAMES, normalize
from app.offloading.agents49.training import train_episode
from app.offloading.integration_contract import FEATURE_NAMES as SIMPY_FEATURES, feature_vector
from app.offloading.models import Task
from app.offloading.rl import OffloadingEnv


class RecordingAgent:
    def __init__(self):
        self.transitions = []

    def act(self, features, epsilon):
        return 0

    def remember(self, *transition):
        self.transitions.append(transition)

    def train_step(self):
        return 0.0


class Agents49Tests(unittest.TestCase):
    def test_hidden_service_does_not_change_visible_queue_while_running(self):
        first = Task(0, .1, 1, 100, 0, 1000, estimated_workload_ms=150)
        waiting = replace(first, task_id=1, arrival_ms=5)
        probe = replace(first, task_id=2, arrival_ms=10)
        vectors = []
        for actual in (100, 300):
            env = OffloadingEnv([replace(first, workload_ms=actual), waiting, probe])
            env.reset()
            _, reward, _, info = env.step(0)
            obs, reward, done, info = env.step(0)
            self.assertFalse(info["terminal_rewards"])
            self.assertEqual(reward, 0)
            self.assertFalse(done)
            self.assertEqual(obs[1].local.queue_work_ms, 290)
            self.assertEqual(obs[1].local.queue_length, 1)
            vectors.append(feature_vector(*obs))
        self.assertEqual(FEATURE_NAMES, SIMPY_FEATURES)
        self.assertEqual(vectors[0], vectors[1])
        self.assertEqual(normalize(vectors[0]).tolist(), normalize(vectors[1]).tolist())

    def test_out_of_order_rewards_and_terminal_drain(self):
        slow = Task(0, .001, 1, 300, 0, 1000)
        fast = replace(slow, task_id=1, workload_ms=1, arrival_ms=1)
        probe = replace(slow, task_id=2, workload_ms=1, arrival_ms=50)
        agent = RecordingAgent()
        agent.act = lambda features, epsilon: next(actions)
        actions = iter((0, 1, 2))
        steps = train_episode(agent, [slow, fast, probe], epsilon_for_step=lambda _: 0, config={})
        self.assertEqual([row["next_task_id"] for row in steps], [1, 2, None])
        self.assertEqual([row["done"] for row in steps], [False, False, True])
        self.assertEqual([[r["task_id"] for r in row["terminal_rewards"]] for row in steps],
                         [[], [1], [2, 0]])
        self.assertEqual(agent.transitions[0][3], agent.transitions[1][0])
        self.assertEqual(agent.transitions[1][3], agent.transitions[2][0])
        self.assertAlmostEqual(agent.transitions[2][2], steps[2]["reward"])
        self.assertTrue(agent.transitions[2][4])

    def test_completion_before_next_decision_is_in_current_step(self):
        first = Task(0, .001, 1, 1, 0, 1000)
        second = replace(first, task_id=1, arrival_ms=100)
        steps = train_episode(RecordingAgent(), [first, second],
                              epsilon_for_step=lambda _: 0, config={})
        self.assertEqual([[r["task_id"] for r in row["terminal_rewards"]] for row in steps],
                         [[0], [1]])
        self.assertEqual([row["reward"] for row in steps], [-.001, -.001])
        self.assertEqual([row["done"] for row in steps], [False, True])

