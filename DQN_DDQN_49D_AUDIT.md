# DQN／DDQN：組員 49 維原型驗收

本輪驗收的是 `DQN_DDQN.zip` 的 49→64→64→3 架構。上一輪七維模型維持 BLOCKED，未轉接、補零或拿 49 維向量截取。組員 ZIP 獨立解至 `work/agents49/incoming/SimPy49_DQN_DDQN_New`，沒有覆蓋 `backend`。ZIP SHA-256 為 `829baf26364b317ed382ab75190a637392568a347080904c6d75025234ae88a0`；成員逐檔 SHA 在 `profiles/agents49/prototype-audit.json`。

|驗收項目|實際結果|判定|
|---|---|---|
|原始單元測試與推論|5/5；兩個 `infer.py` CLI 各載入原權重成功|PASS|
|模型及正規化|6 組 float tensors 皆有限，結構 49→64→64→3；7 個 Task 欄位加每節點 14 欄，順序逐欄符合正式 `FEATURE_NAMES`。尺度逐欄核對；非負數值 `log1p(x/scale)`，三個 available 維度 0/1 原樣保留。|PASS|
|Action/Q 數值|0/1/2=Local/Edge/Cloud；獨立 scalar oracle 核對 Q、有限值、argmax 與遮罩（僅 Edge 可用）。原型及正式兩版本各兩個 fixture 的 Q 隨觀測變化。|PASS|
|原訓練重現|seed 42、4,000 步，兩個完成 CSV 逐列相同，摘要數值相同；權重不位元等同，最大元素差分別 8.882e-16／9.992e-16。|PASS（數值）|
|原訓練觀測無洩漏|隱藏真值 100 或 300 ms；t=10 兩者均無完成事件，原型卻回傳 Local 佇列工作量 90 或 290 ms；下行 backlog 同樣變動。|FAIL（原型）|
|原權重有正式 SimPy 訓練與凍結圖集證據|原紀錄明寫使用合成資料及 heapq；無正式圖集分割或對應 SimPy 事件。新訓練另行驗收。|未驗收（原型）|

|模型|原型完成|更新|平均 Reward|平均延遲 ms|Deadline 達成|
|---|---:|---:|---:|---:|---:|
|DQN|4,000|3,937|-5.582641|5,006.641|42.4%|
|DDQN|4,000|3,937|-5.469519|4,910.519|44.1%|

`event_environment.EventEnvironment.dispatch` 先以 `actual_ms` 求 CPU 結束與回傳結束；`observation` 使用這些時點估算 `queue_work_ms` 與 backlog，讓未完成的工作影響先驗觀測。原 `AsyncRewardBridge` 以後續決策的 state 配對 action，但把該任務較晚才收到的完成 reward 填回較早的單步轉移；這不是正式環境一次 `step` 的觀測／獎勵定義。原 `train.py` 排空後另取合成 task 作末端觀測。Reward 公式本身相符（`-latency_ms/1000 - 1[miss]`），轉移時點不同。原件完整保留；正式訓練不呼叫原 `bridge.py` 或 heapq。

驗證指令，在隔離解壓目錄：
```powershell
python -m unittest discover -s tests -v
python train.py --algorithm both --steps 4000 --seed 42 --output ../../prototype-reproduction
```
Windows 執行原測試時，首次因 sandbox 無法存取系統暫存檔失敗；將 TEMP/TMP/TMPDIR 設到 workspace 下重新執行，五項全部通過。重現摘要、原測試／推論 log、原件校驗及洩漏重現見 `profiles/agents49/evidence/`、`prototype-audit.json` 與 `scripts/agents49_prototype_audit.py`。

