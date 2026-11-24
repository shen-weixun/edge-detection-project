# 實測工作負載與 Local–Edge–Cloud 卸載比較

## 啟動與操作

正常啟動：`docker compose up -d --build`。
啟用 Laya：`docker compose -f compose.yaml -f compose.ai.yaml up -d --build`。
資料庫、InsightFace 與 Laya 模型 Volume 保留；不得使用 `down -v`。

1. 首頁資料集管理選擇 LFW／WIDER FACE，點「以此資料集量測工作負載」，或直接開啟 `/simulator.html`。
2. 在量測區選資料集、張數（1–500）、種子與重複次數（3–20），按量測。
3. 網頁每兩秒查詢進度，顯示成功／失敗數及平均、中位推論耗時。完成後自動保存並選取 Profile。可下載包含失敗原因的 CSV。
4. 選 Measured Workload 與已完成 Profile，設定任務數（不超過成功圖片數）、到達間隔、Deadline、種子和節點參數。
5. 選策略，保留「計入決策耗時」進行正式比較，按「開始比較實驗」。Laya 每次最多 50 筆。
6. 查看摘要、延遲組成、節點負載、每筆來源及任務明細。匯出 CSV 與完整 JSON，保存共同工作負載雜湊及 CSV 雜湊。

## 資料來源與量測範圍

Profiler 從 PostgreSQL 已匯入的 samples 隨機抽樣，使用首頁相同 InsightFace buffalo_l、CPUExecutionProvider、640×640 偵測尺寸、0.5 門檻，執行 detection + recognition。
模型初始化（冷／熱狀態與耗時）、圖片讀取、解碼、每張預熱分開記錄。正式推論至少三次取中位數；在模型鎖內計時，因此不含模型鎖等待。CSV 同時保存原始重複耗時、圖片相對路徑、ID、資料集、MB、解析度、偵測人臉數、設備與模型資訊、成功狀態和錯誤原因。

Profile CSV 與 JSON 自動保存至主機 `profiles/`（容器 `/profiles` 可寫掛載），資料集仍唯讀。容器重啟後完成的 Profile 仍可使用；未完成工作顯示 interrupted 並保留部分紀錄，需重新量測。程式一次只允許一個量測工作。主機 CPU 負載會影響實測，量測期間避免其他推論作業。

Measured 模式只接受伺服器完成並核對 SHA-256 的 CSV，排除失敗圖片，抽樣不重複，不足時報錯。沒有 Profile、損毀檔、無成功圖片時明確拒絕，不切換為 Synthetic。合成模式永遠標示 `synthetic_demo_NOT_measured`。

## 模擬與公平性

工作負載在策略迴圈外生成一次，保留每張圖片與 CSV 推論時間、到達時間及 Deadline；所有策略共用完全相同任務，回傳 `workload_sha256`。每個策略建立新的 SimPy 環境、CPU、傳輸通道及決策資源。策略只接收當下節點狀態與當前任務，無未來完成資訊。

Local 的 speed 固定 1，服務時間為實測中位推論時間；Edge／Cloud 計算時間是此時間除以設定的相對算力。RTT、頻寬、相對算力、單核心 FCFS 排隊、結果大小 16 KB 都是模擬假設。圖片讀取、解碼不加入服務時間。這不是遠端實體設備跑分，也不是辨識準確率測試。

Local-only／Edge-only／Cloud-only 固定節點；Load-threshold 在 Edge CPU 等待佇列小於 2 時選 Edge，否則 Cloud；Latency-aware 依當前 CPU 工作量、上下行積壓、RTT、圖片傳輸量與算力估算完成延遲。Laya 呼叫獨立服務的真實 Router 模型，無規則或隨機備援，失敗回 503。DQN／DDQN 僅保留 select_node 整合介面，尚未實作。

決策耗時在執行主機量測，包含 Laya HTTP 呼叫與首次模型載入。計入模式下共用單一序列決策資源，端到端延遲＝決策等待＋決策執行＋網路（含通道等待）＋CPU 排隊＋運算。未勾選時仍顯示實際決策耗時，但不把它推進模擬時間。正式比較須對所有策略使用相同模式。Deadline 相對任務到達時刻判斷，超時仍完成；目前無丟棄政策，因此完成率 100%、丟棄率 0% 是模型設計，不是策略優勢。

節點 CPU 使用率＝總服務時間／該策略模擬結束時刻；平均／最大佇列和剩餘工作量為決策時點取樣統計，完整 `queue_samples` 包含在 JSON。

## API 與測試

- POST `/api/offloading/profiles`：dataset、count、seed、repeats；202 回傳工作 ID。
- GET `/api/offloading/profiles`、`/profiles/{id}`、`/profiles/{id}/csv`：清單、進度、CSV。
- POST `/api/offloading/experiments`：`workload_mode: measured|synthetic`、`profile_id`、strategies、count、seed、interval_ms、deadline_ms、include_decision_overhead、nodes。

單元測試：`docker compose exec -T backend python -m unittest discover -s tests -v`。
基本 HTTP／策略測試：`verify.cmd`。真實 Laya：`verify-ai.cmd`。
完整真實整合測試（需 Python requests、已匯入資料、Laya 服務）：`python scripts/verify_integration.py`。
整合測試透過實際 FastAPI／PostgreSQL／InsightFace 量測 LFW 30 張及 WIDER val 3 張，讀寫實際 CSV、核對 SimPy 來源與策略公平性，並執行原首頁偵測、驗證及 Laya 真實推論。證據寫入 `work/verification/`。單元測試中的替身只驗證錯誤與時間邊界，不取代這套實際整合。
