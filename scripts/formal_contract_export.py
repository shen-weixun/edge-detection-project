"""Machine-readable additive contract export; contains observable examples only."""
from dataclasses import fields,MISSING
from pathlib import Path
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.offloading.models import Task,DecisionTask,NodeState,SystemState
from app.offloading.integration_contract import FEATURE_NAMES,decision_request
from app.offloading.simulator import Simulator
from app.offloading.strategies import FixedStrategy
from app.offloading import profiles
from app.offloading.estimators import load_registered
out=profiles.root()/'formal-evaluation'
def schema(cls):return [dict(name=f.name,type=str(f.type),required=f.default is MISSING,**({'default':f.default} if f.default is not MISSING else {})) for f in fields(cls)]
spec=dict(schema='offloading-decision-v1',internal_Task=schema(Task),observable_DecisionTask=schema(DecisionTask),NodeState=schema(NodeState),SystemState=schema(SystemState),feature_names=FEATURE_NAMES,feature_count=len(FEATURE_NAMES),action_mapping={0:'local',1:'edge',2:'cloud'},reward='-total_latency_ms/1000 - (0 if deadline_met else 1)',deadline='arrival_ms+deadline_ms',time_decomposition=['decision_queue_ms','decision_ms','network_ms','queue_ms','compute_ms'],forbidden_model_features=['Task.workload_ms','Task.face_count','future_task_list','future_completed_at_ms'],contract='Canonical dataset-relative POSIX paths; externally verified SHA256 and groups, realistic only; no implicit normalization fitted on test')
(out/'team_interface_schema.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding='utf-8')
ids=json.loads((out/'profile-ids.json').read_text());m=json.loads((out/'evaluation/fit-complete.json').read_text());model=load_registered(m['models']['median']);_,rows=profiles.load(ids['lfw/testing']);r=rows[0]
t=Task(0,arrival_ms=0,deadline_ms=1000,estimated_workload_ms=model.predict(r),**r);state=Simulator([],FixedStrategy('local')).get_state();example=decision_request(DecisionTask.observe(t),state)
(out/'team_contract_example.json').write_text(json.dumps(example,ensure_ascii=False,indent=2),encoding='utf-8');print('CONTRACT EXPORT',len(FEATURE_NAMES))
