# DQN／DDQN 組員整合契約（offloading-decision-v1）

> 2026-11-10 更新：新 49 維 DQN／DDQN 已用既有 IndexPolicy/run_policy 進行離線 SimPy 整合；見 DQN_DDQN_SIMPY_ADAPTER.md。以下保留原契約文件；HTTP 策略註冊仍未新增。

本輪沒有修改或訓練 DQN／DDQN；既有 `rl.py`、Task/NodeState、SimPy、Baseline/V1/V2 均保持原檔雜湊。新增 `integration_contract.py` 是獨立轉接工具，不是已訓練策略。真實 DQN／DDQN 權重、特徵正規化與推論耗時尚未提供，實際模型整合為 **NOT VERIFIED**。

## 三種入口與相容範圍

|用途|入口|決策成本|注意|
|---|---|---|---|
|既有固定/Latency/Laya比較|experiment(...), HTTP POST /api/offloading/experiments|include_decision_overhead=True正式|DQN/DDQN HTTP key尚未註冊，送出仍422|
|RL訓練/逐事件互動|OffloadingEnv.reset()/step(int)|排除wall time|既有介面拒絕include_decision_overhead=True，不能把它的結果當正式端到端|
|已訓練外部policy正式評估|IndexPolicy(select_action) + run_policy(tasks, policy, ...)|使用既有Simulator timer|select_action只收49維可觀測tuple，回Python int 0/1/2；沒有改組員程式或替代學習演算法|

若組員現有模型不是這個特徵順序/動作mapping，應由組員提供適配器或重新說明其輸入規格；本輪不直接修改模型、權重或訓練碼。若需HTTP註冊，需另外完成實際模型依賴/載入/失敗處理與向後相容測試，目前 **NOT VERIFIED**。

## Task：只由模擬器持有真值

來源 `backend/app/offloading/models.py:Task`，immutable dataclass；完整欄位及機器可讀schema見 `team_interface_schema.json`。

|欄位|型別／單位|權限與意義|
|---|---|---|
|task_id|int >=0|episode內唯一，episode reset可重用|
|image_size_mb|float >0，十進位MB|可觀測|
|width,height|int，pixels|可觀測，保存模型需要正數|
|arrival_ms|float >=0，ms|模擬epoch相對到達時間|
|deadline_ms|float >0，ms|相對arrival期限；絕對期限=arrival+deadline|
|estimated_workload_ms|float >0，參考Local ms|只由訓練歷史模型/中位數產生|
|result_size_kb|float >0，十進位KB|固定16KB的已宣告假設|
|workload_ms|float >0，Local實測ms|**模擬器內部真值，禁止agent特徵使用**|
|face_count|int >=0|**推論後真值，只能事後分析**|
|source_path,dataset,sample_id|string|資料追蹤與分割，不傳給policy DTO|

Python物件不是安全沙箱，能讀到整個Task/檔案的外部agent可以主動違規。本契約的隔離由傳入的DecisionTask/feature_vector、測試與資料治理保障，不能聲稱防禦惡意反射或檔案讀取。

## DecisionRequest 與 DecisionTask

共用 `decision_request(task,state)` 回傳：

```json
{"schema":"offloading-decision-v1","task":{"task_id":0,"image_size_mb":0.1,"width":250,"height":250,"arrival_ms":0,"deadline_ms":1000,"estimated_workload_ms":500,"result_size_kb":16},"nodes":["三個NodeState物件，依local/edge/cloud順序"]}
```

此處schema是新增離線組員契約，不是改寫Laya HTTP服務。Laya既有 `/decide` 收 `{context,task,nodes,variant}`，variant省略為legacy、V2為v2；不需要傳此schema字串。實驗HTTP `ExperimentRequest` 是整批情境設定，也不是單任務DecisionRequest。完整真實DTO範例見 `team_contract_example.json`（不含真實工作量/人臉數）。

DecisionTask只有8欄：task_id、image_size_mb、width、height、arrival_ms、deadline_ms、estimated_workload_ms、result_size_kb。正式模式只用realistic；Oracle是另列診斷，不可用於正式DQN輸入。

## NodeState 與 SystemState

SystemState={local,edge,cloud}，`nodes()`固定此順序；每個NodeState為immutable snapshot。

|欄位|單位／語意|
|---|---|
|name|local/edge/cloud|
|compute_speed|相對實測Local速度，Local=1|
|queue_length|CPU真正等待佇列長度，不含執行中與尚在上傳|
|queue_work_ms|執行中估計剩餘+CPU等待的參考Local工作量；不是隱藏實際剩餘時間|
|rtt_ms|完整RTT；上/下傳各先支付一半傳播|
|bandwidth_mbps|十進位Mbps，共享模式為min(路徑BW,共享BW)|
|upload_backlog_ms,download_backlog_ms|當前已提交傳輸的估計服務剩餘/等待；不包含尚未產生的未來回傳|
|available|bool，目前配置節點均可用；外部adapter拒絕不可用動作|
|cpu_running|CPU執行數，目前容量1|
|committed_count|已承諾但尚未進CPU的任務數，含upload階段|
|transmitting_count|upload階段任務數，含該階段等待/傳播|
|returning_count|回傳階段任務數，含等待/傳播|
|committed_work_ms|未到CPU承諾的估計參考工作量；不能再把它當CPU waiting重加|
|observed_at_ms|這次節點snapshot的SimPy時間|

CPU、上下行都使用容量1 FCFS Resource。獨立模式Edge/Cloud各一對link；shared模式共用上行一個、下行一個，雙向獨立。沒有即時監測誤差模型。不能把此簡化網路當現實TCP公平共享。

## 49維State特徵與Action

精確順序由 `FEATURE_NAMES`/`team_interface_schema.json`固定，不能自行把Node字典迭代順序當特徵順序。

1. 七個task特徵：image_size_mb,width,height,arrival_ms,deadline_ms,estimated_workload_ms,result_size_kb（不含task_id）。
2. 依local、edge、cloud，各14個NodeState數值特徵：compute_speed,queue_length,queue_work_ms,rtt_ms,bandwidth_mbps,upload_backlog_ms,download_backlog_ms,available,cpu_running,committed_count,transmitting_count,returning_count,committed_work_ms,observed_at_ms。
3. 轉為49個finite float，bool轉0/1；沒有額外全域未來任務/實際完成時間/人臉數。

`Action`為Python int：0=local、1=edge、2=cloud；bool/float/string/numpy scalar需由組員明確轉換成合法Python int。原Simulator的 `select_node` 最終回節點字串。無效/不可用動作丟錯，不偷偷選最佳節點或fallback。

## Reward、Next State、Done 與重置

既有 `OffloadingEnv.step(action)` 回 `(next_observation, summed_reward, done, info)`。observation為 `(DecisionTask,SystemState)`；新特徵可用 `feature_vector(*observation)`。

每個終止任務reward：`-total_latency_ms/1000 - (0 if deadline_met else 1)`。這是原有dimensionless定義，未修改、未額外給最佳節點標籤。step可能暫時沒有任務完成，或同時回多個終止reward；`info.terminal_rewards`內的task_id必須用於延遲credit attribution。不能把本step所有完成reward硬算成剛選的那個任務的即時reward。這是事件推進的SMDP/continuing介面，非每次action立即完成一張圖。

next_observation是下一個待決策事件；done時沒有下個觀測，環境已處理到任務終止。reset重建完整SimPy、CPU、網路、decision queue、統計，未清除外部agent訓練權重；外部agent的episode記憶需自行reset。不得使用sim.results或env._tasks當agent未來資訊。

## 資料與預估器契約

- 本輪test IDs：LFW `8053cd81edaf0f78b6c4cf545fc48eb5`、WIDER `c886a882920b62bb440a3354df8682ca`；各100張，不抽少量再冒稱100張。
- train/validation各40/20，六份Profile ID、檔案checksum、圖片SHA與人物/事件群組在dataset_manifest.json、train_val_test_split.csv；來源路徑必須為正規化dataset-relative POSIX路徑。
- `validate_manifest_split`是新三分割group/content/path guard，須提供真實驗證過的SHA256。既有EpisodeSplit只驗證training/testing來源身份，未新增validation欄；不要誤認它會驗證完整群組/圖片內容。
- 對新複製或改名檔案，來源ID guard不足以驗證內容，必須另算SHA256/dHash/群組。WIDER事件群組不等於人物ID，跨集合人物或所有語意近重複無法完全驗證。
- State scaler/模型超參數只能用training/validation；不得以test重訓、挑checkpoint或改reward。訓練時間與線上predict時間分開。
- 新選定Ridge只按validation MAE；Median預設保留。模型JSON含training/validation來源身份並以內容SHA256 ID註冊；load_registered與validate_test檢查。正式agent與其他策略須使用相同估計器才能隔離policy效果。

## 共用正式執行器範例

```python
from dataclasses import replace
from app.offloading.estimators import load_registered, EstimatedPolicy
from app.offloading.integration_contract import IndexPolicy, run_policy
from app.offloading.workload import generate_tasks
from app.offloading import profiles

_, rows = profiles.load('8053cd81edaf0f78b6c4cf545fc48eb5')
model = load_registered('5405ea0f82f73f4d37ac9b2c06f3f879c9add4cc60e03465c9d18843e9b19c48')
model.validate_test(rows)
tasks = generate_tasks(count=100, interval_ms=70, seed=11, deadline_ms=1000, profile=rows)
tasks = [replace(t, estimated_workload_ms=model.predict(t)) for t in tasks]
# trained_agent由組員供應；此文件不包含已訓練DQN/DDQN。
policy = EstimatedPolicy(IndexPolicy(trained_agent.select_action), model)
result = run_policy(tasks, policy, include_decision_overhead=True,
                    information_mode='realistic', network_mode='independent',
                    deadline_policy='complete_all')
```

特徵正規化與裝置資料搬移若是線上predict的一部分，必須放在select_action裡，才會由同一timer計入。離線載入權重、訓練、資料分割不算線上cost。不得以固定假設成本取代實測predict，也不能把模型秒數加到影像compute_ms。這個例子只保證介面，不證明真實DQN權重可用。

## 統一完成與輸出規格

- 正式固定complete_all；逾期仍完成，Deadline met不同於completion。若將來比較drop_if_expired，所有策略須同一規則另立情境，不與本輪混平均。
- `total_latency_ms = completed_at_ms-arrival_ms = decision_queue_ms+decision_ms+network_ms+queue_ms+compute_ms`。
- network_ms含傳播/傳輸/網路等待，queue_ms只有CPU等待。time-weighted CPU queue為等待面積/整體run horizon，不是決策時點均值。
- run_policy輸出summary/tasks/node_statistics/queue_samples/events，沿用experiment.metrics。summary P95為所有終止任務nearest-rank；丟棄亦含已耗時間。
- 統一CSV欄位、三種配對對照與scenario_id見strategy_comparison.csv、paired_differences.csv、scenario_matrix.csv；`actual_workload_sha256`排除預估欄、保持真值/順序一致。
- seeds11/23/37只改100張test排列；8環境、到達70/300/1000ms、Deadline500/1000/2000ms在preregistered-design.json，不重挑有利情境。

## 驗證與重現

本輪新增8項測試在test_integration_contract.py：49維順序、真值變動隔離、拒絕內部Task、JSON DTO、外部動作、無效/不可用動作、RL延遲reward/終止與標準executor一致、三分割群組/內容守門。加上原77項共85項後端測試。互動RL的decision_wall_ms按原設計是0，外部select_node消融仍保留真實wall記錄，因此相容比對所有模擬結果但分開此一wall觀測欄，沒有更動時間標準。

```powershell
docker compose -f compose.yaml -f compose.ai.yaml up -d --build
docker compose exec -T backend python -m unittest discover -s tests -v
docker compose exec -T backend mkdir -p /app/scripts
Get-ChildItem scripts/formal_*.py | ForEach-Object { docker compose cp $_.FullName ('backend:/app/scripts/'+$_.Name) }
docker compose exec -T backend python /app/scripts/formal_dataset.py
python scripts/formal_design.py --output work/formal-evaluation
python scripts/formal_laya.py
docker compose cp work/formal-evaluation/laya backend:/profiles/formal-evaluation/laya
docker compose exec -T backend python /app/scripts/formal_evaluate.py
docker compose exec -T backend python /app/scripts/formal_reports.py  # 先產生paired CSV
docker compose exec -T backend python /app/scripts/formal_case_study.py
python scripts/verify_formal_api.py
# 將work/formal-evaluation/tests內實測test-summary與logs匯入/profiles/formal-evaluation/tests後
docker compose exec -T backend python /app/scripts/formal_reports.py
```

既有plan/逐圖checkpoint/fit-complete/raw格會重用，避免重測或test再調參。若想跑全新設計，須另立版本輸出目錄並重新事前登錄，不能混入本輪raw資料。不能刪除資料庫volume、資料集或模型快取。
