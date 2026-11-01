# CNN 臉部辨識入門

使用 OpenCV 偵測人臉位置，再用自己訓練的小型 TensorFlow/Keras CNN 分類人物身分。支援照片與即時攝影機。

## 1. 安裝

建議使用 Python 3.11 或 3.12，在專案目錄執行：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

後續範例中的 `python` 可替換成 `.\.venv\Scripts\python`。CPU 即可執行。

## 2. 準備照片

每人一個資料夾，以姓名命名：

```text
data/
  Alice/
    01.jpg
    02.jpg
    ...
  Bob/
    01.jpg
    02.jpg
    ...
```

至少兩人，每人至少兩張可偵測的單人照片；實際建議每人 30–100 張，涵蓋不同光線、角度與表情。每張照片需恰好偵測到一張臉，否則略過。支援 JPG、PNG、BMP。

## 3. 訓練

```powershell
python face_cnn.py train --data data --epochs 30
```

每人約 20% 照片留作驗證，其餘用於訓練；資料增強僅在訓練時啟用。驗證損失連續 5 輪沒有改善時提早停止，保留最佳權重。模型及姓名對照表儲存於 `model/`。

## 4. 辨識

辨識照片，終端機輸出姓名及分數，並產生標註圖片：

```powershell
python face_cnn.py predict --image test.jpg --output result.jpg
```

使用攝影機，按小寫 Q 離開：

```powershell
python face_cnn.py predict
```

可用 `--camera 1` 切換攝影機、`--threshold 0.9` 調整門檻。中文姓名可作為訓練標籤並在照片模式的終端機結果顯示；OpenCV 圖片與視窗標籤建議使用英文姓名。

## 使用限制

這是入門範例，只學習資料夾中的已知人物。softmax 分數低於門檻會標為 `Unknown`，但高分也可能誤認陌生人；分數不是經校準的身分正確機率。少量照片或連拍照片切分所得的驗證準確率，不能代表實際使用效果；請另外用不同拍攝時段的照片測試。此範例不包含活體偵測，不適合作為門禁或登入驗證。

參考：[TensorFlow CNN 圖像分類](https://www.tensorflow.org/tutorials/images/classification)、[OpenCV 人臉偵測](https://docs.opencv.org/4.x/db/d28/tutorial_cascade_classifier.html)。
