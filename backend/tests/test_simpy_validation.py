import unittest
from dataclasses import asdict
from unittest.mock import patch
from app.offloading.models import Task, DecisionTask, NodeConfig
from app.offloading.simulator import Simulator
from app.offloading.strategies import FixedStrategy, LatencyAwareStrategy
from app.offloading.workload import calibration_estimate
from app.offloading.experiment import experiment, metrics

NODES = {'local': NodeConfig(1,0,1000), 'edge': NodeConfig(2,20,80), 'cloud': NodeConfig(2,20,80)}
COSTS = ('decision_queue_ms','decision_ms','network_ms','queue_ms','compute_ms')
def task(i=0, arrival=0, work=100, deadline=10000):
    return Task(i,1,7,work,arrival,deadline,estimated_workload_ms=200)

class EventValidation(unittest.TestCase):
    def conserve(self, rows):
        for r in rows:
            self.assertAlmostEqual(r['total_latency_ms'],sum(r[k] for k in COSTS),places=8)
            self.assertAlmostEqual(r['total_latency_ms'],r['completed_at_ms']-r['arrival_ms'],places=8)

    def test_single_task_hand_calculation(self):
        with patch('app.offloading.simulator.perf_counter',side_effect=[0,.007]):
            r=Simulator([task()],FixedStrategy('edge'),NODES).run()[0]
        self.assertAlmostEqual(r['total_latency_ms'],7+20+100+50+1.6)
        self.assertAlmostEqual(r['cpu_started_at_ms'],117)
        self.conserve([r])

    def test_three_task_fcfs_and_time_weighted_queue(self):
        sim=Simulator([task(i) for i in range(3)],FixedStrategy('local'),include_decision_overhead=False)
        rows=sim.run()
        self.assertEqual([r['cpu_started_at_ms'] for r in rows],[0,100,200])
        self.assertEqual([r['cpu_completed_at_ms'] for r in rows],[100,200,300])
        self.assertEqual([r['queue_ms'] for r in rows],[0,100,200])
        self.assertEqual(sim.node_statistics()['local']['mean_queue_time_weighted'],1)
        self.assertEqual(sim.node_statistics()['local']['cpu_utilization'],1)
        self.conserve(rows)

    def test_arrival_during_upload_has_committed_work(self):
        snapshots=[]
        class Spy:
            def select_node(self,t,s):
                snapshots.append(s)
                return 'edge'
        sim=Simulator([task(0),task(1,20)],Spy(),NODES,False)
        rows=sim.run()
        n=snapshots[1].edge
        self.assertEqual(n.cpu_running,0)
        self.assertEqual(n.queue_length,0)
        self.assertEqual(n.committed_count,1)
        self.assertEqual(n.transmitting_count,1)
        self.assertEqual(n.committed_work_ms,200)
        self.assertEqual(n.observed_at_ms,20)
        self.conserve(rows)

    def test_running_estimate_does_not_reveal_actual_finish(self):
        states=[]
        class Spy:
            def select_node(self,t,s):
                states.append(s);return 'local'
        rows=Simulator([task(0,work=10000),task(1,50)],Spy(),include_decision_overhead=False).run()
        self.assertEqual(states[1].local.queue_work_ms,150)
        self.assertEqual(states[1].local.cpu_running,1)
        self.conserve(rows)

    def test_wall_blocking_preserves_virtual_arrivals(self):
        import time
        times=[]
        class Slow:
            def select_node(self,t,s):
                times.append(s.local.observed_at_ms);time.sleep(.005);return 'local'
        with patch('app.offloading.simulator.perf_counter',side_effect=[0,.1,1,1.1]):
            rows=Simulator([task(0),task(1,20)],Slow()).run()
        self.assertEqual(times,[0,100])
        self.assertAlmostEqual(rows[1]['decision_queue_ms'],80)
        self.conserve(rows)

    def test_ablation_has_no_charged_decision_or_queue(self):
        with patch('app.offloading.simulator.perf_counter',side_effect=[0,.1,1,1.1]):
            rows=Simulator([task(0),task(1)],FixedStrategy('local'),include_decision_overhead=False).run()
        for r in rows:
            self.assertAlmostEqual(r['decision_wall_ms'],100)
            self.assertEqual(r['decision_ms'],0)
            self.assertEqual(r['decision_queue_ms'],0)
        self.conserve(rows)

    def test_independent_vs_shared_uplink_hand_calculation(self):
        class Split:
            def select_node(self,t,s): return ('edge','cloud')[t.task_id]
        finish=[]
        for mode in ['independent','shared']:
            sim=Simulator([task(0),task(1)],Split(),NODES,False,network_mode=mode,shared_bandwidth_mbps=80)
            rows=sim.run();finish.append([r['cpu_started_at_ms'] for r in rows]);self.conserve(rows)
        self.assertEqual(finish,[[110,110],[110,210]])

    def test_serial_download_and_full_duplex(self):
        # Both CPUs finish at 160. Shared download serializes the two 1.6 ms results.
        class Split:
            def select_node(self,t,s): return ('edge','cloud')[t.task_id]
        rows=Simulator([Task(i,.000001,0,100,0,10000) for i in range(2)],Split(),NODES,False,
                       network_mode='shared',shared_bandwidth_mbps=80).run()
        self.assertAlmostEqual(rows[1]['completed_at_ms']-rows[0]['completed_at_ms'],1.6)
        self.conserve(rows)

    def test_complete_all_vs_drop_cpu_wait_and_consumption(self):
        ts=[task(i,deadline=50) for i in range(3)]
        all_rows=Simulator(ts,FixedStrategy('local'),include_decision_overhead=False).run()
        sim=Simulator(ts,FixedStrategy('local'),include_decision_overhead=False,deadline_policy='drop_if_expired')
        dropped=sim.run()
        self.assertEqual(metrics(all_rows)['completion_rate'],1)
        self.assertEqual(metrics(all_rows)['deadline_met_rate'],0)
        self.assertEqual([r['compute_ms'] for r in dropped],[100,0,0])
        self.assertEqual(metrics(dropped)['drop_rate'],1)
        self.assertEqual(sim.nodes['local'].cpu.count,0)
        self.assertEqual(sim.nodes['local'].jobs,{})
        self.assertEqual(sim.nodes['local'].busy_ms,100)
        self.conserve(dropped)

    def test_drop_after_upload_and_release_shared_resources(self):
        sim=Simulator([task(0,deadline=50),task(1,deadline=50)],FixedStrategy('edge'),NODES,False,
                      network_mode='shared',deadline_policy='drop_if_expired')
        rows=sim.run()
        self.assertEqual([r['network_ms'] for r in rows],[110,110])
        self.assertTrue(all(r['compute_ms']==0 and r['dropped'] for r in rows))
        self.assertEqual(sim.nodes['edge'].upload.resource.count,0)
        self.assertEqual(sim.nodes['edge'].upload.pending,{})
        self.assertEqual(sim.nodes['edge'].jobs,{})
        self.conserve(rows)

    def test_drop_after_decision(self):
        with patch('app.offloading.simulator.perf_counter',side_effect=[0,.1]):
            rows=Simulator([task(deadline=50)],FixedStrategy('local'),deadline_policy='drop_if_expired').run()
        self.assertTrue(rows[0]['dropped']);self.assertEqual(rows[0]['compute_ms'],0);self.conserve(rows)

    def test_reset_resources_and_identical_inputs(self):
        ts=[task(0),task(1)]
        a=Simulator(ts,FixedStrategy('edge'),NODES,False)
        b=Simulator(ts,FixedStrategy('edge'),NODES,False)
        self.assertIsNot(a.env,b.env)
        self.assertIsNot(a.decision_engine,b.decision_engine)
        self.assertIsNot(a.nodes['edge'].upload,b.nodes['edge'].upload)
        ar=a.run();br=b.run()
        self.assertEqual([r['completed_at_ms'] for r in ar],[r['completed_at_ms'] for r in br])
        self.assertEqual([r['task'] for r in ar],[asdict(t) for t in ts])
        with self.assertRaises(RuntimeError):a.run()

    def test_no_labels_or_future_tasks_in_policy_contract(self):
        seen=[]
        class Spy:
            def select_node(self,t,s):
                seen.append(asdict(t));return 'local'
        Simulator([task(0),task(1,1000)],Spy(),include_decision_overhead=False).run()
        self.assertEqual(len(seen),2)
        self.assertTrue(all('workload_ms' not in x and 'face_count' not in x and 'source_path' not in x for x in seen))
        self.assertEqual(seen[0]['estimated_workload_ms'],200)
        self.assertEqual(DecisionTask.observe(task(), 'oracle').estimated_workload_ms,100)

    def test_calibration_disjoint_and_target_label_invariance(self):
        train=[dict(dataset='lfw',source_path='train',workload_ms=321)]
        test=[dict(dataset='lfw',source_path='test',workload_ms=999)]
        self.assertEqual(calibration_estimate(train,test),321)
        test[0]['workload_ms']=1
        self.assertEqual(calibration_estimate(train,test),321)
        with self.assertRaisesRegex(ValueError,'overlap'):calibration_estimate(train,train)
        with self.assertRaises(ValueError):calibration_estimate([],test)

    def test_oracle_and_formal_modes_labelled(self):
        for overhead in (True,False):
            x=experiment(count=2,include_decision_overhead=overhead)
            self.assertEqual(x['information_mode'],'realistic')
            self.assertEqual(x['comparison_scope'],'end_to_end' if overhead else 'selection_quality_ablation')
            for s in x['strategies'].values(): self.conserve(s['tasks'])
        self.assertEqual(experiment(count=1,information_mode='oracle')['information_mode'],'oracle')


class AdditionalValidation(unittest.TestCase):
    conserve = EventValidation.conserve
    def test_latency_policy_accounts_for_upload_commitment(self):
        from dataclasses import replace
        state=Simulator([],FixedStrategy('local')).get_state()
        t=DecisionTask.observe(Task(0,.001,1,100,0,1000,estimated_workload_ms=100))
        policy=LatencyAwareStrategy()
        self.assertEqual(policy.select_node(t,state),'edge')
        state=replace(state,edge=replace(state.edge,committed_count=1,committed_work_ms=1000))
        self.assertEqual(policy.select_node(t,state),'local')

    def test_randomized_time_conservation_and_cpu_capacity(self):
        import random
        rng=random.Random(12)
        for mode in ('independent','shared'):
            for drop in ('complete_all','drop_if_expired'):
                ts=[Task(i,rng.uniform(.01,1),1,rng.uniform(1,100),rng.uniform(0,100),50) for i in range(20)]
                sim=Simulator(ts,LatencyAwareStrategy(),include_decision_overhead=False,
                              network_mode=mode,deadline_policy=drop)
                rows=sim.run();self.conserve(rows)
                for name in sim.nodes:
                    intervals=sorted((r['cpu_started_at_ms'],r['cpu_completed_at_ms']) for r in rows
                                     if r['selected_node']==name and r['cpu_started_at_ms'] is not None)
                    for a,b in zip(intervals,intervals[1:]):self.assertLessEqual(a[1],b[0])
                    self.assertEqual(sim.nodes[name].cpu.count,0)
                    self.assertEqual(sim.nodes[name].jobs,{})

    def test_exact_deadline_and_return_drop(self):
        r=Simulator([task(work=100,deadline=100)],FixedStrategy('local'),include_decision_overhead=False,
                    deadline_policy='drop_if_expired').run()[0]
        self.assertTrue(r['completed']);self.assertTrue(r['deadline_met'])
        sim=Simulator([task(deadline=171)],FixedStrategy('edge'),NODES,False,deadline_policy='drop_if_expired')
        r=sim.run()[0]
        self.assertTrue(r['dropped']);self.assertEqual(r['compute_ms'],50)
        self.assertAlmostEqual(r['network_ms'],121.6)
        self.conserve([r])

    def test_laya_payload_excludes_labels(self):
        import json
        from contextlib import contextmanager
        from io import BytesIO
        from app.offloading.laya_client import LayaStrategy
        @contextmanager
        def response(req,timeout):
            payload=json.loads(req.data)
            self.assertEqual(set(payload['task']),set(asdict(DecisionTask.observe(task()))))
            self.assertNotIn('face_count',payload['task'])
            self.assertNotIn('workload_ms',payload['task'])
            self.assertNotIn('source_path',payload['context'])
            yield BytesIO(b'{"node":"edge"}')
        state=Simulator([],FixedStrategy('local')).get_state()
        with patch('app.offloading.laya_client.urlopen',side_effect=response):
            self.assertEqual(LayaStrategy().select_node(DecisionTask.observe(task()),state),'edge')
        with self.assertRaises(TypeError):LayaStrategy().select_node(task(),state)


    def test_shared_links_are_full_duplex_hand_calculation(self):
        class Split:
            def select_node(self,t,s):return ('edge','cloud')[t.task_id]
        ts=[Task(0,.000001,0,2,0,1000,result_size_kb=1000),Task(1,1,0,2,30,1000)]
        sim=Simulator(ts,Split(),NODES,False,network_mode='shared',shared_bandwidth_mbps=80)
        rows=sim.run()
        # A download 21.0001..121.0001 overlaps B upload 40..140.
        self.assertAlmostEqual(rows[0]['completed_at_ms'],121.0001)
        self.assertAlmostEqual(rows[1]['cpu_started_at_ms'],140)
        self.assertIsNot(sim.nodes['edge'].upload.resource,sim.nodes['edge'].download.resource)
        self.conserve(rows)

    def test_stage_partition_excludes_return_from_cpu_work(self):
        states=[]
        class Spy:
            def select_node(self,t,s):states.append(s);return 'edge'
        Simulator([task(0),task(1,20),task(2,115),task(3,165)],Spy(),NODES,False).run()
        self.assertEqual(states[2].edge.cpu_running,1)
        self.assertEqual(states[2].edge.committed_count,1)
        self.assertEqual(states[3].edge.returning_count,1)
        self.assertEqual(states[3].edge.cpu_running,0)
        self.assertEqual(states[3].edge.queue_work_ms,0)
        self.assertEqual(states[3].edge.committed_count,2)
        self.assertEqual(states[3].edge.committed_work_ms,400)

if __name__=='__main__':unittest.main()
