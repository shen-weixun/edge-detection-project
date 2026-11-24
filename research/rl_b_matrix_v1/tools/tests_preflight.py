import unittest
from collections import Counter
from itertools import product
from dataclasses import replace
import numpy as np
from common import ROOT,arrays_equal,rng_state
from design import B,A,DATASETS,LOADS,PATTERNS,SEEDS,load_data,make_tasks,balanced_order
from diagnostics import DiagnosticDQN,DiagnosticDDQN
from evidence import event_evidence,AuditedIntegralEnv,task
from app.offloading.agents49.dqn import DQN
from app.offloading.agents49.ddqn import DDQN
from app.offloading.agents49.integral_env import IntegralEnv
from app.offloading.agents49.adapter import Agent49Policy
from app.offloading.agents49.input_contract import InputSpec
from app.offloading.integration_contract import feature_vector

class Preflight(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import json
        cls.manifest=json.loads((ROOT/'results/design/training-manifest.json').read_text())
        cls.validation=json.loads((ROOT/'results/design/validation-manifest.json').read_text())

    def test_48_unique_cells_every_seed_round(self):
        rows=self.manifest['training']
        for seed,round in product(SEEDS,range(2)):
            subset=[r for r in rows if r['seed']==seed and r['round']==round]
            self.assertEqual(len(subset),48);self.assertEqual(len({r['cell'] for r in subset}),48)
            self.assertEqual({r['epsilon'] for r in subset},{.8 if round==0 else .1})
            self.assertTrue(all(len(r['tasks'])==100 for r in subset))

    def test_every_quarter_factor_balance(self):
        for seed,round,quarter in product(SEEDS,range(2),range(4)):
            rows=[r for r in self.manifest['training'] if r['seed']==seed and r['round']==round and r['quarter']==quarter]
            for field,n in [('dataset',6),('load',4),('network',3),('pattern',6)]:
                self.assertEqual(set(Counter(r[field] for r in rows).values()),{n})

    def test_orders_differ_between_seed_and_round(self):
        orders=[balanced_order(s,r) for s,r in product(SEEDS,range(2))]
        self.assertEqual(len({str(x) for x in orders}),6)

    def test_steady_burst_arrival_span_and_image_sampling(self):
        pools,_,est=load_data()
        for ds in DATASETS:
            a=make_tasks(pools[ds+'/training'],123.,[11,22],est,'steady')
            b=make_tasks(pools[ds+'/training'],123.,[11,22],est,'burst')
            self.assertAlmostEqual(a[-1].arrival_ms,b[-1].arrival_ms,places=8)
            self.assertEqual([x.source_path for x in a],[x.source_path for x in b])
            self.assertEqual(len({x.source_path for x in a})<=40,True)
            self.assertGreater(min(np.diff([x.arrival_ms for x in b])),0)

    def test_real_manifest_paired_patterns_span(self):
        rows=self.manifest['training']
        for seed,round,ds,load,network in product(SEEDS,range(2),DATASETS,LOADS,B):
            pair=[x for x in rows if (x['seed'],x['round'],x['dataset'],x['load'],x['network'])==(seed,round,ds,load,network)]
            self.assertEqual(len(pair),2)
            self.assertAlmostEqual(pair[0]['arrival_span_ms'],pair[1]['arrival_span_ms'],places=6)

    def test_profiles_only_training_validation_and_median(self):
        pools,meta,est=load_data();self.assertEqual(set(k.split('/')[1] for k in pools),{'training','validation'})
        self.assertEqual(sum(len(v) for k,v in pools.items() if k.endswith('/training')),80)
        self.assertAlmostEqual(est.value_ms,470.3018125055678)
        self.assertTrue(all(r['deadline_ms']==1000 for c in self.manifest['training'] for r in c['tasks']))

    def test_union_and_unseen_validation_layers(self):
        cases=self.validation['cases'];self.assertEqual(len(cases),240)
        self.assertEqual({x['layer'] for x in cases},{'extreme_sanity','common_reference','unseen_parameters','B_boundary_or_congestion'})
        training_configs={str(v) for v in B.values()}
        self.assertTrue(all(str(c['nodes']) not in training_configs for c in cases if c['layer']=='unseen_parameters'))
        self.assertEqual(len({c['exogenous_sha256'] for c in cases}),len(cases))

    def test_diagnostic_recording_does_not_change_rng_or_update(self):
        raw=np.ones(49);raw[[14,28,42]]=1
        for plain,diagnostic in [(DQN,DiagnosticDQN),(DDQN,DiagnosticDDQN)]:
            a=plain(seed=42,gamma=1);b=diagnostic(seed=42,gamma=1)
            for i in range(100):
                epsilon=.8 if i<50 else .1
                self.assertEqual(a.act(raw,epsilon),b.act(raw,epsilon));self.assertEqual(rng_state(a),rng_state(b))
            for i in range(64):
                for x in (a,b):x.remember(raw,i%3,-10000.,raw,False)
            for i in range(4):
                self.assertEqual(a.train_step(),b.train_step())
                self.assertTrue(arrays_equal(a.online,b.online));self.assertTrue(arrays_equal(a.target,b.target))
                self.assertEqual(rng_state(a),rng_state(b))
                self.assertGreater(b.last_update_diagnostics['td_clip_count'],0)
                self.assertGreater(b.last_update_diagnostics['gradient_clip_count'],0)

    def test_disabled_diagnostics_equal_original(self):
        raw=np.ones(49)
        a=DQN(seed=9);b=DiagnosticDQN(seed=9);b.diagnostics_enabled=False
        self.assertEqual(a.act(raw,.8),b.act(raw,.8));self.assertEqual(rng_state(a),rng_state(b))

    def test_greedy_diagnostic_no_rng_draw_and_actual_random_branch(self):
        a=DiagnosticDQN(seed=42);raw=np.ones(49);before=rng_state(a)
        a.act(raw,0);self.assertFalse(a.last_action_diagnostics['random_branch']);self.assertEqual(before,rng_state(a))
        a.act(raw,1);self.assertTrue(a.last_action_diagnostics['random_branch'])

    def test_dqn_ddqn_nonzero_bootstrap_differ(self):
        agents=[DQN(seed=1,gamma=1),DDQN(seed=1,gamma=1)]
        for a in agents:
            for w in a.online+a.target:w[:]=0
            a.online[-1][:]=[2,1,0];a.target[-1][:]=[1,3,0]
        self.assertEqual(agents[0]._next_q(np.zeros((1,49)),np.ones((1,3)))[0],3)
        self.assertEqual(agents[1]._next_q(np.zeros((1,49)),np.ones((1,3)))[0],1)

    def test_capacity_observer_preserves_event_results(self):
        work=[task(0),task(1,10),task(2,20)]
        outputs=[]
        for ctor in [IntegralEnv,AuditedIntegralEnv]:
            env=ctor(work);obs=env.reset();rewards=[]
            while obs is not None:obs,r,done,info=env.step(1);rewards.append(r)
            outputs.append((env.sim.results,rewards))
        self.assertEqual(outputs[0],outputs[1])

    def test_real_simpy_reversals_and_hidden_actual_isolation(self):
        cases=event_evidence(ROOT/'results/event-evidence')
        self.assertEqual(cases['cpu_busy']['observation']['V2'],'cloud')
        self.assertEqual(cases['link_busy']['observation']['V2'],'edge')
        self.assertEqual(cases['remote_busy']['observation']['V2'],'local')

