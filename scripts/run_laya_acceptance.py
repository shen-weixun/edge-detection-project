"""Genuine Laya order/repeat/cost diagnostics; failures are model findings.
Run inside the backend container. No policy substitution or prompt tuning.
"""
import sys,json,itertools,time,os
from pathlib import Path
from dataclasses import asdict,replace
from urllib.request import Request,urlopen
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from acceptance_reference import scenarios,single_cost
from app.offloading.models import DecisionTask
from app.offloading.simulator import Simulator
from app.offloading.strategies import FixedStrategy
from app.offloading.laya_client import LayaStrategy

out=Path(os.environ.get('ACCEPTANCE_OUTPUT','/tmp/final-acceptance'));out.mkdir(parents=True,exist_ok=True)
task,sets=scenarios();records=[];errors=[]
def save():
    (out/'laya-permutation-results.json').write_text(json.dumps(dict(records=records,errors=errors),ensure_ascii=False,indent=2),encoding='utf-8')
def invoke(body):
    request=Request('http://laya:8001/decide',data=json.dumps(body,allow_nan=False).encode(),headers={'Content-Type':'application/json'},method='POST')
    t=time.perf_counter()
    with urlopen(request,timeout=180) as r:result=json.load(r)
    return result,(time.perf_counter()-t)*1000
try:
    with urlopen('http://laya:8001/health',timeout=10) as r:health=json.load(r)
    (out/'laya-health.json').write_text(json.dumps(health),encoding='utf-8')
    # Explicit warmup is excluded from permutation and repeat counts.
    state=Simulator([],FixedStrategy('local'),sets['A_local']).get_state()
    warm,_=invoke(dict(task=asdict(DecisionTask.observe(task)),nodes=[asdict(n) for n in state.nodes()],context={'kind':'final_acceptance_warmup'}))
    for scenario,nodes in sets.items():
        state=Simulator([],FixedStrategy('local'),nodes).get_state()
        expected=min(nodes,key=lambda n:single_cost(task,nodes[n],n,True)['total_latency_ms'])
        for order in itertools.permutations(('local','edge','cloud')):
            payload=dict(task=asdict(DecisionTask.observe(task)),nodes=[asdict(getattr(state,n)) for n in order])
            for repeat in range(2):
                result,wall=invoke(dict(payload,context={'kind':'final_acceptance_permutation','scenario':scenario,'order':order,'repeat':repeat}))
                record=dict(scenario=scenario,expected=expected,order=order,repeat=repeat,input=payload,response=result,wall_ms=wall)
                records.append(record);save()
            print('LAYA',scenario,','.join(order),[r['response']['node'] for r in records[-2:]],flush=True)
    sim=Simulator([replace(task,task_id=i,arrival_ms=0) for i in range(3)],LayaStrategy(),sets['B_edge'])
    rows=sim.run()
    for i,r in enumerate(rows):
        assert abs(r['decision_queue_ms']-sum(x['decision_ms'] for x in rows[:i]))<1e-7
        assert abs(r['total_latency_ms']-sum(r[k] for k in ('network_ms','queue_ms','compute_ms','decision_ms','decision_queue_ms')))<1e-7
    (out/'laya-serial-decision-results.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
except Exception as e:
    errors.append(dict(type=type(e).__name__,error=str(e)));save();raise
# Verify raw real model output from the append-only service audit.
audits={r['audit_id']:r for r in map(json.loads,Path('/profiles/laya_audit/decisions.jsonl').read_text(encoding='utf-8').splitlines())}
selected=[];truncated=0
for r in records:
    a=audits[r['response']['audit_id']]
    assert a['state']==r['input']
    assert a['final_choice']==a['raw_output']['answers']['offload_target']['choice']==r['response']['node']
    assert not a['fallback_used'] and 'error' not in a
    truncated+=bool(a['raw_output'].get('usage',{}).get('truncated'))
    selected.append(a)
for r in rows:
    a=audits[r['decision_audit_id']]
    assert a['final_choice']==a['raw_output']['answers']['offload_target']['choice']==r['selected_node']
    assert not a['fallback_used']
    truncated+=bool(a['raw_output'].get('usage',{}).get('truncated'))
    selected.append(a)
(out/'laya-raw-audit.jsonl').write_text(''.join(json.dumps(a,ensure_ascii=False)+'\n' for a in selected),encoding='utf-8')
summary={}
for scenario in sets:
    rs=[r for r in records if r['scenario']==scenario]
    repeated=sum(all(x['response']['node']==[r for r in rs if r['order']==order][0]['response']['node'] for x in rs if x['order']==order) for order in itertools.permutations(('local','edge','cloud')))
    summary[scenario]=dict(expected=rs[0]['expected'],choice_counts=dict(Counter(r['response']['node'] for r in rs)),correct=sum(r['response']['node']==r['expected'] for r in rs),total=len(rs),order_invariant=len({r['response']['node'] for r in rs})==1,repeat_consistent_orders=repeated,orders=6,mean_wall_ms=sum(r['wall_ms'] for r in rs)/len(rs))
summary.update(raw_output_matches=len(selected),truncated=truncated,serial_decision_queue_pass=True)
(out/'laya-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary),flush=True)
