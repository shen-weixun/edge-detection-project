# 小型受控訓練診斷

設計在第一個訓練結果前寫入 `design.json`。因素為DQN／DDQN、completion／integral Reward、20／100任務回合、full／pruned特徵及訓練seed42／43／44，合計48模型。每個模型800次派送、737次更新；檢查點固定0／400／800。沒有根據Validation選checkpoint或調整超參數。

每個種子先生成八個100任務基礎流，涵蓋LFW／WIDER的Low Local優勢、Medium Edge優勢、High Cloud優勢和High Reference。20任務回合由相同基礎流切成五段，保存parent_block、offset_ms與start_index，以還原圖片及段內到達時間。切段會清空資源並重設時鐘，因此這個因素評估整體回合重設效應，不能只歸因於終止標記。100任務回合為8回合，20任務為40回合，總更新預算相同。

只載入Training／Validation Profile，按原凍結計畫驗證成員及路徑／group／SHA分割。每個100任務流有放回使用40張Training圖片；Validation則有放回使用20張，明確不等於100張獨立影像。工作量估計器、原始圖與到達排程在同一比較中一致，baseline維持原定義。特徵消融使用上一輪僅Training決定的19欄遮罩，輸入張量仍49維，沒有用正式Test挑欄。

Validation使用701／709，八情境各穩定／突發100任務流，共32配對案例。每個模型每次評估均複製快照及獨立RNG；訓練期間與結束後都不從Validation取樣更新。評估排除wall-clock成本，代表選擇品質消融，不能作正式端到端性能。保留Average、P95、Deadline、完成率、節點比例與逐任務Q／action，所有失敗seed亦在表中。

`validation-all-seeds.csv`列全部情境／seed／時點，`training-all-seeds.csv`列每個訓練回合，`paired-reward-deltas.csv`列相同案例的積分減completion差值。兩張every-seed圖使用相同顏色表示Reward、不同線型表示seed。圖中的suite平均只用於學習診斷，分層案例保留原始值，不彙成正式排名。個別seed完整趨勢在 `PER_SEED.md`。

新方法證據的重現方式是將此輪source下模組逐檔複製到backend對應路徑，將scripts複製到/app/scripts，舊ZIP複製到/tmp/rl-method-review.zip，保留既有Profile登錄。使用新的輸出目錄，依序執行：

```powershell
docker compose exec -T -e OPENBLAS_NUM_THREADS=1 backend python -m unittest discover -s tests -v
docker compose exec -T -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=1 backend python /app/scripts/rl_long_horizon_study.py /profiles/rl-long-horizon-new /tmp/rl-method-review.zip
docker compose exec -T -e OPENBLAS_NUM_THREADS=1 backend python /app/scripts/rl_long_horizon_report.py /profiles/rl-long-horizon-new
```

原腳本也已修正評估入口，但未覆寫其已完成輸出。第一項測試已證明評估隔離，第二階段證明目標一致，仍須由每個seed的實際曲線判斷能否擴大。49維觀測的Markov充分性、有限回合長度對價值尺度的影響及gamma1函數近似穩定性都是剩餘研究限制。



本輪實際完成48模型、38,400訓練派送、4,608次學習模型Validation與64次baselineValidation，合計4,672次。訓練全流成本與獨立事件sweep的最大差為1.397e-9，低於1e-6門檻。兩演算法在24組對應配置的最終權重均不同，與非零bootstrap測試相符。模型正規化和輸入權限相同，差異不來自baseline修改。

|100任務／完整特徵／Integral|初始Reward|400步|800步|
|---|---:|---:|---:|
|DQN seed42|-4.439|-5.047|-11.546|
|DQN seed43|-4.207|-7.706|-8.775|
|DQN seed44|-9.119|-3.841|-1.945|
|DDQN seed42|-4.439|-4.979|-9.431|
|DDQN seed43|-4.207|-8.962|-9.119|
|DDQN seed44|-9.119|-3.853|-5.186|

數字是固定32個驗證案例的每任務Reward平均，保留各seed，不宣稱獨立影像數為3,200。100任務積分版DQN兩個seed退步；DDQN同樣兩個seed退步，另有單一seed改善。800步時比較積分與completion，在12個DQN配置／seed配對中4個改善、8個退步，DDQN為3個改善、9個退步。這些數目只描述此預算，沒有推論母體勝率或顯著性。

結論為方法及程式驗收通過、學習穩定性尚未通過。新Reward符合宣告的全流成本，並不保證更容易學到策略。gamma1、函數近似、狀態部分可觀測、不同回合價值尺度及梯度裁切都可能影響結果，但本輪沒有完成各因素的單獨因果實驗。依任務要求停止正式Test，不以seed44或某個中途checkpoint作為新正式模型。後續改進仍需留在training／validation，先證明穩定性及選模規則，再另凍結未曝光的新Test。
