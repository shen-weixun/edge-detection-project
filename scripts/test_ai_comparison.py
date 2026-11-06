import unittest,tempfile,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch
from dataclasses import asdict
from app.offloading.models import Task
from app.offloading.simulator import Simulator
from app.offloading.strategies import FixedStrategy
import run_ai_comparison as pilot
class PilotContractTests(unittest.TestCase):
 def test_plan_and_load_basis_are_frozen(self):
  plan,sets,model=pilot.make_plan();self.assertEqual(len(plan['scenarios']),24);self.assertEqual(plan['planned_laya_model_calls']+plan['planned_warmup_calls'],482)
  for s in plan['scenarios']:
   self.assertAlmostEqual(s['reference_mean_service_ms']/s['interval_ms'],s['reference_offered_cpu_load']);self.assertEqual(s['count'],10);self.assertEqual(s['deadline_ms'],1000)
  for d,x in sets.items():self.assertEqual(len({i['image_sha256'] for i in x['images']}),10)
 def test_checkpoint_io_is_outside_decision_clock(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(pilot,'O',Path(tmp)):
   t=Task(0,.1,7,100,0,1000);obs=pilot.Observed(FixedStrategy('local'),{'id':'fixture'},'local');sim=Simulator([t],obs);obs.sim=sim
   with patch('app.offloading.simulator.perf_counter',side_effect=[1.,1.007]):rows=sim.run()
   self.assertAlmostEqual(rows[0]['decision_ms'],7);self.assertAlmostEqual(rows[0]['total_latency_ms'],107);p=Path(tmp)/'raw/decisions/fixture/local/0.json';self.assertTrue(p.exists());record=json.loads(p.read_text());self.assertNotIn('workload_ms',record['task']);self.assertNotIn('face_count',record['task']);self.assertNotIn('source_path',record['task'])
 def test_bad_feature_contract_does_not_start_models(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(pilot,'O',Path(tmp)):
   pilot.save(Path(tmp)/'feature_contract_check.json',{'status':'UNKNOWN'})
   with patch.object(pilot,'warmup') as call:
    with self.assertRaises(AssertionError):pilot.run()
    call.assert_not_called()
 def test_no_state_reused_between_strategies(self):
  t=Task(0,.1,1,100,0,1000)
  with tempfile.TemporaryDirectory() as tmp,patch.object(pilot,'O',Path(tmp)):
   snapshots=[]
   for name in ('first','second'):
    p=pilot.Observed(FixedStrategy('edge'),{'id':'fixture'},name);sim=Simulator([t],p,include_decision_overhead=False);p.sim=sim;rows=sim.run();snapshots.append(asdict(p.records[0]['state']));self.assertEqual(rows[0]['decision_ms'],0)
   self.assertEqual(snapshots[0],snapshots[1])
if __name__=='__main__':unittest.main(verbosity=2)
