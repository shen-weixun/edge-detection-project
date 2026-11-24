# AI 策略分層比較

[100 圖八策略表與圖](expanded/STRATIFIED.md)涵蓋 LFW、WIDER FACE，各依 Low／Medium／High 和 Local／Edge／Cloud 優勢及 Reference 排列。每格使用 100 張凍結測試圖、三種順序，576 策略執行、57,600 任務。[Laya 共同子集十策略表與圖](laya-subset/STRATIFIED.md)保持相同分層順序，每格 5 張 × 2 個歷史固定種子，480 策略執行、2,400 任務。兩套結果各有逐 seed `comparison.csv/json`、同情境 `stratified.csv/json`、`paired-seed-deltas.csv`、24 張圖及 raw JSON。網路時間包含傳輸排隊及 RTT；決策時間計入工作量估計、特徵、正規化及模型運算，Laya wall-time 另含服務呼叫。所有任務最後都完成，Deadline 達成率另算。

八策略擴充的到達間隔由訓練圖集固定，實際 offered load 用凍結測試的實測均值事後計算。表為基準 Edge（速度 3、單 CPU）的 rho。每子集在各節點假設單點全收的 rho 已存於 `design.json`。

|資料集|Low 間隔 ms／rho|Medium 間隔 ms／rho|High 間隔 ms／rho|
|---|---|---|---|
|LFW|541.42／0.300|180.47／0.901|108.28／1.502|
|WIDER|1,244.18／0.284|414.73／0.851|248.84／1.418|

|情境與指標|Latency-aware V1|Latency-aware V2|DQN|DDQN|
|---|---:|---:|---:|---:|
|LFW Medium Local 優勢 平均 ms|1,531.0|1,396.7|1,446.0|1,950.2|
|LFW Medium Local 優勢 P95 ms|2,029.4|1,690.1|1,593.0|2,667.2|
|LFW Medium Local 優勢 Deadline|1.7%|1.7%|0%|0%|
|LFW High Cloud 優勢 平均 ms|26.6|26.7|5,902.7|212.5|
|WIDER Low Local 優勢 平均 ms|2,659.2|2,592.0|2,664.3|4,084.1|
|WIDER Low Local 優勢 P95 ms|8,345.0|8,345.0|4,345.3|9,049.7|
|WIDER Low Local 優勢 Deadline|37.0%|38.0%|0%|0%|
|WIDER High Reference 平均 ms|304.1|311.2|6,886.2|6,886.2|
|WIDER High Reference Deadline|95.3%|95.3%|4.3%|4.3%|

DQN 在 LFW Medium Local 優勢比 V1 平均快約 85 ms、P95 比兩版都低，但平均仍慢於 V2，Deadline 也落後。在 WIDER Low Local 優勢，DQN 大幅降低 P95，平均與 V1 接近、且 Deadline 落後。DDQN 在 LFW High Cloud 優勢大幅改善 DQN 的平均延遲，仍慢於兩版 Latency-aware；在兩個表列 Local 優勢情境，DDQN 平均則慢於 DQN。Edge 優勢的 LFW 三種負載與 WIDER 的 Low、Medium，四種方法的平均接近；WIDER High 開始拉開差距。Reference 中兩個 RL 模型在高負載形成長排隊。上述差異依網路與負載而變，不能用單一排名概括。

Laya 成本取自 480 筆封存真實呼叫，在決定擴充前先估算。若兩版都跑 100 圖 × 24 情境 × 3 種子，需 14,400 次呼叫，依實測平均約 8.03 小時串行 client 決策時間。共同子集選擇直接使用兩版各 240 筆完整封存的模擬，保留當次決策、成本和事件，八個對照重跑相同固定圖片、順序與時程。新增 Laya 呼叫為 0。該時程來自歷史 Pilot aggregate 設計，因此與本輪訓練固定時程的 100 圖設計分表。

|封存服務|Worker 平均／P95 ms|Client 決策平均／P95 ms|決策排隊平均／P95 ms|
|---|---:|---:|---:|
|Laya Original|1,608.56／1,880.25|1,622.57／1,893.00|2,157.18／5,708.39|
|Laya V2|2,379.57／2,869.19|2,392.22／2,882.39|3,793.07／8,995.70|

兩版 Laya 在 24 個共同子集情境的平均延遲均高於 Latency-aware V1，且 Deadline 全部未達。以 LFW Low Reference 為例，V1 為 161.3 ms，Laya Original 4,008.4 ms、V2 7,610.0 ms，決策與排隊是主因。此結果支持本次單決策資源與 1,000 ms Deadline 下的端到端成本結論。Laya 的選點品質、其他服務部署與較長 Deadline 的效益需要另外測量。

