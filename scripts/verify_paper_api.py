"""HTTP backwards compatibility and opt-in estimator/policy validation."""
from pathlib import Path
import json,requests
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'work/paper-improvements'
s=json.loads((OUT/'results/estimator-evaluation.json').read_text());base='http://127.0.0.1:8080/api/offloading';checks=[]
def check(name,condition):
 assert condition,name
 checks.append(name);print('PASS',name,flush=True)
def post(body):return requests.post(base+'/experiments',json=body,timeout=300)
models=requests.get(base+'/estimators',timeout=30).json()
check('registered models discoverable',set(s['model_ids'].values()) <= {m['id'] for m in models})
keys=requests.get(base+'/status',timeout=30).json()['available_strategies']
check('eight additive policy keys',len(keys)==8 and 'latency_aware_v2' in keys and 'laya_v2' in keys)
b=dict(workload_mode='measured',profile_id=s['test_profile_ids']['lfw'],count=2,seed=11,estimator_id=s['model_ids']['median'])
r=post(dict(b,count=1,strategies=keys));check('all eight true policies HTTP',r.status_code==200);a=r.json()
check('all eight same actual input',all([t['task'] for t in v['tasks']]==a['workload'] for v in a['strategies'].values()))
check('both AI versions real audited decisions',all(a['strategies'][k]['tasks'][0]['decision_audit_id'] for k in ('laya','laya_v2')))
r=post(dict(b,estimator_id=s['model_ids'][s['best_feature']],strategies=['local_only','latency_aware_v2']));check('feature model HTTP',r.status_code==200);f=r.json()
check('actual service remains true',all(t['compute_ms']==t['task']['workload_ms'] for t in f['strategies']['local_only']['tasks']))
check('decision DTO hides ground truth',all(not {'face_count','workload_ms','actual_workload_ms'} & t['decision_input'].keys() for v in f['strategies'].values() for t in v['tasks']))
for name,extra in [('missing_model',dict(estimator_id='0'*64)),('invalid_id',dict(estimator_id='../x')),('two_calibrations',dict(calibration_profile_id='a057ded0f08c4837beff2ffd02f390ee')),('overlap',dict(profile_id='44156f8feb7a49269ec3bc6424b5e176')),('oracle_with_model',dict(information_mode='oracle')),('synthetic_with_model',dict(workload_mode='synthetic',profile_id=None)),('dqn',dict(strategies=['dqn'])),('ddqn',dict(strategies=['ddqn']))]:
 check('reject '+name,post(dict(b,**extra)).status_code==422)
r=post(dict(b,strategies=['latency_aware_v2'],include_decision_overhead=False));check('v2 ablation',r.status_code==200 and r.json()['strategies']['latency_aware_v2']['tasks'][0]['decision_ms']==0)
(OUT/'paper-api-results.json').write_text(json.dumps(dict(passed=len(checks),checks=checks,eight_policy_result=a,feature_result=f),ensure_ascii=False,indent=2),encoding='utf-8')
print('TOTAL',len(checks),'PASSED')
