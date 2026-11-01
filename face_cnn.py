"""簡單 CNN 臉部辨識：python face_cnn.py --help"""

import argparse
import json
from pathlib import Path

SIZE = 96
EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}


def load_dependencies():
    global cv2, np, tf
    try:
        import cv2
        import numpy as np
        import tensorflow as tf
    except ImportError as exc:
        raise SystemExit("請先安裝套件：python -m pip install -r requirements.txt") from exc


def detector():
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    if cascade.empty():
        raise ValueError("無法載入 OpenCV 人臉偵測器。")
    return cascade


def find_faces(image, cascade):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5,
                                    minSize=(40, 40))


def crop_face(image, box):
    x, y, w, h = box
    face = cv2.cvtColor(image[y:y + h, x:x + w], cv2.COLOR_BGR2RGB)
    return cv2.resize(face, (SIZE, SIZE))


def read_image(path):
    # 支援 Windows 中文路徑。
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)


def train(args):
    if not args.data.is_dir():
        raise ValueError(f"找不到資料夾：{args.data}")
    names = sorted(p.name for p in args.data.iterdir() if p.is_dir())
    if len(names) < 2:
        raise ValueError("至少需要兩個人物資料夾，例如 data/Alice、data/Bob。")
    cascade = detector()
    rng = np.random.default_rng(42)
    train_x, train_y, val_x, val_y = [], [], [], []
    for label, name in enumerate(names):
        faces = []
        for path in sorted((args.data / name).iterdir()):
            if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
                continue
            image = read_image(path)
            boxes = [] if image is None else find_faces(image, cascade)
            if len(boxes) != 1:
                print(f"略過 {path}：需要恰好一張可偵測的人臉。")
                continue
            faces.append(crop_face(image, boxes[0]))
        if len(faces) < 2:
            raise ValueError(f"{name} 至少需要兩張有效照片，建議準備 30–100 張。")
        rng.shuffle(faces)
        count = max(1, int(len(faces) * 0.2))
        val_x.extend(faces[:count])
        val_y.extend([label] * count)
        train_x.extend(faces[count:])
        train_y.extend([label] * (len(faces) - count))

    tf.keras.utils.set_random_seed(42)
    model = tf.keras.Sequential([
        tf.keras.layers.Input(shape=(SIZE, SIZE, 3)),
        tf.keras.layers.Rescaling(1.0 / 255),
        tf.keras.layers.RandomFlip("horizontal"),
        tf.keras.layers.RandomRotation(0.05),
        tf.keras.layers.Conv2D(32, 3, activation="relu"),
        tf.keras.layers.MaxPooling2D(),
        tf.keras.layers.Conv2D(64, 3, activation="relu"),
        tf.keras.layers.MaxPooling2D(),
        tf.keras.layers.Conv2D(128, 3, activation="relu"),
        tf.keras.layers.GlobalAveragePooling2D(),
        tf.keras.layers.Dropout(0.3),
        tf.keras.layers.Dense(len(names), activation="softmax"),
    ])
    model.compile(optimizer="adam", loss="sparse_categorical_crossentropy",
                  metrics=["accuracy"])
    model.fit(
        np.asarray(train_x), np.asarray(train_y),
        validation_data=(np.asarray(val_x), np.asarray(val_y)),
        epochs=args.epochs, batch_size=16,
        callbacks=[tf.keras.callbacks.EarlyStopping(
            monitor="val_loss", patience=5, restore_best_weights=True)],
    )
    args.model_dir.mkdir(parents=True, exist_ok=True)
    model.save(args.model_dir / "face.keras")
    (args.model_dir / "labels.json").write_text(
        json.dumps(names, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"模型已儲存至 {args.model_dir}")


def recognize(args):
    model = tf.keras.models.load_model(args.model_dir / "face.keras")
    names = json.loads((args.model_dir / "labels.json").read_text(encoding="utf-8"))
    cascade = detector()

    def annotate(frame):
        boxes = find_faces(frame, cascade)
        if len(boxes) == 0:
            return []
        batch = np.asarray([crop_face(frame, box) for box in boxes])
        scores = model.predict(batch, verbose=0)
        results = []
        for (x, y, w, h), score in zip(boxes, scores):
            index = int(np.argmax(score))
            confidence = float(score[index])
            name = names[index] if confidence >= args.threshold else "Unknown"
            results.append({"name": name, "score": round(confidence, 4)})
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            # OpenCV 預設字型不支援中文；中文姓名仍會完整輸出至終端機。
            display = name.encode("ascii", errors="replace").decode("ascii")
            cv2.putText(frame, f"{display} {confidence:.2f}", (x, max(20, y - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        return results

    if args.image:
        frame = read_image(args.image)
        if frame is None:
            raise ValueError(f"無法讀取圖片：{args.image}")
        results = annotate(frame)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        ok, encoded = cv2.imencode(".jpg", frame)
        if not ok:
            raise ValueError("無法編碼輸出圖片。")
        encoded.tofile(args.output)
        print(f"已輸出：{args.output}")
        return

    camera = cv2.VideoCapture(args.camera)
    try:
        if not camera.isOpened():
            raise ValueError("無法開啟攝影機，請檢查權限或調整 --camera。")
        print("按 Q 離開。")
        while True:
            ok, frame = camera.read()
            if not ok:
                raise ValueError("攝影機讀取失敗。")
            annotate(frame)
            cv2.imshow("CNN face recognition - Q to quit", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        camera.release()
        cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description="簡單 CNN 已知人物臉部辨識")
    commands = parser.add_subparsers(dest="command", required=True)
    training = commands.add_parser("train", help="依人物資料夾訓練 CNN")
    training.add_argument("--data", type=Path, default=Path("data"))
    training.add_argument("--epochs", type=int, default=30)
    prediction = commands.add_parser("predict", help="辨識圖片，或使用攝影機")
    prediction.add_argument("--image", type=Path)
    prediction.add_argument("--output", type=Path, default=Path("result.jpg"))
    prediction.add_argument("--camera", type=int, default=0)
    prediction.add_argument("--threshold", type=float, default=0.8)
    for command in (training, prediction):
        command.add_argument("--model-dir", type=Path, default=Path("model"))
    args = parser.parse_args()
    if args.command == "train" and args.epochs < 1:
        parser.error("--epochs 必須大於 0。")
    if args.command == "predict" and not 0 <= args.threshold <= 1:
        parser.error("--threshold 必須介於 0 和 1。")
    load_dependencies()
    try:
        (train if args.command == "train" else recognize)(args)
    except (OSError, ValueError, cv2.error) as exc:
        parser.exit(1, f"錯誤：{exc}\n")


if __name__ == "__main__":
    main()
