import unittest
from unittest.mock import patch
from app.offloading.models import Task, NodeConfig, NodeState, SystemState
from app.offloading.strategies import LatencyAwareStrategy, estimate_latency
from app.offloading.experiment import experiment
from app.offloading.workload import generate_tasks
from app.offloading.simulator import Simulator
from app.offloading.laya_client import LayaStrategy


class StrategiesTest(unittest.TestCase):
    def setUp(self):
        self.task = Task(1, 1, 2, 200, 0, 500)
        self.state = SystemState(
            NodeState("local", 1, 0, 0, 0, 1000),
            NodeState("edge", 4, 0, 0, 20, 200),
            NodeState("cloud", 10, 0, 0, 100, 50),
        )

    def test_latency_aware_selects_edge(self):
        self.assertEqual(LatencyAwareStrategy().select_node(self.task, self.state), "edge")

    def test_queue_changes_policy(self):
        queued = SystemState(self.state.local,
                             NodeState("edge", 4, 4, 2000, 20, 200),
                             self.state.cloud)
        self.assertEqual(LatencyAwareStrategy().select_node(self.task, queued), "local")

    def test_invalid_task_rejected(self):
        with self.assertRaises(ValueError):
            Task(1, -1, 0, 100, 0, 500)

    def test_expected_transfer_units(self):
        self.assertAlmostEqual(estimate_latency(self.task, self.state.edge),
                               50 + 20 + 40 + 16 * 8 / 200)

    def test_real_laya_adapter_parses_typed_result(self):
        from io import BytesIO
        from contextlib import contextmanager
        @contextmanager
        def fake_urlopen(request, timeout):
            self.assertIn(b'"task"', request.data)
            yield BytesIO(b'{"node":"edge","confidence":0.81}')
        with patch("app.offloading.laya_client.urlopen", side_effect=fake_urlopen):
            policy = LayaStrategy()
            self.assertEqual(policy.select_node(self.task, self.state), "edge")
            self.assertEqual(policy.last_confidence, 0.81)

    def test_real_laya_failure_not_faked(self):
        from urllib.error import URLError
        with patch("app.offloading.laya_client.urlopen", side_effect=URLError("down")):
            with self.assertRaisesRegex(RuntimeError, "Laya service unavailable"):
                LayaStrategy().select_node(self.task, self.state)


class SimulationTest(unittest.TestCase):
    def test_task_count_and_seed(self):
        self.assertEqual(generate_tasks(seed=4), generate_tasks(seed=4))

    def test_fixed_local_has_queue_and_no_network(self):
        tasks = [Task(1, 1, 1, 100, 0, 500), Task(2, 1, 1, 100, 0, 500)]
        from app.offloading.strategies import FixedStrategy
        rows = Simulator(tasks, FixedStrategy("local"), include_decision_overhead=False).run()
        self.assertEqual(len(rows), 2)
        self.assertEqual([r["selected_node"] for r in rows], ["local", "local"])
        self.assertTrue(all(r["network_ms"] == 0 for r in rows))
        self.assertGreaterEqual(max(r["queue_ms"] for r in rows), 100)
        self.assertEqual(sorted(r["total_latency_ms"] for r in rows), [100, 200])

    def test_remote_network_and_deadline(self):
        from app.offloading.strategies import FixedStrategy
        config = {"local": NodeConfig(1, 0, 1000),
                  "edge": NodeConfig(2, 20, 100),
                  "cloud": NodeConfig(4, 100, 30)}
        rows = Simulator([Task(0, 1, 2, 200, 0, 100)], FixedStrategy("edge"),
                         nodes=config, include_decision_overhead=False).run()
        self.assertGreater(rows[0]["network_ms"], 100)
        self.assertFalse(rows[0]["deadline_met"])
        self.assertAlmostEqual(rows[0]["total_latency_ms"],
                               rows[0]["network_ms"] + rows[0]["compute_ms"] + rows[0]["queue_ms"], places=3)

    def test_identical_scenario_for_all_policies(self):
        response = experiment(count=5, seed=7, include_decision_overhead=False)
        by_strategy = list(response["strategies"].values())
        first = [r["task"] for r in by_strategy[0]["tasks"]]
        for result in by_strategy[1:]:
            self.assertEqual(first, [r["task"] for r in result["tasks"]])
            self.assertEqual(result["summary"]["completed_count"], 5)
        self.assertEqual(response["profile_source"], "synthetic_demo_NOT_measured")

    def test_unimplemented_dqn_cannot_be_mislabelled(self):
        with self.assertRaisesRegex(ValueError, "not implemented"):
            experiment(strategies=["dqn"])


if __name__ == "__main__":
    unittest.main()
