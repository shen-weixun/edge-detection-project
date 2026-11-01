import io
import os
from threading import Lock
import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 10 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 20_000_000
lock = Lock()
model = None

def decode(data: bytes):
    if len(data) > MAX_BYTES:
        raise ValueError("圖片上限為 10 MB")
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.width * source.height > 20_000_000:
                raise ValueError("圖片上限為 2,000 萬像素")
            rgb = ImageOps.exif_transpose(source).convert("RGB")
            return cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("無法讀取圖片，請使用 JPEG 或 PNG") from exc

def analyze(image):
    global model
    with lock:
        if model is None:
            from insightface.app import FaceAnalysis
            instance = FaceAnalysis(name="buffalo_l", root=os.getenv("MODEL_ROOT", "/models"), allowed_modules=["detection", "recognition"], providers=["CPUExecutionProvider"])
            instance.prepare(ctx_id=-1, det_size=(640, 640), det_thresh=0.5)
            model = instance
        return model.get(image)

def detection(image):
    faces = analyze(image)
    return {"width": image.shape[1], "height": image.shape[0], "faces": [{"bbox": f.bbox.tolist(), "score": float(f.det_score), "landmarks": f.kps.tolist()} for f in faces]}

def verify(first, second, threshold):
    a, b = analyze(first), analyze(second)
    if len(a) != 1 or len(b) != 1:
        raise ValueError("驗證時，每張圖片必須恰好包含一張人臉")
    similarity = float(np.clip(np.dot(a[0].normed_embedding, b[0].normed_embedding), -1, 1))
    return {"similarity": similarity, "threshold": threshold, "match": similarity >= threshold, "note": "研究用途；門檻需依驗證集校準，相似度不是機率。"}
