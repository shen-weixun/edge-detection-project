import unittest,tempfile,json,os
from pathlib import Path
from dataclasses import replace,asdict
from unittest.mock import patch
from io import BytesIO
from contextlib import contextmanager
from app.offloading.estimators import WorkloadEstimator,features,assert_disjoint,register,load_registered
from app.offloading.models import Task,DecisionTask,NodeState,SystemState
from app.offloading.simulator import Simulator,DEFAULT_NODES
from app.offloading.strategies import FixedStrategy,LatencyAwareStrategy
from app.offloading.latency_v2 import estimate_v2,LatencyAwareV2Strategy
from app.offloading.experiment import experiment
from app.offloading.laya_client import LayaV2Strategy
from acceptance_reference import scenarios


def training():
    return [dict(image_size_mb=.1+i*.03,width=100+i*30,height=100,workload_ms=100+i*2,source_path='train/'+str(i),dataset='lfw') for i in range(20)]

class EstimatorTests(unittest.TestCase):
    def test_saved_roundtrip_predictions_and_checksum(self):
        for kind in ('median','ridge_raw','ridge_log'):
            model=WorkloadEstimator.fit(training(),kind)
            with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'PROFILE_ROOT':d}):
                ident=register(model);loaded=load_registered(ident)
                self.assertEqual(model.predict(training()[0]),loaded.predict(training()[0]))
                path=Path(d)/'estimators'/(ident+'.json');data=json.loads(path.read_text());data['value_ms']+=1;path.write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError,'checksum'):load_registered(ident)

    def test_predictions_use_metadata_only(self):
        row=training()[0]
        for kind in ('median','ridge_raw','ridge_log'):
            model=WorkloadEstimator.fit(training(),kind)
            self.assertEqual(model.predict(row),model.predict(dict(row,workload_ms=99999,face_count=1000,source_path='elsewhere',dataset='secret')))
            dto=DecisionTask(1,row['image_size_mb'],row['width'],row['height'],0,1000,1,16)
            self.assertEqual(model.predict(row),model.predict(dto))

    def test_train_validation_test_guard_and_source_alias(self):
        rows=training();model=replace(WorkloadEstimator.fit(rows),validation_identities=('validation/image',))
        for r in [dict(rows[0],dataset='other',source_path='train/./0'),dict(rows[0],source_path='validation/image')]:
            with self.assertRaisesRegex(ValueError,'overlap'):model.validate_test([r])
        with self.assertRaises(ValueError):assert_disjoint(rows,[dict(rows[0])])

    def test_invalid_dimensions_and_model_shapes_rejected(self):
        with self.assertRaises(ValueError):features(dict(image_size_mb=1,width=0,height=100))
        model=WorkloadEstimator.fit(training(),'ridge_raw').to_dict();model['coefficients']=[1]
        with self.assertRaises(ValueError):WorkloadEstimator.from_dict(model)

    def test_realistic_experiment_keeps_actual_service_truth(self):
        model=WorkloadEstimator.fit(training(),'ridge_raw')
        profile=[dict(training()[i],source_path='test/'+str(i),face_count=1,sample_id=str(i)) for i in range(3)]
        result=experiment(count=3,profile=profile,estimator_model=model,strategies=['local_only','latency_aware','latency_aware_v2'],include_decision_overhead=False)
        for policy in result['strategies'].values():self.assertEqual([x['task'] for x in policy['tasks']],result['workload'])
        for row in result['strategies']['local_only']['tasks']:self.assertEqual(row['compute_ms'],row['task']['workload_ms'])
        with self.assertRaises(ValueError):experiment(count=1,profile=profile,estimator_model=model,information_mode='oracle')

    def test_prediction_wall_time_is_charged_inside_policy(self):
        import time
        model=WorkloadEstimator.fit(training(),'median')
        row=dict(training()[0],source_path='test/one',face_count=1,sample_id='1')
        original=WorkloadEstimator.predict
        def slow(instance,observed):
            time.sleep(.005)
            return original(instance,observed)
        with patch.object(WorkloadEstimator,'predict',slow):
            x=experiment(count=1,profile=[row],estimator_model=model,strategies=['local_only'])
        result=x['strategies']['local_only']['tasks'][0]
        self.assertGreaterEqual(result['decision_ms'],4)
        self.assertAlmostEqual(result['total_latency_ms'],result['decision_ms']+result['compute_ms'])
        self.assertTrue(x['estimator']['prediction_in_decision_cost'])

class LatencyV2Tests(unittest.TestCase):
    def test_empty_node_three_advantages_and_hand_formula(self):
        t,sets=scenarios()
        for case,nodes in sets.items():
            sim=Simulator([t],LatencyAwareV2Strategy(),nodes,False)
            row=sim.run()[0];self.assertEqual(row['selected_node'],{'A_local':'local','B_edge':'edge','C_cloud':'cloud'}[case])
            state=Simulator([],FixedStrategy('local'),nodes).get_state()
            expected=estimate_v2(DecisionTask.observe(t),getattr(state,row['selected_node']))['total_ms']
            actual_estimate=Simulator([replace(t,workload_ms=t.estimated_workload_ms)],FixedStrategy(row['selected_node']),nodes,False).run()[0]['total_latency_ms']
            self.assertAlmostEqual(expected,actual_estimate)

    def test_cpu_drains_during_input_transfer(self):
        t=DecisionTask(0,1,1000,1000,0,1000,100,16)
        state=SystemState(NodeState('local',1,1,120,0,1000),NodeState('edge',1,1,80,0,80),NodeState('cloud',1,0,0,1000,1))
        self.assertEqual(LatencyAwareStrategy().select_node(t,state),'local')
        self.assertEqual(LatencyAwareV2Strategy().select_node(t,state),'edge')
        self.assertAlmostEqual(estimate_v2(t,state.edge)['total_ms'],201.6)

    def test_download_backlog_drains_before_compute_finishes(self):
        t=DecisionTask(0,1,1000,1000,0,1000,100,16)
        n=NodeState('edge',1,0,0,0,80,download_backlog_ms=50)
        self.assertAlmostEqual(estimate_v2(t,n)['total_ms'],201.6)
        self.assertAlmostEqual(estimate_v2(t,replace(n,download_backlog_ms=400))['total_ms'],401.6)

    def test_deadline_elapsed_pressure_committed_work_and_unavailable(self):
        t=DecisionTask(0,.001,10,10,0,50,10,16)
        n=NodeState('edge',1,0,0,0,1000,committed_work_ms=100,observed_at_ms=40)
        e=estimate_v2(t,n);self.assertEqual(e['remaining_deadline_ms'],10);self.assertLess(e['slack_ms'],0);self.assertGreater(e['late_ratio'],0)
        self.assertEqual(estimate_v2(t,replace(n,available=False))['total_ms'],float('inf'))

    def test_no_true_work_access_and_no_state_mutation(self):
        t,_=scenarios();state=Simulator([],FixedStrategy('local')).get_state();before=asdict(state)
        a=LatencyAwareV2Strategy().select_node(DecisionTask.observe(t),state)
        b=LatencyAwareV2Strategy().select_node(DecisionTask.observe(replace(t,workload_ms=90000,face_count=900)),state)
        self.assertEqual(a,b);self.assertEqual(before,asdict(state))

    def test_legacy_defaults_and_new_key_are_additive(self):
        result=experiment(count=2,include_decision_overhead=False)
        self.assertEqual(list(result['strategies']),['local_only','edge_only','cloud_only','load_threshold','latency_aware'])
        self.assertIn('latency_aware_v2',experiment(count=1,strategies=['latency_aware_v2'])['strategies'])

class LayaVariantTests(unittest.TestCase):
    def test_v2_real_model_choice_is_never_replaced_by_rule(self):
        t,_=scenarios();state=Simulator([],FixedStrategy('local')).get_state()
        @contextmanager
        def fake(req,timeout):
            body=json.loads(req.data);self.assertEqual(body['variant'],'v2');self.assertNotIn('workload_ms',body['task']);self.assertNotIn('face_count',body['task'])
            yield BytesIO(b'{"node":"cloud","audit_id":"real-choice","model":"multilingual"}')
        with patch('app.offloading.laya_client.urlopen',side_effect=fake):
            policy=LayaV2Strategy();self.assertEqual(policy.select_node(DecisionTask.observe(t),state),'cloud');self.assertEqual(policy.last_audit_id,'real-choice')
