# State 與正規化診斷

分析只讀 training／validation profiles。49 維共同介面與 `simpy49-log1p-v1` 保留；消融版仍用49欄輸入張量，將訓練樣本選定的19欄遮為0，30欄保留。這是有效特徵消融，尚未另訓練30輸入神經網路。遮罩與 checkpoint 必須一起使用。

在24情境、每情境40個訓練決策、隨機派送的960筆觀測中，16欄為常數。包含 deadline、estimated workload、result size、三個 available，以及固定 Local 設定和 Local 網路欄位；此樣本的 cloud.queue_length 也為0。常數只代表這次資料支持範圍，並非所有環境都無用。特別是 Deadline 或預估工作量若未來變動，丟棄後不能處理該變化。

訓練模式不計決策成本，arrival_ms 與三個 observed_at_ms 完全相同；這種重複不必然適用計入決策成本的正式環境。edge／cloud transmitting_count 和 committed_count 在樣本中也重複。索引、逐欄名稱及所有相等欄對記於 `feature-design.json`，原始與正規化矩陣在 `training-observations.npz`。保留 available 三欄供合法動作遮罩，其餘刪除常數、重複與絕對時鐘，共19欄。

具備變化的工作量線索包括 image_size_mb、width、height；資源線索包括 Edge／Cloud speed、RTT、bandwidth；壅塞線索包括 queue_work、queue_length、committed_work/count、鏈路 backlog、cpu_running。這些特徵的物理意義清楚，但單靠變異與 Q 敏感度不能認定具有可靠的預測能力。

固定 log1p 沒有用資料 fit，正規化允許超過1，沒有截斷；所有樣本非負且有限、available 為0/1。尺度與逐欄原始／轉換後 min/max 及驗證範圍保存於 `feature-analysis.csv/json`。在分布之外仍需重新驗證，不能因沒有縮放 fit 就推定泛化無誤。

舊 DQN、DDQN seed42 權重的驗證觀測各2,400筆，逐欄 permutation 結果見 `q-sensitivity-both.csv`。Cloud bandwidth 置換造成 action 改變27.29%／31.00%；Edge bandwidth 為9.08%／16.96%。聯合將 arrival 與三個 observed_at 同加100,000 ms，action 改變23.13%／28.21%。這證明舊模型依賴絕對時鐘。單欄 permutation 可能破壞欄位間約束，不能作為某特徵的真實因果效用。時間平移保持四個時鐘一致，仍只測模型敏感度。

實際重訓消融採3個seed、相同100任務工作負載與2,400 dispatch預算。100任務穩定流 validation 的三seed／24情境平均 Reward 在1,600步時 full=-2.820、pruned=-2.720，到2,400步 full=-2.723、pruned=-3.950。剪除特徵沒有穩定優勢；不據此刪除正式介面或挑選新正式模型。逐步結果及各seed表見 `validation-curves.csv`，此聚合只作學習診斷。

Cloud Advantage 選錯可能與目標錯配、時鐘依賴、訓練回合太短及學習不足共同有關。已證實的觀測依賴與消融退步不支持「去掉常數欄就能解決」的結論。

