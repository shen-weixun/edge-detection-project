# 組員待補資料與正式整合阻擋

**DQN/DDQN FORMAL INTEGRATION: BLOCKED**

目前只可證明權重可執行，不能證明它對應這套SimPy或凍結test。請組員提供下列可驗證資料，不能用七個示範數字或權重形狀替代。

|必要資料|需要的具體證據|
|---|---|
|七維名稱/順序/單位|原訓練environment state builder；逐欄物理定義、時間點與可觀測來源|
|正規化|每欄公式、mean/std或min/max、clip/default值、scaler檔與SHA，證明僅fit training|
|訓練/驗證/測試資料|圖片source/hash/group與split manifest；與正式LFW/WIDER100圖test交集檢查|
|Reward/轉移/Done|reward公式、單位、延遲完成credit attribution、episode終止與reset|
|Action mapping|訓練時0/1/2代表的節點，不能只引用本次CLI顯示文字|
|Environment與參數|訓練SimPy或其他環境程式/版本、CPU/link競爭、RTT/BW/speed/deadline/drop規則|
|訓練證據|seed/超參數、episode/update steps、loss/reward logs、選checkpoint規則與權重SHA|
|Golden fixtures|至少數組原可觀測state→預期normalized7→Q-values→action，以驗證轉接不是猜測|

收到資料後才可評估七維是否能由現有49維合法重建。若需要觀測窗CPU百分比、其他歷史量或訓練用了未來真值，不能直接取49維前七個、補零或拿CPU busy當百分比。應先提出相容性差異，再由組員確認/修正；本輪沒有更改他們演算法或權重。
合法Adapter需把特徵轉換/scaler與act(epsilon=0)放在select_node timer內，分開記錄Q/action與時間，使用相同run_policy/Simulator、Median、test subset、reset與Deadline。不得在test更新權重或以Latency-aware補錯。
本輪不擴大30圖：DQN契約gate未通過，Laya數值可靠性仍有限。不能宣稱DQN/DDQN已與Laya完成公平正式比較；目前只有八個可執行策略在相同10圖pilot下完成比較。
