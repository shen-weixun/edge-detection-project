# Reward 與非同步信用分配審查

原實作是 **B，全域系統事件 Reward**。來源為 `OffloadingEnv.step()` 的區間完成成本總和，以及 `agents49.training.train_episode()` 用目前決策的 state/action 和下一次決策的 state 儲存轉移。每個完成事件的 task_id 對帳正確，但沒有將個別任務 Reward 配回原派送 Action。先前「task_id 完成對帳通過」驗收只證明沒有遺失或重複完成，不能證明 task-level credit assignment。

|seed 42 舊紀錄|完成 Reward|與當前決策同 task_id|最後一步承擔的負成本|
|---|---:|---:|---:|
|DQN|3,840|41.4583%|55.8376%|
|DDQN|3,840|42.3958%|56.5111%|

實際由原 `transitions.jsonl` 重新計算，輸出 `historical-reward.json` 並保存原檔 SHA。這兩個百分比是診斷指標，不能單獨證明全域 MDP 的數學定義錯誤。

最小 SimPy 範例使用 A 在 t=0 派 Local、實際計算 300 ms，B 在 t=1 派 Edge、實際工作 1 ms，C 在 t=50 派 Cloud。B 先完成，A 最後完成。到 C 決策前收 B 的 -0.0214667；最後一次 step 收 C 的 -0.1025977 與 A 的 -0.3，於 C action 的轉移儲存 -0.4025977。A 的初始轉移是 0。修正版在完成訊息送達時，各建立 B→Edge、C→Cloud、A→Local 的一筆終止回饋，A 保留原 dispatch_index=0。各階段與時間見 `minimal-counterexample.json`。

`test_task_credit.py` 覆蓋亂序完成、最後排空、三節點同時完成，以及 gamma=0 下 DQN/DDQN 更新完全相同。全部後端測試 91/91 通過。複合完成批次逐筆處理，不把三筆 reward 加在最後 action。完成通知到達 learner 的時間可以晚於實際完成時間，只有當該次 `step` 回傳 info 才進入 replay，沒有提前取得真值。

B 的精確目標為每次決策 k 到下一次決策間的終止成本總和 r_k，最大化 E[sum gamma^k r_k]；最後決策後排空視為該步的一部分。gamma=.99 按「決策次數」折扣，並非物理時間折扣。從初始狀態看，第20步與第100步的相同成本權重約 .826 與 .370。與未折扣全體任務成本的目標不同，Episode 長度也影響折扣與末端負擔。49 維沒有剩餘任務數或完整在途工作紀錄，因此完整 Markov 性未證明，較合理的描述為部分可觀測決策過程。

新版本採 **A，task-terminal delayed feedback**，目標是條件於派送時觀測及 action 的該任務成本期望。 `task_credit.train_task_episode()` 用 task_id 保存原 state/action，只在完成 info 到達後進 replay。task_done=True、gamma=0；同一筆原向量只作既有 API 所需的有限值佔位，bootstrap 永遠遮罩，不宣稱它是完成時 next_state。Episode_done 另記錄，仍在所有任務完成後結束。Reward 的時點與所屬任務已修正。

這個版本是有延遲標籤與 replay 的 contextual bandit／任務成本回歸。它不學習派送對其他任務的長期外部成本；此限制必須伴隨模型名稱與結果。DQN 與 DDQN 的 target 選擇差異在 gamma=0 下消失，兩者同 seed 的梯度等同。此輪以一份同等更新實作跑任務成本實驗，沒有將它們標成兩個獨立的長期 RL 改善。

已證實原流程與 task-level 宣稱不一致、最後負成本集中、時間特徵敏感及回合長度分布差異。尚未證實這些各自造成舊正式 Test 退步的比例。修正不能以後來的驗證分數反推單一因果，因為 A/B 同時改變目標與折扣。

