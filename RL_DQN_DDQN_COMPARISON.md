# DQN／DDQN 長期方法比較

本輪兩者都使用gamma1與真實非終止bootstrap，模型49→64→64→3、固定log1p、batch64、replay50000、learning rate .0003、target每200更新同步。只有下一步估值不同。

```text
DQN:  y = r + (1-done) max_a Q_target(next_observation,a)
DDQN: a* = argmax_a Q_online(next_observation,a)
      y = r + (1-done) Q_target(next_observation,a*)
```

精確測試中online偏好action0而target偏好action1，得到3.8與.8，確認兩種target確實不同。有限episode仍採非零bootstrap；A類gamma0任務成本方法沒有列為DDQN長期能力證據。

48個小型訓練組合涵蓋algorithm×completion/integral reward×20/100回合×full/pruned×seed42/43/44，每個800 dispatch、737更新。驗證種子701／709，所有方法使用相同固定任務、圖集、到達軌跡、網路、Deadline與正規化。20任務回合是同一100任務基礎流切成五段，各自重設episode；段內到達差相同、絕對時鐘改為從零起。這是回合重設因子本身的差異，不能宣稱20與100回合佇列沿用相同。

完整各seed曲線與失敗紀錄見 `PER_SEED.md`、`validation-all-seeds.csv`、`training-all-seeds.csv`，每個驗證JSON含逐任務Q與選點。表中的跨情境平均只作同一固定驗證suite的學習診斷；具體場景結果可按scene、validation_seed、burst、seed篩選。

|方法來源|State／Action／Reward|Transition與訓練|本專題差異|
|---|---|---|---|
|TriSchedRL 2026|資源／queue／鏈路／能量及三項預測，4n+3維；選資源並以guard修正；動態加權SLA、延遲、能量|DQN、replay與target；合成Poisson／突發流量，配對種子對照；參數部分以範圍提供|本輪採實際SimPy決策觀測、三動作、延遲積分加miss；未加入論文的energy、guard或預測器。時間積分reward為本專題設計|
|AICDQN 2026|預測負載、queue、資源、priority與energy；Local／多Edge／Cloud；動態加權多目標|Dueling Double DQN、per-device replay；1000 episodes×100slots，gamma.9，batch16，RMSProp，target每50步|本輪為普通DQN/DDQN、gamma1有限回合，沒有dueling或GRU-LSTM。任務流長度與時槽長度無法等同|
|LEAOT 2026|可解釋節點分數，延遲、queue、energy與deadline；Edge／Cloud選擇|非RL，沒有Replay、Target或學習episode；Poisson合成流量，10次獨立試驗|Latency-aware是本專題對照，不能直接稱LEAOT重現；本輪以配對的相同validation任務比較|

來源為 [TriSchedRL §§3.3–5](https://link.springer.com/article/10.1007/s10791-026-10607-x)、[AICDQN MDP與Tables 2–4](https://pmc.ncbi.nlm.nih.gov/articles/PMC12886797/)、[LEAOT §§III–V](https://thesai.org/Downloads/Volume17No8/Paper_77-LEAOT_Load_Deadline_Latency.pdf)。

上述論文的公開文字不代替本專題的非同步時序驗收。本輪明確測試Reward／Next State／Done／Target，方法比較不以某篇論文的既有性能改善百分比作驗收標準。



本輪固定預算下，DQN和DDQN的24對最終權重均不相同。這證明實際訓練路徑有分歧，但兩者都沒有跨seed穩定改善，不能宣稱DDQN帶來可靠效益。完整因素配對的最終權重差在 empirical-dqn-ddqn-differences.json，改善與退步案例各自保留。
