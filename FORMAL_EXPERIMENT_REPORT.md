# 正式實驗資料與策略比較報告

本輪目的為擴大獨立圖片及公平比較，不要求V2勝出。原Baseline/V1/V2/估計器/Laya算法保持凍結，所有負面結果保留。

## 資料與量測

每資料集40 training、20 validation、100 testing，共320張成功實測；LFW100張test為100個人物，WIDER群組數如下。test排除既有註冊歷史量測，依seed20261104、人物/事件分組在任何新test推論前凍結。320張內容SHA256互異，dHash64距離<=4預篩無重複。dHash不是人臉/語意重複的完整證明。

|資料集|角色|圖片|群組|
|---|---|---|---|
|lfw|training|40|40|
|lfw|validation|20|20|
|lfw|testing|100|100|
|wider_train|training|40|20|
|wider_train|validation|20|11|
|wider_train|testing|100|16|

107張training/validation有效同模型/CPU/至少3次正式歷史量測重用；新增213張各預熱+3正式，共852次InsightFace呼叫。新test200張全部新量測。read/decode/初始化/warmup/lock wait不算影像inference，CPU compute真值是三次中位數。每圖device/model/原始三次/成功狀態/時間戳與來源provenance保留dataset_manifest.json與measurements/。歷史與新量測批次不同，單host調度/熱狀態會帶來量測變異，未量測跨設備。

## 事前情境矩陣

8環境×3到達間隔70/300/1000×3 Deadline500/1000/2000×3種子11/23/37×2資料集=432格。每格100張test全部使用，seed只改順序。6種Median策略+V1/V2 Ridge=3456次策略run、345600任務。決策使用同一DecisionTask/NodeState可觀測資訊契約，只有刻意隔離的估計器因素改變預測值。

|環境|Local speed|Edge speed/RTT/BW|Cloud speed/RTT/BW|network/shared Mbps|
|---|---|---|---|---|
|reference|1|3/20/120|8/100/55|independent/120|
|local_advantage|1|3/1000/1|8/2000/0.5|independent/120|
|edge_advantage|1|6/4/1000|8/2000/1|independent/120|
|cloud_advantage|1|2/30/80|20/2/1000|independent/120|
|edge_rtt_400|1|3/400/120|8/100/55|independent/120|
|cloud_bandwidth_4|1|3/20/120|8/100/4|independent/120|
|remote_compute_2x|1|6/20/120|16/100/55|independent/120|
|shared_8|1|3/20/120|8/100/55|shared/8|

speed為相對Local，RTT ms、BW Mbps。獨立上下行資源、CPU單容量、shared上下行各獨立但Edge/Cloud共用出口，符合原模型。完整條件scenario_matrix.csv。固定complete_all，逾期仍完成；Deadline為arrival+relative deadline，達成率與最終完成率不同。
正式延遲計入policy timer內的預測與選擇wall time；decision_queue是單序列決策資源等待。訓練/讀取profile/離線選模不算線上決策，也不冒充影像compute。相同任務的actual_workload_sha256跨估計器核對一致。

## Reference環境：全部負載/Deadline/策略（逐條件，不混平均）

|dataset|間隔|Deadline|估計器|策略|平均ms|P95|Deadline率|完成/丟棄|
|---|---|---|---|---|---|---|---|---|
|lfw|1000|1000|median|cloud_only|165.415|194.805|100.0%|100.0%/0.0%|
|lfw|1000|1000|median|edge_only|184.640|263.058|100.0%|100.0%/0.0%|
|lfw|1000|1000|median|latency_aware|165.417|194.807|100.0%|100.0%/0.0%|
|lfw|1000|1000|median|latency_aware_v2|165.424|194.814|100.0%|100.0%/0.0%|
|lfw|1000|1000|median|load_threshold|184.640|263.058|100.0%|100.0%/0.0%|
|lfw|1000|1000|median|local_only|487.814|723.182|100.0%|100.0%/0.0%|
|lfw|1000|1000|ridge|latency_aware|165.428|194.817|100.0%|100.0%/0.0%|
|lfw|1000|1000|ridge|latency_aware_v2|165.436|194.828|100.0%|100.0%/0.0%|
|lfw|1000|2000|median|cloud_only|165.415|194.805|100.0%|100.0%/0.0%|
|lfw|1000|2000|median|edge_only|184.640|263.058|100.0%|100.0%/0.0%|
|lfw|1000|2000|median|latency_aware|165.417|194.808|100.0%|100.0%/0.0%|
|lfw|1000|2000|median|latency_aware_v2|165.425|194.816|100.0%|100.0%/0.0%|
|lfw|1000|2000|median|load_threshold|184.640|263.058|100.0%|100.0%/0.0%|
|lfw|1000|2000|median|local_only|487.814|723.182|100.0%|100.0%/0.0%|
|lfw|1000|2000|ridge|latency_aware|165.429|194.824|100.0%|100.0%/0.0%|
|lfw|1000|2000|ridge|latency_aware_v2|165.438|194.834|100.0%|100.0%/0.0%|
|lfw|1000|500|median|cloud_only|165.415|194.805|100.0%|100.0%/0.0%|
|lfw|1000|500|median|edge_only|184.640|263.058|100.0%|100.0%/0.0%|
|lfw|1000|500|median|latency_aware|165.418|194.812|100.0%|100.0%/0.0%|
|lfw|1000|500|median|latency_aware_v2|165.425|194.815|100.0%|100.0%/0.0%|
|lfw|1000|500|median|load_threshold|184.640|263.058|100.0%|100.0%/0.0%|
|lfw|1000|500|median|local_only|487.814|723.183|74.0%|100.0%/0.0%|
|lfw|1000|500|ridge|latency_aware|165.430|194.820|100.0%|100.0%/0.0%|
|lfw|1000|500|ridge|latency_aware_v2|165.438|194.827|100.0%|100.0%/0.0%|
|lfw|300|1000|median|cloud_only|165.415|194.805|100.0%|100.0%/0.0%|
|lfw|300|1000|median|edge_only|184.640|263.058|100.0%|100.0%/0.0%|
|lfw|300|1000|median|latency_aware|165.418|194.808|100.0%|100.0%/0.0%|
|lfw|300|1000|median|latency_aware_v2|165.425|194.815|100.0%|100.0%/0.0%|
|lfw|300|1000|median|load_threshold|184.641|263.059|100.0%|100.0%/0.0%|
|lfw|300|1000|median|local_only|10052.904|18226.978|3.7%|100.0%/0.0%|
|lfw|300|1000|ridge|latency_aware|165.430|194.820|100.0%|100.0%/0.0%|
|lfw|300|1000|ridge|latency_aware_v2|165.438|194.826|100.0%|100.0%/0.0%|
|lfw|300|2000|median|cloud_only|165.415|194.805|100.0%|100.0%/0.0%|
|lfw|300|2000|median|edge_only|184.640|263.058|100.0%|100.0%/0.0%|
|lfw|300|2000|median|latency_aware|165.418|194.809|100.0%|100.0%/0.0%|
|lfw|300|2000|median|latency_aware_v2|165.426|194.816|100.0%|100.0%/0.0%|
|lfw|300|2000|median|load_threshold|184.640|263.058|100.0%|100.0%/0.0%|
|lfw|300|2000|median|local_only|10052.903|18226.978|8.0%|100.0%/0.0%|
|lfw|300|2000|ridge|latency_aware|165.429|194.819|100.0%|100.0%/0.0%|
|lfw|300|2000|ridge|latency_aware_v2|165.436|194.825|100.0%|100.0%/0.0%|
|lfw|300|500|median|cloud_only|165.415|194.805|100.0%|100.0%/0.0%|
|lfw|300|500|median|edge_only|184.640|263.058|100.0%|100.0%/0.0%|
|lfw|300|500|median|latency_aware|165.417|194.808|100.0%|100.0%/0.0%|
|lfw|300|500|median|latency_aware_v2|165.425|194.814|100.0%|100.0%/0.0%|
|lfw|300|500|median|load_threshold|184.640|263.058|100.0%|100.0%/0.0%|
|lfw|300|500|median|local_only|10052.903|18226.977|0.7%|100.0%/0.0%|
|lfw|300|500|ridge|latency_aware|165.430|194.819|100.0%|100.0%/0.0%|
|lfw|300|500|ridge|latency_aware_v2|165.437|194.828|100.0%|100.0%/0.0%|
|lfw|70|1000|median|cloud_only|171.508|203.027|100.0%|100.0%/0.0%|
|lfw|70|1000|median|edge_only|4857.981|8917.672|8.7%|100.0%/0.0%|
|lfw|70|1000|median|latency_aware|173.997|219.014|100.0%|100.0%/0.0%|
|lfw|70|1000|median|latency_aware_v2|170.589|202.324|100.0%|100.0%/0.0%|
|lfw|70|1000|median|load_threshold|295.695|550.574|100.0%|100.0%/0.0%|
|lfw|70|1000|median|local_only|21437.904|39846.978|1.7%|100.0%/0.0%|
|lfw|70|1000|ridge|latency_aware|173.863|219.026|100.0%|100.0%/0.0%|
|lfw|70|1000|ridge|latency_aware_v2|170.599|202.332|100.0%|100.0%/0.0%|
|lfw|70|2000|median|cloud_only|171.508|203.027|100.0%|100.0%/0.0%|
|lfw|70|2000|median|edge_only|4857.981|8917.673|19.7%|100.0%/0.0%|
|lfw|70|2000|median|latency_aware|173.997|219.014|100.0%|100.0%/0.0%|
|lfw|70|2000|median|latency_aware_v2|170.589|202.324|100.0%|100.0%/0.0%|
|lfw|70|2000|median|load_threshold|295.695|550.573|100.0%|100.0%/0.0%|
|lfw|70|2000|median|local_only|21437.904|39846.978|4.0%|100.0%/0.0%|
|lfw|70|2000|ridge|latency_aware|173.863|219.026|100.0%|100.0%/0.0%|
|lfw|70|2000|ridge|latency_aware_v2|170.601|202.336|100.0%|100.0%/0.0%|
|lfw|70|500|median|cloud_only|171.507|203.027|100.0%|100.0%/0.0%|
|lfw|70|500|median|edge_only|4857.981|8917.672|4.0%|100.0%/0.0%|
|lfw|70|500|median|latency_aware|173.996|219.015|100.0%|100.0%/0.0%|
|lfw|70|500|median|latency_aware_v2|170.588|202.323|100.0%|100.0%/0.0%|
|lfw|70|500|median|load_threshold|295.695|550.573|87.0%|100.0%/0.0%|
|lfw|70|500|median|local_only|21437.904|39846.978|0.7%|100.0%/0.0%|
|lfw|70|500|ridge|latency_aware|173.862|219.026|100.0%|100.0%/0.0%|
|lfw|70|500|ridge|latency_aware_v2|170.600|202.333|100.0%|100.0%/0.0%|
|wider_train|1000|1000|median|cloud_only|251.878|532.268|99.0%|100.0%/0.0%|
|wider_train|1000|1000|median|edge_only|454.025|1400.266|88.0%|100.0%/0.0%|
|wider_train|1000|1000|median|latency_aware|258.956|532.271|98.0%|100.0%/0.0%|
|wider_train|1000|1000|median|latency_aware_v2|258.964|532.279|98.0%|100.0%/0.0%|
|wider_train|1000|1000|median|load_threshold|452.538|1400.266|88.0%|100.0%/0.0%|
|wider_train|1000|1000|median|local_only|9390.436|14455.316|6.7%|100.0%/0.0%|
|wider_train|1000|1000|ridge|latency_aware|267.593|565.171|97.0%|100.0%/0.0%|
|wider_train|1000|1000|ridge|latency_aware_v2|267.602|565.179|97.0%|100.0%/0.0%|
|wider_train|1000|2000|median|cloud_only|251.878|532.269|100.0%|100.0%/0.0%|
|wider_train|1000|2000|median|edge_only|454.025|1400.267|97.0%|100.0%/0.0%|
|wider_train|1000|2000|median|latency_aware|258.956|532.271|100.0%|100.0%/0.0%|
|wider_train|1000|2000|median|latency_aware_v2|258.964|532.280|100.0%|100.0%/0.0%|
|wider_train|1000|2000|median|load_threshold|452.538|1400.267|97.0%|100.0%/0.0%|
|wider_train|1000|2000|median|local_only|9390.436|14455.316|12.3%|100.0%/0.0%|
|wider_train|1000|2000|ridge|latency_aware|267.594|565.172|100.0%|100.0%/0.0%|
|wider_train|1000|2000|ridge|latency_aware_v2|267.603|565.180|100.0%|100.0%/0.0%|
|wider_train|1000|500|median|cloud_only|251.878|532.269|94.0%|100.0%/0.0%|
|wider_train|1000|500|median|edge_only|454.026|1400.267|77.3%|100.0%/0.0%|
|wider_train|1000|500|median|latency_aware|258.957|532.272|94.0%|100.0%/0.0%|
|wider_train|1000|500|median|latency_aware_v2|258.966|532.281|94.0%|100.0%/0.0%|
|wider_train|1000|500|median|load_threshold|452.539|1400.267|77.7%|100.0%/0.0%|
|wider_train|1000|500|median|local_only|9390.436|14455.316|2.7%|100.0%/0.0%|
|wider_train|1000|500|ridge|latency_aware|267.596|565.174|94.0%|100.0%/0.0%|
|wider_train|1000|500|ridge|latency_aware_v2|267.604|565.180|94.0%|100.0%/0.0%|
|wider_train|300|1000|median|cloud_only|300.995|843.194|97.3%|100.0%/0.0%|
|wider_train|300|1000|median|edge_only|4560.499|6755.955|8.3%|100.0%/0.0%|
|wider_train|300|1000|median|latency_aware|290.262|831.345|97.3%|100.0%/0.0%|
|wider_train|300|1000|median|latency_aware_v2|294.570|801.962|96.7%|100.0%/0.0%|
|wider_train|300|1000|median|load_threshold|629.008|2037.643|80.0%|100.0%/0.0%|
|wider_train|300|1000|median|local_only|42273.874|71018.125|0.3%|100.0%/0.0%|
|wider_train|300|1000|ridge|latency_aware|290.534|808.220|96.3%|100.0%/0.0%|
|wider_train|300|1000|ridge|latency_aware_v2|291.234|808.231|96.3%|100.0%/0.0%|
|wider_train|300|2000|median|cloud_only|300.994|843.193|100.0%|100.0%/0.0%|
|wider_train|300|2000|median|edge_only|4560.499|6755.956|17.3%|100.0%/0.0%|
|wider_train|300|2000|median|latency_aware|290.262|831.344|100.0%|100.0%/0.0%|
|wider_train|300|2000|median|latency_aware_v2|294.569|801.964|100.0%|100.0%/0.0%|
|wider_train|300|2000|median|load_threshold|629.007|2037.643|94.7%|100.0%/0.0%|
|wider_train|300|2000|median|local_only|42273.873|71018.124|3.3%|100.0%/0.0%|
|wider_train|300|2000|ridge|latency_aware|290.532|808.219|100.0%|100.0%/0.0%|
|wider_train|300|2000|ridge|latency_aware_v2|291.231|808.228|100.0%|100.0%/0.0%|
|wider_train|300|500|median|cloud_only|300.995|843.195|86.7%|100.0%/0.0%|
|wider_train|300|500|median|edge_only|4560.500|6755.956|5.7%|100.0%/0.0%|
|wider_train|300|500|median|latency_aware|290.263|831.346|89.3%|100.0%/0.0%|
|wider_train|300|500|median|latency_aware_v2|294.574|801.964|88.7%|100.0%/0.0%|
|wider_train|300|500|median|load_threshold|629.010|2037.645|62.0%|100.0%/0.0%|
|wider_train|300|500|median|local_only|42273.874|71018.125|0.3%|100.0%/0.0%|
|wider_train|300|500|ridge|latency_aware|290.539|808.227|91.0%|100.0%/0.0%|
|wider_train|300|500|ridge|latency_aware_v2|291.240|808.234|91.0%|100.0%/0.0%|
|wider_train|70|1000|median|cloud_only|3795.809|5962.397|11.0%|100.0%/0.0%|
|wider_train|70|1000|median|edge_only|15604.831|26521.248|4.3%|100.0%/0.0%|
|wider_train|70|1000|median|latency_aware|1586.230|2975.204|34.7%|100.0%/0.0%|
|wider_train|70|1000|median|latency_aware_v2|1642.128|3006.419|24.3%|100.0%/0.0%|
|wider_train|70|1000|median|load_threshold|2074.238|3344.912|22.7%|100.0%/0.0%|
|wider_train|70|1000|median|local_only|53658.873|92638.125|0.3%|100.0%/0.0%|
|wider_train|70|1000|ridge|latency_aware|1567.102|2776.973|35.7%|100.0%/0.0%|
|wider_train|70|1000|ridge|latency_aware_v2|1621.930|3383.705|26.3%|100.0%/0.0%|
|wider_train|70|2000|median|cloud_only|3795.810|5962.398|16.0%|100.0%/0.0%|
|wider_train|70|2000|median|edge_only|15604.832|26521.249|7.3%|100.0%/0.0%|
|wider_train|70|2000|median|latency_aware|1586.232|2975.204|68.0%|100.0%/0.0%|
|wider_train|70|2000|median|latency_aware_v2|1642.129|3006.420|67.0%|100.0%/0.0%|
|wider_train|70|2000|median|load_threshold|2074.238|3344.912|46.7%|100.0%/0.0%|
|wider_train|70|2000|median|local_only|53658.874|92638.125|2.0%|100.0%/0.0%|
|wider_train|70|2000|ridge|latency_aware|1567.112|2776.984|66.7%|100.0%/0.0%|
|wider_train|70|2000|ridge|latency_aware_v2|1621.934|3383.708|74.0%|100.0%/0.0%|
|wider_train|70|500|median|cloud_only|3795.810|5962.398|7.7%|100.0%/0.0%|
|wider_train|70|500|median|edge_only|15604.831|26521.248|1.3%|100.0%/0.0%|
|wider_train|70|500|median|latency_aware|1586.230|2975.204|9.7%|100.0%/0.0%|
|wider_train|70|500|median|latency_aware_v2|1642.129|3006.421|9.7%|100.0%/0.0%|
|wider_train|70|500|median|load_threshold|2074.238|3344.912|7.3%|100.0%/0.0%|
|wider_train|70|500|median|local_only|53658.873|92638.124|0.3%|100.0%/0.0%|
|wider_train|70|500|ridge|latency_aware|1567.119|2776.976|11.7%|100.0%/0.0%|
|wider_train|70|500|ridge|latency_aware_v2|1621.932|3383.721|13.0%|100.0%/0.0%|

所有8環境/3 Deadline/3間隔完整結果與分解：strategy_comparison.csv逐seed，strategy_aggregate.csv每條件三seed均值/SD/t95CI。包含decision/wall/decision_queue/network/CPUqueue/compute、time-weighted queues、各節點utilization與placement。P95定義為各run all-terminal任務nearest-rank 95th percentile；聚合列P95是三個run P95的平均，不是混合分布P95。
paired_differences.csv提供三種隔離比較的成對變異與df2區間；CI未多重比較校正，seed不產生新的獨立圖片，不以區間挑winner。

![正式reference策略比較](plots/reference_strategy_latency.png)

## 正確性與限制

所有345600筆時間守恆、階段順序、真實compute不變、唯一任務、100%完成及無丟棄；CPU區間不超額，policy DTO沒有真實workload/人臉數/來源路徑。12個100圖零決策成本run另經獨立FCFS CPU與上下行參考/確定性重播。原單元、API與Docker驗證記錄見tests/。核心與V1等受保護SHA256核對未改。
簡化限制：當下節點狀態無監測延遲；固定頻寬序列傳輸/全雙工、固定16KB結果、相對speed線性縮放，不是實際遠端部署；聚合commit不是精確未來排程；單host小量三次推論與三種任務順序，WIDER事件分組不是完整人物隔離。

## 最終八項回答

1. 圖片量：YES，LFW/WIDER各100個內容唯一的新實測test，另各40/20訓練/驗證；群組數及近似重複限制如上，不能把100圖當100個WIDER獨立事件。
2. Median/Ridge：依WORKLOAD_ESTIMATOR_REPORT逐資料集MAE與群組CI判斷；沒有跨資料集全面勝出預設，保留Median。
3. V2：不能宣稱普遍優於V1。固定Median144個條件>1ms計數為{'within_1ms': 90, 'improved_gt1ms': 24, 'regressed_gt1ms': 30}；全量退化格與CI見LATENCY_AWARE_COMPARISON與paired_differences.csv。
4. Laya：FAIL，兩版都未通過數值成本/排列可靠性，原始輸出如實保留。
5. Laya成本：歷史CPU秒級決策與序列等待顯著侵蝕可得卸載效益，正式/消融表已列；本輪新100圖與其他硬體的普遍成本優劣為NOT VERIFIED，沒有重複昂貴推論。
6. 公平性：PASS，所有本輪非AI策略相同100圖、順序、環境、deadline、完整完成標準，決策cost統一；預估器因素刻意隔離。Laya為獨立歷史研究，不混入當前排名。
7. 組員程式：PASS，原RL/核心/V1檔案逐位元組未改；新增獨立可觀測轉接與8項相容測試。真實訓練DQN/DDQN模型未提供，因此實際演算法準確率/耗時整合為NOT VERIFIED，HTTP的DQN key仍未註冊。
8. 期末證據：有條件YES，可支持這批凍結資料與已宣告SimPy假設下的課堂比較與負面結果；不能支持實際遠端平台效能、Laya可靠數值AI或未測DQN成績。

重現命令與介面欄位見TEAM_INTEGRATION_CONTRACT.md、CODEX_PROGRESS.md；所有raw JSON及CSV保留，不因不利結果改算法/測試資料。

## 最終回歸實際結果

85/85後端、2/2 Laya服務mock、109/109 HTTP檢查通過；Docker build/up成功，backend/db/laya healthy、frontend running。18個診斷run共1800任務通過獨立FCFS，另12次確定性重播一致。瀏覽器視覺點擊與真實DQN權重未驗證，詳見tests/test-summary.json與原始logs。

與前輪12圖結果不同，是資料擴大、群組隔離、凍結新圖片與重新擬合訓練集的實驗差異；V1/V2公式未變，不能把新舊數據差當算法改進。
