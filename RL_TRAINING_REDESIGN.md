# 訓練方法修正版與驗證

新方法名稱為 `method-task-terminal-v1`。使用原 SimPy 與 `OffloadingEnv` 的觀測、事件及完成訊息，增添 `agents49/task_credit.py`，以原任務 state/action 存非同步終止回饋。原四個核心檔、原 DQN/DDQN 演算法、歷史權重及正式 Test 結果保留。這是任務成本方法原型，長期 DQN/DDQN 方法尚待另一個明確的全域目標設計。

|對照|回合長度|Reward／折扣|State|
|---|---:|---|---|
|global20|20|舊區間全域總成本，gamma .99|49欄|
|global100|100|舊區間全域總成本，gamma .99|49欄|
|task100|100|完成成本配回原任務，gamma0、task-terminal|49欄|
|task100_pruned|100|同 task100|訓練觀測決定19欄遮罩，保留30欄|

各對照均訓練 seed42／43／44、2,400 dispatch，合計12個模型、28,800 dispatch。global20 為120回合，其餘24回合，每個100任務對照涵蓋24資料集／負載／網路組合各一次。工作負載只從每資料集40張訓練圖片有放回取樣，較長的回合代表重複圖像形成的流量，不是100張獨立訓練圖片。負載間隔由訓練均值和rho .3/.9/1.5固定；一半回合用固定平均速率，另一半在每20任務週期以 .15倍／1.85倍間隔模擬突發。網路與算力沿用四種既有環境，回合內固定。對照保持原baseline與模擬器定義。

驗證使用各20張validation圖片、seed701、有放回生成20及100任務序列，涵蓋24情境與穩定／突發流量。於0/800/1600/2400 dispatch固定檢查，共4,608次診斷執行。評估不計虛擬決策成本，只比較選擇品質。原Test的profile未載入，也未重跑正式Test。所有loss/reward、來源、場景、取樣seed、SHA、transform及曲線存在 `profiles/rl-method-v1`，以 `episodes.jsonl`、`checkpoint.json` 及 `method-checkpoint.npz` 對應。此輪未按validation選擇最佳checkpoint，固定保存2,400步版本。推論時必須載入同目錄checkpoint.json的mode／transform，以rl_method_study.Agent與Policy還原，再load權重；NPZ內的log1p標籤只描述數值正規化，不能代替此處的Reward／遮罩契約。

100任務穩定流的三seed／24情境平均診斷Reward在2,400步分別為 -5.729、-5.138、-2.723、-3.950。這是學習曲線摘要，不能替代分層比較。任務回饋較舊全域目標改善，但仍落後同組 Latency-aware V1/V2 的 -0.980／-0.971。Loss 與 validation 在部分對照持續震盪，尚無收斂證據。更改Reward和gamma的合併介入，無法將差異全部歸因於 task_id credit 修正。

|100任務、穩定validation，3seed均值|global20|global100|task100|pruned|
|---|---:|---:|---:|---:|
|LFW High Cloud 優勢，平均ms|976.4|8,392.2|23.4|23.4|
|WIDER High Reference，平均ms|1,109.9|12,158.1|2,311.8|1,736.1|
|LFW Medium Local 優勢，平均ms|6,596.5|1,589.8|2,426.6|3,183.6|

單純拉長回合沒有一致改善。長回合也包含較晚的絕對時鐘、較深佇列與不同的最後排空占比。原20任務訓練對100任務評估有支持範圍錯配，已證實；其為正式錯誤主因的比例仍未確立。任務成本回歸在Cloud優勢有效、在Reference與Local優勢仍有限，尤其無法計入當前決策對後續任務的外部成本。gamma0也使DDQN與DQN更新等價，故沒有重訓冗餘的同等DDQN組，兩者等價性另有精確梯度測試。

若研究目標必須是整體長期成本，需另定B版本，例如以時間積分的未完成任務數／期限逾期成本作全域增量成本，明確處理 drain、折扣時間單位、回合長度及剩餘任務資訊。必須先證明所選累積成本等於宣告目標，再與A做新控制比較。此候選不在本輪加入，以免改動已驗收核心。現有B版本僅作保留的診斷對照。

新的正式測試集合應從未用於歷次正式結果的 LFW identity／WIDER event groups 選圖，以來源路徑、group和影像SHA隔離所有已曝光資料。先固定圖集、100任務以上的流量、network/compute範圍、Deadline、突發模型、種子、指標及統計方法，再量測並封存。模型、特徵遮罩及超參數只用training/validation凍結；學習曲線尚未穩定時不能先開新Test。100任務長度可以使用流量重複，但獨立影像數和重複次數必須各自報告。

重現命令先將新增模組、測試、`agents49_experiment.py` 與 `rl_method_*.py` 複製進現有Compose backend的對應位置，使用新的輸出路徑，資料沿用既有training/validation profiles：

```powershell
docker compose exec -T backend python -m unittest discover -s tests -v
docker compose exec -T -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=1 backend python /app/scripts/rl_method_study.py /profiles/rl-method-new
docker compose exec -T -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=1 backend python /app/scripts/rl_method_report.py /profiles/rl-method-new
```

第一次容器啟動時Docker daemon未運作；啟動Docker後重建的backend缺少先前只複製在容器內的agents49，完整複製模組後91項測試通過。日誌保留於 `work/rl-method`。本次沒有產生正式Test成績，也沒有認證新模型收斂或優於啟發式策略。

