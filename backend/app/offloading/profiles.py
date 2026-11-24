"""Durable, asynchronous measurement of imported images with the shared InsightFace model."""
import csv
import hashlib
import json
import os
import platform
import random
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from time import perf_counter
from sqlalchemy import select
from .. import inference
from ..db import Session, Sample
from ..datasets import safe_path

FIELDS = ['sample_id', 'source_path', 'dataset', 'image_size_mb', 'width', 'height',
          'face_count', 'inference_ms', 'read_ms', 'decode_ms', 'warmup_ms',
          'repeats', 'inference_samples_ms', 'device', 'model', 'success', 'error']
guard = threading.Lock()
active = None

def root():
    path = Path(os.getenv('PROFILE_ROOT', '/profiles'))
    path.mkdir(parents=True, exist_ok=True)
    return path

def path_for(identifier, suffix='.json'):
    if not re.fullmatch(r'[0-9a-f]{32}', identifier):
        raise ValueError('Profile ID 無效')
    return root() / (identifier + suffix)

def save(meta):
    path = path_for(meta['id'])
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(meta, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    temporary.replace(path)

def get(identifier):
    meta = json.loads(path_for(identifier).read_text(encoding='utf-8'))
    if meta['status'] == 'running' and identifier != active:
        meta.update(status='interrupted', error='後端重啟中斷量測；請建立新工作，部分 CSV 保留供檢查')
        save(meta)
    return meta

def listing():
    return sorted((get(p.stem) for p in root().glob('*.json')), key=lambda m: m['created_at'], reverse=True)

def start(dataset, count, seed, repeats):
    global active
    with guard:
        if active:
            raise RuntimeError('已有量測工作進行中，請等候完成')
        with Session() as session:
            candidates = list(session.execute(select(Sample.id, Sample.path).where(Sample.dataset == dataset).order_by(Sample.id)))
        if len(candidates) < count:
            raise ValueError(f'{dataset} 已匯入 {len(candidates)} 張，少於要求的 {count} 張')
        selected = random.Random(seed).sample(candidates, count)
        identifier = uuid.uuid4().hex
        meta = dict(id=identifier, dataset=dataset, count=count, seed=seed, repeats=repeats,
                    status='running', completed=0, succeeded=0, failed=0,
                    created_at=datetime.now(timezone.utc).isoformat(),
                    device={'host': platform.node(), 'machine': platform.machine(), 'processor': platform.processor(),
                            'platform': platform.platform(), 'provider': 'CPUExecutionProvider'},
                    model='InsightFace buffalo_l; detection + recognition; det_size=640x640; threshold=0.5',
                    timing_scope='read/decode measured separately; inference median excludes model initialization, warmup and lock wait',
                    selected_samples=[{'sample_id': i, 'source_path': p} for i,p in selected])
        active = identifier
        save(meta)
        threading.Thread(target=run, args=(meta, selected), daemon=True).start()
        return meta

def measure_row(sample_id, relative, dataset, repeats):
    row = dict.fromkeys(FIELDS, '')
    row.update(sample_id=sample_id, source_path=relative, dataset=dataset, repeats=repeats,
               device='CPUExecutionProvider', model='buffalo_l', success=False)
    try:
        path = safe_path(Path(os.getenv('DATASET_ROOT', '/datasets')), relative)
        t = perf_counter()
        with path.open('rb') as stream:
            raw = stream.read(inference.MAX_BYTES + 1)
        row['read_ms'] = (perf_counter() - t) * 1000
        row['image_size_mb'] = path.stat().st_size / 1_000_000
        t = perf_counter()
        image = inference.decode(raw)
        row.update(decode_ms=(perf_counter()-t)*1000, width=image.shape[1], height=image.shape[0])
        _, row['warmup_ms'] = inference.measure(image)
        timings = []
        for _ in range(repeats):
            faces, elapsed = inference.measure(image)
            timings.append(elapsed)
        row.update(face_count=len(faces), inference_ms=median(timings),
                   inference_samples_ms=json.dumps(timings), success=True)
    except Exception as exc:
        row['error'] = f'{type(exc).__name__}: {exc}'
    return row

def run(meta, selected):
    global active
    values = []
    try:
        cold = inference.model is None
        t = perf_counter()
        inference.initialize_model()
        meta.update(initialization_ms=(perf_counter()-t)*1000, cold_initialization=cold)
        import insightface, onnxruntime
        meta['versions'] = {'insightface': insightface.__version__, 'onnxruntime': onnxruntime.__version__}
        with path_for(meta['id'], '.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            for identifier, relative in selected:
                row = measure_row(identifier, relative, meta['dataset'], meta['repeats'])
                writer.writerow(row)
                stream.flush()
                meta['completed'] += 1
                meta['succeeded' if row['success'] else 'failed'] += 1
                if row['success']:
                    values.append(row['inference_ms'])
                meta.update(mean_inference_ms=mean(values) if values else None,
                            median_inference_ms=median(values) if values else None)
                save(meta)
        meta['csv_sha256'] = hashlib.sha256(path_for(meta['id'], '.csv').read_bytes()).hexdigest()
        meta['status'] = 'completed' if values else 'failed'
        if not values:
            meta['error'] = '所有圖片量測失敗，請下載 CSV 查看原因'
    except Exception as exc:
        meta.update(status='failed', error=f'{type(exc).__name__}: {exc}')
    finally:
        meta['finished_at'] = datetime.now(timezone.utc).isoformat()
        save(meta)
        with guard:
            active = None

def load(identifier):
    from .workload import load_profile
    meta = get(identifier)
    if meta['status'] != 'completed' or not meta['succeeded']:
        raise ValueError('Profile 尚未完成或沒有成功量測的圖片')
    path = path_for(identifier, '.csv')
    if hashlib.sha256(path.read_bytes()).hexdigest() != meta['csv_sha256']:
        raise ValueError('Profile CSV 校驗失敗，檔案已變動')
    return meta, load_profile(path)
