import unittest,json
from dataclasses import replace
from app.offloading.models import Task,DecisionTask
from app.offloading.simulator import Simulator
from app.offloading.strategies import FixedStrategy
from app.offloading.integration_contract import feature_vector,decision_request,FEATURE_NAMES,IndexPolicy,run_policy,validate_manifest_split
from app.offloading.rl import OffloadingEnv
class TeamContractTests(unittest.TestCase):
 def setUp(self):self.t=Task(0,.1,3,480,0,1000,width=250,height=250,estimated_workload_ms=600);self.state=Simulator([],FixedStrategy('local')).get_state()
 def test_fixed_order_vector_49(self):
  v=feature_vector(DecisionTask.observe(self.t),self.state);self.assertEqual(len(v),49);self.assertEqual(len(v),len(FEATURE_NAMES));self.assertEqual(FEATURE_NAMES[7],'local.compute_speed')
 def test_ground_truth_changes_do_not_change_observation(self):
  a=feature_vector(DecisionTask.observe(self.t),self.state);b=feature_vector(DecisionTask.observe(replace(self.t,workload_ms=99999,face_count=99)),self.state);self.assertEqual(a,b)
 def test_internal_task_rejected_and_json_contract(self):
  with self.assertRaises(TypeError):feature_vector(self.t,self.state)
  d=json.loads(json.dumps(decision_request(DecisionTask.observe(self.t),self.state)));self.assertNotIn('face_count',d['task']);self.assertNotIn('workload_ms',d['task']);self.assertEqual([n['name'] for n in d['nodes']],['local','edge','cloud'])
 def test_external_index_policy_same_engine_metrics(self):
  r=run_policy([self.t],IndexPolicy(lambda v:1),include_decision_overhead=False);self.assertEqual(r['tasks'][0]['selected_node'],'edge');self.assertEqual(r['summary']['completion_rate'],1)
 def test_bad_actions_and_oracle_rejected(self):
  for action in (-1,3,True,1.,'edge'):
   with self.assertRaises(ValueError):IndexPolicy(lambda v:action).select_node(DecisionTask.observe(self.t),self.state)
  with self.assertRaises(ValueError):run_policy([self.t],IndexPolicy(lambda v:0),information_mode='oracle')
 def test_rl_delayed_reward_matches_same_executor(self):
  tasks=[replace(self.t,task_id=i,arrival_ms=i*10) for i in range(3)];e=OffloadingEnv(tasks);e.reset();done=False;reward=0
  while not done:_,r,done,_=e.step(1);reward+=r
  result=run_policy(tasks,IndexPolicy(lambda v:1),include_decision_overhead=False)
  self.assertEqual([{k:v for k,v in t.items() if k!='decision_wall_ms'} for t in e.sim.results],[{k:v for k,v in t.items() if k!='decision_wall_ms'} for t in result['tasks']]);self.assertAlmostEqual(reward,sum(-t['total_latency_ms']/1000-(not t['deadline_met']) for t in result['tasks']))
 def test_three_way_group_hash_path_split(self):
  rows=[dict(role=role,source_path=str(i),image_sha256=str(i),group=str(i)) for i,role in enumerate(('training','validation','testing'))];validate_manifest_split(rows)
  for field in ('source_path','image_sha256','group'):
   bad=[dict(r) for r in rows];bad[-1][field]=bad[0][field]
   with self.assertRaises(ValueError):validate_manifest_split(bad)
 def test_unavailable_action_rejected(self):
  s=replace(self.state,edge=replace(self.state.edge,available=False))
  with self.assertRaises(ValueError):IndexPolicy(lambda v:1).select_node(DecisionTask.observe(self.t),s)
