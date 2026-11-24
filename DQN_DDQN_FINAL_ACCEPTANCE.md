# 新 49 維 DQN／DDQN 最終驗收

新版模型已完成正式 SimPy Adapter、訓練、選模及獨立測試。正式評估入口為 `IndexPolicy`／`run_policy()`。沿用既有模擬器及對照策略。

|驗收項目|結果|證據|
|---|---|---|
|特徵名稱、順序與尺度|PASS。49 欄及可用動作遮罩符合 `simpy49-log1p-v1`|重跑 Golden fixtures，`reproduction/DQN_DDQN_GOLDEN_FIXTURES.json`|
|Q、Action 與模型 SHA|PASS。獨立重算 dense layers、遮罩及 argmax，0/1/2 對應 Local/Edge/Cloud；核對 14,880 筆新 RL 決策及歷史稽核|兩套 `independent-validation.json`、`study.json`、`selected-checkpoints.json`|
|資料隔離|PASS。每資料集 40 train、20 validation、100 test；按路徑、影像 SHA 及 group 查交集，完整擴充覆蓋凍結測試集合|資料分割計畫與 profile SHA、`design.json`|
|決策成本及資源排程|PASS。實測 wall-time 進入 SimPy，決策排隊另計；獨立 FCFS 驗證 CPU 及網路，最大誤差 5.821e-11 ms（擴充）及 1.819e-12 ms（共同子集）|逐任務 raw JSON、獨立稽核|
|Reward、next_state 與 done|PASS。只有區間內完成事件交付 reward，按 task_id 對帳；next_state 為下一次決策，最後排空後 done|88 項後端測試、6 份 transition logs 與原始 SHA|
|Laya 真實輸出|PASS。沿用 480 個不同的 audit_id，完整歷史結果與原始輸入、選擇及推論時間一致|歷史稽核、共同子集 raw JSON 與 `independent-validation.json`|
|訓練及修正後驗證重現|PASS。6 份權重和 6 份轉移日誌 SHA 相同；288 組 validation 模擬結果相同| `reproduction-check.json`、`logs/reproduction.log`|
|版本與選模|PASS。1,043 份封存項目 SHA 通過，原始執行與修正後選模以不同證據記錄| `study.json`、`selected-checkpoints.json`|

舊 Validation 使用 Pilot 測試子集的聚合工作量設定到達間隔；修正後的 Validation 使用訓練圖集推導的間隔，候選訓練日誌與兩個入選權重 SHA 相同。此次完整測試也以訓練資料固定到達率。共同 Laya 子集沿用原執行時程，該時程曾用固定測試子集的聚合工作量定義 offered load，仍需在引用時揭露。模型選擇與工作量估計沒有使用該子集的真值。針對正式資料與程式檢查，未發現仍影響本輪選模或決策輸入的洩漏或版本不一致。

期末報告可引用 24 個情境的八策略結果、受控共同子集的十策略結果、工作量隔離、獨立事件稽核與訓練重現。100 張圖在三個種子下重複排列，無法視為 300 張獨立影像。Laya 每情境共 10 張且 P95 等於樣本最大值；適合說明此系統設定的成本，無法推論一般化 SLA、模型勝率或統計顯著性。部署結果限於現有測量平台與 SimPy 資源假設。原 API／前端尚未註冊新版策略。

