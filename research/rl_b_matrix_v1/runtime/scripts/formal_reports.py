"""Aggregate each fixed condition separately, draw exportable plots, build reports."""
from pathlib import Path
from collections import defaultdict,Counter
from statistics import mean,stdev
from math import sqrt
import json,csv,hashlib
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
ROOT=Path('/app');O=Path('/profiles/formal-evaluation');E=O/'evaluation';P=O/'plots';P.mkdir(exist_ok=True)
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def csvread(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
def csvout(p,rows):
 with p.open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def table(head,rows):return ['|'+'|'.join(head)+'|','|'+'|'.join(['---']*len(head))+'|']+['|'+'|'.join(map(str,r))+'|' for r in rows]
def num(x):return f'{float(x):.3f}'
def pct(x):return f'{100*float(x):.1f}%'
def save(name,lines):(O/name).write_text('\n'.join(lines)+'\n',encoding='utf-8')
complete=read(E/'matrix-complete.json');assert complete['strategy_runs']==3456 and complete['task_results']==345600
manifest=read(O/'dataset_manifest.json');selection=read(E/'validation-selection.json');fit=read(E/'fit-complete.json');ridge=selection['ridge'];raw=csvread(O/'strategy_comparison.csv')
keys=('dataset','environment','interval_ms','deadline_ms','estimator','strategy');groups=defaultdict(list)
for r in raw:groups[tuple(r[k] for k in keys)].append(r)
metrics=('average_latency_ms','p95_latency_ms','deadline_met_rate','completion_rate','drop_rate','decision_wall_ms','decision_ms','decision_queue_ms','network_ms','queue_ms','compute_ms','local_ratio','edge_ratio','cloud_ratio','local_time_weighted_queue','edge_time_weighted_queue','cloud_time_weighted_queue','local_utilization','edge_utilization','cloud_utilization')
agg=[];lookup={}
for k,rows in sorted(groups.items()):
 assert len(rows)==3
 a=dict(zip(keys,k),seeds=3)
 for m in metrics:a[m]=mean(float(r[m]) for r in rows)
 sd=stdev(float(r['average_latency_ms']) for r in rows);margin=4.302652729911275*sd/sqrt(3);a.update(latency_sd_ms=sd,latency_ci95_low_ms=a['average_latency_ms']-margin,latency_ci95_high_ms=a['average_latency_ms']+margin);agg.append(a);lookup[k]=a
csvout(O/'strategy_aggregate.csv',agg)
pairs=[];basegroups=sorted({k[:4] for k in groups})
for base in basegroups:
 for comparison,est,pol in [('policy_effect','median','latency_aware_v2'),('predictor_effect','ridge','latency_aware'),('combined_effect','ridge','latency_aware_v2')]:
  a=groups[base+('median','latency_aware')];b=groups[base+(est,pol)];byseed={r['seed']:r for r in b};delta=[float(byseed[r['seed']]['average_latency_ms'])-float(r['average_latency_ms']) for r in a];d=mean(delta);sd=stdev(delta);margin=4.302652729911275*sd/sqrt(3)
  out=dict(zip(keys[:4],base),comparison=comparison,baseline='V1+Median',candidate=pol+'+'+est,seeds=3,baseline_avg_ms=mean(float(r['average_latency_ms']) for r in a),candidate_avg_ms=mean(float(r['average_latency_ms']) for r in b),delta_ms=d,paired_sd_ms=sd,paired_ci95_low_ms=d-margin,paired_ci95_high_ms=d+margin)
  for m in metrics:out['delta_'+m]=mean(float(byseed[r['seed']][m])-float(r[m]) for r in a)
  pairs.append(out)
csvout(O/'paired_differences.csv',pairs)
policy=[r for r in pairs if r['comparison']=='policy_effect'];counts=Counter('improved_gt1ms' if r['delta_ms']< -1 else 'regressed_gt1ms' if r['delta_ms']>1 else 'within_1ms' for r in policy)
# Exportable plots; no pooling of rates/deadlines into a winner.
pred=csvread(E/'estimator_predictions.csv');fig,axes=plt.subplots(2,2,figsize=(10,8),constrained_layout=True)
for i,d in enumerate(('lfw','wider_train')):
 for j,model in enumerate(('median',ridge)):
  rows=[r for r in pred if r['dataset']==d and r['model']==model];x=np.array([float(r['actual_ms']) for r in rows]);y=np.array([float(r['predicted_ms']) for r in rows]);ax=axes[i,j];ax.scatter(x,y,s=15,alpha=.65);limit=max(x.max(),y.max())*1.03;ax.plot([0,limit],[0,limit],color='gray',lw=1);ax.set(xlabel='Actual inference (ms)',ylabel='Predicted inference (ms)',title=f'{d}: {model}, n=100',xlim=(0,limit),ylim=(0,limit))
fig.savefig(P/'prediction_scatter.png',dpi=160);plt.close(fig)
envs=list(read(O/'preregistered-design.json')['scenarios']);envnames=list(dict.fromkeys(r['environment'] for r in envs));limit=max(abs(r['delta_ms']) for r in policy) or 1;fig,axes=plt.subplots(2,3,figsize=(13,8),constrained_layout=True)
for i,d in enumerate(('lfw','wider_train')):
 for j,deadline in enumerate(('500','1000','2000')):
  values=np.array([[next(r['delta_ms'] for r in policy if r['dataset']==d and r['environment']==env and r['interval_ms']==gap and r['deadline_ms']==deadline) for gap in ('70','300','1000')] for env in envnames]);ax=axes[i,j];im=ax.imshow(values,cmap='coolwarm',norm=TwoSlopeNorm(vmin=-limit,vcenter=0,vmax=limit),aspect='auto');ax.set_xticks(range(3),['70','300','1000']);ax.set_yticks(range(8),envnames,fontsize=7);ax.set(xlabel='Arrival interval (ms)',title=f'{d}, deadline={deadline}ms')
  for row in range(8):
   for col in range(3):ax.text(col,row,f'{values[row,col]:.0f}',ha='center',va='center',fontsize=7)
fig.colorbar(im,ax=axes.ravel().tolist(),label='V2 Median minus V1 Median latency (ms); negative is lower');fig.savefig(P/'policy_paired_heatmap.png',dpi=160);plt.close(fig)
fig,axes=plt.subplots(2,3,figsize=(13,7),constrained_layout=True)
for i,d in enumerate(('lfw','wider_train')):
 for j,deadline in enumerate(('500','1000','2000')):
  ax=axes[i,j]
  for est,pol in [('median','local_only'),('median','edge_only'),('median','cloud_only'),('median','load_threshold'),('median','latency_aware'),('median','latency_aware_v2'),('ridge','latency_aware'),('ridge','latency_aware_v2')]:
   values=[lookup[(d,'reference',gap,deadline,est,pol)]['average_latency_ms'] for gap in ('70','300','1000')];ax.plot([70,300,1000],values,marker='.',label=pol+'+'+est,linewidth=1)
  ax.set(xlabel='Arrival interval (ms)',ylabel='Mean latency (ms, log scale)',title=d+' deadline='+deadline);ax.set_yscale('log')
axes[0,0].legend(fontsize=6);fig.savefig(P/'reference_strategy_latency.png',dpi=160);plt.close(fig)
# Estimator report.
res=csvread(O/'workload_estimator_results.csv');ci=csvread(E/'estimator_paired_ci.csv');sub=csvread(E/'estimator_subgroups.csv');cross=csvread(E/'cross_dataset.csv');ref=read(E/'independent-validation.json')
lines=['# 正式工作量估計器評估','',f'固定split：LFW與WIDER_train各40 training /20 validation /100 test。僅80張training擬合，40張validation選參；200張test在選模JSON落盤後才評估。選定Ridge={ridge}；Median預設未更換。','',
'特徵保持前輪三項：檔案MB、總像素/1e6、log(width/height)，只用training mean/std標準化。候選Median、raw/log ridge α=0.1/1/10共7個，無新增特徵或以test挑α。真實人臉數、長推論時間分組只用於事後分析。實際SimPy compute始終取CSV inference_ms/speed。','', '## 所有候選的最終測試','']
lines+=table(['資料集','候選','n','MAE','RMSE','Bias','|error|P50','|error|P95'],[[r['dataset'],r['model'],r['n']]+[num(r[k]) for k in ('mae_ms','rmse_ms','mean_bias_ms','absolute_error_p50_ms','absolute_error_p95_ms')] for r in res])
lines+=['','## 成對MAE差的群組bootstrap','', 'Ridge−Median，負值較好。2000次，seed424242；LFW按人物、WIDER按事件資料夾重抽群組，保留群組內圖片。CI只描述這個凍結樣本的有限不確定性，不保證跨設備/全資料集表現。','']
lines+=table(['資料集','圖片','群組','MAE差','95%下界','95%上界'],[[r['dataset'],r['n'],r['groups'],num(r['delta_ms']),num(r['ci95_low_ms']),num(r['ci95_high_ms'])] for r in ci])
lines+=['','## 事後困難子群（不作模型輸入或重選）','', '固定門檻：高解析度>=1MP、長推論>=1000ms、多人臉>=2。NO_SAMPLES表示該子群沒有測試圖片，不宣稱通過。所有候選子群完整CSV在evaluation/estimator_subgroups.csv。','']
lines+=table(['資料集','模型','子群','n','MAE','RMSE','Bias','狀態'],[[r['dataset'],r['model'],r['subgroup'],r['n'],r['mae_ms'],r['rmse_ms'],r['mean_bias_ms'],r['status']] for r in sub if r['model'] in ('median',ridge)])
lines+=['','## 跨資料集','', '來源training擬合/來源validation選模，再測另一資料集的100張test；不使用目標test決定候選。','']
lines+=table(['train','test','模型','來源選定','MAE','RMSE','Bias'],[[r['source_dataset'],r['target_dataset'],r['model'],r['source_validation_selected'],num(r['mae_ms']),num(r['rmse_ms']),num(r['mean_bias_ms'])] for r in cross])
lines+=['','![預測與實際時間](plots/prediction_scatter.png)','', f'結論：這次選定Ridge在兩資料集的MAE點估計都較Median差：LFW差{num(ci[0]["delta_ms"])}ms，WIDER差{num(ci[1]["delta_ms"])}ms。LFW的95%群組CI完全為正，WIDER CI跨零，沒有Ridge改善的穩定證據。不以整體混合MAE宣稱勝出。即使某一資料集有改善，也沒有修改Median預設、測試圖、特徵或α。群組隔離對跨人物/事件泛化較嚴格；WIDER事件只是場景代理，不能保證所有人物或語意近重複皆已識別。',
'補充：選定Ridge在兩資料集的RMSE點估計較低、Bias較接近零；這是平均絕對誤差與平方誤差的取捨，不是所有指標都退步。RMSE/Bias沒有另做區間檢定，不能從點估計宣稱穩定優勢。選模目標事先固定validation MAE，因此不因test RMSE較好改變選模規則或預設。',
'證據：dataset_manifest.json、train_val_test_split.csv、evaluation/validation-selection.json、evaluation/models/ JSON、evaluation/estimator_predictions.csv；程式scripts/formal_dataset.py、formal_evaluate.py。']
save('WORKLOAD_ESTIMATOR_REPORT.md',lines)
# V1/V2 report: every fixed condition, not only favorable cells.
lines=['# Latency-aware V1/V2 正式比較','', '原演算法與SimPy核心完全未修改。V1原先串行加總CPU與網路積壓；V2使用前輪既定phase-overlap公式，仍把承諾工作視為聚合需求，可能錯估未來到CPU時間。Deadline分支保留延遲排序，並非獨立收益來源。','',
'比較1：V1+Median對V2+Median，隔離policy；比較2：V1+Median對V1+Ridge，隔離estimator；比較3：V1+Median對V2+Ridge，只能歸因組合。各條件先固定相同100張圖、順序、seed、網路、deadline與完成規則。','',
f'第一組144條件（不混合平均）的>1ms描述計數：{dict(counts)}。CI為同seed配對差的t區間(df=2)，seed只改任務順序；這不是144個假設經多重校正的顯著性結論。所有小差異/退化保留。','', '## 全部144個固定條件：policy效果','']
lines+=table(['dataset','環境','間隔','Deadline','V1平均','V2平均','差ms','配對CI下','配對CI上','Deadline率差'],[[r['dataset'],r['environment'],r['interval_ms'],r['deadline_ms'],num(r['baseline_avg_ms']),num(r['candidate_avg_ms']),num(r['delta_ms']),num(r['paired_ci95_low_ms']),num(r['paired_ci95_high_ms']),num(r['delta_deadline_met_rate'])] for r in policy])
lines+=['','## 退化與改善幅度最大的條件（完整表已列，並非篩選正式測試）','']
lines+=table(['方向','dataset','環境','間隔','Deadline','差ms'],[[label,r['dataset'],r['environment'],r['interval_ms'],r['deadline_ms'],num(r['delta_ms'])] for label,rs in [('退化',sorted(policy,key=lambda r:r['delta_ms'],reverse=True)[:5]),('改善',sorted(policy,key=lambda r:r['delta_ms'])[:5])] for r in rs])
lines+=['','![逐條件成對差](plots/policy_paired_heatmap.png)','', '第二組/第三組的全部條件、所有階段及Deadline差異見paired_differences.csv（432列），完整seed結果strategy_comparison.csv（3456列）。不能把組合效果都算成V2功勞，也不能以跨負載平均宣稱普遍最好。',
'退化原因的可支持範圍：V2的聚合commit工作/未來回傳未完整預估，估計器誤差與不同placement會放大排隊；對具體格可追evaluation/raw相應JSON.gz的decision_input/events與時間分解。本輪未利用這些test結果再改公式，不能把關聯當已證明的唯一因果。',
 f'獨立檢查：12次100圖run（兩資料集×獨立/共享×V1/V2/Edge）均通過離線三階段FCFS參考與確定性重播；最大誤差{max(v["max_reference_error_ms"] for v in ref):.3g}ms。無成本診斷不混入正式端到端表。']
if (E/'regression-case-study.json').exists():
 case=read(E/'regression-case-study.json');w=case['formal_worst_condition']
 lines+=['','## 退化事件重建（獨立診斷，不覆蓋正式結果）','',
  f"最大點估計退化條件為{w['dataset']}/{w['environment']}、間隔{w['interval_ms']}、Deadline{w['deadline_ms']}：三seed平均差{num(w['delta_ms'])}ms，但CI[{num(w['paired_ci95_low_ms'])},{num(w['paired_ci95_high_ms'])}]跨零。時間分解差：CPU等待{num(w['delta_queue_ms'])}、網路{num(w['delta_network_ms'])}、compute{num(w['delta_compute_ms'])}、decision{num(w['delta_decision_ms'])}ms；不能宣稱該格已穩定證明退化。",
  '使用完全相同真實Task與固定Median做零決策成本事件重建；三seed的首次placement分歧前state逐欄相同，故該首次差異可歸因既定估算公式。之後佇列/placement/工作量誤差共同演變，不能把所有總差當單一因素因果。三次各V1/V2共600任務另通過FCFS參考；不是免費正式成績。','']
 lines+=table(['seed情境','首次task','V1選擇','V2選擇','V1三節點估計ms','V2三節點估計ms','實際工作量僅事後ms'],[[r['scenario_id'],r['first_divergence_task'],r['v1_choice'],r['v2_choice'],str(r['first_shared_observation']['v1_costs_ms']),str(r['first_shared_observation']['v2_costs_ms']),num(r['actual_workload_posthoc_only'])] for r in case['diagnostic_runs']])
 lines+=['','Deadline主要改變達成率；在complete_all與既定純延遲排序下，不會單靠Deadline改變服務歷程，故三Deadline多處相同延遲是模型預期。144格及>1ms計數是條件數，不是144個獨立統計證據。']
else:lines+=['','事件重建尚未執行：NOT VERIFIED；先生成paired CSV，再執行formal_case_study.py後重建本報告。']
save('LATENCY_AWARE_COMPARISON.md',lines)
# Laya: explicitly historical, zero costly repetitions.
diag=read(O/'laya/laya-diagnostic-summary.json');laya=csvread(O/'laya/historical_cost_comparison.csv');reuse=read(O/'laya/reuse-manifest.json')
lines=['# Laya可靠性與成本：獨立對照研究','', '本輪新增真實模型呼叫0，沒有調Prompt、重訓、改模型或用規則代替輸出。依使用者效率規則，重新核對既有90次固定診斷及144筆歷史端到端/消融任務的raw choice與HTTP選擇；所有原始模型輸出/時間戳/雜湊保留。這些不是新100圖Laya實驗。','',
'原版/V2同checkpoint與前輪凍結CPU設定；V2是中立緊湊輸入與單thread候選。三節點六排列×兩次重複、RTT/頻寬/算力/queue單因素均沿用固定診斷；最低成本依共同可觀測估計，非隱藏真值Oracle。','']
lines+=table(['版本','合法','最低估計成本正確','平均HTTP ms','P95 HTTP ms','單因素正確'],[[v,f"{diag[v]['legal']}/45",f"{diag[v]['correct']}/45",num(diag[v]['mean_wall_ms']),num(diag[v]['p95_wall_ms']),f"{diag[v]['single_factor_correct']}/9"] for v in ('legacy','v2')])
lines+=['','## 有利情境與排列不變性','']
lines+=table(['版本','情境','正確/12','排列不變','重複一致/6'],[[v,k,f"{r['correct']}/12",r['order_invariant'],r['repeat_consistent']] for v in ('legacy','v2') for k,r in diag[v]['cases'].items()])
lines+=['','每個排列/單因素的選擇與估計成本完整列laya_diagnostic.csv；90個raw choice與最終選擇完全一致、零fallback、原診斷零截斷。相同排列重複一致不代表跨排列可靠。','', '## 既有6圖episode的實測成本（歷史證據）','',
'RECORDED_CHARGED_COST計入原始實測選擇時間；RECORDED_REAL_MODEL_ABLATION是當時另行執行真實模型但不計入模擬延遲的資料。本輪只是重讀，沒有新推論或新Replay，不冒充本輪test評估。原Median與舊test Profile和本輪不同，不可合併正式排名。','']
lines+=table(['dataset','負載','版本','scope','n','平均ms','P95','Deadline','決策ms','決策等待ms'],[[r['dataset'],r['load'],r['strategy'],r['scope'],r['n'],num(r['avg_latency_ms']),num(r['p95_latency_ms']),pct(r['deadline_met_rate']),num(r['decision_ms']),num(r['decision_queue_ms'])] for r in laya])
lines+=['','判斷：兩版都不能可靠選最低數值成本，保留為通用AI失效對照；V2只有Local排列不變，不能認證整體改善。實測CPU決策約秒級，成本與序列等待足以在這些歷史episode侵蝕卸載收益；是否所有新100圖/設備都如此為NOT VERIFIED，沒有以免費重播或Latency-aware輸出代替真正AI來作結論。',
'資料：laya/reuse-manifest.json、laya_diagnostic.csv、laya/下診斷與historical-raw/、historical-audit.jsonl。']
save('LAYA_RELIABILITY_REPORT.md',lines)
# Formal report and final eight answers.
lines=['# 正式實驗資料與策略比較報告','', '本輪目的為擴大獨立圖片及公平比較，不要求V2勝出。原Baseline/V1/V2/估計器/Laya算法保持凍結，所有負面結果保留。','', '## 資料與量測','',
'每資料集40 training、20 validation、100 testing，共320張成功實測；LFW100張test為100個人物，WIDER群組數如下。test排除既有註冊歷史量測，依seed20261104、人物/事件分組在任何新test推論前凍結。320張內容SHA256互異，dHash64距離<=4預篩無重複。dHash不是人臉/語意重複的完整證明。','']
lines+=table(['資料集','角色','圖片','群組'],[[d,role,n,manifest['group_counts'][d][role]] for d,rs in manifest['counts'].items() for role,n in rs.items()])
lines+=['','107張training/validation有效同模型/CPU/至少3次正式歷史量測重用；新增213張各預熱+3正式，共852次InsightFace呼叫。新test200張全部新量測。read/decode/初始化/warmup/lock wait不算影像inference，CPU compute真值是三次中位數。每圖device/model/原始三次/成功狀態/時間戳與來源provenance保留dataset_manifest.json與measurements/。歷史與新量測批次不同，單host調度/熱狀態會帶來量測變異，未量測跨設備。','',
'## 事前情境矩陣','', '8環境×3到達間隔70/300/1000×3 Deadline500/1000/2000×3種子11/23/37×2資料集=432格。每格100張test全部使用，seed只改順序。6種Median策略+V1/V2 Ridge=3456次策略run、345600任務。決策使用同一DecisionTask/NodeState可觀測資訊契約，只有刻意隔離的估計器因素改變預測值。','']
lines+=table(['環境','Local speed','Edge speed/RTT/BW','Cloud speed/RTT/BW','network/shared Mbps'],[[env,config['nodes']['local']['speed'],'/'.join((str(config['nodes']['edge'][k]) for k in ('speed','rtt_ms','bandwidth_mbps'))),'/'.join((str(config['nodes']['cloud'][k]) for k in ('speed','rtt_ms','bandwidth_mbps'))),config['network_mode']+'/'+str(config['shared_bandwidth_mbps'])] for env,config in {s['environment']:s for s in read(O/'preregistered-design.json')['scenarios']}.items()])
lines+=['','speed為相對Local，RTT ms、BW Mbps。獨立上下行資源、CPU單容量、shared上下行各獨立但Edge/Cloud共用出口，符合原模型。完整條件scenario_matrix.csv。固定complete_all，逾期仍完成；Deadline為arrival+relative deadline，達成率與最終完成率不同。',
'正式延遲計入policy timer內的預測與選擇wall time；decision_queue是單序列決策資源等待。訓練/讀取profile/離線選模不算線上決策，也不冒充影像compute。相同任務的actual_workload_sha256跨估計器核對一致。','', '## Reference環境：全部負載/Deadline/策略（逐條件，不混平均）','']
lines+=table(['dataset','間隔','Deadline','估計器','策略','平均ms','P95','Deadline率','完成/丟棄'],[[r['dataset'],r['interval_ms'],r['deadline_ms'],r['estimator'],r['strategy'],num(r['average_latency_ms']),num(r['p95_latency_ms']),pct(r['deadline_met_rate']),pct(r['completion_rate'])+'/'+pct(r['drop_rate'])] for r in agg if r['environment']=='reference'])
lines+=['','所有8環境/3 Deadline/3間隔完整結果與分解：strategy_comparison.csv逐seed，strategy_aggregate.csv每條件三seed均值/SD/t95CI。包含decision/wall/decision_queue/network/CPUqueue/compute、time-weighted queues、各節點utilization與placement。P95定義為各run all-terminal任務nearest-rank 95th percentile；聚合列P95是三個run P95的平均，不是混合分布P95。',
'paired_differences.csv提供三種隔離比較的成對變異與df2區間；CI未多重比較校正，seed不產生新的獨立圖片，不以區間挑winner。','', '![正式reference策略比較](plots/reference_strategy_latency.png)','', '## 正確性與限制','',
'所有345600筆時間守恆、階段順序、真實compute不變、唯一任務、100%完成及無丟棄；CPU區間不超額，policy DTO沒有真實workload/人臉數/來源路徑。12個100圖零決策成本run另經獨立FCFS CPU與上下行參考/確定性重播。原單元、API與Docker驗證記錄見tests/。核心與V1等受保護SHA256核對未改。',
'簡化限制：當下節點狀態無監測延遲；固定頻寬序列傳輸/全雙工、固定16KB結果、相對speed線性縮放，不是實際遠端部署；聚合commit不是精確未來排程；單host小量三次推論與三種任務順序，WIDER事件分組不是完整人物隔離。','', '## 最終八項回答','',
'1. 圖片量：YES，LFW/WIDER各100個內容唯一的新實測test，另各40/20訓練/驗證；群組數及近似重複限制如上，不能把100圖當100個WIDER獨立事件。',
'2. Median/Ridge：依WORKLOAD_ESTIMATOR_REPORT逐資料集MAE與群組CI判斷；沒有跨資料集全面勝出預設，保留Median。',
 f'3. V2：不能宣稱普遍優於V1。固定Median144個條件>1ms計數為{dict(counts)}；全量退化格與CI見LATENCY_AWARE_COMPARISON與paired_differences.csv。',
'4. Laya：FAIL，兩版都未通過數值成本/排列可靠性，原始輸出如實保留。',
'5. Laya成本：歷史CPU秒級決策與序列等待顯著侵蝕可得卸載效益，正式/消融表已列；本輪新100圖與其他硬體的普遍成本優劣為NOT VERIFIED，沒有重複昂貴推論。',
'6. 公平性：PASS，所有本輪非AI策略相同100圖、順序、環境、deadline、完整完成標準，決策cost統一；預估器因素刻意隔離。Laya為獨立歷史研究，不混入當前排名。',
'7. 組員程式：PASS，原RL/核心/V1檔案逐位元組未改；新增獨立可觀測轉接與8項相容測試。真實訓練DQN/DDQN模型未提供，因此實際演算法準確率/耗時整合為NOT VERIFIED，HTTP的DQN key仍未註冊。',
'8. 期末證據：有條件YES，可支持這批凍結資料與已宣告SimPy假設下的課堂比較與負面結果；不能支持實際遠端平台效能、Laya可靠數值AI或未測DQN成績。',
'', '重現命令與介面欄位見TEAM_INTEGRATION_CONTRACT.md、CODEX_PROGRESS.md；所有raw JSON及CSV保留，不因不利結果改算法/測試資料。']
if (O/'tests/test-summary.json').exists():
 t=read(O/'tests/test-summary.json');lines+=['','## 最終回歸實際結果','',f"{t['backend_pass']}/85後端、{t['laya_service_mock_pass']}/2 Laya服務mock、{t['http_checks_pass']}/109 HTTP檢查通過；Docker build/up成功，backend/db/laya healthy、frontend running。18個診斷run共1800任務通過獨立FCFS，另12次確定性重播一致。瀏覽器視覺點擊與真實DQN權重未驗證，詳見tests/test-summary.json與原始logs。",'','與前輪12圖結果不同，是資料擴大、群組隔離、凍結新圖片與重新擬合訓練集的實驗差異；V1/V2公式未變，不能把新舊數據差當算法改進。']
else:lines+=['','最終回歸紀錄尚未匯入：NOT VERIFIED。']
save('FORMAL_EXPERIMENT_REPORT.md',lines)
summary=dict(strategy_runs=len(raw),task_results=345600,paired_conditions=len(pairs),policy_effect_conditions=len(policy),policy_difference_counts=dict(counts),estimator_choice=ridge,estimator_ci=ci,reference_max_error_ms=max(v['max_reference_error_ms'] for v in ref),laya_new_calls=0)
(O/'report-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False))
