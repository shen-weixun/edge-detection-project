"""Compare original, V2 and separately labelled workload-oracle reference."""
import sys,json,csv
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from paper_cases import paper_cases
from acceptance_reference import check_run
from app.offloading.simulator import Simulator
from app.offloading.strategies import LatencyAwareStrategy,estimate_latency
from app.offloading.latency_v2 import LatencyAwareV2Strategy,estimate_v2

out=Path('/tmp/paper-improvements');out.mkdir(exist_ok=True);results={};flat=[]
for case in paper_cases():
    for name in ['latency_aware','latency_aware_v2','oracle_reference']:
        policy=LatencyAwareStrategy() if name=='latency_aware' else LatencyAwareV2Strategy()
        snapshots={}
        class Capture:
            def select_node(self,t,state):
                estimates={n.name:(dict(total_ms=estimate_latency(t,n)) if name=='latency_aware' else estimate_v2(t,n)) for n in state.nodes()}
                selected=case['forced_prefix'].get(t.task_id)
                if selected is None:selected=policy.select_node(t,state)
                snapshots[t.task_id]=dict(observed_at_ms=state.local.observed_at_ms,estimates=estimates,forced_prefix=t.task_id in case['forced_prefix'])
                return selected
        sim=Simulator(case['tasks'],Capture(),case['nodes'],False,information_mode='oracle' if name=='oracle_reference' else 'realistic')
        rows=sim.run()
        verification=check_run(sim,rows)
        for r in rows:
            assert abs(r['total_latency_ms']-sum(r[k] for k in ['network_ms','queue_ms','compute_ms','decision_ms','decision_queue_ms']))<1e-7
            s=snapshots[r['task_id']]
            flat.append(dict(case=case['name'],strategy=name,task_id=r['task_id'],forced_prefix=s['forced_prefix'],observed_at_ms=s['observed_at_ms'],local_estimate_ms=s['estimates']['local']['total_ms'],edge_estimate_ms=s['estimates']['edge']['total_ms'],cloud_estimate_ms=s['estimates']['cloud']['total_ms'],selected=r['selected_node'],actual_latency_ms=r['total_latency_ms'],completed_at_ms=r['completed_at_ms'],deadline_met=r['deadline_met']))
        results[case['name']+'/'+name]=dict(rows=rows,snapshots=snapshots,node_statistics=sim.node_statistics(),independent_reference=verification)
with (out/'latency-controlled.csv').open('w',newline='',encoding='utf-8-sig') as f:
    w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
(out/'latency-controlled.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print('CONTROLLED COMPLETE',len(paper_cases()),'cases,',len(flat),'task results',flush=True)
