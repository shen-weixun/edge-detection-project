# DQN／DDQN：正式 SimPy 訓練報告

兩種演算法均已完成正式 `OffloadingEnv` 訓練。訓練以 seed 42／43／44 各跑 192 回合、每回合 20 個決策，共各 3,840 步與 3,777 次更新。模型結構與組員演算法未改；新權重獨立存為 `*_simpy49.npz`。回放批次 64、learning rate 0.0003、gamma 0.99／決策、target 每 200 更新同步；epsilon 線性由 1 降到 0.05。訓練涵蓋 24 種資料集／負載／網路組合，各重複 8 次。訓練區的任務時程依訓練圖集平均工作量、Edge reference speed 3 及 offered rho 0.3／0.9／1.5 設定。

`agents49.training.train_episode()` 在每次 action 後執行 `OffloadingEnv.step()` 至下一次決策或最後 drain。該時間區段內完成的任務才產生 reward，每個完成事件必須有已派送且從未完成過的 task_id。一次 step 可收 0、1 或多個終止 reward，含可能由較早 action 派送的任務。學習轉移用該步總 reward 與真實下一次決策觀測；保留每筆 reward 的 task_id 做對帳，不把未來結果塞回先前的單步。最後 action 後排空並檢查所有任務已終止；沒有 next task，`done=True` 遮罩 bootstrap，僅為原 `remember()` 的形狀檢查傳入最後合法向量。這是整體系統 reward；延遲信用由 TD 傳播，gamma 是每決策折扣而非每毫秒折扣。

獨立性：LFW 與 WIDER FACE 各有 40 訓練／20 驗證／100 凍結測試圖。已交叉檢查正規化路徑、圖檔 SHA-256 及 identity/group 跨 split 無交集，量測 profile 成員符合凍結清單。`wider_train` 是 WIDER FACE 原始資料集合標籤；本專題另做 group/content 隔離的 training、validation、testing。固定 log1p 無 fit；Median 工作量預測器讀既有登錄產物，用 80 張訓練圖校準。正式情境的時程設計可參考 Pilot aggregate，並未供訓練或最終選模使用。

複查時發現初版候選驗證沿用 Pilot 的 aggregate 到達間隔；這可能讓凍結測試子集統計影響候選排序，雖然訓練時程一直由訓練集推導。已以訓練集時程重跑全部候選的 24×2 次驗證，修正預設 runner。下表為修正後的 seed 101／103 驗證每任務平均 Reward（10 任務／次，epsilon=0，不計決策成本）。兩者仍選中相同 seed 42 checkpoint，SHA 完全相同；保留舊記錄，正式選模證據以 `clean-validation/selection.json` 為準。

|模型|訓練 seed|每回合平均訓練 Reward|驗證每任務平均 Reward|選用|
|---|---:|---:|---:|---|
|DQN|42|-37.104705|-1.378032|是|
|DQN|43|-37.999326|-1.472766|否|
|DQN|44|-46.443946|-2.044837|否|
|DDQN|42|-37.107285|-1.287144|是|
|DDQN|43|-37.181577|-1.472766|否|
|DDQN|44|-45.277082|-1.811216|否|

|正式模型|checkpoint SHA-256|
|---|---|
|DQN|`4ca02e6543ac8bdb5dd25e608eda15ddd5a5726e7f3b716051748143dc4f118c`|
|DDQN|`4bc95eeaf87f8278541b99c95846275611473159fc7f746d5ebe49ca7242b91e`|

`training/*/*/transitions.jsonl` 保存逐步 loss、reward、epsilon、task/next_task、虛擬時間、終止 reward、每回合來源與取樣種子。`training/*/*/checkpoint.json` 保存訓練計數及 checkpoint SHA；`clean-validation/*/*/validation.json` 保存修正後逐情境驗證。修正版 runner 另在同一 Docker 環境完整重訓；六個 checkpoint 與六份逐步 transitions 日誌 SHA-256 均完全相同，並重現修正後驗證分數（`evidence/corrected-reproduction.json`）。未聲稱 loss 收斂、任何模型全面勝出，或不同 CPU/NumPy 會產生逐位相同的 checkpoint。此檢查只用實測圖片工作量的 SimPy 模擬，未量測實際邊緣或雲端主機吞吐。

