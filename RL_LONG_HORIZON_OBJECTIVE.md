# 長期卸載目標與時間積分

A 為 `task-terminal-v1`，在任務完成後回饋原始派送state/action，gamma0。它學習該任務的條件成本，DQN和DDQN的target差異在此退化。

B 為本輪 `integral-global-v1`。在每次真實任務派送時觀測，採取Local／Edge／Cloud action，前進到下一次真實決策，收取途中所有未完成工作持續占用系統的成本。新增 `IntegralSimulator` 僅在原模擬器的arrival／finish邊界維護已到達未終止的task_id集合；`IntegralEnv`沿用原Bridge與事件循環。原四個核心檔未修改。

令到達時間a_i、終止時間c_i，N(t)=sum_i 1[a_i≤t<c_i]。有限任務流、complete_all下：

```text
∫ N(t) dt = Σ_i ∫ 1[a_i≤t<c_i] dt = Σ_i(c_i-a_i)
r_k = - integral_[decision_k,next_decision_or_drain] N(t)dt / 1000
      - 此區間首次結算的Deadline miss數
Σ_k r_k = -Σ_i latency_i_ms/1000 - Σ_i miss_i
```

每個到達及完成事件前，先以當時active數乘經過時間加入積分，再更新集合。每次step讀到目前時點的累計積分差。只在真實完成時從原始結果讀deadline_met，settled_ids防重複；期限到達時不另外扣一次。任何尚未完成工作都不需要預知actual_workload或未來完成時點。

gamma=1，目標是有限回合的未折扣系統總成本。固定N時除以N即平均延遲秒數加miss rate，各miss等價1秒延遲的tradeoff，並非Deadline優先的字典式目標。原complete_all確保所有工作最後結算。最後Action之後繼續積分排空，所有成本完整列入最後轉移。這仍可能有大的terminal reward，但它代表真正的剩餘持有成本，不會再次加入先前已積分的延遲。

Replay的非終止轉移使用真正下一次決策的49維觀測，episode_done=False，bootstrap非零。最後next observation為None，episode_done=True；由於既有remember介面仍驗證向量，儲存上一個合法向量作遮罩後的容器佔位，不稱為真實next state。Task_done只描述該區間完成的task_id，可在episode_done=False時發生；最後一次step可有多個task_done。

這建立合法、無前視的Sequential Observation Transition。49維仍是估計量、缺少完整任務歷史與剩餘任務數，無法證明是完全Markov充分狀態。嚴格描述為部分可觀測系統上的前饋DQN／DDQN；全歷史可定義belief state，但本輪沒有加入RNN或假造未來資訊。長期target有實作，最優性與收斂仍須驗證。

受控completion基準也設gamma=1，使兩者同一完整回合的總成本相等，只比較Reward在事件間的分布。這避免把gamma改變的效果混入時間積分效果。舊gamma=.99結果只保留為歷史，未混入本輪比較。Gamma1在有限、可排空episode下目標有限，但非線性off-policy函數近似的穩定性沒有一般保證。

