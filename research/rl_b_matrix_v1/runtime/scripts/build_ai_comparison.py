"""Re-audit live pilot and publish per-scenario artifacts, never a pooled ranking."""
import sys,json,csv,hashlib,shutil
from pathlib import Path
from dataclasses import asdict
from statistics import mean
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from app.offloading.models import Task,DecisionTask,NodeState,SystemState,NodeConfig
from app.offloading.simulator import Simulator
from app.offloading.strategies import FixedStrategy,estimate_latency
from app.offloading.latency_v2 import estimate_v2
from acceptance_reference import reference
O=Path('/profiles/ai-comparison')
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def csvout(p,rows):
 with p.open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def table(head,rows):return ['|'+'|'.join(head)+'|','|'+'|'.join(['---']*len(head))+'|']+['|'+'|'.join(map(str,row))+'|' for row in rows]
def num(x):return '—' if x is None else f'{float(x):.3f}'
def pct(x):return '—' if x is None else f'{100*float(x):.1f}%'
def doc(name,lines):(O/name).write_text('\n'.join(lines)+'\n',encoding='utf-8')
assert (O/'run-complete.json').exists(),'Wait until live run complete'
plan=read(O/'scenario_manifest.json');subset=read(O/'task_subset_manifest.json');model=read(O/'model-validation/model_validation.json');order=plan['strategy_order'];all_audit={a['audit_id']:a for a in map(json.loads,(Path('/profiles/laya_audit/decisions.jsonl')).read_text(encoding='utf-8').splitlines())};used=[];traces=[];allrows=[];catalog=[];counts={};maxerror=0;est_correct={};w=read(O/'warmup.json')
for warm in w['calls']:
 if warm.get('audit_id'):used.append(warm['audit_id'])
fields=['avg_latency_ms','p95_latency_ms','deadline_met_rate','completion_rate','drop_rate','decision_ms','decision_queue_ms','network_ms','queue_ms','compute_ms','local_ratio','edge_ratio','cloud_ratio','decision_wall_ms','lowest_observable_cost_rate']
for scene in plan['scenarios']:
 rows=[];raw={};sha=None
 for name in order:
  row=dict(scenario_id=scene['id'],dataset=scene['dataset'],load=scene['load'],network=scene['network'],count=scene['count'],seed=scene['seed'],deadline_ms=scene['deadline_ms'],interval_ms=scene['interval_ms'],strategy=name,status='BLOCKED' if name in ('dqn','ddqn') else None,reason='Unknown seven-feature contract and training provenance; no legal adapter' if name in ('dqn','ddqn') else '',workload_sha256=None,**{k:None for k in fields})
  if row['status']=='BLOCKED':rows.append(row);raw[name]=dict(status='BLOCKED',reason=row['reason']);continue
  x=read(O/'raw/runs'/scene['id']/(name+'.json'));raw[name]=x;row.update(status=x['status'],reason=x.get('error',x.get('reason','')),workload_sha256=x['workload_sha256'])
  if sha is None:sha=x['workload_sha256']
  assert sha==x['workload_sha256']
  if x['status']!='PASS':rows.append(row);continue
  tasks=x['result']['tasks'];assert len(tasks)==10;summary=x['result']['summary'];c=summary['components_ms'];row.update(avg_latency_ms=summary['avg_latency_ms'],p95_latency_ms=summary['p95_latency_ms'],deadline_met_rate=summary['deadline_met_rate'],completion_rate=summary['completion_rate'],drop_rate=summary['drop_rate'],decision_ms=c['decision_ms'],decision_queue_ms=c['decision_queue_ms'],network_ms=c['network_ms'],queue_ms=c['queue_ms'],compute_ms=c['compute_ms'],decision_wall_ms=summary['avg_decision_wall_ms'],**{n+'_ratio':summary['placement_ratio'][n] for n in ('local','edge','cloud')});rows.append(row)
  # Independent offline FCFS reference after charged decisions: shift submission
  # to observed post-decision timestamp, keep original arrival only for latency.
  shifted=[Task(**dict(t['task'],arrival_ms=t['arrival_ms']+t['decision_queue_ms']+t['decision_ms'])) for t in tasks];placements={t['task_id']:t['selected_node'] for t in tasks};ref,calendars=reference(shifted,placements,{n:NodeConfig(**v) for n,v in scene['nodes'].items()},scene['network_mode'],scene['shared_bandwidth_mbps'])
  for key,intervals in calendars.items():assert all(a[1]<=b[0]+1e-7 for a,b in zip(intervals,intervals[1:])),key
  hits=[]
  for t in tasks:
   assert abs(t['total_latency_ms']-sum(t[k] for k in ('decision_queue_ms','decision_ms','network_ms','queue_ms','compute_ms')))<1e-6
   for key in ('cpu_started_at_ms','cpu_completed_at_ms','completed_at_ms','network_ms','queue_ms','compute_ms'):
    error=abs(t[key]-ref[t['task_id']][key]);maxerror=max(maxerror,error);assert error<1e-6,(scene['id'],name,t['task_id'],key,error)
   d=read(O/'raw/decisions'/scene['id']/name/(str(t['task_id'])+'.json'));assert d['task']==t['decision_input'];assert t['decision_ms']+1e-7>=d['client_inference_ms']
   obs=DecisionTask(**d['task']);state=SystemState(**{k:NodeState(**v) for k,v in d['state'].items()});costs={n.name:estimate_v2(obs,n)['total_ms'] for n in state.nodes()};correct=costs[t['selected_node']]<=min(costs.values())+1e-7;hits.append(correct)
   a=None
   if name.startswith('laya'):
    a=all_audit[d['audit_id']];assert a['input_state']['task']==d['task'];assert a['input_state']['nodes']==[asdict(n) for n in state.nodes()];assert a['raw_output']['answers']['offload_target']['choice']==a['final_choice']==t['selected_node'];assert not a['fallback_used'] and not a.get('error');used.append(d['audit_id']);est_correct.setdefault(scene['id'],{}).setdefault(name,[]).append(correct)
   traces.append(dict(scenario_id=scene['id'],dataset=scene['dataset'],load=scene['load'],network=scene['network'],strategy=name,task_id=t['task_id'],source_path_posthoc=t['task']['source_path'],input_task_json=json.dumps(d['task'],sort_keys=True),node_state_json=json.dumps(d['state'],sort_keys=True),selected_node=t['selected_node'],decision_ms=t['decision_ms'],client_inference_ms=d['client_inference_ms'],decision_queue_ms=t['decision_queue_ms'],worker_elapsed_ms=a['elapsed_ms'] if a else None,audit_id=d['audit_id'],fallback_used=False,model_failure=False,estimated_costs_ms_json=json.dumps(costs,sort_keys=True),chooses_lowest_observable_cost=correct,actual_workload_ms_posthoc=t['task']['workload_ms'],total_latency_ms=t['total_latency_ms'],deadline_met=t['deadline_met'],scope='LIVE_NO_REPLAY'))
  row['lowest_observable_cost_rate']=mean(hits)
 allrows+=rows;result=dict(scenario=scene,workload_sha256=sha,rows=rows,scope=plan['scope']);save(O/'web/scenarios'/(scene['id']+'.json'),result);save(O/'raw/scenarios'/(scene['id']+'.json'),dict(scenario=scene,strategy_results=raw));catalog.append(dict(scene,results_file='scenarios/'+scene['id']+'.json'))
 # Four scenario-local chart panels; blocked strategies have no bars.
 fig,axes=plt.subplots(2,2,figsize=(17,11),constrained_layout=True);ys=np.arange(10);labels=[n+(' [BLOCKED]' if n in ('dqn','ddqn') else '') for n in order];valid=[r['status']=='PASS' for r in rows]
 def vals(key):return np.array([r[key] if r['status']=='PASS' else np.nan for r in rows],dtype=float)
 a=axes[0,0];a.barh(ys-.16,vals('avg_latency_ms'),.3,label='Average');a.barh(ys+.16,vals('p95_latency_ms'),.3,label='P95',color='#b29659');a.set(xlabel='Latency (ms)',title='Average and P95');a.legend(fontsize=8)
 components=[('decision_queue_ms','Decision queue','#aa6f52'),('decision_ms','Decision','#be9b55'),('network_ms','Network','#548f9c'),('queue_ms','CPU queue','#8a75a4'),('compute_ms','Compute','#2f7553')];left=np.zeros(10)
 for key,label,color in components:
  v=vals(key);axes[0,1].barh(ys,v,left=left,label=label,color=color);left+=np.nan_to_num(v)
 axes[0,1].set(xlabel='Mean component latency (ms)',title='Latency decomposition');axes[0,1].legend(fontsize=7,ncol=3)
 axes[1,0].barh(ys,vals('deadline_met_rate')*100,color='#3b865b');axes[1,0].set(xlabel='Deadline met (%)',title='Deadline attainment',xlim=(0,105));left=np.zeros(10)
 for key,label,color in [('local_ratio','Local','#225d45'),('edge_ratio','Edge','#7da17e'),('cloud_ratio','Cloud','#be9b55')]:
  v=vals(key)*100;axes[1,1].barh(ys,v,left=left,label=label,color=color);left+=np.nan_to_num(v)
 axes[1,1].set(xlabel='Placement (%)',title='Node choice proportions',xlim=(0,105));axes[1,1].legend(fontsize=8)
 for a in axes.flat:
  a.set_yticks(ys,labels,fontsize=8);a.invert_yaxis();a.grid(axis='x',alpha=.15);a.set_axisbelow(True)
  for i,r in enumerate(rows):
   if r['status']!='PASS':a.text(0,i,r['status'],va='center',fontsize=7,color='#8e5623')
 fig.suptitle(f"{scene['dataset']} | {scene['load']} | {scene['network']} | deadline={scene['deadline_ms']} ms | n=10 | seed=11\ninterval={scene['interval_ms']:.2f} ms, reference Edge CPU rho={scene['reference_offered_cpu_load']} | live decisions, simulated execution",fontsize=13)
 p=O/'charts'/scene['dataset']/scene['load']/(scene['network']+'.png');p.parent.mkdir(parents=True,exist_ok=True);fig.savefig(p,dpi=140);plt.close(fig)
 for r in rows:counts[r['status']]=counts.get(r['status'],0)+1
csvout(O/'comparison_results.csv',allrows);csvout(O/'decision_trace.csv',traces);save(O/'web/catalog.json',dict(schema='ai-comparison-view-v1',scope=plan['stage'],scenarios=catalog,blocked=['dqn','ddqn'],replay=False));(O/'raw/model-audit.jsonl').write_text(''.join(json.dumps(all_audit[i],ensure_ascii=False)+'\n' for i in used),encoding='utf-8')
validation=dict(scene_count=24,comparison_rows=len(allrows),status_counts=counts,task_results=len(traces),verified_laya_task_choices=sum(r['strategy'].startswith('laya') for r in traces),warmup_calls=len(w['calls']),audit_entries=len(used),fallback_count=0,raw_choice_mismatches=0,reference_max_error_ms=maxerror,network_and_cpu_resource_calendars='PASS',cost_included='PASS',same_workload='PASS',no_replay=True,lowest_observable_cost={sid:{k:dict(correct=sum(v),n=len(v)) for k,v in bymodel.items()} for sid,bymodel in est_correct.items()},input_truncated=sum(bool(all_audit[i]['raw_output'].get('usage',{}).get('truncated')) for i in used if 'raw_output' in all_audit[i]))
save(O/'validation-summary.json',validation)
# Model and blockers reports distinguish observed facts from unverified semantics.
lines=['# 組員DQN／DDQN模型驗證','', '**DQN/DDQN FORMAL INTEGRATION: BLOCKED**','', 'RAR只解到獨立work/ai-comparison/incoming，未覆蓋原backend。只審查並載入隔離副本；加在execution.txt作為待驗證片段，未複製為production指令。來源/權重原始SHA與執行後逐位元組一致。','']
lines+=table(['模型','架構','finite','數值probe','合法Action','load() ms','平均act ms','P95act ms'],[[k,v['architecture'],v['all_weights_finite'],v['deterministic_probes'],str(v['action_values']),num(v['load_ms']),num(v['mean_inference_ms']),num(v['p95_inference_ms'])] for k,v in model['models'].items()])
lines+=['','每個probe重複20次epsilon=0，action與argmax(Q)一致；Q隨不同數值state變化，49維直接輸入會ValueError。這些是人工數值探針，不是合法SimPy狀態或模型選擇品質測試。load時間只含load()，act只含該函式；不能拿它與Laya完整HTTP pipeline作正式速度排名。','',
'權重與seed42初始值不同，不能因此證明使用了正確資料訓練；可能是其他seed或其他來源。NPZ只有arr0..3，沒有訓練資料、reward、特徵/scaler或checkpoint紀錄，訓練有效性NOT VERIFIED。','',
'snippet實際錯誤：DQN/DDQN呼叫不存在的decide，得到AttributeError；threshold_decide(state)缺edge_cpu得到TypeError。正確推論方法是act(state,epsilon=0)，但改方法名不能補齊七維契約。CPU百分比門檻與CPU queue/瞬時busy不同，因此未替換原Load-threshold，也沒有猜cpu_threshold觀測。','',
'CLI只顯示0=local/1=edge/2=cloud；訓練action label是否一致仍未確認。七維名稱、順序、單位、正規化、訓練資料、Reward、環境皆未確認，沒有建立49→7映射、正式Adapter、訓練或改權重。','',
'證據：model-validation/model_validation.json、member_inference_traces.json、feature_contract_check.json、member-original/六檔SHA；程式scripts/validate_member_models.py。']
doc('model_validation.md',lines)
block=['# 組員待補資料與正式整合阻擋','', '**DQN/DDQN FORMAL INTEGRATION: BLOCKED**','', '目前只可證明權重可執行，不能證明它對應這套SimPy或凍結test。請組員提供下列可驗證資料，不能用七個示範數字或權重形狀替代。','']
block+=table(['必要資料','需要的具體證據'],[['七維名稱/順序/單位','原訓練environment state builder；逐欄物理定義、時間點與可觀測來源'],['正規化','每欄公式、mean/std或min/max、clip/default值、scaler檔與SHA，證明僅fit training'],['訓練/驗證/測試資料','圖片source/hash/group與split manifest；與正式LFW/WIDER100圖test交集檢查'],['Reward/轉移/Done','reward公式、單位、延遲完成credit attribution、episode終止與reset'],['Action mapping','訓練時0/1/2代表的節點，不能只引用本次CLI顯示文字'],['Environment與參數','訓練SimPy或其他環境程式/版本、CPU/link競爭、RTT/BW/speed/deadline/drop規則'],['訓練證據','seed/超參數、episode/update steps、loss/reward logs、選checkpoint規則與權重SHA'],['Golden fixtures','至少數組原可觀測state→預期normalized7→Q-values→action，以驗證轉接不是猜測']])
block+=['','收到資料後才可評估七維是否能由現有49維合法重建。若需要觀測窗CPU百分比、其他歷史量或訓練用了未來真值，不能直接取49維前七個、補零或拿CPU busy當百分比。應先提出相容性差異，再由組員確認/修正；本輪沒有更改他們演算法或權重。',
'合法Adapter需把特徵轉換/scaler與act(epsilon=0)放在select_node timer內，分開記錄Q/action與時間，使用相同run_policy/Simulator、Median、test subset、reset與Deadline。不得在test更新權重或以Latency-aware補錯。',
'本輪不擴大30圖：DQN契約gate未通過，Laya數值可靠性仍有限。不能宣稱DQN/DDQN已與Laya完成公平正式比較；目前只有八個可執行策略在相同10圖pilot下完成比較。']
doc('TEAM_BLOCKERS.md',block)
# Complete hierarchy: dataset -> load -> network; all ten rows visible.
report=['# LFW／WIDER分層AI共同子集比較','', '本輪完成模型檔案檢查、八個可用策略的10圖pilot與分層檢視；DQN/DDQN正式整合依要求BLOCKED。沒有猜七維映射、重訓、覆寫組員或原SimPy、替換Laya或隱藏不利結果。','',
'## 事前固定設計與範圍','', 'LFW/WIDER各從已凍結100圖按seed11不重複取10張；各資料集在全部負載/網路使用同一順序。24格=2資料集×3負載×4既有網路；Deadline1000ms，realistic、complete_all，沿用原80圖training Median，沒有在test重新fit。每策略新建SimPy，決策的predict/選擇/HTTP成本統一實測計入。','',
'負載用事前固定共同子集的實測平均工作量/3（Reference Edge CPU speed3）定義參考平均服務需求tau，interval=tau/rho，rho=0.3/0.9/1.5。這是traffic實驗設計，不是對每圖真值的預測特徵，也不使用策略結果挑參數。其餘網路的節點ρ另存manifest；不能宣稱High在所有卸載placement都必然超載。因圖數10、seed僅1，僅作小型分層驗收，不推廣為穩定最佳演算法。','']
report+=table(['資料集','負載','間隔ms','到達tasks/s','參考服務tasks/s','參考ρ'],[[s['dataset'],s['load'],num(s['interval_ms']),num(s['arrival_rate_per_second']),num(s['reference_service_rate_per_second']),s['reference_offered_cpu_load']] for s in plan['scenarios'] if s['network']=='reference'])
report+=['','四個網路全部沿用前輪參數，沒有依本輪結果調整；speed為相對Local，RTT為ms、BW Mbps。','']
report+=table(['情境','Edge speed/RTT/BW','Cloud speed/RTT/BW','模式'],[[s['network'],'/'.join(str(s['nodes']['edge'][k]) for k in ('speed','rtt_ms','bandwidth_mbps')),'/'.join(str(s['nodes']['cloud'][k]) for k in ('speed','rtt_ms','bandwidth_mbps')),s['network_mode']] for s in plan['scenarios'] if s['dataset']=='lfw' and s['load']=='Low'])
report+=['','## Laya真實推論與計量','', f"任務Laya選擇{validation['verified_laya_task_choices']}次、預熱{len(w['calls'])}次，原始audit與task/state/choice逐一核對。模型服務開始前已載入={w['health_before'].get('model_loaded')}；每版相同中立輸入預熱1次，排除task統計，沒有結果cache或Replay。純首次載入時間NOT SEPARATELY MEASURED，因服務原已載入；不將首次載入塞入正式decision。", 
'client inference包括HTTP/model服務；decision_ms另含既有predict wrapper與均等輕量capture排程，checkpoint JSON I/O在timer後的SimPy事件執行，沒有把大量檔案寫入算成演算法cost。worker_elapsed另在decision_trace.csv，不能稱為純Torch GPU/CPU kernel時間。單序列決策Resource等待明列decision_queue_ms，不算影像compute。',
 f"fallback={validation['fallback_count']}、raw choice mismatch={validation['raw_choice_mismatches']}、input truncated={validation['input_truncated']}。Laya先前排列可靠性限制仍適用，沒有為求勝改prompt。最低共同可觀測phase-overlap估計成本選擇率按情境分開列在下表與validation-summary.json；這不是隱藏真值Oracle或全域最優，也不跨情境合成準確率排名。",'']
for dataset in ('lfw','wider_train'):
 report+=['## '+('LFW' if dataset=='lfw' else 'WIDER FACE'),'']
 for level in ('Low','Medium','High'):
  report+=['### '+level,'']
  for scene in (s for s in plan['scenarios'] if s['dataset']==dataset and s['load']==level):
   rows=[r for r in allrows if r['scenario_id']==scene['id']];report+=['#### '+scene['network'],f"Deadline={scene['deadline_ms']}ms，n=10，seed11，間隔{num(scene['interval_ms'])}ms。",''];report+=table(['策略','狀態','平均ms','P95ms','Deadline','完成/丟棄','決策ms','決策等候','網路ms','CPU等候','compute','Local/Edge/Cloud','最低估計成本選擇率'],[[r['strategy'],r['status'],num(r['avg_latency_ms']),num(r['p95_latency_ms']),pct(r['deadline_met_rate']),pct(r['completion_rate'])+'/'+pct(r['drop_rate']),num(r['decision_ms']),num(r['decision_queue_ms']),num(r['network_ms']),num(r['queue_ms']),num(r['compute_ms']),'/'.join(pct(r[k+'_ratio']) for k in ('local','edge','cloud')),pct(r['lowest_observable_cost_rate'])] for r in rows]);report+=['',f"![{scene['id']}](charts/{dataset}/{level}/{scene['network']}.png)",'']
report+=['## 驗證與可支持的結論','',f"{validation['task_results']}個已完成任務的同workload/時間守恆/CPU與網路獨立FCFS日曆通過；後決策提交時間=arrival+decision_queue+decision_ms，獨立reference最大誤差{maxerror:.3g}ms。原始Task真值只用模擬compute與事後分析，沒有進policy DTO。DQN/DDQN每格BLOCKED，不填零或fallback。", 
'這些是單host、10圖、單seed、固定deadline的描述性比較，不計跨格總排名，不給不存在的重複實驗CI。網路為容量1 FCFS序列資源、固定參數/即時觀測、相對speed縮放與16KB結果的已宣告簡化，並非真實遠端平台。','',
'## 最後八項回答','',
'1. 組員模型能接上嗎：數值權重可執行，但正式SimPy整合BLOCKED，未建立未知七維Adapter。',
'2. 如何合法49→7：必須先取得原state builder、欄位順序/單位/scaler及golden fixtures；目前無合法轉換，未任選七欄。',
'3. 訓練證據足夠嗎：NO。只有演算法與NPZ，無資料分割、訓練環境/reward/過程與checkpoint選擇證據；weights不同初始化不等於正確訓練。',
'4. Laya跨情境如何：上表分層保留所有真實結果與決策等待，數值選擇可靠性仍有限；只在本pilot條件解讀，不跨資料集/網路混排名。',
'5. 是否DQN/DDQN與Laya公平比較：尚未完成，因DQN契約BLOCKED；八個可用策略則用完全相同10圖/順序/估計器/限制/完成條件，沒有拿100圖baseline比10圖Laya。',
'6. 各策略優勢：固定策略在對應資源有利且不壅塞時有可解釋上限/限制，Load-threshold與Latency-aware會受負載/估計誤差影響，V2不是普遍較好。Laya在每格的收益必須和它的實測選擇成本/等待一起看；不能由某一格推全域結論。',
'7. 可放期末報告：可用本輪模型可執行性、BLOCKED理由、共同10圖pilot實測決策+SimPy執行及分層負面結果；不可當完整DQN性能、可信訓練證明、30/100圖正式排名或實際遠端速度。',
'8. 組員補交：完整七維/正規化/state環境/reward/action mapping、train/val/test hash、訓練logs/checkpoint與golden fixtures，詳TEAM_BLOCKERS。','',
'前端 /ai-comparison.html 只顯示一個dataset/load/network，支援指標切換及該情境CSV/JSON；前端/回歸/來源hash測試紀錄另見RUN_TESTS.md與tests/。']
doc('AI_COMPARISON_REPORT.md',report)
run=['# 重現與測試','', '模型契約缺失時不得啟用DQN/DDQN或修改權重。下列模型檢查只用隔離副本。live runner會重用已完成policy checkpoint；部分policy中斷時明列INTERRUPTED，不用舊choice冒充live，也不自動重複該policy昂貴呼叫。','',
'```powershell',
'docker compose -f compose.yaml -f compose.ai.yaml up -d',
'docker compose exec -T backend mkdir -p /app/scripts /tmp/member-review /tmp/ai-comparison',
'docker compose cp work/ai-comparison/incoming/backend backend:/tmp/member-review/backend',
'Get-ChildItem scripts/*ai_comparison*.py,scripts/validate_member_models.py,scripts/formal_design.py | ForEach-Object { docker compose cp $_.FullName ("backend:/app/scripts/"+$_.Name) }',
'docker compose exec -T backend python /app/scripts/validate_member_models.py --source /tmp/member-review/backend --output /tmp/ai-comparison',
'# feature_contract_check.json須由實際檢查產生並匯入/profiles/ai-comparison；model-validation資料夾亦須匯入',
'docker compose exec -T backend python /app/scripts/run_ai_comparison.py --plan',
'docker compose exec -T backend python /app/scripts/run_ai_comparison.py',
'docker compose exec -T backend python /app/scripts/build_ai_comparison.py',
'docker compose exec -T backend python -m unittest discover -s tests -v',
'docker compose exec -T backend python /app/scripts/test_ai_comparison.py',
'node --test frontend/tests/ai-comparison.test.mjs',
'```','',
'第一次呼叫前已固定24格、10圖順序、參考rho與482次模型呼叫預算。要改情境/模型/圖數需另立版本與輸出，不覆蓋本輪。已有有效輸出請勿刪除重新推論。前端publish/build及實際browser export測試紀錄在tests/，沒有執行的項目會明列NOT VERIFIED。']
doc('RUN_TESTS.md',run)
print(json.dumps(validation),flush=True)
