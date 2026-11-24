# 工作量估計器評估

結論：新增可解釋且可保存的三特徵ridge；驗證集選出log-ridge α=10。最終測試WIDER有點估計改善、LFW退步，兩個MAE差的95%區間都跨零；因此保留Median為預設，不宣稱全面或顯著提升。

## 量測與事先固定分割

LFW與WIDER_train各新量測60張（seed271828），每張先預熱再正式3次取中位數；讀取/解碼/載入與鎖等待分開。固定seed314159，各36/12/12張為training/validation/test；合計72/24/24，來源正規化與圖片SHA256皆跨分割零重疊。所有方法在完全相同24張held-out圖片評估，沒有刪除不利結果。WIDER_train是資料集名稱，本次另做獨立影像分割，並非把官方train當作最終模型訓練全體。
測試Profile：LFW `efd4b190bb52a39666b3616c3df22927`；WIDER `03a2cb08e86b52b710d32a839effbc8b`。訓練與選模清單在split-manifest.json；重複內容排除紀錄數=0。

## 方法、特徵與保存

- Median：72張訓練推論時間的中位數，作所有策略相同的先驗。
- Raw ridge：y=b0+b·z；log-ridge：yhat=exp(b0+b·z)。z是以training mean/std標準化的 [檔案MB、總像素/1e6、log(width/height)]。只有三個推論前特徵，禁止人臉數、待測真值、路徑或sample_id成為特徵。
- α候選事先固定0.1/1/10，共Median+6個ridge候選；只依validation MAE選擇。沒有改成test表現最佳的另一候選，也沒有大型模型/Random Forest參數搜尋。
- 係數、center、scale、training/validation identities與schema保存JSON；以內容SHA256 ID註冊，重新載入驗證checksum。API會拒絕含training或validation圖片的測試Profile。實際服務時間始終是原CSV真值，預估僅用在DecisionTask與承諾工作ledger。
- 新模型在policy選擇內實際重新計算一次，因此預測耗時被既有SimPy決策timer統一計入；預先算出的值只供模擬器bookkeeping，準備工作不冒充裝置執行。Median預設舊API行為不變。
選定係數（標準化後log尺度）=[6.388618119862404, 0.12409584990353074, 0.042192674903080735, 0.2799231225238517]；center=[0.05954512499999999, 0.43039666666666665, 0.15407612493212408]；scale=[0.049306972407261895, 0.40421198326345764, 0.23700360731191036]。細節見estimators.py。

## 僅驗證集選模

|候選|validation MAE ms|validation RMSE ms|
|---|---|---|
|median|295.484|530.495|
|ridge_raw-0.1|273.920|394.266|
|ridge_raw-1.0|272.441|391.942|
|ridge_raw-10.0|266.677|380.331|
|ridge_log-0.1|243.530|361.731|
|ridge_log-1.0|243.089|361.129|
|ridge_log-10.0|239.502|359.255|

## 最終測試：所有候選完整揭露

bias=mean(預估−實際)，正數為高估。所有欄位均為ms；完整誤差分布含signed P05/P50/P95與absolute P95，見estimator-test-metrics.csv。

|資料集|方法|n|MAE|RMSE|偏差||error| P95|
|---|---|---|---|---|---|---|
|lfw|median|12|36.104|42.597|-18.241|70.185|
|lfw|ridge_raw-0.1|12|39.207|44.843|-25.991|72.328|
|lfw|ridge_raw-1.0|12|38.538|44.153|-24.648|71.358|
|lfw|ridge_raw-10.0|12|32.351|37.937|-8.377|59.010|
|lfw|ridge_log-0.1|12|44.874|53.002|-37.287|87.266|
|lfw|ridge_log-1.0|12|44.483|52.475|-36.505|86.557|
|lfw|ridge_log-10.0|12|40.423|47.266|-28.383|78.690|
|wider|median|12|598.201|1034.004|-556.299|2302.945|
|wider|ridge_raw-0.1|12|594.135|745.812|-100.323|1460.158|
|wider|ridge_raw-1.0|12|591.286|746.434|-96.964|1465.273|
|wider|ridge_raw-10.0|12|573.748|754.139|-84.240|1511.616|
|wider|ridge_log-0.1|12|538.750|782.787|-227.945|1673.600|
|wider|ridge_log-1.0|12|538.254|784.719|-228.534|1679.921|
|wider|ridge_log-10.0|12|536.625|800.583|-237.282|1733.817|

## 成對差異與跨資料集

下表是feature MAE−Median MAE；負數才代表feature較好。paired bootstrap2000次，seed424242；每資料集僅12測試圖，不能外推所有圖片分布。

|資料集|MAE差 ms|95%下界|95%上界|
|---|---|---|---|
|lfw|4.319|-0.779|9.029|
|wider|-61.575|-262.804|146.518|

跨資料集只在來源資料集的training/validation挑模型，再評估另一資料集test；沒有利用目標test調參。

|train→test|來源validation選定|test MAE|test RMSE|偏差|
|---|---|---|---|---|
|lfw→wider|median-1.0|601.168|1052.176|-589.388|
|wider→lfw|ridge_log-1.0|663.667|664.691|663.667|

限制：原圖尺寸不能直接揭露完成後的人臉數；WIDER的偵測後逐臉辨識工作仍可能造成長尾，這些安全特徵不足以完全識別工作量。當前只有一個量測host、各12張test、沒有跨設備跑分。保留Median，不能以某個test較好的未選候選換掉已凍結模型。

程式：backend/app/offloading/estimators.py、scripts/train_workload_estimators.py；模型檔models/、estimator-predictions.csv、validation-selection.json提供逐圖與選模證據。

## 原文核對與採用範圍

- [論文A原文](https://openaccess.thecvf.com/content/ICCV2023W/RCV/papers/Biswas_Characterizing_Face_Recognition_for_Resource_Efficient_Deployment_on_Edge_ICCVW_2023_paper.pdf)：§2.1.2的預熱/分離量測；§2.2 Eq(1)-(2)用架構與參數數量預測設備throughput，§3.1討論解析度；其量測不含偵測，本專案為完整偵測與辨識管線。本文僅借鏡實測與可解釋校準，不把該式宣稱為逐圖InsightFace時間預測的重現。
- [LEAOT原文](https://thesai.org/Downloads/Volume17No8/Paper_77-LEAOT_Load_Deadline_Latency.pdf)：§III-B Eq(2)-(6)為虛擬工作、queue/speed、傳輸與完成時間；§III-C Eq(9)為相對Deadline超時壓力。未重現Eq(7)-(12)的能量/基礎設施加權分數，也未在固定bandwidth模型中虛構EWMA改善。
- [MARPLE出版社頁](https://www.sciencedirect.com/science/article/abs/pii/S1569190X26000419)：可取得的§5.1/5.2內容描述歷史估計與低開銷決策，作成本評估動機；直接全文請求403，作者稿封存至2027。沒有聲稱重現其AoK/MILP或完整演算法。
- [三層人臉卸載論文D](https://onlinelibrary.wiley.com/doi/abs/10.1002/nem.2146)：僅取得出版社摘要，全文403。僅作三層架構背景，不編造方法章節/公式，不實作其DRL。
A/B原文已下載、抽取並視覺核對公式頁；存取限制記錄於paper-access.json。本文所有V2都是paper-inspired，並非論文完整重現。
