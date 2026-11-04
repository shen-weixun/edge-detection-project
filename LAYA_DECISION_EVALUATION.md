# Laya決策可靠性與成本評估

結論：唯一預先固定的V2在Local情境較好，但Edge/Cloud排列不變性與單因素成本敏感度仍失敗，實測成本較高。因此V2只是可切換探索版本，沒有提升為可靠策略；保留原版，也沒有用Latency-aware、Oracle或排序偷偷替換模型輸出。

## Checkpoint與方法

[官方模型卡的Honest Limits](https://huggingface.co/convaiinnovations/laya#honest-limits)把它定位為可專化的typed分類基礎，未保證零樣本數值決策。實際使用laya0.4.17、Torch2.9.1+cpu、同一multilingual checkpoint；快取revision=7b928d828b7b0e022f929d9bd2e44165aa270148。沒有換權重、訓練或引用其他workflow benchmark成績當本專案準確率。
原版保持JSON/固定Cloud faster等描述與原推論設定；V2只做一次凍結候選：刪除固定節點快慢描述、使用統一ms的預估傳輸/CPU/承諾工作、剩餘Deadline，指定相同multilingual checkpoint，CPU threads=1且每次在lock內還原舊設定。沒有啟用只適用CUDA的fast path，也沒有加入結果快取。
V2 candidate與choice options均保留傳入排列，沒有按成本或名字排序。格式化只有可觀測量的代數轉換，沒有傳最低成本答案。輸入縮短與thread設定是合併候選，不能從此實驗獨立歸因兩者效果。

## 六排列×兩次重複與單因素

共90次模型呼叫：每版36個三節點有利排列測試，加9個RTT/頻寬/算力/CPU queue單因素狀態。另各1次預熱，排除統計。每一版的每個排列重複對均一致，但跨排列並不保證一致。

|版本|合法選擇|最低共同估計成本|平均決策HTTP ms|P95 ms|單因素正確|
|---|---|---|---|---|---|
|legacy|45/45|12/45|1095.775|1262.395|4/9|
|v2|45/45|21/45|1729.374|2012.596|3/9|

|版本|情境|正確/12|排列不變|重複一致/6|
|---|---|---|---|---|
|legacy|A_local|6/12|False|6/6|
|legacy|B_edge|2/12|False|6/6|
|legacy|C_cloud|0/12|False|6/6|
|v2|A_local|12/12|True|6/6|
|v2|B_edge|4/12|False|6/6|
|v2|C_cloud|2/12|False|6/6|

legacy平均input tokens=572.822。

v2平均input tokens=399.978。

雖然V2約400 token對原版573較短，但單thread候選沒有變快；不拿較短輸入冒稱低成本成功。最低成本率以相同observable state的V2物理估計為參考；它不是辨識準確率或真實全域最佳排程。三個空佇列有利情境的兩成本公式排序一致。

## 全部排列結果（沒有隱藏失敗）

|情境|排列|原版兩次|V2兩次|
|---|---|---|---|
|A_local|local→edge→cloud|cloud/cloud|local/local|
|A_local|local→cloud→edge|edge/edge|local/local|
|A_local|edge→local→cloud|cloud/cloud|local/local|
|A_local|edge→cloud→local|local/local|local/local|
|A_local|cloud→local→edge|local/local|local/local|
|A_local|cloud→edge→local|local/local|local/local|
|B_edge|local→edge→cloud|cloud/cloud|edge/edge|
|B_edge|local→cloud→edge|edge/edge|local/local|
|B_edge|edge→local→cloud|local/local|local/local|
|B_edge|edge→cloud→local|local/local|local/local|
|B_edge|cloud→local→edge|local/local|local/local|
|B_edge|cloud→edge→local|local/local|edge/edge|
|C_cloud|local→edge→cloud|local/local|edge/edge|
|C_cloud|local→cloud→edge|edge/edge|cloud/cloud|
|C_cloud|edge→local→cloud|local/local|local/local|
|C_cloud|edge→cloud→local|local/local|local/local|
|C_cloud|cloud→local→edge|edge/edge|local/local|
|C_cloud|cloud→edge→local|local/local|local/local|

單因素完整輸入與原始response見laya-diagnostics.json；90/90原始SDK choice=HTTP choice，fallback=0，truncated=0。

## 計入決策成本與消融

原版正式矩陣跨全部環境、3種子；V2已未通過可靠性，只在reference環境/seed11作6個探索性格，另做對應消融，沒有納入正式可靠排名。以下成對結果全為同圖片/seed/環境。

|資料集|負載|版本|範圍|平均延遲ms|P95|Deadline|決策ms|決策等待ms|
|---|---|---|---|---|---|---|---|---|
|lfw|low|laya|formal|983.829|1145.988|50.00%|694.602|0.000|
|lfw|low|laya|ablation|289.227|431.609|100.00%|0.000|0.000|
|lfw|low|laya_v2|exploratory|2026.684|2236.602|0.00%|1861.317|0.000|
|lfw|low|laya_v2|exploratory_ablation|165.366|172.687|100.00%|0.000|0.000|
|lfw|medium|laya|formal|4313.138|7274.128|0.00%|1350.400|2799.249|
|lfw|medium|laya|ablation|163.489|172.687|100.00%|0.000|0.000|
|lfw|medium|laya_v2|exploratory|5379.226|9125.485|0.00%|1612.693|3470.972|
|lfw|medium|laya_v2|exploratory_ablation|165.366|172.687|100.00%|0.000|0.000|
|lfw|high|laya|formal|4621.809|8027.446|0.00%|1330.120|3128.200|
|lfw|high|laya|ablation|305.818|496.218|100.00%|0.000|0.000|
|lfw|high|laya_v2|exploratory|7067.546|12111.238|0.00%|1964.485|4807.499|
|lfw|high|laya_v2|exploratory_ablation|455.684|757.530|100.00%|0.000|0.000|
|wider|low|laya|formal|2100.627|4012.625|0.00%|1251.730|0.000|
|wider|low|laya|ablation|848.897|2770.761|83.33%|0.000|0.000|
|wider|low|laya_v2|exploratory|2217.033|2837.012|0.00%|1894.089|0.000|
|wider|low|laya_v2|exploratory_ablation|322.944|951.518|100.00%|0.000|0.000|
|wider|medium|laya|formal|4561.798|7712.743|0.00%|1400.627|2838.227|
|wider|medium|laya|ablation|754.639|951.518|100.00%|0.000|0.000|
|wider|medium|laya_v2|exploratory|6886.259|10922.696|0.00%|1935.619|4285.683|
|wider|medium|laya_v2|exploratory_ablation|760.382|951.518|100.00%|0.000|0.000|
|wider|high|laya|formal|4862.450|8317.283|0.00%|1355.551|3183.955|
|wider|high|laya|ablation|370.676|566.662|100.00%|0.000|0.000|
|wider|high|laya_v2|exploratory|8001.350|12575.902|0.00%|2065.320|5271.072|
|wider|high|laya_v2|exploratory_ablation|800.887|2770.761|83.33%|0.000|0.000|

矩陣內504次AI選擇逐一連結audit_id並核對真實raw choice，fallback=0，輸入截斷=0；原始資料matrix-laya-audit.jsonl。
消融decision_ms/decision_queue_ms=0，但wall time仍保留；不是正式端到端效能。Laya真實推論耗時不會被當成影像CPU compute_ms，單一序列決策Resource造成的等待是原模型明示假設。現有模型不適合作為可靠數值卸載決策器；更多未受控Prompt調整沒有驗收依據，因此停止此輪調整。
