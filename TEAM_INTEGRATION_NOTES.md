# 團隊整合說明

本輪沒有修改、實作或訓練DQN/DDQN。沒有改Task/DecisionTask/NodeState/SystemState欄位、RL State/Action/Reward、EpisodeSplit、OffloadingEnv或已驗收的SimPy事件引擎。

## 受保護檔案逐位元組核對

|檔案|起點9739b39→目前|
|---|---|
|backend/app/offloading/rl.py|SHA256完全相同|
|backend/app/offloading/models.py|SHA256完全相同|
|backend/app/offloading/simulator.py|SHA256完全相同|
|backend/tests/test_rl.py|SHA256完全相同|

原三個test_rl案例隨全部77項後端測試重跑；原Baseline預設仍只有五策略。舊calibration_profile_id請求與原laya預設保留，新增功能全部可明確選擇。

## 新增入口與向後相容

- 新策略key：latency_aware_v2、laya_v2；原key與實作保留。STRATEGY_FACTORIES新增key，呼叫端若想嚴格維持舊五策略請使用固定清單，不要假設字典永遠只有五項。
- experiment只在末端新增estimator_model=None；舊參數順序/預設不變。Saved模型只允許realistic measured mode，會拒絕training/validation重疊。
- POST /api/offloading/experiments新增可選estimator_id；它與calibration_profile_id二擇一。舊請求不需更動。GET /api/offloading/estimators列可用模型ID/種類/訓練與驗證數。最多8策略，AI每種最多50任務的限制同樣套用laya_v2。
- EstimatedPolicy只包experiment所建策略，於既有select_node計時內預測，再交給原policy；不改RL互動環境或request_action。模型只讀size/width/height，不讀Task.workload_ms或face_count。
- 節點監測的估計commit ledger預先填入同一模型預估值；實際compute仍只用原Task.workload_ms/speed。DQN同事可繼續接原DecisionTask，若要比較同一模型需使用相同固定split/估計器ID，不能重新接真實工作量。
- Laya服務POST /decide新增variant=legacy|v2，省略就是原版。V2候選輸入與options保留原順序；回傳是真實模型choice，無規則/Oracle fallback。V2單thread只在共享lock內臨時設定、finally還原。
- 新模型JSON schema workload-estimator-v1；校驗ID以SHA256內容定址，無pickle。訓練用的numpy已在原requirements，未新增依賴或修改DQN權重。

## 執行與重現

```powershell
docker compose -f compose.yaml -f compose.ai.yaml up -d --build
docker compose exec -T backend python -m unittest discover -s tests -v
docker compose -f compose.yaml -f compose.ai.yaml exec -T laya python -m unittest test_server -v
docker compose exec -T backend mkdir -p /app/scripts
docker compose cp scripts/train_workload_estimators.py backend:/app/scripts/train_workload_estimators.py
docker compose cp scripts/run_latency_v2_cases.py backend:/app/scripts/run_latency_v2_cases.py
docker compose cp scripts/run_laya_paper_diagnostics.py backend:/app/scripts/run_laya_paper_diagnostics.py
docker compose exec -T backend python /app/scripts/train_workload_estimators.py --lfw 44156f8feb7a49269ec3bc6424b5e176 --wider faef67cd539d44f8b3caea7f58307db8
docker compose exec -T backend python /app/scripts/run_latency_v2_cases.py
docker compose exec -T backend python /app/scripts/run_laya_paper_diagnostics.py
docker compose cp backend:/tmp/paper-improvements/. work/paper-improvements/results/
python scripts/run_paper_comparison.py
python scripts/verify_integration.py --reuse-profiles  # 須設WORKLOAD_PROFILE_ID/CALIBRATION_PROFILE_ID/INTEGRATION_OUTPUT，見CODEX_PROGRESS
python scripts/verify_paper_api.py
python scripts/build_paper_reports.py
```

矩陣腳本保留已完成JSON，重新啟動會驗證同一設定並接續；若要新一輪請使用新輸出目錄/另存舊矩陣，不混入不同實作。重建容器前先cp /tmp結果，模型registry與Profile在既有持久profiles目錄。

## 測試與未通過項目

實際結果：77/77後端（原64+新增13）、2/2 Laya服務測試、78/78原HTTP整合、17/17新增API檢查全部通過。Docker backend/db/laya健康、frontend運作，node --check simulator.js通過。瀏覽器控制介面回報不可用，因此未完成視覺/點擊驗收；HTTP頁面、真實辨識與API流程已驗證。未通過的是Laya數值可靠性與全面預估器改善主張，不是被掩蓋的程式測試失敗。
對DQN後續工作：保持來源內容去重及獨立train/validation/test；固定特徵/動作順序、SMDP延遲reward歸屬與實際決策成本規則。不要把Oracle或Laya錯誤選擇當最佳標籤，也不要把不同負載結果混成一個宣稱優勢的均值。
