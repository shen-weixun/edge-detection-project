# 組員DQN／DDQN模型驗證

**DQN/DDQN FORMAL INTEGRATION: BLOCKED**

RAR只解到獨立work/ai-comparison/incoming，未覆蓋原backend。只審查並載入隔離副本；加在execution.txt作為待驗證片段，未複製為production指令。來源/權重原始SHA與執行後逐位元組一致。

|模型|架構|finite|數值probe|合法Action|load() ms|平均act ms|P95act ms|
|---|---|---|---|---|---|---|---|
|dqn|7-32-ReLU-3|True|30|[0, 1, 2]|0.367|0.005|0.009|
|ddqn|7-32-ReLU-3|True|30|[0, 1, 2]|0.270|0.004|0.005|

每個probe重複20次epsilon=0，action與argmax(Q)一致；Q隨不同數值state變化，49維直接輸入會ValueError。這些是人工數值探針，不是合法SimPy狀態或模型選擇品質測試。load時間只含load()，act只含該函式；不能拿它與Laya完整HTTP pipeline作正式速度排名。

權重與seed42初始值不同，不能因此證明使用了正確資料訓練；可能是其他seed或其他來源。NPZ只有arr0..3，沒有訓練資料、reward、特徵/scaler或checkpoint紀錄，訓練有效性NOT VERIFIED。

snippet實際錯誤：DQN/DDQN呼叫不存在的decide，得到AttributeError；threshold_decide(state)缺edge_cpu得到TypeError。正確推論方法是act(state,epsilon=0)，但改方法名不能補齊七維契約。CPU百分比門檻與CPU queue/瞬時busy不同，因此未替換原Load-threshold，也沒有猜cpu_threshold觀測。

CLI只顯示0=local/1=edge/2=cloud；訓練action label是否一致仍未確認。七維名稱、順序、單位、正規化、訓練資料、Reward、環境皆未確認，沒有建立49→7映射、正式Adapter、訓練或改權重。

證據：model-validation/model_validation.json、member_inference_traces.json、feature_contract_check.json、member-original/六檔SHA；程式scripts/validate_member_models.py。
