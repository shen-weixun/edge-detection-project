# FaceLab 人臉視覺實驗室

React + FastAPI（Python 3.11）+ PostgreSQL 16 + InsightFace，使用 Docker Compose 部署。
保留原本 face_cnn.py 與 FACE_CNN_README.md；新網站不依賴舊的 TensorFlow 範例。

## 功能

- 上傳圖片，用 buffalo_l 的 SCRFD 偵測人臉框、五點特徵與信心分數。
- 兩張照片用 ArcFace 做 1:1 驗證；每張需恰好一張人臉。餘弦相似度預設門檻 0.4 尚未校準，相似度不是機率。
- 匯入並瀏覽 LFW 身分資料夾，以及 WIDER FACE train / val 官方框標註，選取樣本做偵測。
- PostgreSQL 保存樣本索引、標註、分析結果與時間；查看最近 30 次實驗並匯出目前結果 JSON。
- 上傳原圖與 embedding 不保存至磁碟或資料庫；資料集原圖使用唯讀掛載。

這是預訓練模型研究工作台，不包含訓練、1:N 身分搜尋、LFW pairs 官方交叉驗證或 WIDER 官方 AP 評估。資料集匯入不會微調模型。

## Docker 啟動

先啟動 Docker Desktop（Linux containers），在專案根目錄執行：

```powershell
Copy-Item backend/.env.example backend/.env # ?????????
New-Item -ItemType Directory -Force data
docker compose --env-file backend/.env up --build -d
```

網站：http://localhost:8080
API：http://localhost:8080/api/health
日誌：`docker compose --env-file backend/.env logs -f backend`
停止：`docker compose --env-file backend/.env down`，保留資料。加上 -v 會移除資料庫與模型 volume。

第一次建置需下載 Python 套件，第一次推論會下載並載入 buffalo_l 模型，可能需數分鐘。此版本使用 CPU。API 已連線不代表模型已載入。若下載失敗，檢查後端日誌與 GitHub 網路連線；亦可將合法取得的 ONNX 模型放入容器 /models/models/buffalo_l/。模型快取使用 Docker volume。

.env 可設定 PORT 與 POSTGRES_PASSWORD。密碼請使用英數字和連字號；URL 保留字元須另行編碼 DATABASE_URL。修改既有 volume 的環境密碼不會更新 PostgreSQL 帳號。

預設僅綁定 127.0.0.1，資料庫不對外開放。此版本無登入或權限隔離，本機使用者共用紀錄；對外部署前需加入登入、TLS、流量限制與資料保留政策。

## 資料集匯入

依授權從官方取得並解壓；專案不附帶或自動下載人臉資料集。

- LFW：https://vis-www.cs.umass.edu/lfw/
- WIDER FACE：http://shuoyang1213.me/WIDERFACE/

```text
data/
  lfw/Person_Name/Person_Name_0001.jpg
  WIDER_train/images/...
  WIDER_val/images/...
  wider_face_split/wider_face_train_bbx_gt.txt
  wider_face_split/wider_face_val_bbx_gt.txt
```

容器啟動後執行：

```powershell
docker compose --env-file backend/.env exec backend python -m app.import_dataset lfw --images lfw
docker compose --env-file backend/.env exec backend python -m app.import_dataset wider --images WIDER_train/images --annotations wider_face_split/wider_face_train_bbx_gt.txt --split train
docker compose --env-file backend/.env exec backend python -m app.import_dataset wider --images WIDER_val/images --annotations wider_face_split/wider_face_val_bbx_gt.txt --split val
```

匯入使用交易，出錯會回復；以資料集與路徑去重，重跑更新標籤和框，不重複新增。移除磁碟圖片不會自動刪除資料庫索引。完成後重新整理網站。WIDER FACE 無人物身分 ID，僅供偵測；LFW 標籤用於整理，網站不會從偵測結果猜人物姓名。WIDER invalid 框不納入匯入標註。

## 開發

前端：在 frontend 執行 npm ci、npm run dev、npm run build。Vite 將 /api 代理至 localhost:8000。
後端：使用 Python 3.11 安裝 backend/requirements.txt，設定 DATABASE_URL、DATASET_ROOT、MODEL_ROOT，在 backend 執行 python -m uvicorn app.main:app --reload。
本機後端需另行提供 PostgreSQL，Compose 的資料庫預設不暴露主機連接埠。根目錄 requirements.txt 屬於原本的 CNN 範例。

資料集解析測試（無需模型與資料庫）：

```powershell
cd backend
python -m unittest discover -s tests -v
```

主要 API：GET /api/health、GET /api/datasets、GET /api/samples?dataset=lfw、POST /api/detect（multipart file）、POST /api/verify（first、second、threshold）、POST /api/samples/{id}/detect、GET /api/history。

## 授權

InsightFace 程式碼與權重授權不同；官方預訓練模型預設限非商業研究，商用請取得適用授權。資料集亦須遵守各自條款。
參考：https://github.com/deepinsight/insightface/tree/master/python-package


## ????????

1. ?? Docker Desktop????????? `docker compose --env-file backend/.env up --build -d`?
2. ?? http://localhost:8080??????????????????????
3. ????????????????????????????????????????
4. ????? 0.4??????????????????????????????
5. ???????????????????? JSON??????????

??????????????????? 1???????????????????????????????????? 0.4 ???????????????????

???`docker compose --env-file backend/.env ps` ?????`docker compose --env-file backend/.env logs -f backend` ??????????????????????????????????

Docker ??????? db?????? Python ???? localhost?????????? PostgreSQL??? DATASET_ROOT / MODEL_ROOT ????????????? backend/.env ??Docker ????? up -d?????? --build???? Python ??????

## Local–Edge–Cloud 卸載模擬

詳見 [README_OFFLOADING.md](README_OFFLOADING.md)。
