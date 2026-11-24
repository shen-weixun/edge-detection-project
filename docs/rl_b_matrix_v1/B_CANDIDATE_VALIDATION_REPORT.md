# B矩陣六模型候選訓練與完整Validation

日期：2026-11-24（Asia/Taipei）。本輪未執行正式Test、A矩陣訓練、Ridge或14400次延長。所有Seed及最終9600 Checkpoint均保留，未依Validation挑選最佳模型。

## 工程與來源

- 沿用已驗收Smoke不可變來源；130項回歸重新通過。56份歷史契約及336個拒絕案例重新通過。
- 48個B cell各100任務，無梯度事件預檢4800派送完成；資源容量、時間、Integral成本與合法Action均通過。
- 六模型各9600訓練派送、9537次gradient update、47次Target同步；合計57600訓練派送。
- 五個Checkpoint：0/2400/4800/7200/9600，共30個權重、契約、Target/Replay/RNG狀態；checkpoint-sha256.csv列完整SHA。
- 每Checkpoint固定24個分層Validation cases、epsilon=0且不計決策成本，共72000評估派送。
- 最終完整240 cases、六候選＋六Baseline、兩成本模式，共576000評估派送。Raw JSON以gzip無損保存。
- 全部Validation均核對訓練fingerprint與獨立模型完整性，不消耗Training RNG。Bootstrap以更新前Online/Target獨立公式逐次核對。
- Candidate來源、SimPy、Baseline、P0、Normalizer、Integral Reward均未修改；新訓練沒有載入Smoke或歷史權重續訓。

## 固定監測子集學習趨勢

下列是同一24-case監測子集的macro task Reward，用於追蹤時間趨勢，不是跨情境策略排名。越高越好。

| 模型 | 0 | 2400 | 4800 | 7200 | 9600 | 最終−初始 |
|---|---:|---:|---:|---:|---:|---:|
| dqn-s42 | -2.2441 | -0.6784 | -0.6734 | -0.4374 | -0.4483 | +1.7958 |
| dqn-s43 | -2.2441 | -1.1592 | -0.5654 | -0.4595 | -0.4595 | +1.7846 |
| dqn-s44 | -0.4595 | -1.4847 | -0.6080 | -0.4569 | -0.4505 | +0.0090 |
| ddqn-s42 | -2.2441 | -0.6890 | -0.5210 | -0.4642 | -0.4483 | +1.7958 |
| ddqn-s43 | -2.2441 | -1.1337 | -0.5503 | -0.4595 | -0.4595 | +1.7846 |
| ddqn-s44 | -0.4595 | -1.4537 | -0.6056 | -0.4569 | -0.4552 | +0.0043 |

## 最終Validation診斷（各模型240 cases，不含決策成本）

| 模型 | Mean優／劣於V2案例數 | 劣於事後最佳固定式 | ≥99%單節點案例 | Local-entry全Cloud | TD裁切 | 梯度張量裁切 |
|---|---:|---:|---:|---:|---:|---:|
| dqn-s42 | 50/140 | 74 | 203 | 24/24 | 0.00% | 24.25% |
| dqn-s43 | 50/116 | 50 | 219 | 24/24 | 0.08% | 30.53% |
| dqn-s44 | 50/116 | 50 | 214 | 24/24 | 0.00% | 22.06% |
| ddqn-s42 | 51/153 | 107 | 170 | 24/24 | 0.01% | 24.94% |
| ddqn-s43 | 50/116 | 54 | 222 | 24/24 | 0.08% | 31.16% |
| ddqn-s44 | 50/116 | 50 | 215 | 24/24 | 0.00% | 22.27% |

上述計數不代表統計顯著性；同一Validation圖像反覆派送，Seed是任務軌跡變化，不是新增獨立人臉樣本。事後最佳固定式僅診斷，不是可部署策略或訓練標籤。

## 分層結果與失敗證據

- full-validation.csv：逐資料集／負載／網路／Steady-Burst／Seed／成本模式的Mean、P95、Deadline、Reward、Action Ratio及分階段成本。
- baseline-differences.csv：每個候選對六Baseline的配對差距；未修改Baseline或合併成總排名。
- checkpoint-validation.csv、checkpoint-baseline-differences.csv、learning-curves.csv：五個Checkpoint與配對Baseline。
- fixed-policy-regret.csv：明顯固定選點與完整Episode成本的反例；mean-improves-p95-worsens.csv保留Mean改善但P95惡化的案例（若存在）。
- queue-probes.csv：實際SimPy來源的同圖／同環境不同佇列控制觀測，保存每Checkpoint Q與Action。不同於V1/V2本身不構成錯誤。
- actual-exploration-and-reversals.csv：每Seed、每Episode的實際探索分支與自然流成本分項反轉；此反轉是估計成本診斷，非真實最優或因果標籤。
- decision-cost-effects.csv：同任務、同模型計入／不計入實際決策成本；wall-time成本包含原Adapter及Median預測，不含訓練診斷。
- update-diagnostics.csv與原始updates.jsonl.gz：Raw TD、Loss、Q、梯度裁切、Replay、Target、獨立Bootstrap差異與誤差。
- charts/：六份逐Seed學習曲線，以及按dataset/network分開的Mean、P95、Deadline圖；所有Training Seeds分欄保留。

## 可支持與不能支持的結論

- 工程完成不等於收斂；只有兩輪、五個監測點，不能宣稱漸近收斂。
- 高探索轉低探索同時改變行為策略；Training Reward改善不能單獨歸因Q學習，須看固定Greedy Validation。
- 所有Seed保留。不因不佳Reward、固定選點或尾延遲自行重訓或調參。
- 對共享網路拓撲、其他算力或真實CPU共享不作泛化宣稱；主訓練為independent與相對速度1/3/8。
- Local Profile為歷史CPU量測，硬體型號與threads來源不足仍存在；16KB結果是固定假設。
- 下一輪先審查分層失敗與估計偏差，再決定A矩陣／延長／Ridge；本輪不自動執行任何延伸。
