# 正式工作量估計器評估

固定split：LFW與WIDER_train各40 training /20 validation /100 test。僅80張training擬合，40張validation選參；200張test在選模JSON落盤後才評估。選定Ridge=ridge_log-10；Median預設未更換。

特徵保持前輪三項：檔案MB、總像素/1e6、log(width/height)，只用training mean/std標準化。候選Median、raw/log ridge α=0.1/1/10共7個，無新增特徵或以test挑α。真實人臉數、長推論時間分組只用於事後分析。實際SimPy compute始終取CSV inference_ms/speed。

## 所有候選的最終測試

|資料集|候選|n|MAE|RMSE|Bias||error|P50||error|P95|
|---|---|---|---|---|---|---|---|
|lfw|median|100|74.749|111.891|-17.507|44.015|253.193|
|lfw|ridge_raw-0.1|100|81.360|111.300|1.441|59.759|243.153|
|lfw|ridge_raw-1|100|83.050|111.180|5.533|63.600|241.699|
|lfw|ridge_raw-10|100|95.328|114.590|30.962|77.739|243.408|
|lfw|ridge_log-0.1|100|74.972|112.122|-16.872|45.069|252.121|
|lfw|ridge_log-1|100|75.483|111.755|-14.998|46.935|250.367|
|lfw|ridge_log-10|100|79.169|110.469|-3.111|58.100|238.924|
|wider_train|median|100|626.352|1393.634|-588.406|105.748|2824.880|
|wider_train|ridge_raw-0.1|100|827.167|1356.804|-8.807|595.353|2827.709|
|wider_train|ridge_raw-1|100|814.493|1346.262|-14.538|618.711|2804.280|
|wider_train|ridge_raw-10|100|759.810|1305.729|-39.757|539.336|2715.471|
|wider_train|ridge_log-0.1|100|761.782|1379.594|-136.996|440.457|2899.075|
|wider_train|ridge_log-1|100|747.850|1366.512|-149.233|447.734|2901.494|
|wider_train|ridge_log-10|100|690.737|1322.025|-201.780|396.177|2877.760|

## 成對MAE差的群組bootstrap

Ridge−Median，負值較好。2000次，seed424242；LFW按人物、WIDER按事件資料夾重抽群組，保留群組內圖片。CI只描述這個凍結樣本的有限不確定性，不保證跨設備/全資料集表現。

|資料集|圖片|群組|MAE差|95%下界|95%上界|
|---|---|---|---|---|---|
|lfw|100|100|4.420|1.788|7.230|
|wider_train|100|16|64.385|-72.006|217.058|

## 事後困難子群（不作模型輸入或重選）

固定門檻：高解析度>=1MP、長推論>=1000ms、多人臉>=2。NO_SAMPLES表示該子群沒有測試圖片，不宣稱通過。所有候選子群完整CSV在evaluation/estimator_subgroups.csv。

|資料集|模型|子群|n|MAE|RMSE|Bias|狀態|
|---|---|---|---|---|---|---|---|
|lfw|median|high_resolution_ge1MP|0||||NO_SAMPLES|
|lfw|median|long_actual_ge1000ms|0||||NO_SAMPLES|
|lfw|median|multiple_faces_ge2|26|176.333928225806|196.73928285171553|-164.5916764944279|EVALUATED|
|lfw|ridge_log-10|high_resolution_ge1MP|0||||NO_SAMPLES|
|lfw|ridge_log-10|long_actual_ge1000ms|0||||NO_SAMPLES|
|lfw|ridge_log-10|multiple_faces_ge2|26|163.01118865055747|184.73722214486546|-150.15579174790412|EVALUATED|
|wider_train|median|high_resolution_ge1MP|30|410.2346187668445|994.5070807178357|-362.29311796099256|EVALUATED|
|wider_train|median|long_actual_ge1000ms|24|2183.07453832737|2822.618468951283|-2183.07453832737|EVALUATED|
|wider_train|median|multiple_faces_ge2|57|1064.5655233540565|1845.0707006112243|-1064.5655233540565|EVALUATED|
|wider_train|ridge_log-10|high_resolution_ge1MP|30|407.7417204371532|995.5331212468317|-382.603327074745|EVALUATED|
|wider_train|ridge_log-10|long_actual_ge1000ms|24|1784.3327765452823|2553.808896714633|-1776.0837830199596|EVALUATED|
|wider_train|ridge_log-10|multiple_faces_ge2|57|921.4070010475524|1692.0379423785237|-634.1110285781399|EVALUATED|

## 跨資料集

來源training擬合/來源validation選模，再測另一資料集的100張test；不使用目標test決定候選。

|train|test|模型|來源選定|MAE|RMSE|Bias|
|---|---|---|---|---|---|---|
|lfw|wider_train|median|median|633.936|1404.385|-613.436|
|wider_train|lfw|median|ridge_log-10|379.671|395.387|379.629|
|wider_train|lfw|ridge_log-10|ridge_log-10|1017.582|1023.732|1017.582|

![預測與實際時間](plots/prediction_scatter.png)

結論：這次選定Ridge在兩資料集的MAE點估計都較Median差：LFW差4.420ms，WIDER差64.385ms。LFW的95%群組CI完全為正，WIDER CI跨零，沒有Ridge改善的穩定證據。不以整體混合MAE宣稱勝出。即使某一資料集有改善，也沒有修改Median預設、測試圖、特徵或α。群組隔離對跨人物/事件泛化較嚴格；WIDER事件只是場景代理，不能保證所有人物或語意近重複皆已識別。
補充：選定Ridge在兩資料集的RMSE點估計較低、Bias較接近零；這是平均絕對誤差與平方誤差的取捨，不是所有指標都退步。RMSE/Bias沒有另做區間檢定，不能從點估計宣稱穩定優勢。選模目標事先固定validation MAE，因此不因test RMSE較好改變選模規則或預設。
證據：dataset_manifest.json、train_val_test_split.csv、evaluation/validation-selection.json、evaluation/models/ JSON、evaluation/estimator_predictions.csv；程式scripts/formal_dataset.py、formal_evaluate.py。
