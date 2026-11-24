# RNG 隔離驗收

原始 `DQN.act(epsilon=0)` 會呼叫 `rng.random()`；`rl_method_study.evaluate()` 使用訓練中的同一 Agent，驗證次數因此改變後續探索與 replay 抽樣。舊ZIP仍保留原始程式與結果，舊模型比較受此混雜影響。

修正 `agents49/dqn.py`，只在 epsilon>0 才抽探索亂數。新增 `evaluation.evaluation_snapshot()`，深複製模型並建立獨立的評估 RNG。修正舊 runner 的評估入口，使用該快照；新 runner 也使用快照。驗證時不呼叫 remember/train_step，且檢查訓練 RNG state 不變。探索與 replay 仍共用 Agent 原本的訓練 RNG，該選擇不影響驗證隔離。

`test_integral_rl.py` 對 DQN、DDQN 各執行相同 seed73、90任務、相同27次更新的兩條訓練。另一條在每個決策後插入獨立驗證，甚至讓評估策略以epsilon=.1消耗自己的亂數。兩條的 online、target 權重每個元素、更新數及 RNG state 完全相同。另一測試確認修正版純greedy呼叫不消耗RNG。

原ZIP內DQN的最小反例則在訓練中插入7次greedy呼叫，兩條訓練權重的SHA不同，確認可重現原污染。新版本同條件隔離後SHA相同。數值與雜湊保存 `evidence/rng-isolation.json`；原始測試日誌在 `logs/tests.log`。完整後端99項測試通過。

此修復會改變日後訓練的亂數序列，因此不能預期重現受污染舊訓練的權重。舊結果保留歷史用途；新比較全部使用相同修正版與固定評估時點。

