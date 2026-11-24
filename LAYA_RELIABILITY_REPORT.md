# Laya可靠性與成本：獨立對照研究

本輪新增真實模型呼叫0，沒有調Prompt、重訓、改模型或用規則代替輸出。依使用者效率規則，重新核對既有90次固定診斷及144筆歷史端到端/消融任務的raw choice與HTTP選擇；所有原始模型輸出/時間戳/雜湊保留。這些不是新100圖Laya實驗。

原版/V2同checkpoint與前輪凍結CPU設定；V2是中立緊湊輸入與單thread候選。三節點六排列×兩次重複、RTT/頻寬/算力/queue單因素均沿用固定診斷；最低成本依共同可觀測估計，非隱藏真值Oracle。

|版本|合法|最低估計成本正確|平均HTTP ms|P95 HTTP ms|單因素正確|
|---|---|---|---|---|---|
|legacy|45/45|12/45|1095.775|1262.395|4/9|
|v2|45/45|21/45|1729.374|2012.596|3/9|

## 有利情境與排列不變性

|版本|情境|正確/12|排列不變|重複一致/6|
|---|---|---|---|---|
|legacy|A_local|6/12|False|6|
|legacy|B_edge|2/12|False|6|
|legacy|C_cloud|0/12|False|6|
|v2|A_local|12/12|True|6|
|v2|B_edge|4/12|False|6|
|v2|C_cloud|2/12|False|6|

每個排列/單因素的選擇與估計成本完整列laya_diagnostic.csv；90個raw choice與最終選擇完全一致、零fallback、原診斷零截斷。相同排列重複一致不代表跨排列可靠。

## 既有6圖episode的實測成本（歷史證據）

RECORDED_CHARGED_COST計入原始實測選擇時間；RECORDED_REAL_MODEL_ABLATION是當時另行執行真實模型但不計入模擬延遲的資料。本輪只是重讀，沒有新推論或新Replay，不冒充本輪test評估。原Median與舊test Profile和本輪不同，不可合併正式排名。

|dataset|負載|版本|scope|n|平均ms|P95|Deadline|決策ms|決策等待ms|
|---|---|---|---|---|---|---|---|---|---|
|lfw|high|laya|RECORDED_REAL_MODEL_ABLATION|6|305.818|496.218|100.0%|0.000|0.000|
|lfw|high|laya_v2|RECORDED_CHARGED_COST|6|7067.546|12111.238|0.0%|1964.485|4807.499|
|lfw|high|laya_v2|RECORDED_REAL_MODEL_ABLATION|6|455.684|757.530|100.0%|0.000|0.000|
|lfw|high|laya|RECORDED_CHARGED_COST|6|4621.809|8027.446|0.0%|1330.120|3128.200|
|lfw|low|laya|RECORDED_REAL_MODEL_ABLATION|6|289.227|431.609|100.0%|0.000|0.000|
|lfw|low|laya_v2|RECORDED_CHARGED_COST|6|2026.684|2236.602|0.0%|1861.317|0.000|
|lfw|low|laya_v2|RECORDED_REAL_MODEL_ABLATION|6|165.366|172.687|100.0%|0.000|0.000|
|lfw|low|laya|RECORDED_CHARGED_COST|6|983.829|1145.988|50.0%|694.602|0.000|
|lfw|medium|laya|RECORDED_REAL_MODEL_ABLATION|6|163.489|172.687|100.0%|0.000|0.000|
|lfw|medium|laya_v2|RECORDED_CHARGED_COST|6|5379.226|9125.485|0.0%|1612.693|3470.972|
|lfw|medium|laya_v2|RECORDED_REAL_MODEL_ABLATION|6|165.366|172.687|100.0%|0.000|0.000|
|lfw|medium|laya|RECORDED_CHARGED_COST|6|4313.138|7274.128|0.0%|1350.400|2799.249|
|wider_train|high|laya|RECORDED_REAL_MODEL_ABLATION|6|370.676|566.662|100.0%|0.000|0.000|
|wider_train|high|laya_v2|RECORDED_CHARGED_COST|6|8001.350|12575.902|0.0%|2065.320|5271.072|
|wider_train|high|laya_v2|RECORDED_REAL_MODEL_ABLATION|6|800.887|2770.761|83.3%|0.000|0.000|
|wider_train|high|laya|RECORDED_CHARGED_COST|6|4862.450|8317.283|0.0%|1355.551|3183.955|
|wider_train|low|laya|RECORDED_REAL_MODEL_ABLATION|6|848.897|2770.761|83.3%|0.000|0.000|
|wider_train|low|laya_v2|RECORDED_CHARGED_COST|6|2217.033|2837.012|0.0%|1894.089|0.000|
|wider_train|low|laya_v2|RECORDED_REAL_MODEL_ABLATION|6|322.944|951.518|100.0%|0.000|0.000|
|wider_train|low|laya|RECORDED_CHARGED_COST|6|2100.627|4012.625|0.0%|1251.730|0.000|
|wider_train|medium|laya|RECORDED_REAL_MODEL_ABLATION|6|754.639|951.518|100.0%|0.000|0.000|
|wider_train|medium|laya_v2|RECORDED_CHARGED_COST|6|6886.259|10922.696|0.0%|1935.619|4285.683|
|wider_train|medium|laya_v2|RECORDED_REAL_MODEL_ABLATION|6|760.382|951.518|100.0%|0.000|0.000|
|wider_train|medium|laya|RECORDED_CHARGED_COST|6|4561.798|7712.743|0.0%|1400.627|2838.227|

判斷：兩版都不能可靠選最低數值成本，保留為通用AI失效對照；V2只有Local排列不變，不能認證整體改善。實測CPU決策約秒級，成本與序列等待足以在這些歷史episode侵蝕卸載收益；是否所有新100圖/設備都如此為NOT VERIFIED，沒有以免費重播或Latency-aware輸出代替真正AI來作結論。
資料：laya/reuse-manifest.json、laya_diagnostic.csv、laya/下診斷與historical-raw/、historical-audit.jsonl。
