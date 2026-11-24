# SimPy 最終驗收報告

日期：2026-11-04（Asia/Taipei）。驗收前 Git 為 `0ef365b`，初始工作目錄乾淨。先前四份報告、九組實驗、資料集、資料庫與模型快取均保留。

本次修正與驗證實作提交：`877d653`；報告與進度另行提交。

## 最終判斷

**SimPy 在已宣告的單核心、FCFS、非搶先、串列鏈路模型下有條件 PASS，可進入單學期課堂專題實驗。Latency-aware 三個明顯有利情境均通過。Laya 的排列不變性與成本敏感性 FAIL；不得把 Laya 當成已可靠學會卸載成本的策略。**
工作量估計的校準/測試隔離通過，但 LFW 歷史中位數對 WIDER 的誤差很大。可用來研究「預測有誤差時的卸載」，不能宣稱準確預測任意人臉工作負載。此判斷依手算、獨立參考模型及實際模型輸出，不以測試數量代替架構證據。

## 驗收總表

證據根目錄為 `work/final-acceptance/`；交付包中同名證據另附。PASS只涵蓋表列範圍。

|測試項目|驗證方法／預期|實際結果|判定|證據／相關程式|限制|
|---|---|---|---|---|---|
|1. 時間非負與順序|逐筆arrival≤CPU start≤CPU finish≤terminal，階段事件時間非遞減|518筆受控/實測結果符合；舊52項含丟棄邊界也通過|PASS|results/core-checks.json；tests/acceptance_reference.py:check_run；simulator._process|主驗收reference為complete_all、零虛擬決策成本|
|2. 時間守恆|五元件相加等於terminal-arrival|518筆符合，並與獨立FCFS計算最大差3.2401e-12 ms；真實Laya序列3筆亦符合|PASS|core-summary.json；laya-serial-decision-results.json；test_simpy_validation.py|容差1e-7 ms；不以改寫統計湊總和|
|3. CPU/網路容量|CPU區間不重疊；序列鏈路容量1，shared與independent分開驗證|每筆CPU起訖、完成及network總時間吻合獨立排程；資源清空；共享鏈路明顯產生競爭|PASS|network-contention-details.json；acceptance_reference.reference/check_run；Simulator資源|非連續公平分頻，不模擬實體封包|
|4. 確定性重現|固定資料/seed/config/策略、決策計費0，重播事件結果一致|15組實測負載各重播一次，逐欄相同；只排除實測decision_wall_ms|PASS|run_final_acceptance.py；test_deterministic_replay_ignores_only_wall_measurement|不保證wall-clock微秒成本重現|
|5. 無遺失/重複/共享狀態|輸入/輸出數及task_id唯一；每次新Environment與資源|全部518筆唯一終止；64項測試含重置、drop釋放與RL reset|PASS|check_run；test_simpy_validation.py；test_rl.py|不含程式異常中止後復原協定|
|6. 決策資訊一致|所有策略只收DecisionTask與當前SystemState|真實workload/face_count任意改動不影響當前DTO；Laya原始輸入亦無這些標籤|PASS|test_target_true_work_and_faces_do_not_change_current_observation；models.DecisionTask；laya_client|Python呼叫端可自行寫錯估計值；正式experiment會覆寫為校準估計|
|7. 校準/測試隔離|拒絕同來源別名；核對目前檔案內容SHA256；改測試標籤不改預測|原guard可繞過已修正；4組實際比較路徑及內容重疊皆0|PASS|split-evidence.json；test_acceptance_regressions.py；workload.source_identity/calibration_estimate；rl.EpisodeSplit|生產guard不自動查不同路徑的同內容/硬連結，新資料須另去重|
|8. 三個有利情境|事先獨立手算最小估計值；實際Latency-aware應選L/E/C|A→Local、B→Edge、C→Cloud；所有9個固定候選均吻合手算|PASS|controlled-scenarios.csv/json；test_final_acceptance.py|手算受控案例不代表多任務全域最優|
|9. 低中高負載|固定單節點超載時Lindley等待累積，低負載CPU等待0|同LFW30/5策略/3負載共450筆符合獨立FCFS；固定單節點高負載逐筆等待非遞減|PASS|measured-load.csv/details.json；test_lindley_overload_growth_and_queue_integral|中負載以Edge為基準，不表示三節點皆同利用率|
|10. RTT/頻寬/算力|單任務固定節點，RTT↑與頻寬↓不可降低網路耗時；speed↑不可增CPU耗時|24個參數格全部吻合公式；Latency-aware另24筆符合估計最小值且隨環境改選|PASS|sensitivity.csv；single_cost；test_single_remote_parameter_monotonicity_and_arithmetic|固定RTT/BW/speed，無動態干擾|
|Laya排列不變性|同語意狀態6排列都應選相同最佳節點|三情境均依排列改變選擇|FAIL|laya-permutation-results.json；laya-raw-audit.jsonl|模型限制，未用規則代替|
|Laya成本敏感性|三情境所有排列/重複應選明顯最低成本節點|A 6/12、B 2/12、C 0/12；合計8/36|FAIL|laya-summary.json|不是SimPy事件錯誤|
|Laya相同輸入重複|完全相同模型狀態輸入兩次，選擇一致|18組排列各2次，18/18對一致|PASS|laya-permutation-results.json|僅兩次、當前CPU/checkpoint，不宣稱所有執行環境都一致|
|Laya原始輸出/序列決策成本|raw choice=response=SimPy choice；決策等待等於前序決策成本和|39/39核對一致，零fallback/截斷；序列3筆時間守恆|PASS|laya-raw-audit.jsonl；laya-serial-decision-results.json|39=36排列呼叫+3序列呼叫；預熱另1次排除|
|遠端硬體/多核心/能耗/動態網路|實體驗證或不同模型測試|本次未實作，也未宣稱有驗證|NOT TESTED|SIMPY_ARCHITECTURE_AUDIT.md|這些不是現行簡化模型能力|

## 三個節點有利情境與獨立手算

共同輸入：1 MB、1000×1000、設定回傳16 KB；決策估計600 ms，內部實際工作量480 ms。600為獨立受控歷史先驗，沒有用待測480來預測自己。所有策略使用同一Realistic DTO，初始三節點均空。Local相對算力固定1；B的Local「較慢」是相對Edge的6倍速度而言。
公式（十進位單位、全為ms）：上傳=8000×MB/Mbps；下載=8×KB/Mbps；遠端network=RTT+上傳+下載；CPU=工作量/speed。單任務無等待，總和=network+CPU。決策計費0以隔離事件模型；真實決策成本另驗。

|情境|節點|speed / RTT ms / Mbps|估計總延遲|手算實際總延遲|SimPy實際|網路/CPU排隊/CPU|實際選擇|判定|
|---|---|---|---:|---:|---:|---|---|---|
|A_local|local|1/0/1000|600.000|480.000|480.000|0.000/0.000/480.000|✓|PASS|
|A_local|edge|3/1000/1|9328.000|9288.000|9288.000|9128.000/0.000/160.000||PASS|
|A_local|cloud|8/2000/0.5|18331.000|18316.000|18316.000|18256.000/0.000/60.000||PASS|
|B_edge|local|1/0/1000|600.000|480.000|480.000|0.000/0.000/480.000||PASS|
|B_edge|edge|6/4/1000|112.128|92.128|92.128|12.128/0.000/80.000|✓|PASS|
|B_edge|cloud|8/2000/1|10203.000|10188.000|10188.000|10128.000/0.000/60.000||PASS|
|C_cloud|local|1/0/1000|600.000|480.000|480.000|0.000/0.000/480.000||PASS|
|C_cloud|edge|2/30/80|431.600|371.600|371.600|131.600/0.000/240.000||PASS|
|C_cloud|cloud|20/2/1000|40.128|34.128|34.128|10.128/0.000/24.000|✓|PASS|

例如B/Edge：估計=600/6+4+8+0.128=112.128；實際=480/6+4+8+0.128=92.128。估計值和真實服務時間不同是刻意的資訊隔離，不是時間不守恆。

## 同一實測LFW30的低、中、高負載

Profile `6ddb0a187ba44065a5beaf0450ad259e`，seed=42，Deadline=1000 ms；原校準 `a057ded0f08c4837beff2ffd02f390ee`。算力1/3/8、RTT0/20/100、Mbps1000/120/55；獨立網路、complete_all。所有15組共用相同圖片順序、實際推論真值及估計；影像批次hash見measured-manifest.json。
低：間隔1023.917 ms，大於所有單圖本機CPU服務時間；中：143.955 ms=平均本機工作431.864/Edge speed3，Edge名義ρ=1；高：13.496 ms，連Cloud名義ρ亦為4。Local在中負載本來就超載，因此不能把三節點的負載級別混稱相同ρ。ρ的定義是平均服務時間/到達間隔，不是表中的有限批次利用率。

|負載/策略|平均ms|P95 ms|CPU等待ms|上/下載等待ms（ref）|Deadline達成率|
|---|---:|---:|---:|---|---:|
|low/local_only|431.863|574.537|0.000|0.000/0.000|100.00%|
|low/edge_only|165.958|213.481|0.000|0.000/0.000|100.00%|
|low/cloud_only|158.353|176.111|0.000|0.000/0.000|100.00%|
|low/load_threshold|165.958|213.481|0.000|0.000/0.000|100.00%|
|low/latency_aware|158.353|176.111|0.000|0.000/0.000|100.00%|
|medium/local_only|4705.020|8558.031|4273.157|0.000/0.000|10.00%|
|medium/edge_only|243.636|353.640|77.678|0.000/0.000|100.00%|
|medium/cloud_only|158.353|176.111|0.000|0.000/0.000|100.00%|
|medium/load_threshold|243.636|353.640|77.678|0.000/0.000|100.00%|
|medium/latency_aware|158.353|176.111|0.000|0.000/0.000|100.00%|
|high/local_only|6596.672|12210.876|6164.809|0.000/0.000|6.67%|
|high/edge_only|2090.242|3840.181|1924.284|0.000/0.000|20.00%|
|high/cloud_only|757.305|1299.662|598.952|0.000/0.000|70.00%|
|high/load_threshold|604.729|1088.434|446.064|0.000/0.000|86.67%|
|high/latency_aware|489.933|877.224|303.234|0.000/0.000|100.00%|

|負載/策略|時間加權CPU等待數 L/E/C|CPU利用率 L/E/C|
|---|---|---|
|low/local_only|0.000/0.000/0.000|43.10%/0.00%/0.00%|
|low/edge_only|0.000/0.000/0.000|0.00%/14.47%/0.00%|
|low/cloud_only|0.000/0.000/0.000|0.00%/0.00%/5.43%|
|low/load_threshold|0.000/0.000/0.000|0.00%/14.47%/0.00%|
|low/latency_aware|0.000/0.000/0.000|0.00%/0.00%/5.43%|
|medium/local_only|9.895/0.000/0.000|100.00%/0.00%/0.00%|
|medium/edge_only|0.000/0.531/0.000|0.00%/98.38%/0.00%|
|medium/cloud_only|0.000/0.000/0.000|0.00%/0.00%/37.45%|
|medium/load_threshold|0.000/0.531/0.000|0.00%/98.38%/0.00%|
|medium/latency_aware|0.000/0.000/0.000|0.00%/0.00%/37.45%|
|high/local_only|14.275/0.000/0.000|100.00%/0.00%/0.00%|
|high/edge_only|0.000/13.300/0.000|0.00%/99.50%/0.00%|
|high/cloud_only|0.000/0.000/10.426|0.00%/0.00%/93.97%|
|high/load_threshold|0.000/0.568/8.281|0.00%/44.52%/90.40%|
|high/latency_aware|0.429/2.103/4.716|89.25%/96.87%/81.55%|

觀察與解釋：
- 低負載固定三策略CPU等待皆0；中負載Local平均等待4273.157、Edge 77.678、Cloud 0；高負載依序6164.809、1924.284、598.952 ms，符合過載積累。
- 高負載固定單節點的每筆等待非遞減；這個強條件在本批每圖服務時間均大於間隔時適用。一般變動服務時間在ρ接近1時可以暫時消退，不能強迫所有情況等待單調增加。
- 高負載Latency-aware分散到三節點，平均489.933、P95 877.224 ms；有限批次Deadline全達標不代表ρ穩定或全域最優。
- 本批LFW圖片小，上/下載排隊皆0是合理現象，不是漏算；另用1 MB同時到達案例刻意壓滿鏈路驗證。表中ref傳輸等待由獨立資源日曆算出，未冒充既有API本來就有的細分量測欄位。SimPy所有CPU起訖/終止/網路總時間均已逐筆吻合該模型。
- 時間加權等待數獨立核對為 ΣCPU等待時間 / 最後終止時間；CPU利用率為Σ實際服務時間/同一期間（包含頭尾閒置與回傳），因此可以低於輸入名義ρ。

## 網路與算力敏感度

同一受控圖片，單次只改表列節點的一個參數；其餘使用DEFAULT_NODES。固定該節點執行以排除策略改選的干擾，另獨立記錄Latency-aware在同環境的選擇。

|節點|變動參數|值|手算/SimPy總ms|網路ms|CPU ms|Latency-aware選擇|判定|
|---|---|---:|---|---:|---:|---|---|
|edge|rtt_ms|0|227.733/227.733|67.733|160.000|edge|PASS|
|edge|rtt_ms|20|247.733/247.733|87.733|160.000|edge|PASS|
|edge|rtt_ms|200|427.733/427.733|267.733|160.000|cloud|PASS|
|edge|rtt_ms|1000|1227.733/1227.733|1067.733|160.000|cloud|PASS|
|edge|bandwidth_mbps|1|8308.000/8308.000|8148.000|160.000|cloud|PASS|
|edge|bandwidth_mbps|8|1196.000/1196.000|1036.000|160.000|cloud|PASS|
|edge|bandwidth_mbps|80|281.600/281.600|121.600|160.000|edge|PASS|
|edge|bandwidth_mbps|1000|188.128/188.128|28.128|160.000|edge|PASS|
|edge|speed|1|567.733/567.733|87.733|480.000|cloud|PASS|
|edge|speed|3|247.733/247.733|87.733|160.000|edge|PASS|
|edge|speed|8|147.733/147.733|87.733|60.000|edge|PASS|
|edge|speed|20|111.733/111.733|87.733|24.000|edge|PASS|
|cloud|rtt_ms|0|207.782/207.782|147.782|60.000|cloud|PASS|
|cloud|rtt_ms|20|227.782/227.782|167.782|60.000|cloud|PASS|
|cloud|rtt_ms|200|407.782/407.782|347.782|60.000|edge|PASS|
|cloud|rtt_ms|1000|1207.782/1207.782|1147.782|60.000|edge|PASS|
|cloud|bandwidth_mbps|1|8288.000/8288.000|8228.000|60.000|edge|PASS|
|cloud|bandwidth_mbps|8|1176.000/1176.000|1116.000|60.000|edge|PASS|
|cloud|bandwidth_mbps|80|261.600/261.600|201.600|60.000|cloud|PASS|
|cloud|bandwidth_mbps|1000|168.128/168.128|108.128|60.000|cloud|PASS|
|cloud|speed|1|727.782/727.782|247.782|480.000|edge|PASS|
|cloud|speed|3|407.782/407.782|247.782|160.000|edge|PASS|
|cloud|speed|8|307.782/307.782|247.782|60.000|edge|PASS|
|cloud|speed|20|271.782/271.782|247.782|24.000|cloud|PASS|

共享與獨立資源手算：四個1 MB任務同到達，交替送Edge/Cloud；兩節點speed2、RTT20、80 Mbps，單上傳100 ms、CPU240 ms、下載1.6 ms。獨立模式同時各用一條上傳資源；共享模式上傳序列起點10/110/210/310 ms。上下載資源彼此獨立，既有及新增full-duplex測試也通過。

|模式|task|節點|上傳開始→結束（ref）|上傳等待（ref）|CPU開始→結束（SimPy）|總延遲ms|
|---|---:|---|---|---:|---|---:|
|independent|0|edge|10.000→110.000|0.000|110.000→350.000|361.600|
|independent|1|cloud|10.000→110.000|0.000|110.000→350.000|361.600|
|independent|2|edge|110.000→210.000|100.000|350.000→590.000|601.600|
|independent|3|cloud|110.000→210.000|100.000|350.000→590.000|601.600|
|shared|0|edge|10.000→110.000|0.000|110.000→350.000|361.600|
|shared|1|cloud|110.000→210.000|100.000|210.000→450.000|461.600|
|shared|2|edge|210.000→310.000|200.000|350.000→590.000|601.600|
|shared|3|cloud|310.000→410.000|300.000|450.000→690.000|701.600|

獨立參考模型位於 `backend/tests/acceptance_reference.py`，不呼叫Simulator或estimate_latency：先依到達+RTT/2排上傳，再按上傳完成排各CPU，最後按CPU完成+RTT/2排下載。每個資源用FCFS的start=max(ready,previous_finish)遞迴。策略選擇只在模擬完成後餵給此參考；真實工作量不會因此回流決策。此參考涵蓋complete_all與零決策計費；drop與真實決策成本由另列回歸測試驗證。

## 工作量估計誤差與資料隔離

定義error=estimated−actual；MAE=mean(|error|)、RMSE=sqrt(mean(error²))、bias=mean(error)，正偏差為高估。內部 `Task.workload_ms` 就是本表actual_workload_ms；沒有為了改欄位名稱再增加一份互相可能失配的真值。正式策略只能取得DecisionTask.estimated_workload_ms。

|估計器|測試資料|n|估計ms|實際平均ms|MAE ms|RMSE ms|偏差ms|
|---|---|---:|---:|---:|---:|---:|---:|
|production_LFW_historical_median|lfw|30|460.953|431.864|78.906|107.731|29.089|
|production_LFW_historical_median|wider_train|30|460.953|1006.082|567.770|1404.073|-545.129|
|production_LFW_historical_median|wider_val|3|460.953|1199.911|738.958|1234.688|-738.958|
|diagnostic_WIDER_training_median|wider_val|3|519.202|1199.911|705.656|1200.733|-680.709|

- 正式估計器只讀LFW校準30張的歷史推論時間中位數460.953 ms，沒有使用待測圖片真值或人臉數；測試列只用於來源獨立性檢查。把所有測試真值乘100、人臉數改999，估計不變。
- LFW30、WIDER_train30、WIDER_val3對此LFW校準集，及獨立WIDER_train→WIDER_val診斷，共4組比較，正規化路徑重疊與影像內容SHA256重疊皆0。WIDER_train在第一個估計器表列是「預測評估資料」，只有最後一列才充當另一估計器的校準集。
- DecisionTask不含真實workload、face_count、sample_id、source_path或未來完成時間；task_id僅該次任務序號。大小/寬高在推論前可取得；result_size_kb為固定假設16 KB。節點剩餘CPU工作由歷史估計扣除已觀測服務時間，不讀真實排定完成時刻。
- 目前無證據顯示實際Profile洩漏；但找到可繞過原身份guard的改標籤/./別名輸入，已先重現再修正。新guard使用正規化來源路徑，不能靠改dataset標籤取得新身份。
- WIDER長尾明顯：LFW估計用在WIDER_train的RMSE約1404 ms；即使用獨立WIDER訓練中位數預測val3仍有約1201 ms RMSE。誤差是泛化不足，不是資料洩漏。val只有3張，不能用它做模型選擇或宣稱泛化精度。
- 保留原中位數Baseline；本次沒有用驗收測試集調參或新增高維估計器。若課堂正式主張WIDER預測準確，需另留較大的校準/驗證/測試分割並預先選定特徵；現有證據不足以支持此主張。

## Laya獨立驗收

三情境使用上文完全相同的Realistic可觀測資訊；每情境6種nodes陣列順序×2次重複=36真實模型呼叫，另做1次預熱（排除統計）與3筆實際Simulator序列決策。context只用於服務audit，不傳進Router狀態；提示、checkpoint與原規則均未修改。

|情境|最低成本節點|實際選擇分布（12次）|符合最低成本|排列不變|重複一致|平均HTTP wall ms|
|---|---|---|---:|---|---|---:|
|A_local|local|{'cloud': 4, 'edge': 2, 'local': 6}|6/12|FAIL|6/6對|964.307|
|B_edge|edge|{'cloud': 2, 'edge': 2, 'local': 8}|2/12|FAIL|6/6對|1188.965|
|C_cloud|cloud|{'local': 8, 'edge': 4}|0/12|FAIL|6/6對|1165.809|

|情境|節點陣列順序|第一次→第二次選擇|
|---|---|---|
|A_local|local→edge→cloud|cloud → cloud|
|A_local|local→cloud→edge|edge → edge|
|A_local|edge→local→cloud|cloud → cloud|
|A_local|edge→cloud→local|local → local|
|A_local|cloud→local→edge|local → local|
|A_local|cloud→edge→local|local → local|
|B_edge|local→edge→cloud|cloud → cloud|
|B_edge|local→cloud→edge|edge → edge|
|B_edge|edge→local→cloud|local → local|
|B_edge|edge→cloud→local|local → local|
|B_edge|cloud→local→edge|local → local|
|B_edge|cloud→edge→local|local → local|
|C_cloud|local→edge→cloud|local → local|
|C_cloud|local→cloud→edge|edge → edge|
|C_cloud|edge→local→cloud|local → local|
|C_cloud|edge→cloud→local|local → local|
|C_cloud|cloud→local→edge|edge → edge|
|C_cloud|cloud→edge→local|local → local|

以上足以否定目前模型的排列不變性，且C的12次全未選Cloud。不能因同輸入重複一致就稱成本敏感。這是Laya可靠性FAIL，沒有改用Latency-aware代打。沒有輸入截斷（0/36），原始choice/HTTP回傳/SimPy分配39次核對一致，故不能把錯誤選擇歸咎於串接偷換。

|序列任務|選擇|實測決策ms|決策等待ms|CPU排隊ms|總延遲ms|
|---|---|---:|---:|---:|---:|
|0|cloud|1136.994|0.000|0.000|11324.994|
|1|cloud|1376.967|1136.994|0.000|19324.994|
|2|cloud|1253.371|2513.961|0.000|27324.994|

三筆同時到達時，第二筆決策等待等於第一筆決策耗時，第三筆等於前兩筆之和（容差1e-7 ms）。模型wall time含HTTP及服務端鎖等待，不是節點的影像CPU服務；這是目前宣告的單一序列決策器假設。此段明確計入決策成本，與前面的零成本事件模型驗收分開。

## 重現問題、修正範圍與前後證據

1. **等待佇列統計／快照**：立即取得CPU的單任務，原本先寫cpu_wait，造成max_queue=1，應為0。`_Node.state`也可能在同一虛擬時刻的grant與resume之間把已取得CPU的工作列為等待。改以Resource.queue與Resource.count判定等待/占用，max_queue在提出request後從真正等待列更新。沒有改CPU服務時間或事件timeout。
2. **資料分割身份**：原本用(dataset, source_path)當身份，改dataset或使用./別名可以讓同檔案跨分割。`workload.source_identity`正規化相對路徑並忽略dataset標籤，校準與`rl.EpisodeSplit`共用。不能因此宣稱已自動解決不同路徑相同內容或symlink問題；實際驗收另用內容雜湊核對。
3. `scripts/verify_integration.py`新增INTEGRATION_OUTPUT，讓本輪API證據另存、不覆寫舊78項紀錄。其餘修改為測試與驗收腳本。生產程式僅simulator.py/workload.py/rl.py做上述小修；策略成本公式、Laya提示與模型、實測Profile皆未變。

先執行4項新增回歸：3失敗、1既有行為通過（failing-regressions.txt）；修正後全部通過。新舊版本各重播15組同一實測負載（before-after-regression.json），所有分配相同，CPU/網路/總延遲最大差0 ms；低負載等無等待情境的max_queue由1修正0。先前九格結果保留為歷史紀錄，不覆寫或冒稱重新執行。

## 測試指令與真正執行結果

完整指令均從專案根目錄執行。Dockerfile原本不COPY scripts，所以獨立腳本須明確cp；後續重建容器需重做cp。測試用helper已由backend/tests進映像。

```powershell
docker compose -f compose.yaml -f compose.ai.yaml up -d --build
docker compose exec -T backend python -m unittest discover -s tests -v
docker compose exec -T backend mkdir -p /app/scripts
docker compose cp scripts/run_final_acceptance.py backend:/app/scripts/run_final_acceptance.py
docker compose cp scripts/run_laya_acceptance.py backend:/app/scripts/run_laya_acceptance.py
docker compose exec -T backend python /app/scripts/run_final_acceptance.py
docker compose exec -T backend python /app/scripts/run_laya_acceptance.py
docker compose cp backend:/tmp/final-acceptance/. work/final-acceptance/results/
$env:WORKLOAD_PROFILE_ID='6ddb0a187ba44065a5beaf0450ad259e'
$env:CALIBRATION_PROFILE_ID='a057ded0f08c4837beff2ffd02f390ee'
$env:INTEGRATION_OUTPUT='work/final-acceptance/api-integration'
python scripts/verify_integration.py --reuse-profiles
python scripts/build_final_acceptance_report.py
```

- 驗收前52/52通過；新增4項修復回歸+8項受控/參考驗收，最終映像 **64/64通過、0失敗**（final-tests.txt）。
- 核心腳本77次run核對、518筆結果；15組負載另重播，僅wall測量欄位允許變動。所有斷言通過（core-log.txt/core-checks.json）。
- API **78/78通過**，含原人臉偵測、同圖驗證、真實Laya成功與Realistic缺失/重疊校準拒絕；本輪證據api-integration/，未覆寫work/audit/integration/。
- Compose實際建置/啟動成功，PostgreSQL/backend/Laya健康，首頁及模擬器HTTP200；未刪除volume或模型資料。
- Laya可靠性故意獨立判定FAIL，不能將整個驗收報告稱「全部測試通過」。診斷腳本成功完成表示收集到證據，不代表模型可靠性PASS。

新增測試的實際名稱：

|測試函式|判定|檔案|
|---|---|---|
|test_idle_cpu_has_zero_max_waiting_queue|PASS|backend/tests/test_acceptance_regressions.py|
|test_relabelling_same_source_cannot_bypass_calibration_split|PASS|backend/tests/test_acceptance_regressions.py|
|test_relabelling_same_source_cannot_bypass_rl_split|PASS|backend/tests/test_acceptance_regressions.py|
|test_three_simultaneous_jobs_have_two_waiters_not_three|PASS|backend/tests/test_acceptance_regressions.py|
|test_deterministic_replay_ignores_only_wall_measurement|PASS|backend/tests/test_final_acceptance.py|
|test_lindley_overload_growth_and_queue_integral|PASS|backend/tests/test_final_acceptance.py|
|test_scenario_A_local_advantage|PASS|backend/tests/test_final_acceptance.py|
|test_scenario_B_edge_advantage|PASS|backend/tests/test_final_acceptance.py|
|test_scenario_C_cloud_advantage|PASS|backend/tests/test_final_acceptance.py|
|test_shared_capacity_reference_and_full_duplex|PASS|backend/tests/test_final_acceptance.py|
|test_single_remote_parameter_monotonicity_and_arithmetic|PASS|backend/tests/test_final_acceptance.py|
|test_target_true_work_and_faces_do_not_change_current_observation|PASS|backend/tests/test_final_acceptance.py|

## 研究限制與DQN/DDQN前置條件

- 單核心CPU與串列非搶先服務；共享網路是min(路徑Mbps,共用出口Mbps)的單瓶頸近似，並非真實多跳網路或公平分頻。RTT固定且不占頻寬資源，上下載全雙工。
- Edge/Cloud依本機真實工作量線性縮放，沒有實體遠端跑分；圖片讀取/解碼/傳輸失敗/能耗未建模，固定16 KB結果大小。
- 狀態假設即時免費可觀測；Latency-aware將承諾工作與網路積壓相加，是保守啟發式，未精確建模所有流水線重疊；預測偏差可改變策略排名。
- 期限drop是已開始階段完成後才判斷、非搶先丟棄；平均終止延遲包括被丟棄任務，需同時報完成率、丟棄率與Deadline達成率。
- 本批是有限30任務和固定順序，不是穩態佇列估計，也沒有信賴區間。驗收看機制與獨立參考吻合，不宣稱單次排名統計顯著。
- 本次可重現的兩類程式缺陷已修正。**DQN/DDQN開始訓練前必須**：凍結觀測欄位順序/正規化與action 0/1/2；按圖像內容去重並固定訓練/驗證/測試manifest；只用訓練校準估計器與調超參數；明確使用現有延遲回饋/半馬可夫時間間隔與task_id歸屬；正式評估實作select_node並統一計入決策成本，不能把互動訓練思考wall time當服務成本。
- 沒有需要為DQN重新設計SimPy事件引擎的證據；也未訓練或驗證任何DQN/DDQN權重。不能把Laya錯誤標籤當作最佳卸載的監督真值。

## 七項明確回答

1. **事件排程是否正確？** 在已測的宣告模型範圍內PASS：手算、獨立FCFS逐段核對、資源/時間守恆及重播一致；不宣稱未測的所有擴充模型均正確。
2. **網路、CPU、決策與排隊符合假設？** 是；單核心/全雙工序列通道/單決策器/階段邊界期限政策皆明示並有對應證據。瞬間CPU等待快照與最大佇列錯誤已修正。
3. **Latency-aware會合理選擇不同節點？** 是；三個有利情境分別Local/Edge/Cloud，24格敏感度選擇亦吻合獨立估計最低值。這不等於長期負載全域最優。
4. **估計器有資料洩漏？** 現行正式流程及本次4組實際來源/內容隔離未發現洩漏，測試標籤變動不影響預測；原身份guard繞過已修正。新資料的異路徑同內容仍需去重，WIDER誤差不能當洩漏證據。
5. **影響研究結論的限制？** 歷史估計器的分布外偏差、固定線性算力/網路假設、免費即時狀態、啟發式流水線近似、序列決策成本與有限樣本；Laya另外有排列/成本敏感性失敗。
6. **DQN/DDQN前必須修正什麼？** 本次發現的等待統計與資料身份檢查已修；訓練前仍須完成上節列出的固定觀測/action/reward、內容去重及資料/估計器分割契約，不能用驗收測試集調參。
7. **是否達到課堂專題驗收？** 有條件達到，可開始以明示簡化假設比較Baseline與Latency-aware、研究估計誤差；Laya只能作為可靠性未通過的實驗對象，不能宣稱有效AI最佳決策。若研究主張依賴準確WIDER預測或真實遠端效能，現有證據不達該主張的驗收標準。
