import unittest
from app.offloading.models import Task
from app.offloading.simulator import Simulator
from app.offloading.strategies import FixedStrategy
from app.offloading.workload import calibration_estimate
from app.offloading.rl import EpisodeSplit

class AcceptanceRegressions(unittest.TestCase):
    def test_idle_cpu_has_zero_max_waiting_queue(self):
        s=Simulator([Task(0,1,1,100,0,1000)],FixedStrategy('local'),include_decision_overhead=False)
        s.run()
        self.assertEqual(s.node_statistics()['local']['max_queue'],0)

    def test_three_simultaneous_jobs_have_two_waiters_not_three(self):
        s=Simulator([Task(i,1,1,100,0,1000) for i in range(3)],FixedStrategy('local'),include_decision_overhead=False)
        s.run();self.assertEqual(s.node_statistics()['local']['max_queue'],2)

    def test_relabelling_same_source_cannot_bypass_calibration_split(self):
        training=[dict(source_path='lfw/a.jpg',dataset='lfw',workload_ms=100)]
        testing=[dict(source_path='lfw/./a.jpg',dataset='wider_val',workload_ms=200)]
        with self.assertRaisesRegex(ValueError,'overlap'):calibration_estimate(training,testing)

    def test_relabelling_same_source_cannot_bypass_rl_split(self):
        from dataclasses import replace
        a=Task(0,1,1,100,0,1000,source_path='lfw/a.jpg',dataset='lfw')
        with self.assertRaisesRegex(ValueError,'overlap'):
            EpisodeSplit((a,),(replace(a,source_path='lfw/./a.jpg',dataset='wider_val'),))
