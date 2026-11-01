# 策略與耗時

偵測、雙圖驗證、資料集樣本偵測均接受 multipart `strategy`：

| API 值 | 介面名稱 |
| --- | --- |
| fixed | 固定式／門檻策略 |
| latency_aware | Latency-aware |
| dqn_ddqn | DQN／DDQN |
| decision_model | 決策模型（進階） |

省略時使用 fixed；其他值由 FastAPI 回應 422。
目前全部走相同本地基線，尚未實作強化學習決策或遠端卸載。

成功結果新增 strategy、execution_target=device、execution_mode=local_baseline、timings_ms 與 timing_scope，並一併保存於 PostgreSQL 的 result JSON。
timings_ms.device 使用單調時鐘測量本地後端處理，單位毫秒，含圖片解碼、必要的模型初始化、鎖等待、推論（驗證含兩張圖片與相似度計算），不含網路上傳或資料庫寫入。資料集請求也包含圖片讀檔。
edge 與 cloud 目前為 null，介面顯示「未執行」，不是 0 毫秒的量測結果。device 在此指本機 Python 後端，不代表瀏覽器端執行模型。
