"""One frozen Laya V2 candidate, compared with unchanged legacy inputs.
No prompt search, cost-based output substitution, or candidate sorting.
"""
import sys,json,itertools,time,os
from pathlib import Path
from dataclasses import asdict,replace
from statistics import mean
from math import ceil
from urllib.request import Request,urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from acceptance_reference import scenarios
from app.offloading.models import DecisionTask
from app.offloading.simulator import Simulator
from app.offloading.strategies import FixedStrategy,estimate_latency
from app.offloading.latency_v2 import estimate_v2

out=Path('/tmp/paper-improvements');out.mkdir(exist_ok=True);records=[]
def call(payload):
    started=time.perf_counter()
    req=Request('http://laya:8001/decide',data=json.dumps(payload,allow_nan=False).encode(),headers={'Content-Type':'application/json'},method='POST')
    with urlopen(req,timeout=180) as response:result=json.load(response)
    return result,(time.perf_counter()-started)*1000

def save():
    (out/'laya-diagnostics.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')

t,sets=scenarios();task=DecisionTask.observe(t)
base=Simulator([],FixedStrategy('local')).get_state()
warm=[]
for variant in ('legacy','v2'):
    result,wall=call(dict(task=asdict(task),nodes=[asdict(n) for n in base.nodes()],variant=variant,context={'kind':'paper_warmup'}));warm.append(dict(variant=variant,result=result,wall_ms=wall))
(out/'laya-warmup.json').write_text(json.dumps(warm,indent=2),encoding='utf-8')
for case,nodes in sets.items():
    state=Simulator([],FixedStrategy('local'),nodes).get_state()
    costs={n.name:estimate_v2(task,n)['total_ms'] for n in state.nodes()};expected=min(costs,key=costs.get)
    for order in itertools.permutations(('local','edge','cloud')):
        for repeat in range(2):
            for variant in ('legacy','v2'):
                payload=dict(task=asdict(task),nodes=[asdict(getattr(state,n)) for n in order],variant=variant,context=dict(kind='paper_permutation',case=case,order=order,repeat=repeat))
                response,wall=call(payload);records.append(dict(kind='permutation',case=case,order=order,repeat=repeat,variant=variant,expected=expected,costs_ms=costs,payload=payload,response=response,wall_ms=wall));save()
        print('PERMUTATION',case,','.join(order),'complete',flush=True)
changes=[('base',None,{}),('edge_rtt','edge',dict(rtt_ms=1000)),('cloud_rtt','cloud',dict(rtt_ms=1000)),('edge_bandwidth','edge',dict(bandwidth_mbps=1)),('cloud_bandwidth','cloud',dict(bandwidth_mbps=1000)),('edge_compute','edge',dict(compute_speed=12)),('cloud_compute','cloud',dict(compute_speed=40)),('edge_cpu_queue','edge',dict(queue_work_ms=6000,queue_length=10)),('cloud_cpu_queue','cloud',dict(queue_work_ms=6000,queue_length=10))]
for name,node,change in changes:
    state=replace(base,**{node:replace(getattr(base,node),**change)}) if node else base
    costs={n.name:estimate_v2(task,n)['total_ms'] for n in state.nodes()};expected=min(costs,key=costs.get)
    for variant in ('legacy','v2'):
        payload=dict(task=asdict(task),nodes=[asdict(n) for n in state.nodes()],variant=variant,context=dict(kind='paper_single_factor',case=name))
        response,wall=call(payload);records.append(dict(kind='single_factor',case=name,variant=variant,expected=expected,costs_ms=costs,payload=payload,response=response,wall_ms=wall));save()
    print('SINGLE_FACTOR',name,flush=True)
audit={a['audit_id']:a for a in map(json.loads,Path('/profiles/laya_audit/decisions.jsonl').read_text(encoding='utf-8').splitlines())}
raw=[]
for r in records:
    a=audit[r['response']['audit_id']];assert a['raw_output']['answers']['offload_target']['choice']==a['final_choice']==r['response']['node'];assert not a['fallback_used'] and not a.get('error')
    assert a['input_state']==dict(task=r['payload']['task'],nodes=r['payload']['nodes'])
    if r['variant']=='v2':assert [n['node'] for n in a['state']['candidates']]==[n['name'] for n in r['payload']['nodes']]
    raw.append(a)
(out/'laya-diagnostic-audit.jsonl').write_text(''.join(json.dumps(a,ensure_ascii=False)+'\n' for a in raw),encoding='utf-8')
summary={}
for variant in ('legacy','v2'):
    rs=[r for r in records if r['variant']==variant];per=[r for r in rs if r['kind']=='permutation'];walls=sorted(r['wall_ms'] for r in rs)
    case_info={}
    for case in sets:
        cs=[r for r in per if r['case']==case]
        case_info[case]=dict(correct=sum(r['response']['node']==r['expected'] for r in cs),total=len(cs),order_invariant=len({r['response']['node'] for r in cs})==1,choices=[r['response']['node'] for r in cs],repeat_consistent=sum(cs[i]['response']['node']==cs[i+1]['response']['node'] for i in range(0,len(cs),2)))
    summary[variant]=dict(total=len(rs),legal=sum(r['response']['node'] in ('local','edge','cloud') for r in rs),correct=sum(r['response']['node']==r['expected'] for r in rs),mean_wall_ms=mean(walls),p95_wall_ms=walls[ceil(.95*len(walls))-1],cases=case_info,single_factor_correct=sum(r['response']['node']==r['expected'] for r in rs if r['kind']=='single_factor'))
summary['raw_choices_verified']=len(raw);summary['truncated']=sum(bool(a['raw_output'].get('usage',{}).get('truncated')) for a in raw)
(out/'laya-diagnostic-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary),flush=True)
