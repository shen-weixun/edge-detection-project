# Latency-aware V2 報告

保留原latency_aware，新增latency_aware_v2；不改SimPy timeout、Resource、真實工作量或RL觀測/action/reward。V2以phase overlap減少串行相加的過度預估，但仍是聚合估計，不能保證所有情境較好。

## 物理意義與公式

令 c=(queue_work_ms+committed_work_ms)/speed、x=estimated_workload_ms/speed、r=RTT/2、u=MB×8000/Mbps、d=KB×8/Mbps，U/D為當下上/下載backlog（全部ms）。Local：T=c+x。遠端：
```text
input_ready = max(r, U) + u
cpu_finish = max(input_ready, c) + x
T = max(cpu_finish + r, D) + d
remaining_deadline = deadline_ms - max(0, observed_at_ms - arrival_ms)
slack = remaining_deadline - T
late_ratio = max(0, T - remaining_deadline) / deadline_ms
post_cpu_pressure = (c + x) / max(remaining_deadline, epsilon)
```
原版會把CPU work、上/下載積壓和全部網路服務相加；V2容許既有工作在本任務傳播/上傳/運算期間排空。已承諾未到CPU的工作仍納入c，未看真實完成時間或未來任務。
決策採(是否超期、相對超時、T、post_cpu_pressure、節點名)詞典序，無任意加權相加。必須坦白：只以最低延遲為主要目標時，Deadline判斷不會改變T的排序；pressure只解完全相同T的平手。因此改善主要來自重疊時間估計，不聲稱Deadline分支單獨提高績效。
本模型頻寬固定且即時可觀測，未加入無資料支持的EWMA或能耗估算；未實作LEAOT完整加權score。

## 九個固定情境

包含Local/Edge/Cloud有利、Edge CPU積壓、Cloud上傳壅塞、短Deadline、突發、嚴重低估與CPU/傳輸重疊。以下列非強制prefix任務；固定prefix只用於建立相同背景負載。Oracle僅知道當前與既有任務的真實工作量，不知道未來到達，也不是MARPLE MILP或保證最優上界。

|情境|策略|task|Local估計|Edge估計|Cloud估計|選擇|實際延遲|Deadline達成|
|---|---|---|---|---|---|---|---|---|
|A_local|latency_aware|0|600.000|9328.000|18331.000|local|480.000|True|
|A_local|latency_aware_v2|0|600.000|9328.000|18331.000|local|480.000|True|
|A_local|oracle_reference|0|480.000|9288.000|18316.000|local|480.000|True|
|B_edge|latency_aware|0|600.000|112.128|10203.000|edge|92.128|True|
|B_edge|latency_aware_v2|0|600.000|112.128|10203.000|edge|92.128|True|
|B_edge|oracle_reference|0|480.000|92.128|10188.000|edge|92.128|True|
|C_cloud|latency_aware|0|600.000|431.600|40.128|cloud|34.128|True|
|C_cloud|latency_aware_v2|0|600.000|431.600|40.128|cloud|34.128|True|
|C_cloud|oracle_reference|0|480.000|371.600|34.128|cloud|34.128|True|
|edge_cpu_backlog|latency_aware|1|600.000|2277.800|322.782|cloud|307.782|True|
|edge_cpu_backlog|latency_aware_v2|1|600.000|2201.133|322.782|cloud|307.782|True|
|edge_cpu_backlog|oracle_reference|1|480.000|2161.133|307.782|cloud|307.782|True|
|cloud_link_backlog|latency_aware|1|600.000|287.733|1115.055|edge|247.733|True|
|cloud_link_backlog|latency_aware_v2|1|600.000|287.733|990.055|edge|247.733|True|
|cloud_link_backlog|oracle_reference|1|480.000|247.733|975.055|edge|247.733|True|
|short_deadline|latency_aware|0|600.000|112.128|10203.000|edge|92.128|True|
|short_deadline|latency_aware_v2|0|600.000|112.128|10203.000|edge|92.128|True|
|short_deadline|oracle_reference|0|480.000|92.128|10188.000|edge|92.128|True|
|burst|latency_aware|0|600.000|227.733|191.873|cloud|176.873|True|
|burst|latency_aware|1|600.000|227.733|266.873|edge|187.733|True|
|burst|latency_aware|2|600.000|427.733|266.873|cloud|236.873|True|
|burst|latency_aware|3|600.000|427.733|341.873|cloud|296.873|True|
|burst|latency_aware|4|600.000|427.733|416.873|cloud|356.873|True|
|burst|latency_aware|5|600.000|427.733|491.873|edge|347.733|True|
|burst|latency_aware_v2|0|600.000|227.733|191.873|cloud|176.873|True|
|burst|latency_aware_v2|1|600.000|227.733|202.327|cloud|236.873|True|
|burst|latency_aware_v2|2|600.000|227.733|277.327|edge|187.733|True|
|burst|latency_aware_v2|3|600.000|411.067|277.327|cloud|296.873|True|
|burst|latency_aware_v2|4|600.000|411.067|352.327|cloud|356.873|True|
|burst|latency_aware_v2|5|600.000|411.067|427.327|edge|347.733|True|
|burst|oracle_reference|0|480.000|187.733|176.873|cloud|176.873|True|
|burst|oracle_reference|1|480.000|187.733|176.873|cloud|236.873|True|
|burst|oracle_reference|2|480.000|187.733|232.327|edge|187.733|True|
|burst|oracle_reference|3|480.000|331.067|232.327|cloud|296.873|True|
|burst|oracle_reference|4|480.000|331.067|292.327|cloud|356.873|True|
|burst|oracle_reference|5|480.000|331.067|352.327|edge|347.733|True|
|large_underestimate|latency_aware|0|100.000|121.067|260.282|local|6000.000|False|
|large_underestimate|latency_aware_v2|0|100.000|121.067|260.282|local|6000.000|False|
|large_underestimate|oracle_reference|0|6000.000|2087.733|997.782|cloud|997.782|True|
|cpu_transfer_overlap|latency_aware|1|600.000|481.700|406.280|cloud|406.280|True|
|cpu_transfer_overlap|latency_aware_v2|1|600.000|381.700|406.280|edge|381.700|True|
|cpu_transfer_overlap|oracle_reference|1|600.000|381.700|406.280|edge|381.700|True|

重疊案例：原版選Cloud406.28ms；V2選Edge381.70ms。嚴重低估案例：兩者皆選Local而耗6000ms；workload-oracle選Cloud997.782ms。這顯示改善估算仍無法修復未知工作量的巨大預測偏差。

## 各情境正式端到端差異

每格3種子，每trial6個同一測試Profile抽樣圖片；正值Δ為V2較慢，沒有跨不同環境/負載混成單一最佳排名。完整mean/P95、Deadline、CPU/傳輸/決策等待與分配見matrix-summary.csv及matrix-aggregate.csv。

|資料集|環境|負載|估計器|V1均值|V2均值|Δ ms|Deadline V1→V2|
|---|---|---|---|---|---|---|---|
|lfw|reference|low|median|160.062|160.076|0.014|100.00%→100.00%|
|lfw|reference|low|ridge_log-10.0|160.077|160.118|0.041|100.00%→100.00%|
|lfw|reference|medium|median|160.073|160.086|0.013|100.00%→100.00%|
|lfw|reference|medium|ridge_log-10.0|160.091|160.106|0.014|100.00%→100.00%|
|lfw|reference|high|median|188.723|197.429|8.706|100.00%→100.00%|
|lfw|reference|high|ridge_log-10.0|188.739|197.435|8.696|100.00%→100.00%|
|lfw|network_constrained|low|median|278.430|278.447|0.017|100.00%→100.00%|
|lfw|network_constrained|low|ridge_log-10.0|278.455|278.466|0.012|100.00%→100.00%|
|lfw|network_constrained|medium|median|278.427|278.443|0.017|100.00%→100.00%|
|lfw|network_constrained|medium|ridge_log-10.0|278.455|278.463|0.008|100.00%→100.00%|
|lfw|network_constrained|high|median|397.329|419.635|22.306|100.00%→100.00%|
|lfw|network_constrained|high|ridge_log-10.0|397.351|419.662|22.311|100.00%→100.00%|
|lfw|fast_compute|low|median|96.283|96.286|0.004|100.00%→100.00%|
|lfw|fast_compute|low|ridge_log-10.0|96.320|96.325|0.005|100.00%→100.00%|
|lfw|fast_compute|medium|median|96.282|96.292|0.010|100.00%→100.00%|
|lfw|fast_compute|medium|ridge_log-10.0|96.314|96.313|-0.001|100.00%→100.00%|
|lfw|fast_compute|high|median|127.186|122.887|-4.299|100.00%→100.00%|
|lfw|fast_compute|high|ridge_log-10.0|127.234|122.909|-4.325|100.00%→100.00%|
|wider|reference|low|median|232.121|232.130|0.008|100.00%→100.00%|
|wider|reference|low|ridge_log-10.0|224.113|224.126|0.013|100.00%→100.00%|
|wider|reference|medium|median|241.485|241.494|0.009|100.00%→100.00%|
|wider|reference|medium|ridge_log-10.0|232.671|232.698|0.028|100.00%→100.00%|
|wider|reference|high|median|384.775|352.767|-32.008|94.44%→100.00%|
|wider|reference|high|ridge_log-10.0|348.724|357.212|8.488|100.00%→100.00%|
|wider|network_constrained|low|median|508.756|508.771|0.015|88.89%→88.89%|
|wider|network_constrained|low|ridge_log-10.0|508.511|508.528|0.017|88.89%→88.89%|
|wider|network_constrained|medium|median|858.191|772.819|-85.372|83.33%→66.67%|
|wider|network_constrained|medium|ridge_log-10.0|541.836|682.602|140.766|100.00%→83.33%|
|wider|network_constrained|high|median|837.746|874.919|37.174|83.33%→61.11%|
|wider|network_constrained|high|ridge_log-10.0|728.201|739.573|11.372|72.22%→72.22%|
|wider|fast_compute|low|median|170.808|170.829|0.021|100.00%→100.00%|
|wider|fast_compute|low|ridge_log-10.0|148.482|148.510|0.028|100.00%→100.00%|
|wider|fast_compute|medium|median|212.673|212.686|0.013|100.00%→100.00%|
|wider|fast_compute|medium|ridge_log-10.0|148.478|148.528|0.050|100.00%→100.00%|
|wider|fast_compute|high|median|217.707|229.641|11.934|100.00%→100.00%|
|wider|fast_compute|high|ridge_log-10.0|208.515|197.853|-10.663|100.00%→100.00%|

36個分開條件格（2估計器×2資料集×3環境×3負載），以1ms作實務差異註記：{'within_1ms': 22, 'regressed': 9, 'improved': 5}。這是條件格數，不是將不同情境延遲混平均；所有小差異仍完整列出，不因開銷抖動宣稱普遍優勢。

## 剩餘限制

聚合c把尚在傳輸的承諾工作當成可服務需求，沒有每個先前任務的預估到CPU時間；可能低估未來的CPU空轉或累積，亦可能保守估計排隊。既有download backlog並不包含尚未完成運算的未來回傳。候選延遲只是估計，不是排程真值。短Deadline/爆量下可退化，沒有修改不利測試或以結果校正輸出。
程式latency_v2.py；13項新後端測試（含保存/資料隔離/成本）、paper_cases.py與run_latency_v2_cases.py可重現；原事件正確性測試仍通過。

## 原文核對與採用範圍

- [論文A原文](https://openaccess.thecvf.com/content/ICCV2023W/RCV/papers/Biswas_Characterizing_Face_Recognition_for_Resource_Efficient_Deployment_on_Edge_ICCVW_2023_paper.pdf)：§2.1.2的預熱/分離量測；§2.2 Eq(1)-(2)用架構與參數數量預測設備throughput，§3.1討論解析度；其量測不含偵測，本專案為完整偵測與辨識管線。本文僅借鏡實測與可解釋校準，不把該式宣稱為逐圖InsightFace時間預測的重現。
- [LEAOT原文](https://thesai.org/Downloads/Volume17No8/Paper_77-LEAOT_Load_Deadline_Latency.pdf)：§III-B Eq(2)-(6)為虛擬工作、queue/speed、傳輸與完成時間；§III-C Eq(9)為相對Deadline超時壓力。未重現Eq(7)-(12)的能量/基礎設施加權分數，也未在固定bandwidth模型中虛構EWMA改善。
- [MARPLE出版社頁](https://www.sciencedirect.com/science/article/abs/pii/S1569190X26000419)：可取得的§5.1/5.2內容描述歷史估計與低開銷決策，作成本評估動機；直接全文請求403，作者稿封存至2027。沒有聲稱重現其AoK/MILP或完整演算法。
- [三層人臉卸載論文D](https://onlinelibrary.wiley.com/doi/abs/10.1002/nem.2146)：僅取得出版社摘要，全文403。僅作三層架構背景，不編造方法章節/公式，不實作其DRL。
A/B原文已下載、抽取並視覺核對公式頁；存取限制記錄於paper-access.json。本文所有V2都是paper-inspired，並非論文完整重現。

額外獨立核對：9情境×3策略共27次run/51任務，使用既有acceptance_reference離線三階段FCFS計算，不匯入估計公式；CPU與上下行日曆容量、階段/終止時間、queue面積皆通過，最大誤差6.04e-14ms。逐筆參考與資源日曆見latency-controlled.json。
