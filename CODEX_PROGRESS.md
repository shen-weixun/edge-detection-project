# 組員模型審查與AI分層pilot：本輪完成（2026-11-06，Asia/Taipei）

- 起點7a38ef7，Git初始乾淨。第一階段commit caf6894；完整分層pilot/前端與測試commit 19d6501。本輪只新增隔離模型檢查/共同子集runner、分層報表/前端與tests，原SimPy/V1/V2/估計器/RL/Laya等11檔SHA全部未變。
- backend.rar獨立解至work/ai-comparison/incoming，6來源/weights原始SHA與RAR SHA驗證未變，沒有覆蓋production backend、改寫組員訓練或更新權重。
- DQN/DDQN皆真正載入7×32-ReLU×3 NPZ（arr0..3），全部finite、不同數值state Q會變化，30 probes各重複20次epsilon0確定且Q argmax=action，測得合法0/1/2。49維直接送入會ValueError。weights不同seed42初始，但無訓練證據；沒有用微秒probe當正式性能。
- DQN/DDQN FORMAL INTEGRATION: BLOCKED。七維名稱/順序/單位/scaler/訓練資料split/Reward/訓練action mapping/環境/選checkpoint證據缺失；未任取49→7，未建立假Adapter，未宣稱已正確訓練。TEAM_BLOCKERS.md有具體必補資料與golden fixtures。
- execution snippet實際重現DQN/DDQN .decide AttributeError、threshold缺edge_cpu TypeError。只保留證據與建議，不貼回原execution；CPU百分比threshold未替換既有Load-threshold。
- 24格10圖pilot全部完成：2資料集×Low/Medium/High×4既有網路；seed11、deadline1000、realistic、complete_all、原80 training Median不重fit。每資料集從凍結100圖固定10張，所有八可用策略同圖/順序/時程/真值/估計器；每策略全新SimPy，沒有拿舊100圖baseline比較。DQN/DDQN每格BLOCKED null性能，48列不填零。
- 負載參考本固定10圖子集實測平均工作量/Edge speed3，interval=tau/rho，rho0.3/0.9/1.5，僅設計到達時程，未把個別真值給policy。LFW間隔600.28/200.09/120.06ms，WIDER1333.01/444.34/266.60ms；各網路實現節點rho另列，不宣稱全系統同樣負載。
- 新Laya真實任務選擇480次+預熱2次=預算482，沒有Replay/自動重複/結果cache/fallback；原始audit 482項保存，480任務input/state/raw choice/final choice全一致，truncated0。服務開始前已loaded，純首次模型載入時間未測；一致預熱排除任務統計。實際client任務成本合計868686.4ms+預熱8649.6ms，這是預算會計、不是跨情境總排名。
- 八策略192run/1920task全完成，240比較列（192 PASS+48 BLOCKED）；每情境獨立表/四合一圖，不混總排名。原始decision trace、逐policy checkpoint、24情境JSON與24圖保存。獨立離線FCFS按post-decision提交時間檢查所有CPU/上下載日曆、時間守恆、實際compute與成本計入通過，max error3.638e-12ms。
- Laya在本輪固定1000ms期限各格兩版達成率均0%，數值選擇仍有限，不能認證有效數值卸載AI。因DQN契約gate BLOCKED及Laya可靠性限制，不擴大30圖；本輪只作小型即時驗收/對照證據，不冒稱完整DQN正式比較。
- 新頁 http://localhost:8080/ai-comparison.html 已部署；資料集→負載→網路唯一篩選，五指標、四種圖、10策略狀態、同情境CSV/JSON/PNG匯出。原simulator.html保留功能並新增導覽。
- 實際測試PASS：原85後端+4pilot契約+2服務mock+9前端資料+59真實headless Edge E2E+63HTTP。涵蓋24篩選/五指標/真正下載讀回/手機overflow/原網站InsightFace detect+verify。desktop/mobile/PNG已實際目視核對。先前CUA瀏覽器連線無法使用，改獨立headless profile，不控制現有使用者分頁。
- 測試初次pilot腳本少import path，保存原錯誤log後只修測試路徑，4/4通過；雙欄小圖經目視後改成可讀單欄並重跑59 E2E。未放寬標準、未改正式策略或數據。
- 原始組員6檔/RAR、共同20圖SHA、11受保護檔、先前四份交付包1282個檔SHA全部核對未變；未刪DB、dataset或cache/volume。Docker backend/db/laya healthy、frontend running，只有前端重建。
- 封存曾遇Windows cp950預設編碼無法讀中文JSON，初版草稿保留於本chat work/ai-comparison-initial-encoding；只將封存讀取改明確UTF-8，不變更模型、實驗或CSV。
- 可執行範圍已完成。未完成且無法代做者：七維/訓練契約與合法DQN/DDQN正式Adapter/公平模型比較；需組員提供文件後另開版本。不可把BLOCKED當PASS，也不能因缺資料猜映射。

## 重現、恢復與交付

profiles/ai-comparison/為durable原始實驗，work/ai-comparison/為檢查/測試logs；outputs/ai-comparison/（本chat工作區）封存全部交付。主報告AI_COMPARISON_REPORT.md逐項回答八問，model_validation.md區分數值probe/未知訓練，TEAM_BLOCKERS.md可轉交組員，RUN_TESTS.md提供指令。

scripts/validate_member_models.py、run_ai_comparison.py、build_ai_comparison.py、publish_ai_results.py、test_ai_comparison.py、test_ai_browser.mjs、verify_ai_http.py、finalize_ai_tests.py為本輪來源。runner嚴格source/plan hash，已完成policy不重跑，部分中斷保留為INTERRUPTED而非混Replay；不要刪checkpoint。frontend/public/ai-comparison/保存immutable分層摘要與PNG，無須再跑模型即可檢視。

```powershell
docker compose -f compose.yaml -f compose.ai.yaml up -d
node --test frontend/tests/ai-comparison.test.mjs
docker compose exec -T backend python -m unittest discover -s tests -v
docker compose exec -T backend python /app/scripts/test_ai_comparison.py
node scripts/test_ai_browser.mjs
python scripts/verify_ai_http.py
```

/app/scripts若重建後消失，先按RUN_TESTS.md從scripts copy；原始member來源只放/tmp/member-review或隔離work。不要將沒有七維契約的DQN註冊到現有API。完整Git提交與封存HEAD在delivery-manifest.json。

---

# 本輪執行中紀錄（歷史，以上方完成狀態為準）

# AI共同子集比較與組員模型檢查（2026-11-06，進行中）

- 起點7a38ef7，Git乾淨；原SimPy/V1/Estimator/Laya與RL等11檔來源SHA保存work/ai-comparison/protected-baseline.json，禁止覆寫原backend。
- backend.rar已列目錄並獨立解至work/ai-comparison/incoming/，只將隔離副本放container /tmp/member-review；RAR/6原始檔與weights SHA保存，未修改來源、未呼叫train_step。
- 實際兩模型load與30個純數值probe/每個20次epsilon0重複通過：架構7×32→3、arr0..3完整finite、Q隨輸入變化、action涵蓋0/1/2、重複確定。weights不同於seed42初始值，但不構成訓練證據；無資料/環境/reward/scaler/訓練logs。
- snippet錯誤已實際重現：DQN/DDQN無decide() AttributeError；threshold_decide(state)缺edge_cpu TypeError。threshold百分比語義沒有直接映成SimPy queues，保留原Load-threshold。
- DQN/DDQN FORMAL INTEGRATION: BLOCKED。七維名稱/順序/單位/正規化/訓練資料/Reward/訓練action mapping/環境皆未確認，不猜49→7、不訓練或修改組員權重，保留獨立推論證據，繼續其他策略。
- 24格10圖pilot事前凍結：LFW/WIDER×Low/Medium/High×原有Local/Edge/Cloud-favorable及Reference，seed11，Deadline1000，realistic、complete_all、原訓練Median。每個資料集從凍結100圖按seed11固定取10張，所有8個可用策略完全相同子集與順序。DQN/DDQN每格顯示BLOCKED，不填性能。
- 負載以事前共同子集的實測平均compute/參考Edge speed3校準，reference CPU rho=0.3/0.9/1.5；僅設計固定到達間隔，未用於fit預估器或傳個別真值給policy。非宣稱每個網路/策略皆同實現利用率，另保存各節點counterfactual rho/完整速率與服務能力。
- 新Laya預算480次live task decision+2次一致預熱=482次，按先前CPU均值估約678秒，單policy10任務checkpoint；每decision記錄在timer外寫入，failure/部分run明列、不混Replay、不fallback。DQN契約BLOCKED且Laya既有可靠性FAIL，不擴大30圖比較。
- 下一步執行24格真實Laya共同子集、稽核audit/time/CPU/link、建立分層網頁與四種圖表及CSV/JSON匯出、完整回歸、封存outputs/ai-comparison。下方為先前完成紀錄。

---

# 正式實驗本輪已完成（2026-11-04，Asia/Taipei）

- 起點8a80cc5。階段提交：4ef5e10（metadata群組分割/情境登錄）、721cede（正式估計器與相容介面）。正式比較/報告提交fa162ee；最終封存HEAD見delivery-manifest.json。
- Phase1：320/320真實成功圖；LFW與WIDER各40 training、20 validation、100新test。train/val重用107張有效三次量測，新213張預熱+3正式共852次InsightFace呼叫。逐圖原始時間/中位數/人臉數/設備版本/失敗欄保存，無合成推論時間。新test200圖與242張歷史已測圖片的SHA256交集0。
- 分割seed20261104；LFW人物群組40/20/100、WIDER事件群組20/11/16，跨角色group/path/hash0重疊；320圖64bit dHash距離均>4。WIDER人物/所有語意近重複不能完全驗證，已說明。
- 時序：資料split在新增推論前凍結；情境矩陣在量測進行中、模型選擇/策略評估前凍結，不宣稱矩陣早於所有圖片推論。選圖/情境不使用新test結果挑勝者。
- Phase2：80 training擬合7候選，只以40 validation MAE選log-Ridge α10；test每資料集100。Median MAE：LFW74.749、WIDER626.352ms；Ridge79.169、690.737ms。差+4.420（cluster95CI[1.788,7.230]）、+64.385（CI[-72.006,217.058]）ms。Ridge RMSE/Bias點較好但MAE未改善，保留Median預設。所有候選、P50/P95、困難子群、跨資料集、scatter圖、模型JSON與checksum保留。
- Phase3：432固定格（2資料集×8環境×3間隔×3 Deadline×3 seeds），每格全部100圖；六Median策略+兩Ridge策略=3456 run/345600任務。三種比較(policy/estimator/combined)分開，432筆配對條件與CI。V2+Median對V1+Median144條件：24改善>1ms、30退步>1ms、90差<=1ms，條件數不是獨立證據，也不跨情境混排名。
- 最大點估計退化WIDER/Local有利/70ms/Deadline500：V2平均+1324.455ms，三seed CI[-1743.430,4392.340]跨零。CPU等待+1026.027ms、網路+278.114ms。額外6次100圖零成本事件重建，首次相同state下V1選Local/V2選Edge，原始states/costs/全trace保留，未修改V2或正式結果。
- 獨立FCFS：12次100圖原/共享網路V1/V2/Edge run +6次案例run，共1800任務；最大誤差7.276e-12ms。另12次確定性重播一致。正式345600筆time conservation/真值compute/CPU容量/任務唯一/相同truth/DTO隔離全部通過。
- Phase4：本輪Laya新推論0。90固定真實診斷+144歷史成本任務重新核對raw choice完全一致、無fallback；原版12/45、V2 21/45最低共同估計成本選擇正確，兩者仍FAIL數值/排列可靠性。歷史CPU決策均值1095.8/1729.4ms及實測排隊/成本消融分開保存，不偽稱本輪100圖測試，也沒有免費Replay冒充真實推論。
- Phase5：新增獨立integration_contract.py：49可觀測特徵、0/1/2動作、外部policy使用同Simulator/metrics、三分割群組/hash guard。原RL/核心/Baseline/V1/V2/估計器/Laya10個檔逐位元組未改。實際DQN/DDQN模型與HTTP key註冊仍NOT VERIFIED/未支援，介面問題與適配範例在TEAM_INTEGRATION_CONTRACT.md，不修改組員程式。
- 完整重建後85/85後端（原77+8介面）、2/2 Laya服務mock、109/109 HTTP回歸通過；包括新100圖Profile/CSV三次中位數/校驗、舊calibration/default5、隔離guard、網路/丟棄模式與網站真實辨識。Laya新增模型呼叫0。Docker backend/db/laya healthy、frontend running，JS語法PASS。瀏覽器視覺點擊NOT VERIFIED。
- 先前三份證據包402個檔雜湊核對未變；沒有刪除/覆寫舊實驗、DB、資料、模型/volume。五報告、全部CSV/raw JSON.gz/圖表與logs於本輪outputs/formal-evaluation。
- 封存驗證抓到Git archive的autocrlf換行轉換會使部分runtime來源hash不符，影響嚴格接續重播；只修封存腳本，改封存已提交工作樹的原始bytes。初版封存保留於本chat workspace work/，正式數據與策略未改。
- 可執行工作已完成。可用作宣告模型假設下的正式課堂證據；不支持實際遠端平台速度、Laya可靠數值決策、未測DQN成績或全面Ridge/V2勝出。後續只在提供真實組員模型/外部硬體時再做相應驗證，不需重測有效資料。

## 本輪恢復與重現

逐圖checkpoint與全部正式輸出持久化在原專案profiles/formal-evaluation/；源腳本scripts/formal_*.py與verify_formal_api.py。重跑會驗證/重用plan、fit-complete與raw格，不能依test重選候選或把不同版本混在舊目錄。全新研究設計需另立版本目錄並事前凍結。

```powershell
docker compose -f compose.yaml -f compose.ai.yaml up -d --build
docker compose exec -T backend python -m unittest discover -s tests -v
docker compose -f compose.yaml -f compose.ai.yaml exec -T laya python -m unittest test_server -v
docker compose exec -T backend mkdir -p /app/scripts
Get-ChildItem scripts/formal_*.py | ForEach-Object { docker compose cp $_.FullName ('backend:/app/scripts/'+$_.Name) }
docker compose exec -T backend python /app/scripts/formal_dataset.py
python scripts/formal_design.py --output work/formal-evaluation
python scripts/formal_laya.py
docker compose cp work/formal-evaluation/laya backend:/profiles/formal-evaluation/laya
docker compose exec -T backend python /app/scripts/formal_evaluate.py
docker compose exec -T backend python /app/scripts/formal_reports.py
docker compose exec -T backend python /app/scripts/formal_case_study.py
docker compose exec -T backend python /app/scripts/formal_contract_export.py
python scripts/verify_formal_api.py
# 先保存/匯入work/formal-evaluation/tests真實test-summary及logs，再重建最終報告
docker compose exec -T backend python /app/scripts/formal_reports.py
```

test-summary需依實際執行log生成，不得只複製PASS文字。完整驗證數據見tests/、evaluation/independent-validation.json及regression-case-study.json。原團隊接口規格/待支援項見TEAM_INTEGRATION_CONTRACT.md。

---

# 本輪階段紀錄（歷史，以上方完成狀態為準）

# 正式資料與組員整合：本輪進行中（2026-11-04）

- 起點8a80cc5，Git乾淨；既有核心、V1/Baseline、RL與兩個Laya版本凍結，10個原始檔雜湊保存在work/formal-evaluation/protected-baseline.json。
- 已讀前輪驗收與原始碼；資料庫LFW13233、WIDER_train12880、WIDER_val3226，足夠實測。
- 新分割seed20261104，LFW人物與WIDER事件資料夾互斥。每資料集40 training/20 validation/100 testing，320圖片內容SHA256與64bit dHash距離<=4去重，選圖不看推論時間；test排除全部已註冊歷史量測圖片。本次dHash排除0。完整plan在/profiles/formal-evaluation/plan.json與host work/formal-evaluation/plan.json，凍結後不依結果換圖。
- 訓練/驗證重用107張相同buffalo_l/CPU/三次正式實測（CSV校驗有效）；其餘213張預熱+3次正式，預計852次InsightFace呼叫。逐圖片持久化/profiles/formal-evaluation/measurements，可續跑；不重測有效資料。
- 正式矩陣於資料量測進行中、模型選擇及策略評估前固定：8環境×3間隔70/300/1000×3 deadline500/1000/2000×3 seeds11/23/37×2資料集=432情境格，每格100圖全部使用，只改順序。六個Median策略+兩個Ridge策略，共3456策略run/345600任務結果。raw/log ridge α候選0.1/1/10，只用validation MAE選；三因素比較分開。
- Laya原版/V2均不再調參，本輪新增模型決策預算0。重用90次固定可靠性診斷與已存端到端/消融原始紀錄，重新核對raw choice，不將舊資料偽稱新100圖實驗。不作大型Laya矩陣。
- 新增共用integration_contract.py僅為可觀測49特徵/0,1,2動作/外部policy呼叫與三分割guard，沒有更改組員RL；新增8項相容測試待資料量測後統一驗證。
- Phase1/2已完成：320/320成功，所有原始三次與中位數核對；正式test200圖均新測。群組：LFW train/val/test=40/20/100；WIDER=20/11/16事件群組，跨角色0重疊。Validation選log-Ridge α10；test MAE差Ridge−Median LFW+4.420ms，cluster95CI[1.788,7.230]；WIDER+64.385ms，CI[-72.006,217.058]。Median保留。模型JSON/checksum/所有7候選與跨資料集/子群保留。
- Phase4證據重用稽核已完成：90真實診斷+144歷史成本任務raw選擇一致、無fallback，本輪新Laya模型呼叫0，不冒充本輪100圖比較。
- 新介面8項+原77項全部85/85通過。矩陣進行中，下一步完成432格→獨立FCFS/確定性重播→API/Docker回歸→五報告與outputs/formal-evaluation封存。

恢復：docker compose exec -T backend python /app/scripts/formal_dataset.py（自動略過已持久化圖片）。不要重建容器前丟失/app/scripts；源腳本已存scripts/formal_dataset.py，可重新docker compose cp。/profiles持久化不會被重建清除。

---

# 前輪完成紀錄（歷史）

# 論文啟發改善：本輪已完成（2026-11-04，Asia/Taipei）

- 起點9739b39，初始Git乾淨；實作階段commit f312837；完整比較/驗證與五報告commit cf66d4d。五份本輪報告已生成，原驗收文件/實驗不覆寫。
- 完成Phase 1–5：真實量測LFW60+WIDER60（每圖預熱+3正式）；各36/12/12訓練/驗證/測試，內容SHA256跨分割重複0。7個候選只用validation選log-ridge α10；24張test固定不重選。
- 新估計器相對Median：LFW MAE36.104→40.423ms；WIDER598.201→536.625ms。成對bootstrap兩組CI均跨0，沒有全面改善證據，保留Median預設。跨資料集轉移誤差完整揭露。
- 九個受控情境51筆結果保存；27次run以獨立三階段FCFS/資源日曆核對，最大時間差6.04e-14ms。CPU/傳輸重疊案例406.28→381.70ms；6000ms未知重工作量兩版皆失敗，Oracle另列。
- 已完成192個API實驗格/894策略結果/5364筆任務；兩資料集、3種子、3負載、3環境。真實成本正式比較、預估器隔離、Oracle與成本消融分開。36條件格V2相對原版平均延遲差超過1ms：5改善、9退步、22差小於1ms；所有逐格結果保留，沒有混合排名。
- Laya90次診斷（另2次預熱）+504次矩陣原始決策均留存；原版45次診斷12正確、V2 21正確，排列36次8→18正確，但Edge/Cloud排列不變性均失敗。單因素4/9→3/9，平均HTTP成本1095.8→1729.4ms。V2可靠性FAIL，僅探索版本，不再調prompt，不使用規則冒充AI。
- 最終通過77/77後端單元（含原64、RL三案例）、2/2服務單元、78/78原HTTP整合、17/17新增API。5364任務時間守恆/真實compute不變/CPU區間容量、504 raw choice與HTTP選擇及DTO逐筆連結均通過。Docker完整建置成功，backend/db/laya healthy、frontend running，JS語法通過。
- RL相關四檔simulator.py/models.py/rl.py/test_rl.py SHA256與起點完全相同。沒有修改DQN/DDQN、介面或權重。之前outputs兩份證據包共131個雜湊檔核對未變。沒有清除資料集、DB、模型或volume。
- 實驗腳本曾因探索性消融與原消融同檔名觸發assert停下，未覆寫舊資料；已改獨立scope=exploratory_ablation續跑，192格完整。
- 限制：A/B原文實讀並核對公式；C只能取得索引方法段、全文403；D只有摘要。所有實作為paper-inspired。小樣本/單host/簡化固定網路與聚合ledger限制見五報告。瀏覽器控制不可用，未執行視覺/點擊驗收；HTTP網站、人臉辨識及真實API已通過。
- 可執行階段無剩餘待辦。未達成的研究主張：Laya可靠數值決策、新估計器全面提升、V2普遍優勢；已如實報告，不以更多test調參掩蓋。

## 本輪檔案與重現

新增estimators.py、latency_v2.py、test_paper_improvements.py、paper_cases.py；擴充experiment.py/strategies.py/laya_client.py/api.py與Laya服務、前端可選入口；五個scripts提供訓練、受控、真實模型診斷、矩陣、報告，verify_paper_api.py補向後相容檢查。完整清單見git diff 9739b39..HEAD --stat。

```powershell
docker compose -f compose.yaml -f compose.ai.yaml up -d --build
docker compose exec -T backend python -m unittest discover -s tests -v
docker compose -f compose.yaml -f compose.ai.yaml exec -T laya python -m unittest test_server -v
$env:WORKLOAD_PROFILE_ID='6ddb0a187ba44065a5beaf0450ad259e'
$env:CALIBRATION_PROFILE_ID='a057ded0f08c4837beff2ffd02f390ee'
$env:INTEGRATION_OUTPUT=(Join-Path (Get-Location) 'work/paper-improvements/api-integration')
python scripts/verify_integration.py --reuse-profiles
python scripts/verify_paper_api.py
python scripts/run_paper_comparison.py
python scripts/build_paper_reports.py
```

模型重訓/受控/診斷指令見TEAM_INTEGRATION_NOTES.md；已完成格會從JSON重讀並驗證frozen配置，不會偷換結果。要重做實驗應先另存舊資料、使用新輸出目錄。work/paper-improvements/results有模型、分割、預測與90次診斷；matrix/保存192格原始API JSON，matrix-summary/aggregate.csv為逐seed/彙整，matrix-laya-audit.jsonl為504個真實worker輸出。完整測試log與Docker建置/健康log同目錄保存。

---

# 本輪執行時階段紀錄（歷史，以上方完成狀態為準）

# 論文啟發改善進行中（2026-11-04）

- 起點9739b39，初始Git乾淨。禁止修改DQN/DDQN與RL介面；simulator.py/models.py/rl.py/test_rl.py SHA256已保存work/paper-improvements/protected-baseline.json。
- 舊64項測試基準通過；加入新預估器與策略/API後64項仍通過。
- 原文：A PDF已讀§2.1/2.2 Eq1-2與§3.1；B PDF已讀§III Eq2-13/Algorithm1；C取得原出版社可搜尋§5.1/5.2內容，直接全文連線403，作者稿封存至2027；D僅取得出版社摘要，未取得全文。未宣稱完全重現。
- 新增estimators.py（Median、3個預先定義特徵之raw/log ridge、JSON保存/校驗/分割guard）、latency_v2.py（時間維度與階段重疊估計、deadline/slack/load解釋）、LayaV2Strategy與服務variant=v2（中立緊湊輸入、不排序、不代改輸出、同multilingual checkpoint、單CPU thread並還原legacy設定）。原版策略/預估器預設保留。
- 正在以seed271828量測LFW60與WIDER_train60，各3次正式推論+預熱；完成後按固定種子做36/12/12 train/validation/test分割，不以test挑模型。量測紀錄work/paper-improvements/measurement-jobs.json。
- 已完成：LFW/WIDER各60張真實3次量測，固定36/12/12分割、內容SHA256去重；ridge_log α=10僅以validation MAE選定。已保存所有7個候選及誤差/分布/paired-bootstrap 95%CI，註冊模型107e734e...（Median）與49861dc7...（ridge_log）。測試Profile LFW=efd4b190bb52a39666b3616c3df22927、WIDER=03a2cb08e86b52b710d32a839effbc8b。
- 已完成9個受控情境、51筆v1/v2/Oracle結果；新12項後端單元+2項Laya服務單元通過，原64無退步。另加1項預測成本計入現有policy timer測試，需最後全量重跑（預期77後端+2服務）。
- Laya唯一凍結V2：原版45診斷12正確、V2 45診斷21正確；排列情境8/36→18/36，但V2只有Local排列不變、B/C仍失敗，單因素4/9→3/9且wall平均1095.8→1729.4ms。凍結，不再以test追調prompt。V2不納入可靠正式排名，只做小型探索性對照。
- 下一步固定矩陣：兩資料集、seed11/23/37、到達間隔10000/200/25ms、deadline1000、3環境（原參數、共享且受限網路、倍增遠端算力），每trial6個held-out圖片。Median下7策略54格正式端到端；feature下6個非AI策略54格隔離估計器效果；Oracle54格另列；原環境18格Median決策成本消融；LayaV2僅兩資料集/三負載/seed11原環境做正式/消融探索性6+6格。所有圖像與設定按cell一致，保存全部不利結果。不更動模型與分割。
- 診斷與訓練結果已複製至work/paper-improvements/results，重建容器前必須先cp /tmp/paper-improvements。

---

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
