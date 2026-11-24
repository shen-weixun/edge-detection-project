# SimPy 49D：十策略共同驗收與分層比較

比較的 DQN／DDQN 權重為原演算法在正式 SimPy 重新訓練的版本。組員的 49 維原型可以獨立推論，也可經 Adapter 派送任務，但其 heapq 訓練有先驗觀測洩漏，因此原權重不列入正式性能表。原七維模型仍 BLOCKED。Laya Original 與 Laya V2 使用真實模型；既有 Latency-aware 和 V2、Load-threshold、Local／Edge／Cloud-only 共六個對照。

|驗收狀態|判定及證據|
|---|---|
|49 維原權重可載入|PASS：5 項原測試、4,000 步數值重現、獨立 Q 值及可用遮罩 fixture|
|49 維模型可接正式 SimPy|PASS：原型各 3 任務的 smoke、正式 `IndexPolicy`／`run_policy` 路徑、88 項後端測試|
|正式 SimPy 訓練完成|PASS：兩模型各三訓練種子、6 個 checkpoint；完成 reward、loss、SHA 及選模證據|
|未參與訓練的測試圖驗證|PASS：Pilot 用凍結 testing 的 10 張／資料集；正式擴充排除這 10 張，另用 seed 23／37 取樣|
|十策略公平比較|PASS（小型正式分層設計）：48 組條件／種子、480 策略執行、2,400 任務；480 次新 Laya 真實決策，無 fallback／replay／截斷|

Pilot 24 情境 × 10 策略 = 240 次執行、2,400 任務。每個策略使用同一批凍結 10 圖、seed 11、相同到達時程；Laya 兩策略使用先前已完成且輸入完全一致的完整執行，480 筆真實決策逐筆對帳。這不是將歷史答案 replay 到新狀態；所有 Laya 虛擬事件和其實測 wall-time 都來自同一份原執行。本輪 Pilot 追加 0 次 Laya 呼叫。Pilot 的獨立 FCFS 參考及延遲加總最大誤差均為 3.638e-12 ms；正式比較為 1.819e-12 ms。兩階段的完整決策稽核均確認每種 AI 策略 240 筆有效決策。

正式擴充按 LFW／WIDER FACE → Low／Medium／High → Local／Edge／Cloud 優勢及 Reference 分開，每情境 seed 23、37，每種子 5 張共用圖。固定 1,000 ms Deadline、Realistic、complete_all、相同節點／網路與 Median，全部由新 SimPy instance 執行。CPU 用參考裝置實測工作量除以節點速度；網路為獨立上下行鏈路（情境配置照原 Pilot），真實策略 wall-time 和單一決策資源的排隊時間計入。決策與 Laya worker 耗時為本機實測，CPU、網路、排隊及總延遲為 SimPy。各 seed 逐策略 CSV 保留全部欄位；分層 CSV 的 P95 是該情境合併 10 筆任務後重新求 nearest-rank，在 5 或 10 筆下等於最大值。兩種子的結果僅代表小型課堂比較，不能據此估計部署 SLA、顯著性或跨情境總排名。

負載名稱以既有 Pilot 的 Edge reference offered rho 0.3／0.9／1.5 定義到達間隔。正式 holdout 沿用這些間隔，實際每個小子集的 offered load 不一定恰為該比率。兩個種子的五張圖互不重疊，每資料集共 10 張新測試圖；同一批圖跨負載／網路重複配對。同一情境內才合併兩個種子。資料及預測器來源與 checkpoint 可查 `study.json` 和 `clean-validation/selection.json`。

兩個具體結果（每格是該情境兩個種子的 10 筆任務，完整數據與圖表見分層報告）：

|情境|策略|平均延遲 ms|P95 ms|Deadline|平均決策 ms|平均決策排隊 ms|Local / Edge / Cloud|
|---|---|---:|---:|---:|---:|---:|---|
|LFW / Low / Reference|Latency-aware|161.30|178.26|100%|0.017|0.00|0% / 0% / 100%|
|LFW / Low / Reference|DQN|173.92|219.98|100%|0.349|0.00|0% / 100% / 0%|
|LFW / Low / Reference|DDQN|173.82|219.97|100%|0.248|0.00|0% / 100% / 0%|
|LFW / Low / Reference|Laya Original|4,008.44|7,023.15|0%|1,747.72|2,092.18|0% / 80% / 20%|
|LFW / Low / Reference|Laya V2|7,610.04|12,131.40|0%|2,838.86|4,482.23|40% / 60% / 0%|
|WIDER / High / Local 優勢|Latency-aware|3,313.19|8,882.26|20%|0.016|0.00|100% / 0% / 0%|
|WIDER / High / Local 優勢|DQN|4,119.09|5,684.14|0%|0.403|0.00|0% / 100% / 0%|
|WIDER / High / Local 優勢|DDQN|3,742.03|5,407.08|0%|0.294|0.00|0% / 70% / 30%|

在 WIDER / High / Local 優勢，兩個新模型的 P95 低於 Latency-aware，但平均延遲較高且沒有任務達成 Deadline；只看一項指標會得出不同結論。Laya 在本次 48 組條件／種子的兩版 Deadline 達成率均為 0%，決策與決策排隊在上述 LFW 範例占主要延遲。這不等於原始節點選擇每次都錯，也不表示其他服務延遲或並行度下會得到相同結果。

|交付|內容|
|---|---|
|Pilot `STRATIFIED.md`、`comparison.csv`、`stratified.csv/json`|24 情境 × 10 策略、逐情境圖表|
|正式 `STRATIFIED.md`、`comparison.csv`、`stratified.csv/json`|每情境合併結果及逐種子結果，獨立圖表|
|`pilot/raw/`、`formal/raw/`|任務、事件、節點統計、各階段延遲、RL raw/normalized/Q/action|
|舊 `frozen-profiles/ai-comparison/raw/model-audit.jsonl`、新 `formal/laya-audit.json`|Laya 實際輸入、原始選擇、信心、模型、worker wall-time，audit_id 對應 SimPy 任務|
|`*/independent-validation.json`、`*/policy-evidence.json`|獨立計算 P95、Deadline、CPU／頻寬 FCFS、時間守恆與輸入；驗證 RL Q/action 和 Laya 紀錄|
|`evidence/*.log`|`unittest`、原包重現、正式訓練／Pilot／Formal 執行、校驗紀錄|

以下指令以專案根目錄及現有 Compose backend 為前提。交付包的 `frozen-profiles` 含可重現所需的量測 CSV、估計器與既有 Pilot 完整 Laya 執行，應放到隔離重現 workspace 的 `profiles`；組員 ZIP 解壓至新的暫存目錄。按順序跑；正式重跑會產生新的真實 Laya 呼叫及 wall-time，核對已交付資料不需要重新推論。使用新的輸出路徑，保留本輪封存。

```powershell
docker compose exec -T backend python -m unittest discover -s tests -v
# 現行腳本使用 training-only 時程選模。將 scripts 下 runner 複製到 /app/scripts，
# 將解壓根目錄 SimPy49_DQN_DDQN_New 複製到容器 /tmp/agents49-member/source。
foreach ($stage in 'prototype','train','pilot','formal') {
    docker compose exec -T -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=1 backend python -u /app/scripts/agents49_experiment.py $stage --output /profiles/agents49-reproduce --member /tmp/agents49-member/source --archive /profiles/ai-comparison
    if ($LASTEXITCODE -ne 0) { break }
}
# 離線證據校驗：實際執行版及重算 checkpoint 的檔案隨包保存。
python scripts/agents49_evidence.py pilot profiles/agents49 profiles
python scripts/agents49_evidence.py formal profiles/agents49 profiles
docker compose exec -T backend python /app/scripts/agents49_report.py pilot /profiles/agents49
docker compose exec -T backend python /app/scripts/agents49_report.py formal /profiles/agents49
```

若正在重現修正前的已封存工作樹輸出，需用 evidence 內的實際執行版 runner 加 `agents49_revalidate.py` 得到 `clean-validation`。使用現行 runner 執行新實驗時，預設已用正確驗證時程；不要混用不同版本的 `study.json`。封存輸出分層圖、逐種子 CSV 及原始 JSON 留在 `profiles/agents49` 和交付包。

結果的適用範圍是本專題的簡化 SimPy 與當次實測決策服務。Laya 是否找到最低成本節點與是否完成整合是不同判定；資料不能證明它是可靠的數值最佳化器。模型原型、前端、HTTP 策略列表和歷史資料保留。

