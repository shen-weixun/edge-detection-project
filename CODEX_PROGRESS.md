# 本輪最終驗收更新（2026-11-04，Asia/Taipei）

- 本輪驗收起點 `0ef365b`，初始工作目錄乾淨；之前四報告、九格實驗與資料皆保留。
- 發現並先以失敗回歸重現兩類問題：單任務立即取得CPU仍出現max_queue=1；同一來源改dataset標籤/./別名可繞過校準與RL分割guard。4項新增回歸原本3失敗/1通過。
- 最小修正：Resource.queue/count決定等待/占用、真正排入CPU後更新max_queue；正規化來源路徑作身份，校準和EpisodeSplit共用。沒有改服務時間、策略公式、Laya模型/提示或Profile。
- 最終64/64單元測試、78/78本輪API檢查通過。三受控情境A→Local、B→Edge、C→Cloud。
- 獨立FCFS參考核對77次run、518筆結果，最大誤差3.2401e-12 ms。LFW30同圖5策略低中高負載450筆，每組另做確定性重播；網路/算力24格+24次自適應選擇通過。
- 修改前版本0ef365b與修改後重播15組相同負載：節點分配相同、CPU/網路/終止時間差0 ms；低負載max_queue由1改0。
- 4組真實校準/測試比較的來源與內容SHA256重疊皆0，改測試標籤不改估計。LFW MAE78.906/RMSE107.731 ms；LFW先驗→WIDER_train MAE567.770/RMSE1404.073，→WIDER_val3 MAE738.958/RMSE1234.688 ms，需揭露分布外低估。
- Laya真實36次排列/重複+3筆序列成本稽核：39/39原始輸出與實際選擇一致、零fallback/截斷；18/18相同排列重複對一致，但三情境排列不變性全FAIL、成本最低選擇僅8/36。未用規則代替AI。
- 本輪最終判定：SimPy在已宣告假設下有條件PASS，可進入單學期課堂實驗；Laya可靠性FAIL，WIDER準確預測/真實遠端效能不在可支持主張內。完整七項回答見SIMPY_FINAL_ACCEPTANCE.md。
- 證據獨立保存於work/final-acceptance/，API輸出分流至api-integration/，沒有覆寫work/audit/或先前交付outputs/simpy-audit/。
- 最終建置映像已啟動。未刪除資料庫、資料集、模型快取或volume，未做破壞性Git操作。
- Git：本輪修正及驗證實作提交 `877d653`；後續報告/進度另提交，無未提交的其他組員修改。

## 本輪恢復與重現

從原edge-detection-project根目錄：

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

產報表前須保有本輪final-tests.txt及results/before-after-regression.json；這兩項都在交付證據副本中。若重跑單元，將完整輸出另存final-tests.txt；compare_before.py及before-source/保留在證據目錄，可獨立重播基準。不要以診斷腳本exit=0冒稱Laya可靠性通過，應讀laya-summary.json。

本輪無必要工作未完成。未測範圍：真實遠端硬體、網路擾動/能耗/多核心、DQN/DDQN權重訓練、跨瀏覽器完整UI回歸；這些均未宣稱通過。下一步可依報告的DQN資料/觀測/action/reward契約啟動獨立訓練工作。

---

# 前輪歷史進度（以下內容保留，52項與九格結論屬當時版本）

# Codex 執行進度與恢復方式

## 完成狀態

2026-11-04（Asia/Taipei）本次所有可執行階段已完成。網站與AI服務保持運行。

|階段|結果|
|---|---|
|完整閱讀與架構報告|完成；models/simulator/strategies/experiment/workload/API/profiler/Laya/Compose/測試/腳本/前端及實測inference均核對|
|修改前證據|原始Git版本三個P0問題實際重現；九格原始結果完整保留|
|決策資訊權限|Realistic預設，獨立歷史校準；Oracle明示；六策略相同DecisionTask|
|事件與時間驗證|單任務手算、三任務FCFS、非同步到達、重置、元件守恆通過|
|狀態與佇列|承諾/上傳/CPU等待/執行/回傳分離；時間加權與決策時點統計分列|
|網路與Deadline|獨立/共享全雙工序列瓶頸；complete_all/階段邊界drop均有測試|
|公平性與RL|真實成本與消融分開；EpisodeSplit/State/Action/Reward/Next/Done/reset具備測試；無假DQN策略|
|Docker/API/人臉功能|標準與AI覆寫建置成功；78項整合通過；真實偵測、同圖驗證、Laya推論成功|
|九格重跑|原LFW30、3到達間隔×3Deadline×6策略；1620結果、270真實Laya決策|
|全批次稽核|99項情境檢查通過；時間守恆最大誤差7.276e-12 ms；零fallback、零輸入截斷|
|瀏覽器與交付|實測3任務五策略比較完成；修正快取資源混用；四報告與完整CSV/JSON交付|

## Git

- 分支 `feature/measured-workload-integration`；初始工作目錄乾淨，基準 `f8ec3563aada7f574f9264da95314b9a599ee4ef`。
- `6a12688`：模擬器核心、資訊權限與49項測試。
- `71f8647`：最終52項測試、RL資料分割、前端/API參數、健康檢查與可重現報表腳本。
- 最後文件提交見 `git log -1`；只包含本任務報告、進度與測試檔案末尾空白修正。沒有破壞性Git操作，沒有更動其他組員的未提交工作。
- 正式九格執行後只新增RL分割/驗證與前端資源版本，沒有再修改正式實驗使用的Simulator/策略/真實工作負載/Laya提示。

## 實際證據

- 最終52/52單元／事件／RL測試：`work/audit/unit-tests-final.txt`。
- 78/78 API整合：`work/audit/integration/integration-results.json`與`integration-log.txt`。
- 舊九格：`work/audit/before/`；原始另一份仍在此前交付目錄，未覆寫。
- 新九格：本聊天`outputs/simpy-audit/after/`；完整比較在`work/audit/comparison/`並複製至交付目錄。
- 消融18筆：`work/audit/real-six-policy-ablation.json`（包括3次真實Laya）。
- 最終Docker映像建置及健康：`work/audit/build-final.txt`、`health-final.jsonl`。
- 原始三P0重現：`work/audit/baseline-reproduction.json`與`baseline-source/`。
- 原測試Profile `6ddb0a187ba44065a5beaf0450ad259e`；CSV SHA256 `1abfff4bfc55c487d7a6592b6a2a81e04accf38f5708073292e13ab4d6ec3ccc`。
- 獨立校準Profile `a057ded0f08c4837beff2ffd02f390ee`，seed=100，30張/每張3次，與測試來源零重疊；CSV SHA256 `400f621f33fc2977fa198237f4447c88dd13e08360fbd71faecf04081879013b`；中位估計460.952837 ms。
- 第一個新校準seed=20261104與測試重疊1張，因此拒絕用於正式實驗，該量測仍保留，沒有刪除資料。

## 恢復與重現

專案位於 `C:/Users/wubai/Documents/Codex/2026-11-02/https-github-com-shen-weixun-edge/work/edge-detection-project`。

```powershell
docker compose -f compose.yaml -f compose.ai.yaml up -d --build
docker compose exec -T backend python -m unittest discover -s tests -v
$env:WORKLOAD_PROFILE_ID='6ddb0a187ba44065a5beaf0450ad259e'
$env:CALIBRATION_PROFILE_ID='a057ded0f08c4837beff2ffd02f390ee'
python scripts/verify_integration.py --reuse-profiles
# 若要新的一輪九格，指定新輸出目錄，不覆寫已交付證據：
$env:EXPERIMENT_OUTPUT='work/audit/new-grid'
python scripts/run_sensitivity.py
# 對已存在的新九格重建比較表：
python scripts/audit_results.py --before work/audit/before --after $env:EXPERIMENT_OUTPUT --audit profiles/laya_audit/decisions.jsonl --output work/audit/new-comparison
```

`audit_validation_report.py`由最終單元測試log與integration-results.json產生逐項報告。若新增測試，需同步維護預期結果表；不可直接沿用舊的PASS數。

## 剩餘限制（不是本次未完成工作）

- Edge/Cloud仍是假設相對算力及網路，沒有遠端硬體實測。
- drop為非搶先階段邊界政策，不是到Deadline立即取消。
- 歷史估計器是常數中位數，狀態監測假設即時；身份去重未檢查異路徑相同內容。
- DQN/DDQN尚無有效權重或訓練結果；介面測試不能充當學習成效。
- 九格為單次每格，wall-clock成本受主機負載影響；新舊模型定義不同，不可宣稱同條件演算法改善。
- 瀏覽器已驗證一條實測比較流程，非所有瀏覽器尺寸/完整視覺回歸。

禁止刪除volume、資料庫、模型快取或資料集；未執行down -v。
