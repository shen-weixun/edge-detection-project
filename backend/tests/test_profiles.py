import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app.offloading.profiles import FIELDS, measure_row, path_for
from app.offloading.workload import load_profile, generate_tasks
from app.offloading.experiment import experiment
from app.offloading.models import Task
from app.offloading.simulator import Simulator
from app.offloading.strategies import FixedStrategy

class ProfileTests(unittest.TestCase):
    def make_csv(self, path, rows):
        with path.open('w', newline='') as f:
            w=csv.DictWriter(f, fieldnames=FIELDS);w.writeheader();w.writerows(rows)

    def row(self, **extra):
        return dict(sample_id='17',source_path='lfw/A/A.jpg',dataset='lfw',image_size_mb=.1,
                    face_count=1,inference_ms=123,repeats=3,model='buffalo_l',success=True,**extra)

    def test_csv_roundtrip_and_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'p.csv';self.make_csv(p,[self.row()]);profile=load_profile(p)
            t=generate_tasks(1,profile=profile)[0]
            self.assertEqual((t.source_path,t.dataset,t.workload_ms),('lfw/A/A.jpg','lfw',123))

    def test_failed_rows_are_excluded_without_fabrication(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'p.csv';r=self.row();r.update(success=False,inference_ms='',error='decode failed')
            self.make_csv(p,[r,self.row()]);self.assertEqual(len(load_profile(p)),1)
            self.make_csv(p,[r])
            with self.assertRaises(ValueError):load_profile(p)

    def test_legacy_unverified_csv_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'p.csv';p.write_text('image_size_mb,face_count,inference_ms\n1,1,42\n')
            with self.assertRaises(ValueError):load_profile(p)

    def test_missing_profile_never_becomes_synthetic(self):
        with self.assertRaises(FileNotFoundError):load_profile('/nonexistent/profile.csv')
        with self.assertRaises(ValueError):generate_tasks(1,profile=[])

    def test_measurement_failure_records_reason(self):
        r=measure_row(1,'../outside','lfw',3)
        self.assertFalse(r['success']);self.assertIn('ValueError',r['error'])
        self.assertEqual(r['inference_ms'],'')

    def test_profile_path_traversal_rejected(self):
        with self.assertRaises(ValueError):path_for('../outside')

    def test_no_replacement_sampling(self):
        p=[dict(image_size_mb=1,face_count=1,workload_ms=100,source_path=str(i),dataset='lfw',sample_id=str(i)) for i in range(4)]
        tasks=generate_tasks(4,seed=8,profile=p)
        self.assertEqual(len({t.source_path for t in tasks}),4)
        self.assertEqual(tasks,generate_tasks(4,seed=8,profile=p))
        with self.assertRaises(ValueError):generate_tasks(5,profile=p)

    def test_measured_policy_fairness_and_reset(self):
        p=[dict(image_size_mb=1,face_count=1,workload_ms=100,source_path=str(i),dataset='lfw',sample_id=str(i)) for i in range(3)]
        a=experiment(count=3,profile=p,include_decision_overhead=False)
        b=experiment(count=3,profile=p,include_decision_overhead=False)
        self.assertEqual(a['workload_sha256'],b['workload_sha256'])
        for r in a['strategies'].values():
            self.assertEqual([x['task'] for x in r['tasks']],a['workload'])
            self.assertEqual(r['summary']['drop_rate'],0)
        self.assertEqual(a['strategies']['local_only']['tasks'][0]['compute_ms'],100)

    def test_decision_deadline_and_component_sum(self):
        with patch('app.offloading.simulator.perf_counter',side_effect=[1,1.6]):
            r=Simulator([Task(0,1,1,100,0,500)],FixedStrategy('local')).run()[0]
        self.assertFalse(r['deadline_met']);self.assertEqual(r['decision_ms'],600)
        self.assertAlmostEqual(r['total_latency_ms'],sum(r[k] for k in ['network_ms','queue_ms','compute_ms','decision_ms','decision_queue_ms']),places=3)

    def test_decision_engine_serial_queue(self):
        with patch('app.offloading.simulator.perf_counter',side_effect=[0,.1,1,1.1]):
            rows=Simulator([Task(i,1,1,10,0,500) for i in range(2)],FixedStrategy('local')).run()
        self.assertAlmostEqual(rows[1]['decision_queue_ms'],100)

    def test_metadata_is_captured_at_decision_not_completion(self):
        class Policy:
            count = 0
            def select_node(self, task, state):
                self.count += 1
                self.last_model = 'model-'+str(self.count)
                self.last_confidence = self.count / 10
                self.last_audit_id = str(self.count)
                return 'local'
        with patch('app.offloading.simulator.perf_counter',side_effect=[0,.1,1,1.1]):
            rows=Simulator([Task(i,1,1,1000,0,5000) for i in range(2)],Policy()).run()
        self.assertEqual([r['decision_audit_id'] for r in rows],['1','2'])
        self.assertEqual([r['decision_model'] for r in rows],['model-1','model-2'])
        self.assertEqual([r['decision_confidence'] for r in rows],[.1,.2])
