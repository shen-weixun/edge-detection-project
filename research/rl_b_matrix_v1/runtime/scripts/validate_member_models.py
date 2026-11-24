"""Inspect supplied member models in isolation; never infer feature semantics."""
import argparse,sys,types,importlib.util,importlib.machinery,json,hashlib,time
from pathlib import Path
import numpy as np

def validate(source,out):
 source=Path(source).resolve();out=Path(out);out.mkdir(parents=True,exist_ok=True)
 files=sorted(p for p in source.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
 before={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
 pkg=types.ModuleType('member_review_pkg');pkg.__path__=[str(source/'app')];sys.modules[pkg.__name__]=pkg
 for name in ('dqn','ddqn'):
  spec=importlib.util.spec_from_file_location(pkg.__name__+'.'+name,source/'app'/(name+'.py'));mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
 rng=np.random.default_rng(20261106);probes=[np.zeros(7),np.ones(7),np.array([.5,.3,.03,.2,.5,.3,.2])]+[np.eye(7)[i] for i in range(7)]+[r for r in rng.uniform(-1,1,(20,7))]
 results={};traces=[]
 for name in ('dqn','ddqn'):
  cls=getattr(sys.modules[pkg.__name__+'.'+name],name.upper());agent=cls();p=source/'models'/(name+'.npz')
  with np.load(p,allow_pickle=False) as data:
   keys=list(data.files);arr=[data['arr_'+str(i)].copy() for i in range(4)]
  assert keys==['arr_'+str(i) for i in range(4)];assert [list(a.shape) for a in arr]==[[7,32],[32],[32,3],[3]];assert all(np.isfinite(a).all() for a in arr)
  initial=[a.copy() for a in agent.online];start=time.perf_counter();agent.load(p);load_ms=(time.perf_counter()-start)*1000
  for state in probes[:3]:agent.act(state,epsilon=0)
  for i,state in enumerate(probes):
   start=time.perf_counter();action=agent.act(state,epsilon=0);ms=(time.perf_counter()-start)*1000;_,q=agent._forward(state.reshape(1,7),agent.online);repeated=[agent.act(state,epsilon=0) for _ in range(20)]
   assert type(action) is int and action in (0,1,2) and np.isfinite(q).all() and action==int(q[0].argmax()) and all(x==action for x in repeated)
   traces.append(dict(model=name,probe=i,scope='SYNTHETIC_NUMERIC_PROBE_NO_SEMANTIC_FEATURE_MAPPING',state=state.tolist(),q_values=q[0].tolist(),action=action,inference_ms=ms,repeat_actions=repeated))
  wrong_dim=None
  try:agent.act(np.zeros(49),epsilon=0)
  except ValueError as e:wrong_dim=type(e).__name__
  assert wrong_dim=='ValueError'
  selected=[r for r in traces if r['model']==name];qs=np.array([r['q_values'] for r in selected]);assert np.any(np.ptp(qs,axis=0)>1e-9)
  results[name]=dict(load_ms=load_ms,keys=keys,shapes=[list(a.shape) for a in arr],all_weights_finite=True,deterministic_probes=len(probes),action_values=sorted({r['action'] for r in selected}),q_varies_with_input=True,architecture='7-32-ReLU-3',weights_exactly_equal_seed42_initialization=all(np.array_equal(a,b) for a,b in zip(initial,arr)),weight_distance_from_seed42=[float(np.linalg.norm(a-b)) for a,b in zip(initial,arr)],mean_inference_ms=float(np.mean([r['inference_ms'] for r in selected])),p95_inference_ms=float(np.quantile([r['inference_ms'] for r in selected],.95)),wrong_49_dim_rejected=True,has_decide_method=hasattr(agent,'decide'),has_training_environment_or_logs=False)
 text=next((source/'app').glob('*.txt'));loader=importlib.machinery.SourceFileLoader(pkg.__name__+'.member_snippet',str(text));spec=importlib.util.spec_from_loader(loader.name,loader);snippet=importlib.util.module_from_spec(spec);loader.exec_module(snippet);errors={}
 for strategy in ('dqn','ddqn','threshold'):
  try:snippet.choose_node(strategy,probes[2])
  except Exception as e:errors[strategy]=dict(type=type(e).__name__,message=str(e))
 assert errors['dqn']['type']==errors['ddqn']['type']=='AttributeError' and errors['threshold']['type']=='TypeError'
 after={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files};assert before==after
 evidence=dict(models=results,source_sha256=before,source_unchanged=True,snippet_errors=errors,training_evidence='NOT VERIFIED; algorithm code and weights alone are not training provenance',formal_integration='BLOCKED',feature_contract=dict(dimension=7,names=None,order=None,units=None,normalization=None,training_data=None,reward=None,training_environment=None,action_mapping_cli=['local','edge','cloud'],training_action_mapping='NOT VERIFIED'),fallback='No fallback observed in supplied act/load implementation; invalid/missing methods in snippet fail instead of providing a valid adapter')
 (out/'model_validation.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8');(out/'member_inference_traces.json').write_text(json.dumps(traces,indent=2),encoding='utf-8');(out/'feature_contract_check.json').write_text(json.dumps(dict(status='DQN/DDQN FORMAL INTEGRATION: BLOCKED',reason='Seven feature semantics/order/units/scaler/training environment/reward provenance absent; no legal 49-to-7 mapping',feature_contract=evidence['feature_contract'],mapping_created=False,weights_modified=False),ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(evidence,ensure_ascii=False),flush=True)
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--source',required=True);a.add_argument('--output',required=True);args=a.parse_args();validate(args.source,args.output)
