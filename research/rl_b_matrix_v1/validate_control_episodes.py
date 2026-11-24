"""Post-run controlled Validation only: actual whole-episode costs, no updates."""
import gzip,hashlib,json,os,shutil,sys,zipfile
from pathlib import Path
BASE=Path(__file__).resolve().parent
ROOT=Path('/tmp/candidate-controls');ROOT.mkdir()
with zipfile.ZipFile(BASE/'candidate-run.zip') as z:
    manifest=json.loads(z.read('RUN_SHA256.json'))
    for name in z.namelist():
        p=(ROOT/name).resolve();assert p.is_relative_to(ROOT);p.parent.mkdir(parents=True,exist_ok=True)
        b=z.read(name)
        if name in manifest:assert hashlib.sha256(b).hexdigest()==manifest[name]
        p.write_bytes(b)
os.environ['DATABASE_URL']='sqlite:///:memory:'
sys.path[:0]=[str(ROOT/'runtime/backend'),str(ROOT/'tools')]
import numpy as np
from evidence import task,W,conservation,CapacityAudit
from design import B,config
from app.offloading.simulator import Simulator
from app.offloading.agents49.adapter import load_agent,Agent49Policy
from common import canonical,digest

OUT=BASE/'control-validation';OUT.mkdir()
specs=[('cpu_idle','ec_boundary',[],200),
       ('cpu_busy','ec_boundary',[(i,float(i),.1,W,'edge') for i in range(3)],200),
       ('link_idle','network_4',[],100),('link_busy','network_4',[(0,0.,1.,W,'cloud')],100),
       ('remote_idle','local_entry',[],500),
       ('remote_busy','local_entry',[(i,float(i),.1,W,'edge' if i<6 else 'cloud') for i in range(18)],500)]
def run(spec,agent=None,probe_action=None):
    name,network,prefix,at=spec;forced={i:node for i,t,s,w,node in prefix}
    work=[task(i,t,s,w) for i,t,s,w,node in prefix]+[task(99,at)]
    adapter=Agent49Policy(agent) if agent is not None else None
    class Policy:
        def select_node(self,t,state):
            if t.task_id!=99:return forced[t.task_id]
            return adapter.select_node(t,state) if adapter is not None else ('local','edge','cloud')[probe_action]
    sim=Simulator(work,Policy(),include_decision_overhead=False,**config(dict(nodes=B[network])))
    audit=CapacityAudit(sim);sim.start()
    while sim.env.peek()!=float('inf'):sim.env.step();audit.record()
    rows=sorted(sim.results,key=lambda r:r['task_id']);conservation(rows)
    cost=sum(r['total_latency_ms']/1000+int(not r['deadline_met']) for r in rows)
    probe=next(r for r in rows if r['task_id']==99)
    return dict(case=name,node=probe['selected_node'],probe_latency_ms=probe['total_latency_ms'],episode_cost=cost,
        tasks=rows,events=sim.events,capacity_maxima=audit.maxima,decision=None if adapter is None else adapter.decisions[-1])

def save(name,obj):
    (OUT/name).write_bytes(gzip.compress(canonical(obj),compresslevel=3,mtime=0))
fixed={}
for spec in specs:
    fixed[spec[0]]=[]
    for action in range(3):
        result=run(spec,probe_action=action);fixed[spec[0]].append(result);save(f'{spec[0]}-fixed{action}.json.gz',result)
rows=[]
checkpoints=json.loads((ROOT/'candidate-results/checkpoints.json').read_text())
old_evidence=json.loads((ROOT/'results/event-evidence/event-reversals.json').read_text())
for meta in checkpoints:
    if meta['step']!=9600:continue
    key=f'{meta["algorithm"]}-s{meta["seed"]}';folder=ROOT/f'candidate-results/models/{key}/checkpoints/09600'
    agent=load_agent(meta['algorithm'],folder/'policy.npz',meta['sha256'],contract_index=folder/'input-contract-index.json');agent.gamma=1
    before=digest(agent.rng.bit_generator.state)
    for spec in specs:
        result=run(spec,agent=agent)
        assert result['decision']['raw_features']==list(old_evidence[spec[0]]['observation']['features'])
        best=min(fixed[spec[0]],key=lambda x:x['episode_cost'])
        row=dict(policy_key=key,case=spec[0],selected_node=result['node'],probe_latency_ms=result['probe_latency_ms'],episode_cost=result['episode_cost'],
            best_probe_action_hindsight=best['node'],best_episode_cost=best['episode_cost'],episode_cost_regret=result['episode_cost']-best['episode_cost'],
            q_values=result['decision']['q_values'],note='Last-probe counterfactual completed costs only; never used as an agent input or training label')
        rows.append(row);save(f'{key}-{spec[0]}.json.gz',result)
    assert before==digest(agent.rng.bit_generator.state)
result=dict(verdict='PASS',models=6,scenarios=6,gradient_updates=0,formal_test=False,control_rows=rows,
    fixed_counterfactuals=18,model_probe_episodes=36,training_dispatches=0)
(OUT/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result),flush=True)
