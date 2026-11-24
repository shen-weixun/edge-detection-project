# 強化學習方法與論文對照

本輪直接查閱 LEAOT 的出版 PDF、TriSchedRL 的 Springer 全文及 AICDQN 的 PMC 全文。Muslim 2021 的出版頁可確認書目，但全文連結回到摘要頁，PDF 回傳 403。其內文方法尚未完成驗證。相同作者 2022 年 JAIT 論文有另一個 DOI，不能作為指定 2021 論文的內文證據。

|論文|State／Action／Reward|Episode、Replay、Target|到達與資源|隔離、收斂與公平性|
|---|---|---|---|---|
|Muslim 2021|出版摘要描述手機／Edge／Core，目標包含時間、能量、金錢與辨識準確率；精確向量、Reward 公式待全文|NOT VERIFIED|合成情境；精確參數待全文|NOT VERIFIED|
|LEAOT 2026|以工作量、FCFS 佇列、鏈路與期限形成節點成本分數，選 Edge／Cloud；沒有 RL reward|無訓練 episode、replay 或 target network|Poisson 到達、合成任務；參考 1,000 任務、8 Edge，雲端 CPU 與頻寬另設|10 次試驗與信賴區間；方法間獨立種子，故不能視為逐任務配對；無影像 train/test split；無 RL 收斂|
|TriSchedRL 2026|Eq.7 為 4n+3 維資源、佇列、鏈路、能量及三項預測；選資源，再以 guard 修正；Reward 加權 SLA、延遲、能量|DQN、target/replay；buffer 上限 1e5、batch 64–256；部分參數以範圍呈現|Poisson 與突發合成流量；異質 Edge／Cloud、時變網路|10 次配對執行；預測器宣稱獨立測試；圖示 reward 穩定性。未交代可直接複製的亂序 task_id 回饋協定|
|AICDQN 2026|佇列、資源、預測到達、優先度及能量；Local／多 Edge／Cloud；動態加權延遲、能量與優先度罰則|Dueling Double DQN；1,000 episodes×100 slots、gamma .9、batch16、RMSProp；target 每50步，per-device replay|每 slot 到達率 .3；50裝置／5 Edge／1 Cloud，RTT 與 CPU 分層|宣稱相同環境對照並展示學習曲線；未提供本專題式影像隔離清單；原始資料須向作者索取|

來源分別為 [Muslim 出版頁](https://onlinelibrary.wiley.com/doi/10.1002/nem.2146)、[LEAOT 全文](https://thesai.org/Downloads/Volume17No8/Paper_77-LEAOT_Load_Deadline_Latency.pdf)、[TriSchedRL 全文 §§3.3–5.2](https://link.springer.com/article/10.1007/s10791-026-10607-x)、[AICDQN 全文 MDP、Tables 2–4](https://pmc.ncbi.nlm.nih.gov/articles/PMC12886797/)。

本專題採用 SimPy、實測 InsightFace 工作量、49 維可觀測介面及三節點選擇。固定 log1p 正規化、Reward 的秒數加逾期罰則、100 任務回合、task_id 終止回饋與 gamma=0 成本回歸都是本次自行定義。上述三篇可讀全文沒有提供足以直接驗收本專題非同步完成協定的參考實作。Energy、priority、guard 或 GRU-LSTM 未在本輪加入；引用論文不能代替此處的時序測試。

原文存取限制使 Muslim 2021 的逐項方法比較維持 NOT VERIFIED。其餘比較只確認公開原文陳述，未重現作者程式與數值結果。

