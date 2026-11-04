# Local–Edge–Cloud architecture audit

## Baseline at f8ec356

`workload.load_profile` validates successful buffalo_l CSV rows with >=3 measurements. `profiles.measure_row` measures read, decode, warmup and median detection+recognition separately. `generate_tasks` samples without replacement; `experiment.experiment` creates one manifest and a fresh Simulator per strategy. No actual remote image inference occurs.

`Simulator._process`: arrival -> shared capacity-one decision Resource -> synchronous policy call measured with perf_counter -> optional virtual decision timeout -> outbound RTT/2 -> serialized upload -> capacity-one FCFS CPU -> return RTT/2 -> serialized download -> result. A synchronous model call pauses wall-clock execution of the event loop, but advances virtual time only through the explicit timeout; queued arrivals still execute at their scheduled virtual times.

`_Node` has one CPU and two `_SerializedLink` Resources. Edge and Cloud links are independent (model A), and uplink/downlink are independent full duplex. Each transfer monopolizes its link, not processor sharing. RTT consumes time but not channel capacity. Local bypasses all network stages. MB/KB are decimal; upload milliseconds = MB*8000/Mbps, result = KB*8/Mbps. Result size defaults to 16 KB. Speeds default to 1/3/8, RTT 0/20/100 ms, bandwidth 1000/120/55 Mbps (`DEFAULT_NODES`, `NodeConfig`). CPU capacity is deliberately one per node.

`Task` includes actual inference and face count; `estimate_latency` and `LayaStrategy.select_node` consume these. This is oracle information, despite the original observable-contract docstring. `Node.state` derives true outstanding CPU work from a future work_until and omits tasks still transmitting. `queue_samples` samples only at decisions. `metrics` assumes completion=1/drop=0. DQN/DDQN are rejected; no training interface existed.

## Confirmed findings and planned corrections

|Priority|Evidence|Correction|
|---|---|---|
|P0|strategies.estimate_latency, laya_client.select_node consume actual per-image labels|Separate DecisionTask, historical disjoint calibration, explicit realistic/oracle|
|P0|_process increments outstanding only after upload|Track commitments, transmission, CPU waiting/running and returning independently with estimated work|
|P0|_process reports decision_ms although ablation advances no time|Report wall measurement separately; charged component zero in ablation|
|P1|Node.state uses actual future remaining service|Estimate remaining work from historical estimate and elapsed observable service, never true scheduled finish|
|P1|Only decision-sampled queue means|Integrate CPU waiting count over virtual time|
|P1|Independent channels could be mistaken for shared access|Explicit independent/shared modes and hand-calculated contention tests|
|P1|metrics hardcodes completion|Explicit complete_all and stage-boundary drop_if_expired; account for consumed stages|
|P1|No RL transitions/reset|Shared DecisionTask/State/Action transition adapter, no trained-policy claim|

Original evidence remains under `work/audit/before`. Final validation and model limitations will be appended after tests.


## 修正後架構與精確假設（audit-v2）

### 資料與資訊權限

- `models.Task` 是模擬器內部輸入，保留實測 workload_ms、face_count 與來源身份；結果 JSON 可供離線稽核，但不傳入策略。
- `models.DecisionTask.observe` 為所有六策略建立相同的 frozen DTO，僅含 task_id、檔案大小、寬高、到達時間、相對 Deadline、預估工作量、設定的回傳大小；不含來源路徑、人物身份、真實推論時間、實際人臉數、未來任務清單或完成時間。task_id 只供該次決策關聯。
- `workload.calibration_estimate` 使用另一份、來源身份零重疊的歷史 Profile 中位數。這是簡單常數估計器，不假裝依圖片特徵建模。Realistic 實測 API 缺少校準集或有重疊一律 422，沒有偷用全測試集平均值。合成示範使用明示的 150 ms 先驗。
- `Simulator(information_mode='oracle')` 才用當前任務真實工作量作為 estimated_workload_ms；輸出頂層與 config 清楚標記 oracle。仍不提供人臉數或未來任務。Oracle 只是工作量資訊理想化；不保證某個啟發式策略一定形成數學上界。
- `laya_client.LayaStrategy.select_node` 限定 DecisionTask 類型，禁止意外將內部 Task 序列化；模型呼叫失敗或非法節點仍報錯，無 fallback。`laya_service.server.decide` 保留真實 Router、原始輸出與 audit_id。
- 身份隔離目前以 `(dataset, source_path)` 核對，沒有對不同路徑的影像做內容去重。既有 LFW 相同路徑不能進入校準與測試兩邊；外部新增重複檔案時需另行核對內容。

### 事件與資源

`Simulator._process` 依序：到達 → 等待單一決策資源 → 取得當下狀態與 DecisionTask → 真實策略呼叫 → 計入其 wall time 的虛擬 timeout → 選定節點並建立承諾 → 上傳 RTT/2 → 上傳資源排隊與傳輸 → CPU FCFS 等待 → CPU 執行 → 回傳 RTT/2 → 下載資源排隊與傳輸 → 完成或期限政策終止。

同步 HTTP/模型呼叫會暫停模擬執行的真實時間，但 SimPy 虛擬時間仍只由事件推進。模型輸入使用呼叫開始時的快照，決策執行期間可能已過時；這是明確的序列決策器假設。`test_wall_blocking_preserves_virtual_arrivals` 驗證 A 決策 100 ms、B 在 20 ms 到達時，B 等待 80 ms，而不是改寫 B 到達時間。固定策略也實測函式呼叫成本，沒有替換為 AI 成本或設定固定假成本。

- 每策略、每次 experiment 都建立新的 Environment、CPU/鏈路/決策 Resource 與統計，`Simulator.start/run` 禁止重用同一 episode。
- CPU 一律容量 1（本次不增加多核心設定），非搶先、FCFS。真實服務時間仍為原 CSV 推論時間除以相對算力，不會因改用估計決策就修改執行真值。
- `_SerializedLink` 使用 capacity=1 Resource；pending 只保存可從檔案大小與設定頻寬計算的傳輸耗時，不從未來 CPU 結果推算。
- 模式 A `independent`：Edge/Cloud 各自擁有獨立上、下載通道。模式 B `shared`：兩節點共用一個上傳 Resource 與另一個下載 Resource，有效頻寬為 min(路徑頻寬, 共用出口頻寬)。這是單一串列瓶頸近似，不是兩層網路管線，也不是連續公平分頻模型。共享模式同一方向同時只能服務一個任務。
- 上下載獨立全雙工；RTT 的兩半不占序列化通道。Local 完全不走傳輸。MB/KB 皆十進位。結果大小固定假設 16 KB，與真實人臉數無關。

### 節點狀態與預測

`_Node.jobs` / `_Node.stage` 記錄 committed、upload、cpu_wait、cpu_run、return 五階段。`_Node.state` 提供：

|欄位|定義|是否含真實未來結果|
|---|---|---|
|queue_length|已到 CPU 的等待數，不含執行者|否|
|cpu_running|目前 CPU 執行數|否|
|queue_work_ms|等待任務估計工作量＋max(0, 執行者估計工作量－已執行時間×speed)|否；即使實際長任務超出預估也不暴露未來剩餘時間|
|committed_count/work_ms|已分配、尚未進 CPU 的任務數／預估參考工作量|否|
|transmitting_count|處於上傳階段（含 RTT、通道等待）的任務數|否|
|returning_count|CPU 完成後回傳中的任務數，不再占 CPU 工作量|否|
|upload/download_backlog_ms|目前通道服務與等待的剩餘可計算傳輸需求|否|
|observed_at_ms|快照的虛擬時間|否|

`strategies.estimate_latency` 加入承諾工作，避免看不見上傳中的 A；但它仍是可重現的保守啟發式：將 CPU 工作、鏈路積壓與本任務網路時間相加，沒有精確求解傳輸/CPU 的重疊流水線。不能把估計值當成真正完成時間。Load-threshold 仍以門檻 2 決定 Edge/Cloud，現在將尚未到達 CPU 的承諾任務納入負載門檻，因此與舊版本策略語義略有不同。

`_Node.stage` 在每個階段切換時積分 CPU 等待數，`Simulator.node_statistics` 同時輸出決策時點平均及時間加權平均；正式 UI 優先顯示時間加權值。平均期間為虛擬 0 到該策略最後終止事件，包括閒置及回傳時間。CPU utilization 使用所有已耗用 compute_ms / 同一期間。

### 時間守恆與期限

結果保留完整浮點精度（不在各元件先四捨五入）：

`completed_at_ms - arrival_ms = decision_queue_ms + decision_ms + network_ms + queue_ms + compute_ms`。

network_ms 包含 RTT、鏈路等待與實際傳輸；queue_ms 只含 CPU 等待。`decision_wall_ms` 永遠記錄測得成本。正式 include_decision_overhead=True 時，decision_ms 等於 wall；消融時 decision_ms=0、decision_queue_ms=0，wall 獨立保留，輸出 comparison_scope=selection_quality_ablation。消融不是端到端效能。

- `complete_all`：永遠執行到結果送達，Deadline 僅判定是否達標。
- `drop_if_expired`：只在非搶先階段邊界或取得排隊資源時檢查 `now > arrival + deadline`，等於期限仍有效。已開始的決策、傳播、傳輸或計算全部計費；等待者取得資源時若已過期不再開始服務。不是期限一到就強制中斷；因此終止時間可超出 Deadline。
- 過期即使已算完或下載完也拒絕結果，completed=False、dropped=True；已耗用 CPU/網路時間保留。每個輸入都有一筆終止紀錄與 drop_reason，Resource 透過 context manager 釋放。
- `experiment.metrics` 分別計算 Deadline 達成率、最終完成率、丟棄率；平均/P95 的母體明示為所有終止任務（包含被丟棄者的已耗用延遲）。不同 drop 政策不能只用平均延遲判定好壞。

### DQN/DDQN 與可維護性

`rl.OffloadingEnv` 使用同一 Simulator、DecisionTask、SystemState，提供 reset、離散 action 0/1/2、step -> next observation/reward/done/info。以 SimPy Event 暫停在決策邊界，沒有 busy wait，也不讓外部訓練思考時間誤算為系統決策成本。reward = -實際終止延遲秒數 - Deadline 未達罰則 1；任務未完成時回饋延後，info.terminal_rewards 用 task_id 歸屬。最後一次 action 後排空事件，done=True。這是半馬可夫、延遲回饋介面；尚無 Gym 套件依賴、訓練器或有效權重。訓練/測試資料須使用同一身份隔離規則；實驗 API 仍拒絕 dqn/ddqn。正式評估訓練完成的策略時應實作 select_node，重新統一計入決策成本。

### 仍影響研究結論的限制

1. 只量到本機 InsightFace CPU 的 detection+recognition 中位數；Edge/Cloud 的線性加速、固定 RTT/頻寬及 16 KB 回傳皆是假設，並非遠端跑分。沒有建模讀取、解碼、能耗、失敗重試或可變頻寬。
2. 假設所有節點狀態即時、免費且可靠可觀測；真實分散式監測延遲未模擬。
3. 估計器僅歷史中位數；沒有準確度保證，沒有利用人物數標籤。校準主機負載可能造成分布差異。
4. 序列決策器、非搶先 CPU、串列鏈路與共用出口近似都會影響排名。共享模式不是舊獨立模式結果的重新命名。
5. 真實 Laya 模型保留原提示與 checkpoint；本次未訓練、未調優或改用固定規則。輸入序列長度、截斷與原始選擇將由 audit_id 稽核。
6. 相同 seed 重現工作負載與離散事件邏輯；端到端 wall-clock 決策耗時受主機負載影響，不能保證逐位重現。單次九格不是統計顯著性證明。
7. Oracle 僅供資訊理想化診斷。RL 介面驗證不代表已完成 DQN/DDQN 訓練。


## 最終結果與分級處理狀態

- P0：真值/人臉數洩漏、上傳中承諾需求不可見、決策消融時間不守恆均已重現並修正。原始重現數據：731 ms/9人臉直接可見、上傳中Edge work=0、消融total=50/components=150。
- P1：可觀測剩餘工作估計、時間加權佇列、獨立/共用網路、兩種期限政策與完成率分離、RL事件介面均已實作及測試。`rl.EpisodeSplit`額外提供訓練/測試來源零重疊檢查與獨立環境工廠。
- P2：保留完整浮點結果、可稽核事件軌跡/決策輸入、API與UI參數、Laya健康檢查、版本化前端腳本、可重現報表腳本已完成。
- 52項單元/事件測試、78項API整合、99項九格情境稽核通過。1620筆時間守恆最大誤差7.276e-12 ms；270次正式Laya原始輸出一致、零fallback、零截斷。
- 原九格與新九格共54列比較保存在before-after-full.csv。九格平均Latency-aware由156.961到158.846 ms；Laya由7812.957到17055.819 ms，Deadline平均由16.67%到1.48%。這些是資訊權限/模型狀態/實測wall成本改變後的結果，不能當成同條件演算法優劣改善。
- 正式實驗後僅補充RL隔離介面、測試與前端快取版本；未變更九格的模擬器、策略、工作負載真值或Laya模型/提示。
