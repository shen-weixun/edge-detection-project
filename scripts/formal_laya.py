"""Reuse and re-audit genuine Laya evidence: zero additional model calls."""
from pathlib import Path
import json,csv,shutil,hashlib
ROOT=Path(__file__).resolve().parents[1];O=ROOT/'work/formal-evaluation/laya';O.mkdir(parents=True,exist_ok=True);old=ROOT/'work/paper-improvements';R=old/'results'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def csvout(p,rows):
 with p.open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
records=read(R/'laya-diagnostics.json');audit={a['audit_id']:a for a in map(json.loads,(R/'laya-diagnostic-audit.jsonl').read_text().splitlines())};rows=[]
for r in records:
 a=audit[r['response']['audit_id']];choice=a['raw_output']['answers']['offload_target']['choice'];assert choice==a['final_choice']==r['response']['node'];assert not a['fallback_used'];assert a['input_state']['task']==r['payload']['task'];assert not {'face_count','workload_ms','source_path'} & r['payload']['task'].keys()
 rows.append(dict(kind=r['kind'],case=r['case'],order='>'.join(r.get('order',[])),repeat=r.get('repeat',''),variant=r['variant'],expected_lowest_estimated_cost=r['expected'],raw_choice=choice,final_choice=r['response']['node'],correct=choice==r['expected'],http_wall_ms=r['wall_ms'],worker_elapsed_ms=a['elapsed_ms'],audit_id=a['audit_id'],original_timestamp=a['timestamp'],evidence_scope='REUSED_GENUINE_DIAGNOSTIC_NOT_NEW_INFERENCE',costs_ms_json=json.dumps(r['costs_ms'])))
csvout(ROOT/'work/formal-evaluation/laya_diagnostic.csv',rows)
for name in ('laya-diagnostics.json','laya-diagnostic-audit.jsonl','laya-diagnostic-summary.json'):shutil.copy2(R/name,O/name)
# Retain only historical reference/seed11 raw experiments used in the cost tables.
trace_audit={a['audit_id']:a for a in map(json.loads,(old/'matrix-laya-audit.jsonl').read_text().splitlines())};costs=[];ids=[]
for p in (old/'matrix').glob('*.json'):
 x=read(p);req=x['request'];name=p.name
 if '-reference-' not in name or req['seed']!=11 or 'median' not in name:continue
 scope='RECORDED_CHARGED_COST' if req['include_decision_overhead'] else 'RECORDED_REAL_MODEL_ABLATION'
 for strategy,result in x['strategies'].items():
  if strategy not in ('laya','laya_v2'):continue
  for t in result['tasks']:
   a=trace_audit[t['decision_audit_id']];assert a['final_choice']==t['selected_node']==a['raw_output']['answers']['offload_target']['choice'];assert a['input_state']['task']==t['decision_input'];assert not a['fallback_used'];ids.append(a['audit_id'])
  q=result['summary'];costs.append(dict(source_file=name,dataset='lfw' if name.startswith('lfw') else 'wider_train',load=name.split('-')[2],strategy=strategy,scope=scope,n=q['task_count'],avg_latency_ms=q['avg_latency_ms'],p95_latency_ms=q['p95_latency_ms'],deadline_met_rate=q['deadline_met_rate'],decision_ms=q['components_ms']['decision_ms'],decision_queue_ms=q['components_ms']['decision_queue_ms'],network_ms=q['components_ms']['network_ms'],queue_ms=q['components_ms']['queue_ms'],compute_ms=q['components_ms']['compute_ms'],avg_decision_wall_ms=q['avg_decision_wall_ms'],scope_note='PREVIOUS_6_IMAGE_EPISODE_NOT_CURRENT_100_IMAGE_TEST'))
  (O/'historical-raw').mkdir(exist_ok=True);shutil.copy2(p,O/'historical-raw'/p.name)
assert len(rows)==90 and len(costs)==24
csvout(O/'historical_cost_comparison.csv',costs)
(O/'historical-audit.jsonl').write_text(''.join(json.dumps(trace_audit[i],ensure_ascii=False)+'\n' for i in ids),encoding='utf-8')
manifest=dict(new_model_calls=0,diagnostic_rows=90,historical_cost_rows=len(costs),historical_task_choices=len(ids),all_raw_choices_match=True,no_fallback=True,source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [R/'laya-diagnostics.json',R/'laya-diagnostic-audit.jsonl',R/'laya-diagnostic-summary.json']},limits='All evidence reused; this is not new inference or a current 100-image Laya evaluation. Existing charged and ablation runs made true separate model calls in their original round; reopening them is not a new replay experiment.')
(O/'reuse-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8');print('LAYA REUSE VERIFIED',manifest['diagnostic_rows'],manifest['historical_task_choices'],'new calls=0')
