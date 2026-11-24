# Reward 與事件時序驗證

測試程式 `backend/tests/test_integral_rl.py`，完整執行 `python -m unittest discover -s tests -v`，99項通過。原始JSON證據在 `evidence/reward-timing.json`、`evidence/bootstrap-targets.json`；訓練每個episode的任務原始結果、轉移、積分事件及獨立重算值在各run的 `training.jsonl`。

|案例|預期／實際驗證|判定|
|---|---|---|
|A慢Local、B後到先完成|完成ID依次[]、[1]、[2,0]；最後一個step才episode_done；累積cost等於所有任務延遲秒數+miss|PASS|
|三節點同時完成|3個任務各100ms延遲，期限50ms，總積分300ms、miss3、總Reward=-3.3|PASS|
|最後排空|最後next observation=None，所有active清空、各task只結算一次|PASS|
|不同間隔|到達0/2/30、Local工作10/5/2；面積2+16+5+0+2=25ms，Reward=-.025|PASS|
|不可預知真值|第一任務actual100/300，t=5皆未完成，下一觀測完全相同，Reward皆-.005|PASS|
|Task_done與Episode_done|中途有完成但episode未結束，最後可多筆完成|PASS|
|合法Next State|同任務流／action逐步與原OffloadingEnv的feature_vector完全相同|PASS|
|非零Bootstrap|online Q=[3,1,0]、target Q=[1,4,0]、r=-.2、gamma1；DQN y=3.8、DDQN y=.8|PASS|
|全流成本核算|每回合用原始arrival/completed時點重建另一份事件sweep積分，和latency加總及Reward核對|由獨立報表稽核|

首次容器複製目錄產生巢狀路徑，測試無法匯入新增模組。改為逐檔複製至確定路徑後重跑通過，首次錯誤保存在 `logs/first-container-copy.log`。沒有降低測試誤差門檻。浮點誤差限制為1e-6；獨立稽核的實際最大誤差記於 `independent-audit.json`。

