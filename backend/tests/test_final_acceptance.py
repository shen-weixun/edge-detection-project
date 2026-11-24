import unittest
from dataclasses import asdict,replace
from app.offloading.models import Task,DecisionTask,NodeConfig
from app.offloading.simulator import Simulator,DEFAULT_NODES
from app.offloading.strategies import FixedStrategy,LatencyAwareStrategy,estimate_latency
from acceptance_reference import scenarios,single_cost,check_run

class FinalAcceptance(unittest.TestCase):
    def scenario(self,key,winner):
        task,sets=scenarios();nodes=sets[key]
        s=Simulator([task],LatencyAwareStrategy(),nodes,False)
        state=s.get_state();observable=DecisionTask.observe(task)
        expected={n:single_cost(task,cfg,n,True)['total_latency_ms'] for n,cfg in nodes.items()}
        self.assertEqual(min(expected,key=expected.get),winner)
        self.assertEqual(LatencyAwareStrategy().select_node(observable,state),winner)
        for n in state.nodes():self.assertAlmostEqual(estimate_latency(observable,n),expected[n.name])
        row=s.run()[0];self.assertEqual(row['selected_node'],winner)
        self.assertAlmostEqual(row['total_latency_ms'],single_cost(task,nodes[winner],winner)['total_latency_ms'])
        check_run(s,[row])
        # Verify all alternatives too; no choice is forced in Latency-aware.
        for name in nodes:
            fixed=Simulator([task],FixedStrategy(name),nodes,False);rows=fixed.run();check_run(fixed,rows)
            self.assertAlmostEqual(rows[0]['total_latency_ms'],single_cost(task,nodes[name],name)['total_latency_ms'])

    def test_scenario_A_local_advantage(self):self.scenario('A_local','local')
    def test_scenario_B_edge_advantage(self):self.scenario('B_edge','edge')
    def test_scenario_C_cloud_advantage(self):self.scenario('C_cloud','cloud')

    def test_single_remote_parameter_monotonicity_and_arithmetic(self):
        t,_=scenarios()
        for node in ('edge','cloud'):
            for field,values,direction in [('rtt_ms',[0,20,200,1000],1),('bandwidth_mbps',[1,8,80,1000],-1),('speed',[1,3,8,20],-1)]:
                totals=[]
                for value in values:
                    configs=dict(DEFAULT_NODES);configs[node]=replace(configs[node],**{field:value})
                    sim=Simulator([t],FixedStrategy(node),configs,False);rows=sim.run();check_run(sim,rows)
                    manual=single_cost(t,configs[node],node)
                    self.assertAlmostEqual(rows[0]['total_latency_ms'],manual['total_latency_ms'])
                    totals.append(rows[0]['compute_ms'] if field=='speed' else rows[0]['network_ms'])
                self.assertTrue(all(direction*(b-a)>=-1e-9 for a,b in zip(totals,totals[1:])))

    def test_shared_capacity_reference_and_full_duplex(self):
        t,_=scenarios();ts=[replace(t,task_id=i) for i in range(4)]
        nodes={n:NodeConfig(2,0 if n=='local' else 20,80) for n in DEFAULT_NODES}
        class Split:
            def select_node(self,t,s):return ('edge','cloud')[t.task_id%2]
        results=[]
        for mode in ('independent','shared'):
            sim=Simulator(ts,Split(),nodes,False,network_mode=mode,shared_bandwidth_mbps=80)
            rows=sim.run();check_run(sim,rows);results.append(rows)
        self.assertGreater(results[1][1]['cpu_started_at_ms'],results[0][1]['cpu_started_at_ms'])

    def test_lindley_overload_growth_and_queue_integral(self):
        for gap in (200,100,20):
            tasks=[Task(i,.01,1,100,i*gap,1000) for i in range(10)]
            sim=Simulator(tasks,FixedStrategy('local'),include_decision_overhead=False)
            rows=sim.run();check_run(sim,rows)
            expected=[i*max(0,100-gap) for i in range(10)]
            self.assertEqual([r['queue_ms'] for r in rows],expected)
            self.assertEqual(sim.node_statistics()['local']['max_queue'],0 if gap>=100 else 8)

    def test_deterministic_replay_ignores_only_wall_measurement(self):
        tasks=[Task(i,.1+i*.01,1,100+i,17*i,1000) for i in range(20)]
        outputs=[]
        for _ in range(2):
            sim=Simulator(tasks,LatencyAwareStrategy(),include_decision_overhead=False,network_mode='shared')
            rows=sim.run();check_run(sim,rows)
            outputs.append([{k:v for k,v in r.items() if k!='decision_wall_ms'} for r in rows])
        self.assertEqual(*outputs)

    def test_target_true_work_and_faces_do_not_change_current_observation(self):
        t,_=scenarios()
        self.assertEqual(DecisionTask.observe(t),DecisionTask.observe(replace(t,workload_ms=99999,face_count=999)))
        self.assertNotIn('workload_ms',asdict(DecisionTask.observe(t)))
        self.assertNotIn('face_count',asdict(DecisionTask.observe(t)))
