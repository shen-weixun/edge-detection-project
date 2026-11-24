"""Aggregate frozen results without pooling different workloads/settings.
Build the five requested reports only after every declared cell completed.
"""
from pathlib import Path
from collections import defaultdict,Counter
from statistics import mean,stdev
from math import sqrt
import json,csv,hashlib
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'work/paper-improvements';R=OUT/'results'
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def csvread(path):return list(csv.DictReader(path.open(encoding='utf-8-sig')))
def writecsv(path,rows):
    with path.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def number(x):return f'{float(x):.3f}'
def percent(x):return f'{100*float(x):.2f}%'
def table(headers,rows):return ['|'+'|'.join(headers)+'|','|'+'|'.join(['---']*len(headers))+'|']+['|'+'|'.join(map(str,row))+'|' for row in rows]
def save(name,lines):(ROOT/name).write_text('\n'.join(lines)+'\n',encoding='utf-8')

complete=read(OUT/'matrix-complete.json');assert complete['status']=='COMPLETE' and complete['cells']==192
rows=csvread(OUT/'matrix-summary.csv');assert len(rows)==894
selection=read(R/'estimator-evaluation.json');feature=selection['best_feature'];split=read(R/'split-manifest.json');model=read(R/'models'/(feature+'.json'))
checks=read(OUT/'protected-baseline.json');protected={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==sha for p,sha in checks.items()};assert all(protected.values())
groups=defaultdict(list)
keys=('dataset','environment','load','estimator','scope','strategy')
for r in rows:groups[tuple(r[k] for k in keys)].append(r)
fields=('avg_latency_ms','p95_ms','deadline_met_rate','decision_ms','decision_queue_ms','network_ms','cpu_queue_ms','compute_ms','local_ratio','edge_ratio','cloud_ratio','local_time_weighted_queue','edge_time_weighted_queue','cloud_time_weighted_queue')
aggregates=[];lookup={}
for key,rs in sorted(groups.items()):
    a=dict(zip(keys,key));a['trials']=len(rs)
    for f in fields:a[f]=mean(float(r[f]) for r in rs)
    values=[float(r['avg_latency_ms']) for r in rs]
    a['latency_sd_ms']=stdev(values) if len(values)>1 else 0
    margin=4.302652729911275*a['latency_sd_ms']/sqrt(3) if len(values)==3 else None
    a['latency_ci95_low_ms']=a['avg_latency_ms']-margin if margin is not None else ''
    a['latency_ci95_high_ms']=a['avg_latency_ms']+margin if margin is not None else ''
    aggregates.append(a);lookup[key]=a
writecsv(OUT/'matrix-aggregate.csv',aggregates)
comparisons=[]
for dataset in ('lfw','wider'):
 for env in ('reference','network_constrained','fast_compute'):
  for load in ('low','medium','high'):
   for estimator in ('median',feature):
    a=lookup[(dataset,env,load,estimator,'formal','latency_aware')];b=lookup[(dataset,env,load,estimator,'formal','latency_aware_v2')]
    comparisons.append(dict(dataset=dataset,environment=env,load=load,estimator=estimator,v1_avg_ms=a['avg_latency_ms'],v2_avg_ms=b['avg_latency_ms'],delta_ms=b['avg_latency_ms']-a['avg_latency_ms'],v1_deadline=a['deadline_met_rate'],v2_deadline=b['deadline_met_rate']))
writecsv(OUT/'latency-v2-comparison.csv',comparisons)
# All matrix AI choices are checked against append-only genuine worker outputs.
audit={a['audit_id']:a for a in map(json.loads,(ROOT/'profiles/laya_audit/decisions.jsonl').read_text(encoding='utf-8').splitlines())}
ids=read(OUT/'matrix-audit-ids.json');assert len(ids)==504
raw=[audit[i] for i in ids]
assert all(not a['fallback_used'] and not a.get('error') and a['raw_output']['answers']['offload_target']['choice']==a['final_choice'] for a in raw)
# Independently join HTTP task choices and decision DTOs to worker raw outputs.
task_count=0;cpu_intervals=0
for cellpath in (OUT/'matrix').glob('*.json'):
 cell=read(cellpath)
 for strategy,result in cell['strategies'].items():
  task_count+=len(result['tasks'])
  assert len({t['task_id'] for t in result['tasks']})==6
  for node,stats in result['node_statistics'].items():
   assert 0<=stats['cpu_utilization']<=1+1e-9
   intervals=sorted((t['cpu_started_at_ms'],t['cpu_completed_at_ms']) for t in result['tasks'] if t['selected_node']==node)
   for start,end in intervals:assert 0<=start<=end
   for previous,current in zip(intervals,intervals[1:]):assert previous[1]<=current[0]+1e-7
   cpu_intervals+=len(intervals)
  for t in result['tasks']:
   assert t['completed'] and not t['dropped']
   assert abs(t['compute_ms']-t['task']['workload_ms']/cell['config']['nodes'][t['selected_node']]['speed'])<1e-6
   if strategy.startswith('laya'):
    a=audit[t['decision_audit_id']]
    assert a['final_choice']==t['selected_node']
    assert a['input_state']['task']==t['decision_input']
assert task_count==5364 and cpu_intervals==5364
(OUT/'matrix-laya-audit.jsonl').write_text(''.join(json.dumps(a,ensure_ascii=False)+'\n' for a in raw),encoding='utf-8')
audit_check=dict(cells=192,strategy_rows=894,task_results=5364,matrix_laya_choices_verified=len(raw),matrix_truncated_inputs=sum(bool(a['raw_output'].get('usage',{}).get('truncated')) for a in raw),protected_files=protected)
(OUT/'verification-summary.json').write_text(json.dumps(audit_check,indent=2),encoding='utf-8')

A='https://openaccess.thecvf.com/content/ICCV2023W/RCV/papers/Biswas_Characterizing_Face_Recognition_for_Resource_Efficient_Deployment_on_Edge_ICCVW_2023_paper.pdf'
B='https://thesai.org/Downloads/Volume17No8/Paper_77-LEAOT_Load_Deadline_Latency.pdf'
C='https://www.sciencedirect.com/science/article/abs/pii/S1569190X26000419'
D='https://onlinelibrary.wiley.com/doi/abs/10.1002/nem.2146'
M='https://huggingface.co/convaiinnovations/laya#honest-limits'
sources=['','## 原文核對與採用範圍','',
 f'- [論文A原文]({A})：§2.1.2的預熱/分離量測；§2.2 Eq(1)-(2)用架構與參數數量預測設備throughput，§3.1討論解析度；其量測不含偵測，本專案為完整偵測與辨識管線。本文僅借鏡實測與可解釋校準，不把該式宣稱為逐圖InsightFace時間預測的重現。',
 f'- [LEAOT原文]({B})：§III-B Eq(2)-(6)為虛擬工作、queue/speed、傳輸與完成時間；§III-C Eq(9)為相對Deadline超時壓力。未重現Eq(7)-(12)的能量/基礎設施加權分數，也未在固定bandwidth模型中虛構EWMA改善。',
 f'- [MARPLE出版社頁]({C})：可取得的§5.1/5.2內容描述歷史估計與低開銷決策，作成本評估動機；直接全文請求403，作者稿封存至2027。沒有聲稱重現其AoK/MILP或完整演算法。',
 f'- [三層人臉卸載論文D]({D})：僅取得出版社摘要，全文403。僅作三層架構背景，不編造方法章節/公式，不實作其DRL。',
 'A/B原文已下載、抽取並視覺核對公式頁；存取限制記錄於paper-access.json。本文所有V2都是paper-inspired，並非論文完整重現。']

# Workload report: every candidate and adverse test result retained.
lines=['# 工作量估計器評估','',
'結論：新增可解釋且可保存的三特徵ridge；驗證集選出log-ridge α=10。最終測試WIDER有點估計改善、LFW退步，兩個MAE差的95%區間都跨零；因此保留Median為預設，不宣稱全面或顯著提升。',
'', '## 量測與事先固定分割','',
'LFW與WIDER_train各新量測60張（seed271828），每張先預熱再正式3次取中位數；讀取/解碼/載入與鎖等待分開。固定seed314159，各36/12/12張為training/validation/test；合計72/24/24，來源正規化與圖片SHA256皆跨分割零重疊。所有方法在完全相同24張held-out圖片評估，沒有刪除不利結果。WIDER_train是資料集名稱，本次另做獨立影像分割，並非把官方train當作最終模型訓練全體。',
 f'測試Profile：LFW `{selection["test_profile_ids"]["lfw"]}`；WIDER `{selection["test_profile_ids"]["wider"]}`。訓練與選模清單在split-manifest.json；重複內容排除紀錄數={len(split["duplicates_excluded"])}。',
'', '## 方法、特徵與保存','',
'- Median：72張訓練推論時間的中位數，作所有策略相同的先驗。',
'- Raw ridge：y=b0+b·z；log-ridge：yhat=exp(b0+b·z)。z是以training mean/std標準化的 [檔案MB、總像素/1e6、log(width/height)]。只有三個推論前特徵，禁止人臉數、待測真值、路徑或sample_id成為特徵。',
'- α候選事先固定0.1/1/10，共Median+6個ridge候選；只依validation MAE選擇。沒有改成test表現最佳的另一候選，也沒有大型模型/Random Forest參數搜尋。',
'- 係數、center、scale、training/validation identities與schema保存JSON；以內容SHA256 ID註冊，重新載入驗證checksum。API會拒絕含training或validation圖片的測試Profile。實際服務時間始終是原CSV真值，預估僅用在DecisionTask與承諾工作ledger。',
'- 新模型在policy選擇內實際重新計算一次，因此預測耗時被既有SimPy決策timer統一計入；預先算出的值只供模擬器bookkeeping，準備工作不冒充裝置執行。Median預設舊API行為不變。',
 f'選定係數（標準化後log尺度）={model["coefficients"]}；center={model["center"]}；scale={model["scale"]}。細節見estimators.py。',
'', '## 僅驗證集選模','']
lines+=table(['候選','validation MAE ms','validation RMSE ms'],[[k,number(v['mae_ms']),number(v['rmse_ms'])] for k,v in selection['validation'].items()])
lines+=['','## 最終測試：所有候選完整揭露','', 'bias=mean(預估−實際)，正數為高估。所有欄位均為ms；完整誤差分布含signed P05/P50/P95與absolute P95，見estimator-test-metrics.csv。','']
lines+=table(['資料集','方法','n','MAE','RMSE','偏差','|error| P95'],[[x['dataset'],x['method'],x['n'],number(x['mae_ms']),number(x['rmse_ms']),number(x['bias_ms']),number(x['abs_error_p95_ms'])] for x in csvread(R/'estimator-test-metrics.csv')])
lines+=['','## 成對差異與跨資料集','', '下表是feature MAE−Median MAE；負數才代表feature較好。paired bootstrap2000次，seed424242；每資料集僅12測試圖，不能外推所有圖片分布。','']
lines+=table(['資料集','MAE差 ms','95%下界','95%上界'],[[x['dataset'],number(x['mean_difference_ms']),number(x['ci95_low_ms']),number(x['ci95_high_ms'])] for x in selection['confidence']])
lines+=['','跨資料集只在來源資料集的training/validation挑模型，再評估另一資料集test；沒有利用目標test調參。','']
lines+=table(['train→test','來源validation選定','test MAE','test RMSE','偏差'],[[x['train_dataset']+'→'+x['test_dataset'],x['selected_using_source_validation'],number(x['mae_ms']),number(x['rmse_ms']),number(x['bias_ms'])] for x in selection['cross_domain']])
lines+=['','限制：原圖尺寸不能直接揭露完成後的人臉數；WIDER的偵測後逐臉辨識工作仍可能造成長尾，這些安全特徵不足以完全識別工作量。當前只有一個量測host、各12張test、沒有跨設備跑分。保留Median，不能以某個test較好的未選候選換掉已凍結模型。',
'', '程式：backend/app/offloading/estimators.py、scripts/train_workload_estimators.py；模型檔models/、estimator-predictions.csv、validation-selection.json提供逐圖與選模證據。']+sources
save('WORKLOAD_ESTIMATOR_EVALUATION.md',lines)

# Latency V2 report.
lines=['# Latency-aware V2 報告','',
'保留原latency_aware，新增latency_aware_v2；不改SimPy timeout、Resource、真實工作量或RL觀測/action/reward。V2以phase overlap減少串行相加的過度預估，但仍是聚合估計，不能保證所有情境較好。',
'', '## 物理意義與公式','',
'令 c=(queue_work_ms+committed_work_ms)/speed、x=estimated_workload_ms/speed、r=RTT/2、u=MB×8000/Mbps、d=KB×8/Mbps，U/D為當下上/下載backlog（全部ms）。Local：T=c+x。遠端：',
'```text',
'input_ready = max(r, U) + u',
'cpu_finish = max(input_ready, c) + x',
'T = max(cpu_finish + r, D) + d',
'remaining_deadline = deadline_ms - max(0, observed_at_ms - arrival_ms)',
'slack = remaining_deadline - T',
'late_ratio = max(0, T - remaining_deadline) / deadline_ms',
'post_cpu_pressure = (c + x) / max(remaining_deadline, epsilon)',
'```',
'原版會把CPU work、上/下載積壓和全部網路服務相加；V2容許既有工作在本任務傳播/上傳/運算期間排空。已承諾未到CPU的工作仍納入c，未看真實完成時間或未來任務。',
'決策採(是否超期、相對超時、T、post_cpu_pressure、節點名)詞典序，無任意加權相加。必須坦白：只以最低延遲為主要目標時，Deadline判斷不會改變T的排序；pressure只解完全相同T的平手。因此改善主要來自重疊時間估計，不聲稱Deadline分支單獨提高績效。',
'本模型頻寬固定且即時可觀測，未加入無資料支持的EWMA或能耗估算；未實作LEAOT完整加權score。',
'', '## 九個固定情境','',
'包含Local/Edge/Cloud有利、Edge CPU積壓、Cloud上傳壅塞、短Deadline、突發、嚴重低估與CPU/傳輸重疊。以下列非強制prefix任務；固定prefix只用於建立相同背景負載。Oracle僅知道當前與既有任務的真實工作量，不知道未來到達，也不是MARPLE MILP或保證最優上界。','']
controlled=csvread(R/'latency-controlled.csv')
lines+=table(['情境','策略','task','Local估計','Edge估計','Cloud估計','選擇','實際延遲','Deadline達成'],[[x['case'],x['strategy'],x['task_id'],number(x['local_estimate_ms']),number(x['edge_estimate_ms']),number(x['cloud_estimate_ms']),x['selected'],number(x['actual_latency_ms']),x['deadline_met']] for x in controlled if x['forced_prefix']=='False'])
lines+=['','重疊案例：原版選Cloud406.28ms；V2選Edge381.70ms。嚴重低估案例：兩者皆選Local而耗6000ms；workload-oracle選Cloud997.782ms。這顯示改善估算仍無法修復未知工作量的巨大預測偏差。',
'', '## 各情境正式端到端差異','',
'每格3種子，每trial6個同一測試Profile抽樣圖片；正值Δ為V2較慢，沒有跨不同環境/負載混成單一最佳排名。完整mean/P95、Deadline、CPU/傳輸/決策等待與分配見matrix-summary.csv及matrix-aggregate.csv。','']
lines+=table(['資料集','環境','負載','估計器','V1均值','V2均值','Δ ms','Deadline V1→V2'],[[x['dataset'],x['environment'],x['load'],x['estimator'],number(x['v1_avg_ms']),number(x['v2_avg_ms']),number(x['delta_ms']),percent(x['v1_deadline'])+'→'+percent(x['v2_deadline'])] for x in comparisons])
material=Counter('improved' if x['delta_ms']< -1 else 'regressed' if x['delta_ms']>1 else 'within_1ms' for x in comparisons)
lines+=['',f'36個分開條件格（2估計器×2資料集×3環境×3負載），以1ms作實務差異註記：{dict(material)}。這是條件格數，不是將不同情境延遲混平均；所有小差異仍完整列出，不因開銷抖動宣稱普遍優勢。',
'', '## 剩餘限制','',
'聚合c把尚在傳輸的承諾工作當成可服務需求，沒有每個先前任務的預估到CPU時間；可能低估未來的CPU空轉或累積，亦可能保守估計排隊。既有download backlog並不包含尚未完成運算的未來回傳。候選延遲只是估計，不是排程真值。短Deadline/爆量下可退化，沒有修改不利測試或以結果校正輸出。',
'程式latency_v2.py；13項新後端測試（含保存/資料隔離/成本）、paper_cases.py與run_latency_v2_cases.py可重現；原事件正確性測試仍通過。']+sources
controlled=read(R/'latency-controlled.json')
maxerr=max(v['independent_reference']['max_reference_error_ms'] for v in controlled.values())
lines+=['',f'額外獨立核對：9情境×3策略共27次run/51任務，使用既有acceptance_reference離線三階段FCFS計算，不匯入估計公式；CPU與上下行日曆容量、階段/終止時間、queue面積皆通過，最大誤差{maxerr:.3g}ms。逐筆參考與資源日曆見latency-controlled.json。']
save('LATENCY_AWARE_V2_REPORT.md',lines)

# Laya report, diagnostic reliability separate from runtime validity.
diag=read(R/'laya-diagnostic-summary.json');audit_diag=[json.loads(x) for x in (R/'laya-diagnostic-audit.jsonl').read_text(encoding='utf-8').splitlines()]
lines=['# Laya決策可靠性與成本評估','',
'結論：唯一預先固定的V2在Local情境較好，但Edge/Cloud排列不變性與單因素成本敏感度仍失敗，實測成本較高。因此V2只是可切換探索版本，沒有提升為可靠策略；保留原版，也沒有用Latency-aware、Oracle或排序偷偷替換模型輸出。',
'', '## Checkpoint與方法','',
 f'[官方模型卡的Honest Limits]({M})把它定位為可專化的typed分類基礎，未保證零樣本數值決策。實際使用laya0.4.17、Torch2.9.1+cpu、同一multilingual checkpoint；快取revision=7b928d828b7b0e022f929d9bd2e44165aa270148。沒有換權重、訓練或引用其他workflow benchmark成績當本專案準確率。',
'原版保持JSON/固定Cloud faster等描述與原推論設定；V2只做一次凍結候選：刪除固定節點快慢描述、使用統一ms的預估傳輸/CPU/承諾工作、剩餘Deadline，指定相同multilingual checkpoint，CPU threads=1且每次在lock內還原舊設定。沒有啟用只適用CUDA的fast path，也沒有加入結果快取。',
'V2 candidate與choice options均保留傳入排列，沒有按成本或名字排序。格式化只有可觀測量的代數轉換，沒有傳最低成本答案。輸入縮短與thread設定是合併候選，不能從此實驗獨立歸因兩者效果。',
'', '## 六排列×兩次重複與單因素','',
'共90次模型呼叫：每版36個三節點有利排列測試，加9個RTT/頻寬/算力/CPU queue單因素狀態。另各1次預熱，排除統計。每一版的每個排列重複對均一致，但跨排列並不保證一致。','']
lines+=table(['版本','合法選擇','最低共同估計成本','平均決策HTTP ms','P95 ms','單因素正確'],[[v,f"{diag[v]['legal']}/{diag[v]['total']}",f"{diag[v]['correct']}/{diag[v]['total']}",number(diag[v]['mean_wall_ms']),number(diag[v]['p95_wall_ms']),f"{diag[v]['single_factor_correct']}/9"] for v in ('legacy','v2')])
lines+=['','|版本|情境|正確/12|排列不變|重複一致/6|','|---|---|---|---|---|']
for v in ('legacy','v2'):
 for case,d in diag[v]['cases'].items():lines.append(f"|{v}|{case}|{d['correct']}/12|{d['order_invariant']}|{d['repeat_consistent']}/6|")
for v in ('legacy','v2'):
 selected=[a for a in audit_diag if a['variant']==v];tokens=mean(a['raw_output']['usage']['input_tokens'] for a in selected)
 lines+=['',f'{v}平均input tokens={tokens:.3f}。']
lines+=['','雖然V2約400 token對原版573較短，但單thread候選沒有變快；不拿較短輸入冒稱低成本成功。最低成本率以相同observable state的V2物理估計為參考；它不是辨識準確率或真實全域最佳排程。三個空佇列有利情境的兩成本公式排序一致。',
'', '## 全部排列結果（沒有隱藏失敗）','']
records=read(R/'laya-diagnostics.json')
pairs=defaultdict(list)
for a in records:
 if a['kind']=='permutation':pairs[(a['case'],tuple(a['order']),a['variant'])].append(a['response']['node'])
lines+=table(['情境','排列','原版兩次','V2兩次'],[[case,'→'.join(order),'/'.join(pairs[(case,order,'legacy')]),'/'.join(pairs[(case,order,'v2')])] for case in ('A_local','B_edge','C_cloud') for order in __import__('itertools').permutations(('local','edge','cloud'))])
lines+=['','單因素完整輸入與原始response見laya-diagnostics.json；90/90原始SDK choice=HTTP choice，fallback=0，truncated=0。','', '## 計入決策成本與消融','',
'原版正式矩陣跨全部環境、3種子；V2已未通過可靠性，只在reference環境/seed11作6個探索性格，另做對應消融，沒有納入正式可靠排名。以下成對結果全為同圖片/seed/環境。','']
comparison_ai=[]
for dataset in ('lfw','wider'):
 for load in ('low','medium','high'):
  for strategy in ('laya','laya_v2'):
   formal_scope='formal' if strategy=='laya' else 'exploratory'
   for scope in (formal_scope,'exploratory_ablation' if strategy=='laya_v2' else 'ablation'):
    a=next(x for x in rows if x['dataset']==dataset and x['environment']=='reference' and x['load']==load and x['seed']=='11' and x['estimator']=='median' and x['scope']==scope and x['strategy']==strategy)
    comparison_ai.append([dataset,load,strategy,scope,number(a['avg_latency_ms']),number(a['p95_ms']),percent(a['deadline_met_rate']),number(a['decision_ms']),number(a['decision_queue_ms'])])
lines+=table(['資料集','負載','版本','範圍','平均延遲ms','P95','Deadline','決策ms','決策等待ms'],comparison_ai)
lines+=['',f'矩陣內{len(raw)}次AI選擇逐一連結audit_id並核對真實raw choice，fallback=0，輸入截斷={audit_check["matrix_truncated_inputs"]}；原始資料matrix-laya-audit.jsonl。',
'消融decision_ms/decision_queue_ms=0，但wall time仍保留；不是正式端到端效能。Laya真實推論耗時不會被當成影像CPU compute_ms，單一序列決策Resource造成的等待是原模型明示假設。現有模型不適合作為可靠數值卸載決策器；更多未受控Prompt調整沒有驗收依據，因此停止此輪調整。']
save('LAYA_DECISION_EVALUATION.md',lines)

# Full comparison report, per-environment/load tables rather than grand means.
lines=['# 多資料集／負載／環境實驗比較','',
'所有算法與模型在執行前凍結，192個API實驗格全部完成；894個策略結果、5364筆任務。保留所有原始JSON、每種子CSV及不利結果。禁止混合不同到達率/網路條件作單一最佳排名。',
'', '## 固定設計','',
'- 資料：新量測LFW60/WIDER60的held-out各12張，36/12/12分割；每trial從該12張用seed11/23/37不重複抽6張，所有策略/估計器在同cell完全同圖、同順序、同真實服務時間。這是有限批次，不是穩態負載研究。',
'- low/medium/high固定到達間隔10000/200/25 ms、Deadline1000 ms。標籤是預先固定情境，不保證每種算力/每個離群圖片都具有相同ρ。',
'- reference：speed1/3/8、RTT0/20/100、Mbps1000/120/55，獨立網路；network_constrained：Edge RTT100/BW8、Cloud RTT300/BW4，共享上下載8 Mbps；fast_compute：只把Edge/Cloud speed改6/16，其餘reference。',
'- Median下7策略×54格正式比較；selected feature下6非AI策略×54格隔離預估器影響；Oracle V2×54格另列；reference下18格Median決策成本消融。失敗的LayaV2另12個探索/消融格，不納入可靠排名。',
'- 每個正式策略含新模型預測與真實select_node wall time、決策排隊；共同離線fit、registry載入、模擬器準備、圖片讀取/解碼不算相機端到端延遲。每格隨機但固定策略執行順序，重建各自Environment/Resource。',
'- 各格3次seed結果計sample SD及t(2)=4.30265的均值95%區間，僅描述這3個資料排序/抽樣與該主機成本波動；樣本小、不是廣泛泛化證明。P95先每trial用nearest-rank計，再列三trial均值；不混不同條件的樣本重算P95。',
'完整每種子全部指標matrix-summary.csv；分組均值/SD/CI/節點比例/時間加權佇列matrix-aggregate.csv。資源、時間守恆、原始來源一致性都逐筆檢查。',
'', '## Median基準：每個環境單獨列示','']
for dataset in ('lfw','wider'):
 for env in ('reference','network_constrained','fast_compute'):
  lines+=['',f'### {dataset} / {env}','']
  rs=[a for a in aggregates if a['dataset']==dataset and a['environment']==env and a['estimator']=='median' and a['scope']=='formal']
  lines+=table(['負載','策略','平均ms [95%區間]','P95 ms','Deadline','CPU等待ms','決策ms','決策等待ms','L/E/C分配'],[[a['load'],a['strategy'],number(a['avg_latency_ms'])+' ['+number(a['latency_ci95_low_ms'])+','+number(a['latency_ci95_high_ms'])+']',number(a['p95_ms']),percent(a['deadline_met_rate']),number(a['cpu_queue_ms']),number(a['decision_ms']),number(a['decision_queue_ms']),'/'.join(percent(a[n+'_ratio']) for n in ('local','edge','cloud'))] for a in rs])
lines+=['','## 隔離預估器效果：固定策略、只換模型','',
'以下Δ為feature−Median，兩者均含自己的預測成本且真實服務工作量完全相同。其他固定策略也全保留於CSV，未因對估計不敏感而刪除。','']
feature_rows=[]
for dataset in ('lfw','wider'):
 for env in ('reference','network_constrained','fast_compute'):
  for load in ('low','medium','high'):
   for strategy in ('latency_aware','latency_aware_v2'):
    a=lookup[(dataset,env,load,'median','formal',strategy)];b=lookup[(dataset,env,load,feature,'formal',strategy)]
    feature_rows.append([dataset,env,load,strategy,number(a['avg_latency_ms']),number(b['avg_latency_ms']),number(b['avg_latency_ms']-a['avg_latency_ms']),percent(a['deadline_met_rate'])+'→'+percent(b['deadline_met_rate'])])
lines+=table(['資料集','環境','負載','策略','Median均值','feature均值','Δ ms','Deadline變化'],feature_rows)
lines+=['','## Oracle只作資訊理想化參考','',
'只額外知道當前/已承諾任務的實測工作量，不預知未來到達；仍使用V2啟發式，沒有MILP全域最佳保證，亦沒有真實模型預測成本，不能混入公平排名。','']
lines+=table(['資料集','環境','負載','Realistic Median V2','Oracle V2'],[[d,e,l,number(lookup[(d,e,l,'median','formal','latency_aware_v2')]['avg_latency_ms']),number(lookup[(d,e,l,'oracle','oracle','latency_aware_v2')]['avg_latency_ms'])] for d in ('lfw','wider') for e in ('reference','network_constrained','fast_compute') for l in ('low','medium','high')])
lines+=['','## 判斷與限制','',
'沒有以跨情境平均宣稱某方法最好。V2在特定重疊/負載條件可能獲益，也可能因聚合承諾需求、工作量誤差與串行決策延遲而退化；依各格表與原始資料判斷。Laya原版/V2皆未通過可靠性，因此其效能結果是失效行為分析，不是成功AI最佳化證明。新預估器WIDER點改善不代表策略每格皆改善；表內完整揭露。',
'沒有跨設備實測、穩態穩定性保證或大型測試集。網路/算力/16KB結果/即時狀態沿用已驗收假設。沒有刪除任何舊實驗、資料庫、資料集或模型快取。']+sources
save('EXPERIMENT_COMPARISON.md',lines)

# Integration notes: untouched RL plus additive API fields.
lines=['# 團隊整合說明','',
'本輪沒有修改、實作或訓練DQN/DDQN。沒有改Task/DecisionTask/NodeState/SystemState欄位、RL State/Action/Reward、EpisodeSplit、OffloadingEnv或已驗收的SimPy事件引擎。',
'', '## 受保護檔案逐位元組核對','']
lines+=table(['檔案','起點9739b39→目前'],[[p,'SHA256完全相同' if yes else 'CHANGED'] for p,yes in protected.items()])
lines+=['','原三個test_rl案例隨全部77項後端測試重跑；原Baseline預設仍只有五策略。舊calibration_profile_id請求與原laya預設保留，新增功能全部可明確選擇。',
'', '## 新增入口與向後相容','',
'- 新策略key：latency_aware_v2、laya_v2；原key與實作保留。STRATEGY_FACTORIES新增key，呼叫端若想嚴格維持舊五策略請使用固定清單，不要假設字典永遠只有五項。',
'- experiment只在末端新增estimator_model=None；舊參數順序/預設不變。Saved模型只允許realistic measured mode，會拒絕training/validation重疊。',
'- POST /api/offloading/experiments新增可選estimator_id；它與calibration_profile_id二擇一。舊請求不需更動。GET /api/offloading/estimators列可用模型ID/種類/訓練與驗證數。最多8策略，AI每種最多50任務的限制同樣套用laya_v2。',
'- EstimatedPolicy只包experiment所建策略，於既有select_node計時內預測，再交給原policy；不改RL互動環境或request_action。模型只讀size/width/height，不讀Task.workload_ms或face_count。',
'- 節點監測的估計commit ledger預先填入同一模型預估值；實際compute仍只用原Task.workload_ms/speed。DQN同事可繼續接原DecisionTask，若要比較同一模型需使用相同固定split/估計器ID，不能重新接真實工作量。',
'- Laya服務POST /decide新增variant=legacy|v2，省略就是原版。V2候選輸入與options保留原順序；回傳是真實模型choice，無規則/Oracle fallback。V2單thread只在共享lock內臨時設定、finally還原。',
'- 新模型JSON schema workload-estimator-v1；校驗ID以SHA256內容定址，無pickle。訓練用的numpy已在原requirements，未新增依賴或修改DQN權重。',
'', '## 執行與重現','',
'```powershell',
'docker compose -f compose.yaml -f compose.ai.yaml up -d --build',
'docker compose exec -T backend python -m unittest discover -s tests -v',
'docker compose -f compose.yaml -f compose.ai.yaml exec -T laya python -m unittest test_server -v',
'docker compose exec -T backend mkdir -p /app/scripts',
'docker compose cp scripts/train_workload_estimators.py backend:/app/scripts/train_workload_estimators.py',
'docker compose cp scripts/run_latency_v2_cases.py backend:/app/scripts/run_latency_v2_cases.py',
'docker compose cp scripts/run_laya_paper_diagnostics.py backend:/app/scripts/run_laya_paper_diagnostics.py',
'docker compose exec -T backend python /app/scripts/train_workload_estimators.py --lfw 44156f8feb7a49269ec3bc6424b5e176 --wider faef67cd539d44f8b3caea7f58307db8',
'docker compose exec -T backend python /app/scripts/run_latency_v2_cases.py',
'docker compose exec -T backend python /app/scripts/run_laya_paper_diagnostics.py',
'docker compose cp backend:/tmp/paper-improvements/. work/paper-improvements/results/',
'python scripts/run_paper_comparison.py',
'python scripts/verify_integration.py --reuse-profiles  # 須設WORKLOAD_PROFILE_ID/CALIBRATION_PROFILE_ID/INTEGRATION_OUTPUT，見CODEX_PROGRESS',
'python scripts/verify_paper_api.py',
'python scripts/build_paper_reports.py',
'```','',
'矩陣腳本保留已完成JSON，重新啟動會驗證同一設定並接續；若要新一輪請使用新輸出目錄/另存舊矩陣，不混入不同實作。重建容器前先cp /tmp結果，模型registry與Profile在既有持久profiles目錄。',
'', '## 測試與未通過項目','',
'實際結果：77/77後端（原64+新增13）、2/2 Laya服務測試、78/78原HTTP整合、17/17新增API檢查全部通過。Docker backend/db/laya健康、frontend運作，node --check simulator.js通過。瀏覽器控制介面回報不可用，因此未完成視覺/點擊驗收；HTTP頁面、真實辨識與API流程已驗證。未通過的是Laya數值可靠性與全面預估器改善主張，不是被掩蓋的程式測試失敗。',
'對DQN後續工作：保持來源內容去重及獨立train/validation/test；固定特徵/動作順序、SMDP延遲reward歸屬與實際決策成本規則。不要把Oracle或Laya錯誤選擇當最佳標籤，也不要把不同負載結果混成一個宣稱優勢的均值。']
save('TEAM_INTEGRATION_NOTES.md',lines)
print(json.dumps(dict(reports=5,verification=audit_check,v2_material_cells=dict(material)),ensure_ascii=False))
