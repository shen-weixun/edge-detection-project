from pathlib import Path
import os,json,csv,statistics,collections
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
out=Path(os.getenv('EXPERIMENT_OUTPUT',str(Path(__file__).resolve().parents[1]/'work'/'sensitivity')))
audit={x['audit_id']:x for x in map(json.loads,(out/'decisions.jsonl').read_text(encoding='utf-8-sig').splitlines())}
rows=list(csv.DictReader((out/'summary.csv').open(encoding='utf-8-sig')))
trace=[];choices=collections.Counter();agree=0;models=collections.Counter();truncated=0
for path in sorted(out.glob('interval-*-deadline-*.json')):
 x=json.loads(path.read_text(encoding='utf-8'));interval=x['config']['interval_ms'];deadline=x['config']['deadline_ms']
 for t in x['strategies']['laya']['tasks']:
  a=audit[t['decision_audit_id']];raw=a['raw_output'];answer=raw['answers']['offload_target'];task=a['state']['task']
  assert answer['choice']==a['final_choice']==t['selected_node']
  assert not a['fallback_used'] and 'error' not in a
  assert a['context']['source_path']==t['task']['source_path'] and a['context']['task_id']==t['task_id']
  assert task['workload_ms']==t['task']['workload_ms'] and task['deadline_ms']==deadline
  estimates={}
  for n in a['state']['nodes']:
   v=(task['workload_ms']+n['queue_work_ms'])/n['compute_speed']
   if n['name']!='local':v+=n['rtt_ms']+task['image_size_mb']*8000/n['bandwidth_mbps']+task['result_size_kb']*8/n['bandwidth_mbps']+n['upload_backlog_ms']+n['download_backlog_ms']
   estimates[n['name']]=v
  fastest=min(estimates,key=estimates.get);agree+=fastest==t['selected_node'];choices[t['selected_node']]+=1;models[raw['routing']['model']]+=1;truncated+=bool(raw.get('usage',{}).get('truncated'))
  trace.append(dict(interval_ms=interval,deadline_ms=deadline,task_id=t['task_id'],source_path=t['task']['source_path'],audit_id=a['audit_id'],task_json=json.dumps(task),nodes_json=json.dumps(a['state']['nodes']),raw_output_json=json.dumps(raw),final_choice=a['final_choice'],estimated_fastest=fastest,estimates_json=json.dumps(estimates),decision_ms=t['decision_ms'],decision_queue_ms=t['decision_queue_ms']))
assert len(trace)==270
with (out/'laya-decision-trace.csv').open('w',newline='',encoding='utf-8-sig') as f:
 w=csv.DictWriter(f,fieldnames=list(trace[0]));w.writeheader();w.writerows(trace)
probes=json.loads((out/'diagnostic-probes.json').read_text(encoding='utf-8-sig'))
analysis=dict(decisions_checked=len(trace),raw_choice_final_match=270,fallback_used=0,selected=choices,checkpoint=models,truncated_inputs=truncated,observable_estimate_agreement=agree,probe_correct=sum(p['expected_fastest']==p['response']['node'] for p in probes),probe_total=len(probes))
(out/'audit-analysis.json').write_text(json.dumps(analysis,indent=2),encoding='utf-8');print(json.dumps(analysis,indent=2))
strategies=['local_only','edge_only','cloud_only','load_threshold','latency_aware','laya'];intervals=[70,300,1000];deadlines=[500,1000,2000]
def find(i,d,s):return next(r for r in rows if int(float(r['interval_ms']))==i and int(float(r['deadline_ms']))==d and r['strategy']==s)
fig,axes=plt.subplots(1,2,figsize=(13,5),constrained_layout=True)
for s in strategies:axes[0].plot(intervals,[float(find(i,1000,s)['avg_latency_ms']) for i in intervals],marker='o',label=s)
axes[0].set(xlabel='Arrival interval (ms)',ylabel='Mean end-to-end latency (ms)',title='Same 30 LFW images; deadline 1000 ms',yscale='log');axes[0].legend(fontsize=8);axes[0].grid(alpha=.2)
bottom=np.zeros(3)
for key,label in [('decision_queue_ms','Decision queue'),('avg_decision_ms','Measured decision'),('cpu_queue_ms','CPU queue'),('network_ms','Network + channel wait'),('compute_ms','Simulated compute')]:
 values=np.array([float(find(i,1000,'laya')[key]) for i in intervals]);axes[1].bar([0,1,2],values,bottom=bottom,label=label);bottom+=values
axes[1].set(xticks=[0,1,2],xticklabels=['70','300','1000'],xlabel='Arrival interval (ms)',ylabel='Mean latency (ms)',title='Laya latency breakdown');axes[1].legend(fontsize=8)
fig.savefig(out/'arrival-queue-comparison.png',dpi=170);plt.close(fig)
fig,ax=plt.subplots(figsize=(12,4),constrained_layout=True);vals=np.array([[float(find(i,d,s)['deadline_met_rate'])*100 for i in intervals for d in deadlines] for s in strategies]);im=ax.imshow(vals,cmap='RdYlGn',vmin=0,vmax=100,aspect='auto')
ax.set(xticks=range(9),xticklabels=[f'{i}/{d}' for i in intervals for d in deadlines],yticks=range(6),yticklabels=strategies,xlabel='Arrival interval / Deadline (ms)',title='Deadline attainment (%) — actual Laya CPU decisions, simulated service/network')
for iy in range(6):
 for ix in range(9):ax.text(ix,iy,f'{vals[iy,ix]:.1f}',ha='center',va='center',fontsize=9)
fig.colorbar(im,ax=ax,label='%');fig.savefig(out/'deadline-attainment.png',dpi=170);plt.close(fig)
report='''# Laya 選擇稽核、到達間隔與 Deadline 實驗

使用同一份最近建立的 LFW 30 張實測 Profile；Profile ID、CSV SHA-256、固定圖片序列 SHA-256 與節點設定見 manifest.json。所有 9 組均固定相同圖片、順序、實測推論時間、seed=42、節點參數，僅改到達間隔／Deadline。每組六策略使用全新 SimPy 狀態；正式結果統一計入決策與決策等待。先做一次 Laya 預熱（warmup.json，不計入九組）。每情境僅執行一次，因此決策 wall-clock 有執行主機抖動，不能據小差距宣稱統計顯著。

## Laya 原始輸出與固定預設檢查

'''
report+=f"共核對 {len(trace)} 筆正式模型決策；270/270 原始 choice、服務 final_choice、SimPy selected_node 完全一致；fallback_used 全部為 false，輸入截斷 {truncated} 筆。分配合計 {dict(choices)}。所有決策實際路由到 {dict(models)}。原始 routing.reason 顯示數字及 Latin 結構未識別特定語言時採用預設 multilingual checkpoint；這是模型選擇預設，並非 Cloud 節點 fallback。\n\n"
report+='''服務與 client 沒有固定回傳 Cloud；缺失或非法 choice 會報錯。每次輸入 task、三節點 state、完整 questions、Router 原始回傳（機率、信心、usage、routing）及 final_choice 均保存於 decisions.jsonl，亦展開為 laya-decision-trace.csv。audit_id 與結果 task 一對一連結。修正原本在任務完成時才讀取共用策略 metadata 的問題，現在決策後立即保存，避免信心值／模型資訊被後續任務覆寫。

'''
report+=f"將每次快照按目前 Latency-aware 的估算式重算，Laya 選擇與估算最低延遲一致 {agree}/270 筆。這只衡量與估算式相符程度，不是模型準確率。真實 LFW 圖片很小，且 Cloud 相對算力設定為 8 倍，Cloud 在不少任務確實具有低服務延遲；但這不足以證明 Laya 能正確處理數值與排隊。\n\n"
report+='''額外六次「合成診斷」（非實測工作負載、未混入九組結果）：讓 local／edge／cloud 分別有壓倒性優勢，再反轉 nodes 陣列順序；同一狀態語意的輸入順序改變就導致選擇變動。結果如下：

|明顯最佳節點|原始順序選擇|反轉順序選擇|
|---|---|---|
'''
for n in ['local','edge','cloud']:
 pp=[p for p in probes if p['expected_fastest']==n];report+=f"|{n}|{pp[0]['response']['node']}|{pp[1]['response']['node']}|\n"
report+='''
這證明模型不是固定選 Cloud，也顯示目前 checkpoint／提示對節點排列敏感，未可靠遵循數值成本；僅憑 30 次 Cloud 不能視為已學會最佳卸載策略。原 criteria 還包含「Cloud faster compute」等固定文字，可能加強語意偏好；此為待驗證假說。本輪保持原模型和提示一致，未用規則替換 Laya 或偷偷改選節點。

## 到達間隔：固定 Deadline 1000 ms

|策略|間隔 ms|平均端到端 ms|平均決策排隊 ms|平均 CPU 排隊 ms|達成率|
|---|---:|---:|---:|---:|---:|
'''
for s in strategies:
 for i in intervals:
  r=find(i,1000,s);report+=f"|{s}|{i}|{float(r['avg_latency_ms']):.2f}|{float(r['decision_queue_ms']):.2f}|{float(r['cpu_queue_ms']):.2f}|{float(r['deadline_met_rate'])*100:.1f}%|\n"
report+='''
Laya 的主要等待在共用序列決策資源，不在 Cloud CPU；70/300 ms 到達比每次約 0.9 秒決策更快，形成決策積壓。1000 ms 到達讓決策等待大幅下降，但平均延遲仍含真實決策成本。Local-only 的 CPU 排隊亦隨放慢到達改善。不能把此決策瓶頸歸因於 Cloud 網路。

## Deadline 達成率
'''
for i in intervals:
 report+=f'\n### 到達間隔 {i} ms\n\n|策略|500 ms|1000 ms|2000 ms|\n|---|---:|---:|---:|\n'
 for s in strategies:report+='|'+s+'|'+'|'.join(f"{float(find(i,d,s)['deadline_met_rate'])*100:.1f}%" for d in deadlines)+'|\n'
report+='''
放寬 Deadline 不會消除過載。Laya 在 1000 ms 到達、2000 ms Deadline 的本次 30 筆皆達標；70/300 ms 仍有明顯決策排隊。Deadline 會傳給 Laya，因此不同 Deadline 的模型選擇可變，且實測決策時間也會抖動；各列是各自執行的完整實驗，不是把同一延遲事後換門檻。

## 驗證與檔案

- 九組 × 六策略 × 三十任務＝1620 筆模擬結果；其中270次真實Laya決策。另1次預熱、6次合成診斷，合計277筆稽核。
- 28項單元測試通過，0失敗，新增決策metadata不被後續任務覆寫的回歸測試。
- 比較原始 JSON：interval-*-deadline-*.json；摘要：summary.csv；逐次模型紀錄：decisions.jsonl、laya-decision-trace.csv；固定設定：manifest.json。
- 修改 compose.ai.yaml、laya_service/server.py、backend/app/offloading/laya_client.py、simulator.py、backend/tests/test_profiles.py；新增 scripts/run_sensitivity.py、probe_laya.py、analyze_sensitivity.py。
- 稽核持久保存於主機 profiles/laya_audit/decisions.jsonl；不更動既有資料集或模型快取。
- 重現：啟動 AI Compose；設定 WORKLOAD_PROFILE_ID 和 EXPERIMENT_OUTPUT，執行 python scripts/run_sensitivity.py。節點狀態診斷需從 backend 容器執行 scripts/probe_laya.py。這批結果僅適用此 LFW Profile、CPU模型與模擬參數，不是實際 Cloud/Edge 跑分。
'''
(out/'實驗分析報告.md').write_text(report,encoding='utf-8')
