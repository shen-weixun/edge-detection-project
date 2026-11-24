"""Full B event-only gate: real events, no neural actions/Replay/gradient updates."""
import json
from common import ROOT,digest,write,file_sha
from design import load_data,config
from evidence import AuditedIntegralEnv,conservation
from app.offloading.models import Task
from app.offloading.strategies import LatencyAwareV2Strategy
from app.offloading.integration_contract import feature_vector
from app.offloading.agents49.input_contract import InputSpec,prepare_state
from candidate_common import OUT,gzwrite,resources,resource_guard

def run():
    assert json.loads((ROOT/'results/PREFLIGHT_PASS.json').read_text())['passed']
    assert file_sha(ROOT/'results/design/training-manifest.json')=='e21e58ebdfa1c4c8acbe5899ee112323bc75b258c148bb577fe9f46fd4bf9279'
    assert file_sha(ROOT/'results/design/validation-manifest.json')=='6b104b1e98d982d0aad7cdca96fd14d5c3d50c3116f56296dab2e19e2ac1e23a'
    t=json.loads((ROOT/'results/design/training-manifest.json').read_text());v=json.loads((ROOT/'results/design/validation-manifest.json').read_text())
    load_data() # Includes path/content/group Train/Validation separation guards.
    for case in t['training']:
        assert digest({k:x for k,x in case.items() if k not in ('epsilon','exogenous_sha256')})==case['exogenous_sha256']
    for case in v['cases']:
        assert digest({k:x for k,x in case.items() if k!='exogenous_sha256'})==case['exogenous_sha256']
    selected=[c for c in t['training'] if c['seed']==42 and c['round']==0];assert len(selected)==48
    results=[]
    for i,case in enumerate(selected):
        env=AuditedIntegralEnv([Task(**r) for r in case['tasks']],**config(case));obs=env.reset();reward=0.;actions=[]
        while obs is not None:
            prepared=prepare_state(feature_vector(*obs),InputSpec())
            node=LatencyAwareV2Strategy().select_node(*obs);action=('local','edge','cloud').index(node)
            assert action in prepared.available_actions
            obs,r,done,info=env.step(action);reward+=r;actions.append(action)
        rows=env.sim.results;assert len(rows)==100 and all(r['completed'] and not r['dropped'] for r in rows)
        error=conservation(rows);cost=sum(r['total_latency_ms']/1000+int(not r['deadline_met']) for r in rows)
        assert abs(reward+cost)<1e-6 and abs(env.sim.area_ms-sum(r['total_latency_ms'] for r in rows))<1e-6
        row=dict(cell=case['cell'],exogenous_sha256=case['exogenous_sha256'],completed=100,decisions=100,
                 gradient_updates=0,time_error_ms=error,reward_error=abs(reward+cost),capacity_maxima=env.capacity_audit.maxima,verdict='PASS')
        gzwrite(OUT/f'preflight/cell-{i:02d}.json.gz',dict(summary=row,tasks=rows,events=env.sim.events,cost_events=env.sim.cost_events))
        results.append(row)
        if (i+1)%12==0:print(f'Event preflight {i+1}/48 cells PASS',flush=True)
    write(OUT/'preflight/event-only-summary.json',dict(verdict='PASS',cells=48,decisions=4800,gradient_updates=0,cases=results))
    write(OUT/'preflight/SOURCE_AND_EVENT_GATE_PASS.json',dict(verdict='PASS',smoke_source_verified=True,
        historical_contracts_verified=56,original_regression_tests=130,event_cells=48,training_manifest_sha256=file_sha(ROOT/'results/design/training-manifest.json'),
        validation_manifest_sha256=file_sha(ROOT/'results/design/validation-manifest.json'),resources=resource_guard()))

if __name__=='__main__':run()
