# DQN／DDQN：正式 SimPy 推論整合

`backend/app/offloading/agents49/` 是獨立模組，避免原 ZIP 的 `app.offloading.rl` 套件和正式 `rl.py` 衝突。組員的 `dqn.py`、`ddqn.py`、`normalizer.py` 原樣複製；正式 `rl.py`、`OffloadingEnv`、`EpisodeSplit`、`Simulator`、`IndexPolicy` 與既有策略無修改。原 ZIP 的 `SystemState.feature_vector()` 示例不適用；`agents49.adapter.Agent49Policy` 使用既有 `IndexPolicy` → `integration_contract.feature_vector(task, state)`，搭配 `run_policy()`。這次以離線實驗程式提供整合，現有 API 和前端的策略列表維持原樣。

`load_agent()` 先驗證 SHA-256、NPZ 欄位、形狀、有限性，再以原模型 `load()` 載入並檢查正規化版本。不合法的模型或 Q 值會報錯；沒有 fallback。推論採 epsilon=0，先做可用節點遮罩，再取最大 Q，按 Local、Edge、Cloud 固定順序處理同分。Adapter 的一次 forward 與組員 `act(epsilon=0)` 數值結果用 Golden fixtures 交叉比對。每次決策保存 49 個原始值、正規化值、三個 Q、action、節點及 task_id；逐任務核對實際派送。

`Simulator._process()` 先取得單一決策資源，才擷取正式 `DecisionTask`、`SystemState`。每次策略 wall-time 計入估計器、向量建構、正規化、forward、argmax 與記憶體稽核資料的成本；JSON 寫入在模擬後。決策等待另列，決策 wall-time 不算 CPU 運算。實驗可讀取 `result.tasks[].decision_wall_ms`、`decision_queue_ms` 與 `agent_decisions[]`。Native 訓練省略 wall-time，以免訓練更新耗時污染虛擬排程；正式評估兩者皆計入。

|證據|實際驗證|
|---|---|
|`DQN_DDQN_GOLDEN_FIXTURES.json`|49 欄逐一對齊；獨立 `math.log1p`、`math.fsum` 及 ReLU 核對原型與正式權重的 Q、action 與遮罩|
|`backend/tests/test_agents49.py`|觀測不受未完成真值影響；正常、亂序與 drain 的 reward 時點和 next_state|
|`profiles/agents49/evidence/prototype-simpy-smoke.json`|原權重各 3 筆合成任務走正式 SimPy，記錄實際決策成本與 Q／action；此 smoke 不驗收原型的訓練品質|
|`profiles/agents49/pilot/raw/`|兩個新正式模型各 24×10 筆完整 Q/action，與實際 SimPy 派送一致|
|`profiles/agents49/study.json`|核心及執行版本 SHA-256、分割、設定與模型契約|

純觀測只能降低洩漏風險，無法證明 49 維是完整 Markov state。不同節點實際算力、影像模型與網路行為仍是既有 SimPy 假設；估計工作量相同的影像可有不同實際負載。圖集結果不代表真實三節點部署。

