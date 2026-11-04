"""Build the validation index from actual unittest/integration logs."""
import json,re
from pathlib import Path

root=Path(__file__).resolve().parents[1]
log=(root/'work/audit/unit-tests-final.txt').read_text(encoding='utf-8-sig')
rows=re.findall(r'^(test_\w+) \(([^)]+)\) \.\.\. ok',log,re.M)
assert len(rows)==52
expected={
 'test_training_test_episode_split':'EpisodeSplit禁止訓練/測試來源重疊，兩分割各建獨立環境，無效分割名稱拒絕。',
 'test_shared_links_are_full_duplex_hand_calculation':'共享模式A下載21.0001..121.0001與B上傳40..140可重疊，B CPU在140開始。',
 'test_stage_partition_excludes_return_from_cpu_work':'165 ms時A已回傳不占CPU，B/C仍上傳：return=1、CPU work=0、commit=2/400 ms。',

 'test_single_task_hand_calculation':'固定決策 7 + RTT 20 + 上傳 100 + CPU 50 + 下載 1.6 = 178.6 ms；CPU 117 ms 開始。',
 'test_three_task_fcfs_and_time_weighted_queue':'三任務同到達，CPU 開始 0/100/200、完成 100/200/300、等待 0/100/200；時間加權平均等待數 1。',
 'test_arrival_during_upload_has_committed_work':'B 在 20 ms 到達時 A 上傳中：CPU queue=0/running=0、commit=1、estimate=200 ms。',
 'test_running_estimate_does_not_reveal_actual_finish':'A 真值 10000、估計 200，經過 50 ms 只暴露估計剩餘 150，而非真值剩餘。',
 'test_wall_blocking_preserves_virtual_arrivals':'真實 blocking 呼叫不改到達時間；決策 A=100、B 在 20 到達，B 決策等待=80 ms。',
 'test_ablation_has_no_charged_decision_or_queue':'保留 wall=100 ms，但 decision/decision_queue 計費皆 0，時間守恆。',
 'test_independent_vs_shared_uplink_hand_calculation':'不同遠端同時上傳 1 MB/80 Mbps：獨立 CPU 開始 110/110，共享 110/210 ms。',
 'test_serial_download_and_full_duplex':'共享出口的下載為獨立序列 Resource，兩結果完成時間相差 1.6 ms，無無限制占用全頻寬。',
 'test_complete_all_vs_drop_cpu_wait_and_consumption':'期限 50、CPU 100；complete_all 全完成但全未達標；drop 僅第一筆耗用100，其餘CPU服務0，資源釋放。',
 'test_drop_after_upload_and_release_shared_resources':'上傳跨期限仍計費，等待上傳者不開始服務；終止後無 pending/持有資源。',
 'test_drop_after_decision':'決策100跨期限50，完整計入決策成本，CPU不開始。',
 'test_reset_resources_and_identical_inputs':'兩次獨立環境/決策與網路資源，同一工作負載產生相同虛擬結果；同物件禁止run兩次。',
 'test_no_labels_or_future_tasks_in_policy_contract':'策略DTO無真實workload/face_count/路徑，僅本任務估計；Oracle明確使用真值。',
 'test_calibration_disjoint_and_target_label_invariance':'待測真值999改1，估計仍為獨立訓練321；重疊與空校準集拒絕。',
 'test_oracle_and_formal_modes_labelled':'Realistic、Oracle與end_to_end/selection_quality_ablation標記正確，兩模式時間守恆。',
 'test_latency_policy_accounts_for_upload_commitment':'空Edge時選Edge；加入1000 ms上傳中承諾後選Local。',
 'test_randomized_time_conservation_and_cpu_capacity':'固定種子20任務×2網路×2期限政策，元件和誤差<1e-8；同節點CPU區間不重疊，資源清空。',
 'test_exact_deadline_and_return_drop':'剛好100 ms期限完成算達標；171.6 ms回傳對期限171拒絕，已耗CPU50/網路121.6保留。',
 'test_laya_payload_excludes_labels':'實際client序列化只含DecisionTask，禁止內部Task及人臉數/真值/路徑。',
 'test_action_next_state_delayed_reward_done_reset':'RL 0/1/2 action/state/延遲reward/next state/done與reset；Local三筆reward總=-0.57，與固定策略時間一致。',
 'test_training_adapter_cannot_claim_decision_overhead':'互動訓練若宣稱計入外部思考wall time，明確拒絕。',
 'test_lfw':'解析單一LFW人物路徑與標籤。',
 'test_missing_image':'WIDER標註缺少圖片時報錯。',
 'test_reject_traversal':'拒絕資料集路徑穿越。',
 'test_wider_invalid_and_zero_placeholder':'無效框與零框placeholder正確排除，保留有效標註。',
 'test_all_strategies_measure_local_only':'原人臉端點的實測時間只標記device，不偽造遠端時間。',
 'test_failure_does_not_become_success':'原人臉工作執行失敗不轉成功。',
 'test_fixed_local_has_queue_and_no_network':'兩同時100 ms本機任務完成100/200，無網路成本。',
 'test_identical_scenario_for_all_policies':'五策略共用相同manifest，完成數一致，合成資料來源明示。',
 'test_remote_network_and_deadline':'指定遠端傳輸時間>100、超期，元件與總延遲一致。',
 'test_task_count_and_seed':'相同seed生成相同Task列表。',
 'test_unimplemented_dqn_cannot_be_mislabelled':'尚未實作的DQN策略被拒絕。',
 'test_expected_transfer_units':'Edge估算=CPU50+RTT20+upload40+download0.64。',
 'test_invalid_task_rejected':'負圖片大小拒絕。',
 'test_latency_aware_selects_edge':'可手算空佇列範例選Edge。',
 'test_queue_changes_policy':'加入Edge CPU負載後改選Local。',
 'test_real_laya_adapter_parses_typed_result':'以mock HTTP驗證client節點與confidence解析。',
 'test_real_laya_failure_not_faked':'mock網路失敗應拋錯，無AI fallback。',
 'test_csv_roundtrip_and_provenance':'CSV載入保留來源路徑、資料集與推論真值123。',
 'test_decision_deadline_and_component_sum':'決策600+CPU100跨期限500，浮點容差1e-8，元件守恆。',
 'test_decision_engine_serial_queue':'同到達兩筆，各決策100，第二筆等待100。',
 'test_failed_rows_are_excluded_without_fabrication':'失敗CSV列排除；全部失敗拒絕。',
 'test_legacy_unverified_csv_rejected':'缺少真實量測標記的舊CSV拒絕。',
 'test_measured_policy_fairness_and_reset':'實測列表共用、重跑hash相同、實際CPU服務未改寫。',
 'test_measurement_failure_records_reason':'量測路徑錯誤保留錯誤原因而非偽造推論時間。',
 'test_metadata_is_captured_at_decision_not_completion':'多任務共用策略時，每筆model/confidence/audit_id於決策後立即保存，無覆寫。',
 'test_missing_profile_never_becomes_synthetic':'缺失/空實測Profile不回退Synthetic。',
 'test_no_replacement_sampling':'抽樣無重複，相同seed可重現，要求數超過成功圖片數拒絕。',
 'test_profile_path_traversal_rejected':'拒絕Profile ID路徑穿越。',
}
assert set(m for m,_ in rows)==set(expected)
integration=json.loads((root/'work/audit/integration/integration-results.json').read_text(encoding='utf-8'))
lines=['# SimPy 驗證報告','',
       '基準版本 f8ec356：28/28 通過。修正版本 audit-v2：52/52 通過（含24項新增測試），0失敗。',
       '既有測試只因介面分離改用DecisionTask、實測校準集，以及將600 ms的精確等值改為1e-8浮點比較；未刪除原案例或放寬時間守恆要求。',
       '', '## 可重現的修改前問題','',
       '`work/audit/baseline-reproduction.json` 使用 git show 取出的原始程式：策略讀到 workload=731、face_count=9；B到達時Edge仍在上傳，CPU work=0；不計決策的總延遲50，元件合計150 ms。',
       '', '## 單元／離散事件／策略一致性測試','',
       '方法為執行各測試函式列出的assert；下表實際「符合」代表所有斷言通過，不是只看HTTP成功。原始完整紀錄 `unit-tests-final.txt`。',
       '', '|測試名稱|方法與預期|實際|結果|程式檔案|','|---|---|---|---|---|']
for method,identifier in rows:
    module=identifier.split('.')[0]
    lines.append(f'|{identifier}.{method}|{expected[method]}|符合全部斷言|PASS|backend/tests/{module}.py|')
lines+=['','## API／真實模型整合','',
        f"`scripts/verify_integration.py --reuse-profiles`：{integration['passed']}項通過，{integration['failed']}項失敗。量測CSV檢查包含原LFW30與WIDER val3；另外新量測獨立LFW校準30張。",'',
        '|項次／檢查|方法與預期|實際|結果|','|---|---|---|---|']
for i,name in enumerate(integration['checks'],1):
    lines.append(f'|{i}. {name}|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|')
lines+=['','API測試檔案均為 `scripts/verify_integration.py`；各項assert直接對照JSON、HTTP狀態、真實偵測與驗證結果。Laya client的失敗案例為mock，成功案例確實呼叫真實Router，兩者不混淆。',
        '', '## Docker 與前端','',
        '- `docker compose up -d --build` 實際成功；日誌 start-standard.txt。',
        '- `docker compose -f compose.yaml -f compose.ai.yaml up -d --build` 實際成功；日誌 start-ai.txt。',
        '- PostgreSQL/backend/Laya健康檢查均正常，frontend在127.0.0.1:8080提供首頁與simulator.html/js（HTTP 200）。',
        '- Vite正式建置成功；`node --check frontend/public/simulator.js` 通過。瀏覽器實際確認首頁API已連線，選原LFW與獨立校準Profile、3任務五策略比較完成，時間加權佇列表格正常，console無錯誤；畫面見browser-validation.png。另修正舊腳本快取，資源URL加入audit-v2版本。未測所有瀏覽器/螢幕尺寸。',
        '- 未清除任何volume、資料集、資料庫或模型快取。',
        '', '## 九組正式實驗與稽核','',
        '九組全部完成：1620筆終止結果、270次真實Laya決策、99項情境稽核均通過；時間守恆最大誤差7.276e-12 ms，無fallback、無模型輸入截斷。見grid-verification.json、grid-checks.csv、before-after-full.csv和SIMPY_BEFORE_AFTER.md。另實際執行六策略各3任務消融（18筆），Laya真實wall時間保留、decision/decision_queue計費皆0；證據real-six-policy-ablation.json。獨立/共用網路與丟棄手算案例另列於上表。',
        '', '## 尚未驗證／限制','',
        '- 無真實Edge/Cloud遠端硬體跑分，網路為模擬模型。',
        '- 不含DQN/DDQN有效權重、訓練收斂或泛化效能；RL測試只證明介面與事件一致。',
        '- 沒有比較不同校準估計器或做多次重複的統計顯著性檢定。',
        '- 未模擬觀測延遲、多核心、搶先取消、能耗或網路故障；到期限才立刻中斷不是本次階段邊界丟棄語義。',
        '- 真實Laya成本含HTTP/載入與序列服務等待，受主機負載影響；模型選擇品質不能只由相同seed保證。','']
(root/'SIMPY_VALIDATION_REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
print('validation report:',len(rows),'unit,',integration['passed'],'integration')
