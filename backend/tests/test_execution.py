import unittest
from unittest.mock import patch
from app.execution import execute_local

class ExecutionTests(unittest.TestCase):
    def test_all_strategies_measure_local_only(self):
        for strategy in ['fixed', 'latency_aware', 'dqn_ddqn', 'decision_model']:
            with self.subTest(strategy=strategy), patch('app.execution.perf_counter', side_effect=[10, 10.125]):
                result = execute_local(lambda: {'faces': []}, strategy)
                self.assertEqual(result['timings_ms'], {'device': 125.0, 'edge': None, 'cloud': None})
                self.assertEqual(result['strategy'], strategy)
                self.assertEqual(result['execution_target'], 'device')
                self.assertEqual(result['faces'], [])

    def test_failure_does_not_become_success(self):
        def fail():
            raise ValueError('no face')
        with self.assertRaisesRegex(ValueError, 'no face'):
            execute_local(fail, 'fixed')
