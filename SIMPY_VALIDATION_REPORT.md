# SimPy 驗證報告

基準版本 f8ec356：28/28 通過。修正版本 audit-v2：52/52 通過（含24項新增測試），0失敗。
既有測試只因介面分離改用DecisionTask、實測校準集，以及將600 ms的精確等值改為1e-8浮點比較；未刪除原案例或放寬時間守恆要求。

## 可重現的修改前問題

`work/audit/baseline-reproduction.json` 使用 git show 取出的原始程式：策略讀到 workload=731、face_count=9；B到達時Edge仍在上傳，CPU work=0；不計決策的總延遲50，元件合計150 ms。

## 單元／離散事件／策略一致性測試

方法為執行各測試函式列出的assert；下表實際「符合」代表所有斷言通過，不是只看HTTP成功。原始完整紀錄 `unit-tests-final.txt`。

|測試名稱|方法與預期|實際|結果|程式檔案|
|---|---|---|---|---|
|test_datasets.DatasetTests.test_lfw.test_lfw|解析單一LFW人物路徑與標籤。|符合全部斷言|PASS|backend/tests/test_datasets.py|
|test_datasets.DatasetTests.test_missing_image.test_missing_image|WIDER標註缺少圖片時報錯。|符合全部斷言|PASS|backend/tests/test_datasets.py|
|test_datasets.DatasetTests.test_reject_traversal.test_reject_traversal|拒絕資料集路徑穿越。|符合全部斷言|PASS|backend/tests/test_datasets.py|
|test_datasets.DatasetTests.test_wider_invalid_and_zero_placeholder.test_wider_invalid_and_zero_placeholder|無效框與零框placeholder正確排除，保留有效標註。|符合全部斷言|PASS|backend/tests/test_datasets.py|
|test_execution.ExecutionTests.test_all_strategies_measure_local_only.test_all_strategies_measure_local_only|原人臉端點的實測時間只標記device，不偽造遠端時間。|符合全部斷言|PASS|backend/tests/test_execution.py|
|test_execution.ExecutionTests.test_failure_does_not_become_success.test_failure_does_not_become_success|原人臉工作執行失敗不轉成功。|符合全部斷言|PASS|backend/tests/test_execution.py|
|test_offloading.SimulationTest.test_fixed_local_has_queue_and_no_network.test_fixed_local_has_queue_and_no_network|兩同時100 ms本機任務完成100/200，無網路成本。|符合全部斷言|PASS|backend/tests/test_offloading.py|
|test_offloading.SimulationTest.test_identical_scenario_for_all_policies.test_identical_scenario_for_all_policies|五策略共用相同manifest，完成數一致，合成資料來源明示。|符合全部斷言|PASS|backend/tests/test_offloading.py|
|test_offloading.SimulationTest.test_remote_network_and_deadline.test_remote_network_and_deadline|指定遠端傳輸時間>100、超期，元件與總延遲一致。|符合全部斷言|PASS|backend/tests/test_offloading.py|
|test_offloading.SimulationTest.test_task_count_and_seed.test_task_count_and_seed|相同seed生成相同Task列表。|符合全部斷言|PASS|backend/tests/test_offloading.py|
|test_offloading.SimulationTest.test_unimplemented_dqn_cannot_be_mislabelled.test_unimplemented_dqn_cannot_be_mislabelled|尚未實作的DQN策略被拒絕。|符合全部斷言|PASS|backend/tests/test_offloading.py|
|test_offloading.StrategiesTest.test_expected_transfer_units.test_expected_transfer_units|Edge估算=CPU50+RTT20+upload40+download0.64。|符合全部斷言|PASS|backend/tests/test_offloading.py|
|test_offloading.StrategiesTest.test_invalid_task_rejected.test_invalid_task_rejected|負圖片大小拒絕。|符合全部斷言|PASS|backend/tests/test_offloading.py|
|test_offloading.StrategiesTest.test_latency_aware_selects_edge.test_latency_aware_selects_edge|可手算空佇列範例選Edge。|符合全部斷言|PASS|backend/tests/test_offloading.py|
|test_offloading.StrategiesTest.test_queue_changes_policy.test_queue_changes_policy|加入Edge CPU負載後改選Local。|符合全部斷言|PASS|backend/tests/test_offloading.py|
|test_offloading.StrategiesTest.test_real_laya_adapter_parses_typed_result.test_real_laya_adapter_parses_typed_result|以mock HTTP驗證client節點與confidence解析。|符合全部斷言|PASS|backend/tests/test_offloading.py|
|test_offloading.StrategiesTest.test_real_laya_failure_not_faked.test_real_laya_failure_not_faked|mock網路失敗應拋錯，無AI fallback。|符合全部斷言|PASS|backend/tests/test_offloading.py|
|test_profiles.ProfileTests.test_csv_roundtrip_and_provenance.test_csv_roundtrip_and_provenance|CSV載入保留來源路徑、資料集與推論真值123。|符合全部斷言|PASS|backend/tests/test_profiles.py|
|test_profiles.ProfileTests.test_decision_deadline_and_component_sum.test_decision_deadline_and_component_sum|決策600+CPU100跨期限500，浮點容差1e-8，元件守恆。|符合全部斷言|PASS|backend/tests/test_profiles.py|
|test_profiles.ProfileTests.test_decision_engine_serial_queue.test_decision_engine_serial_queue|同到達兩筆，各決策100，第二筆等待100。|符合全部斷言|PASS|backend/tests/test_profiles.py|
|test_profiles.ProfileTests.test_failed_rows_are_excluded_without_fabrication.test_failed_rows_are_excluded_without_fabrication|失敗CSV列排除；全部失敗拒絕。|符合全部斷言|PASS|backend/tests/test_profiles.py|
|test_profiles.ProfileTests.test_legacy_unverified_csv_rejected.test_legacy_unverified_csv_rejected|缺少真實量測標記的舊CSV拒絕。|符合全部斷言|PASS|backend/tests/test_profiles.py|
|test_profiles.ProfileTests.test_measured_policy_fairness_and_reset.test_measured_policy_fairness_and_reset|實測列表共用、重跑hash相同、實際CPU服務未改寫。|符合全部斷言|PASS|backend/tests/test_profiles.py|
|test_profiles.ProfileTests.test_measurement_failure_records_reason.test_measurement_failure_records_reason|量測路徑錯誤保留錯誤原因而非偽造推論時間。|符合全部斷言|PASS|backend/tests/test_profiles.py|
|test_profiles.ProfileTests.test_metadata_is_captured_at_decision_not_completion.test_metadata_is_captured_at_decision_not_completion|多任務共用策略時，每筆model/confidence/audit_id於決策後立即保存，無覆寫。|符合全部斷言|PASS|backend/tests/test_profiles.py|
|test_profiles.ProfileTests.test_missing_profile_never_becomes_synthetic.test_missing_profile_never_becomes_synthetic|缺失/空實測Profile不回退Synthetic。|符合全部斷言|PASS|backend/tests/test_profiles.py|
|test_profiles.ProfileTests.test_no_replacement_sampling.test_no_replacement_sampling|抽樣無重複，相同seed可重現，要求數超過成功圖片數拒絕。|符合全部斷言|PASS|backend/tests/test_profiles.py|
|test_profiles.ProfileTests.test_profile_path_traversal_rejected.test_profile_path_traversal_rejected|拒絕Profile ID路徑穿越。|符合全部斷言|PASS|backend/tests/test_profiles.py|
|test_rl.RLValidation.test_action_next_state_delayed_reward_done_reset.test_action_next_state_delayed_reward_done_reset|RL 0/1/2 action/state/延遲reward/next state/done與reset；Local三筆reward總=-0.57，與固定策略時間一致。|符合全部斷言|PASS|backend/tests/test_rl.py|
|test_rl.RLValidation.test_training_adapter_cannot_claim_decision_overhead.test_training_adapter_cannot_claim_decision_overhead|互動訓練若宣稱計入外部思考wall time，明確拒絕。|符合全部斷言|PASS|backend/tests/test_rl.py|
|test_rl.RLValidation.test_training_test_episode_split.test_training_test_episode_split|EpisodeSplit禁止訓練/測試來源重疊，兩分割各建獨立環境，無效分割名稱拒絕。|符合全部斷言|PASS|backend/tests/test_rl.py|
|test_simpy_validation.AdditionalValidation.test_exact_deadline_and_return_drop.test_exact_deadline_and_return_drop|剛好100 ms期限完成算達標；171.6 ms回傳對期限171拒絕，已耗CPU50/網路121.6保留。|符合全部斷言|PASS|backend/tests/test_simpy_validation.py|
|test_simpy_validation.AdditionalValidation.test_latency_policy_accounts_for_upload_commitment.test_latency_policy_accounts_for_upload_commitment|空Edge時選Edge；加入1000 ms上傳中承諾後選Local。|符合全部斷言|PASS|backend/tests/test_simpy_validation.py|
|test_simpy_validation.AdditionalValidation.test_laya_payload_excludes_labels.test_laya_payload_excludes_labels|實際client序列化只含DecisionTask，禁止內部Task及人臉數/真值/路徑。|符合全部斷言|PASS|backend/tests/test_simpy_validation.py|
|test_simpy_validation.AdditionalValidation.test_randomized_time_conservation_and_cpu_capacity.test_randomized_time_conservation_and_cpu_capacity|固定種子20任務×2網路×2期限政策，元件和誤差<1e-8；同節點CPU區間不重疊，資源清空。|符合全部斷言|PASS|backend/tests/test_simpy_validation.py|
|test_simpy_validation.AdditionalValidation.test_shared_links_are_full_duplex_hand_calculation.test_shared_links_are_full_duplex_hand_calculation|共享模式A下載21.0001..121.0001與B上傳40..140可重疊，B CPU在140開始。|符合全部斷言|PASS|backend/tests/test_simpy_validation.py|
|test_simpy_validation.AdditionalValidation.test_stage_partition_excludes_return_from_cpu_work.test_stage_partition_excludes_return_from_cpu_work|165 ms時A已回傳不占CPU，B/C仍上傳：return=1、CPU work=0、commit=2/400 ms。|符合全部斷言|PASS|backend/tests/test_simpy_validation.py|
|test_simpy_validation.EventValidation.test_ablation_has_no_charged_decision_or_queue.test_ablation_has_no_charged_decision_or_queue|保留 wall=100 ms，但 decision/decision_queue 計費皆 0，時間守恆。|符合全部斷言|PASS|backend/tests/test_simpy_validation.py|
|test_simpy_validation.EventValidation.test_arrival_during_upload_has_committed_work.test_arrival_during_upload_has_committed_work|B 在 20 ms 到達時 A 上傳中：CPU queue=0/running=0、commit=1、estimate=200 ms。|符合全部斷言|PASS|backend/tests/test_simpy_validation.py|
|test_simpy_validation.EventValidation.test_calibration_disjoint_and_target_label_invariance.test_calibration_disjoint_and_target_label_invariance|待測真值999改1，估計仍為獨立訓練321；重疊與空校準集拒絕。|符合全部斷言|PASS|backend/tests/test_simpy_validation.py|
|test_simpy_validation.EventValidation.test_complete_all_vs_drop_cpu_wait_and_consumption.test_complete_all_vs_drop_cpu_wait_and_consumption|期限 50、CPU 100；complete_all 全完成但全未達標；drop 僅第一筆耗用100，其餘CPU服務0，資源釋放。|符合全部斷言|PASS|backend/tests/test_simpy_validation.py|
|test_simpy_validation.EventValidation.test_drop_after_decision.test_drop_after_decision|決策100跨期限50，完整計入決策成本，CPU不開始。|符合全部斷言|PASS|backend/tests/test_simpy_validation.py|
|test_simpy_validation.EventValidation.test_drop_after_upload_and_release_shared_resources.test_drop_after_upload_and_release_shared_resources|上傳跨期限仍計費，等待上傳者不開始服務；終止後無 pending/持有資源。|符合全部斷言|PASS|backend/tests/test_simpy_validation.py|
|test_simpy_validation.EventValidation.test_independent_vs_shared_uplink_hand_calculation.test_independent_vs_shared_uplink_hand_calculation|不同遠端同時上傳 1 MB/80 Mbps：獨立 CPU 開始 110/110，共享 110/210 ms。|符合全部斷言|PASS|backend/tests/test_simpy_validation.py|
|test_simpy_validation.EventValidation.test_no_labels_or_future_tasks_in_policy_contract.test_no_labels_or_future_tasks_in_policy_contract|策略DTO無真實workload/face_count/路徑，僅本任務估計；Oracle明確使用真值。|符合全部斷言|PASS|backend/tests/test_simpy_validation.py|
|test_simpy_validation.EventValidation.test_oracle_and_formal_modes_labelled.test_oracle_and_formal_modes_labelled|Realistic、Oracle與end_to_end/selection_quality_ablation標記正確，兩模式時間守恆。|符合全部斷言|PASS|backend/tests/test_simpy_validation.py|
|test_simpy_validation.EventValidation.test_reset_resources_and_identical_inputs.test_reset_resources_and_identical_inputs|兩次獨立環境/決策與網路資源，同一工作負載產生相同虛擬結果；同物件禁止run兩次。|符合全部斷言|PASS|backend/tests/test_simpy_validation.py|
|test_simpy_validation.EventValidation.test_running_estimate_does_not_reveal_actual_finish.test_running_estimate_does_not_reveal_actual_finish|A 真值 10000、估計 200，經過 50 ms 只暴露估計剩餘 150，而非真值剩餘。|符合全部斷言|PASS|backend/tests/test_simpy_validation.py|
|test_simpy_validation.EventValidation.test_serial_download_and_full_duplex.test_serial_download_and_full_duplex|共享出口的下載為獨立序列 Resource，兩結果完成時間相差 1.6 ms，無無限制占用全頻寬。|符合全部斷言|PASS|backend/tests/test_simpy_validation.py|
|test_simpy_validation.EventValidation.test_single_task_hand_calculation.test_single_task_hand_calculation|固定決策 7 + RTT 20 + 上傳 100 + CPU 50 + 下載 1.6 = 178.6 ms；CPU 117 ms 開始。|符合全部斷言|PASS|backend/tests/test_simpy_validation.py|
|test_simpy_validation.EventValidation.test_three_task_fcfs_and_time_weighted_queue.test_three_task_fcfs_and_time_weighted_queue|三任務同到達，CPU 開始 0/100/200、完成 100/200/300、等待 0/100/200；時間加權平均等待數 1。|符合全部斷言|PASS|backend/tests/test_simpy_validation.py|
|test_simpy_validation.EventValidation.test_wall_blocking_preserves_virtual_arrivals.test_wall_blocking_preserves_virtual_arrivals|真實 blocking 呼叫不改到達時間；決策 A=100、B 在 20 到達，B 決策等待=80 ms。|符合全部斷言|PASS|backend/tests/test_simpy_validation.py|

## API／真實模型整合

`scripts/verify_integration.py --reuse-profiles`：78項通過，0項失敗。量測CSV檢查包含原LFW30與WIDER val3；另外新量測獨立LFW校準30張。

|項次／檢查|方法與預期|實際|結果|
|---|---|---|---|
|1. / HTTP|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|2. /simulator.html HTTP|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|3. /simulator.js HTTP|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|4. /api/health HTTP|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|5. invalid measured/mode/strategy {'workload_mode': 'measured', 'count': 1}|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|6. invalid measured/mode/strategy {'workload_mode': 'measured', 'profile_id': '00000000000000000000000000000000', 'count': 1}|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|7. invalid measured/mode/strategy {'workload_mode': 'synthetic', 'profile_id': '00000000000000000000000000000000'}|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|8. invalid measured/mode/strategy {'strategies': ['dqn']}|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|9. profile validation {'dataset': 'invalid'}|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|10. profile validation {'dataset': 'lfw', 'repeats': 2}|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|11. profile validation {'dataset': 'lfw', 'count': 501}|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|12. lfw real measurement completed|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|13. lfw CSV checksum|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|14. lfw real CSV schema|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|15. wider_val real measurement completed|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|16. wider_val CSV checksum|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|17. wider_val real CSV schema|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|18. CSV actually reaches SimPy|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|19. CSV inference times unchanged in tasks|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|20. five policies same tasks|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|21. delay decomposition|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|22. explicit no-drop completion|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|23. repeat experiment identical workload hash|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|24. explicit synthetic label|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|25. WIDER real profile reaches SimPy|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|26. homepage real sample detection|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|27. homepage real same-image verification|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|28. real Laya model decision|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|29. Laya decision deadline miss reflected|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|30. API modes independent/complete_all|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|31. API conservation independent/complete_all|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|32. API completion/drop accounting independent/complete_all|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|33. API conservation independent/complete_all|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|34. API completion/drop accounting independent/complete_all|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|35. API conservation independent/complete_all|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|36. API completion/drop accounting independent/complete_all|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|37. API conservation independent/complete_all|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|38. API completion/drop accounting independent/complete_all|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|39. API conservation independent/complete_all|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|40. API completion/drop accounting independent/complete_all|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|41. API modes independent/drop_if_expired|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|42. API conservation independent/drop_if_expired|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|43. API completion/drop accounting independent/drop_if_expired|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|44. API conservation independent/drop_if_expired|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|45. API completion/drop accounting independent/drop_if_expired|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|46. API conservation independent/drop_if_expired|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|47. API completion/drop accounting independent/drop_if_expired|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|48. API conservation independent/drop_if_expired|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|49. API completion/drop accounting independent/drop_if_expired|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|50. API conservation independent/drop_if_expired|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|51. API completion/drop accounting independent/drop_if_expired|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|52. API modes shared/complete_all|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|53. API conservation shared/complete_all|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|54. API completion/drop accounting shared/complete_all|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|55. API conservation shared/complete_all|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|56. API completion/drop accounting shared/complete_all|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|57. API conservation shared/complete_all|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|58. API completion/drop accounting shared/complete_all|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|59. API conservation shared/complete_all|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|60. API completion/drop accounting shared/complete_all|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|61. API conservation shared/complete_all|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|62. API completion/drop accounting shared/complete_all|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|63. API modes shared/drop_if_expired|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|64. API conservation shared/drop_if_expired|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|65. API completion/drop accounting shared/drop_if_expired|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|66. API conservation shared/drop_if_expired|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|67. API completion/drop accounting shared/drop_if_expired|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|68. API conservation shared/drop_if_expired|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|69. API completion/drop accounting shared/drop_if_expired|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|70. API conservation shared/drop_if_expired|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|71. API completion/drop accounting shared/drop_if_expired|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|72. API conservation shared/drop_if_expired|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|73. API completion/drop accounting shared/drop_if_expired|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|74. API rejects invalid calibration/config {'calibration_profile_id': None}|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|75. API rejects invalid calibration/config {'calibration_profile_id': '6ddb0a187ba44065a5beaf0450ad259e'}|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|76. API rejects invalid calibration/config {'network_mode': 'invalid'}|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|77. API rejects invalid calibration/config {'deadline_policy': 'invalid'}|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|
|78. API ablation labelled|實際HTTP請求／回應斷言，應符合上述契約|符合|PASS|

API測試檔案均為 `scripts/verify_integration.py`；各項assert直接對照JSON、HTTP狀態、真實偵測與驗證結果。Laya client的失敗案例為mock，成功案例確實呼叫真實Router，兩者不混淆。

## Docker 與前端

- `docker compose up -d --build` 實際成功；日誌 start-standard.txt。
- `docker compose -f compose.yaml -f compose.ai.yaml up -d --build` 實際成功；日誌 start-ai.txt。
- PostgreSQL/backend/Laya健康檢查均正常，frontend在127.0.0.1:8080提供首頁與simulator.html/js（HTTP 200）。
- Vite正式建置成功；`node --check frontend/public/simulator.js` 通過。瀏覽器實際確認首頁API已連線，選原LFW與獨立校準Profile、3任務五策略比較完成，時間加權佇列表格正常，console無錯誤；畫面見browser-validation.png。另修正舊腳本快取，資源URL加入audit-v2版本。未測所有瀏覽器/螢幕尺寸。
- 未清除任何volume、資料集、資料庫或模型快取。

## 九組正式實驗與稽核

九組全部完成：1620筆終止結果、270次真實Laya決策、99項情境稽核均通過；時間守恆最大誤差7.276e-12 ms，無fallback、無模型輸入截斷。見grid-verification.json、grid-checks.csv、before-after-full.csv和SIMPY_BEFORE_AFTER.md。另實際執行六策略各3任務消融（18筆），Laya真實wall時間保留、decision/decision_queue計費皆0；證據real-six-policy-ablation.json。獨立/共用網路與丟棄手算案例另列於上表。

## 尚未驗證／限制

- 無真實Edge/Cloud遠端硬體跑分，網路為模擬模型。
- 不含DQN/DDQN有效權重、訓練收斂或泛化效能；RL測試只證明介面與事件一致。
- 沒有比較不同校準估計器或做多次重複的統計顯著性檢定。
- 未模擬觀測延遲、多核心、搶先取消、能耗或網路故障；到期限才立刻中斷不是本次階段邊界丟棄語義。
- 真實Laya成本含HTTP/載入與序列服務等待，受主機負載影響；模型選擇品質不能只由相同seed保證。
