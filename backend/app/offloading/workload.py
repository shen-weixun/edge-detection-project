"""Real-profile CSV loader and explicitly synthetic demo workload generator."""
import csv
import random
from pathlib import Path
from .models import Task
from statistics import median
from math import isfinite
import posixpath


def source_identity(source_path):
    """Dataset labels cannot turn the same relative file into a new image."""
    return posixpath.normpath(str(source_path).replace('\\', '/'))


def calibration_estimate(training, testing):
    """Constant historical median, fitted only to a disjoint calibration set."""
    def identities(rows):
        return {source_identity(r.get('source_path', '')) for r in rows}
    if not training or any(not r.get('source_path') for r in training + testing):
        raise ValueError('Calibration and test rows require source identities')
    if identities(training) & identities(testing):
        raise ValueError('Calibration/test image overlap')
    value = median(r['workload_ms'] for r in training)
    if not isfinite(value) or value <= 0:
        raise ValueError('Invalid calibration workload')
    return value


def load_profile(path):
    rows = []
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        for item in csv.DictReader(f):
            if item.get('success') != 'True':
                if item.get('success') == 'False':
                    continue
                raise ValueError('CSV 缺少實測成功標記，不能作為正式 Profile')
            if int(item.get('repeats', 0)) < 3 or item.get('model') != 'buffalo_l':
                raise ValueError('CSV 必須使用 buffalo_l 並至少重複量測三次')
            image_mb = float(item["image_size_mb"])
            face_count = int(item["face_count"])
            workload_ms = float(item["inference_ms"])
            # Reuse Task's validation: no negative, nonfinite or zero workloads.
            Task(0, image_mb, face_count, workload_ms, 0, 1000)
            rows.append(dict(image_size_mb=image_mb, face_count=face_count, workload_ms=workload_ms,
                             source_path=item['source_path'], dataset=item['dataset'], sample_id=item['sample_id'],
                             width=int(item.get('width') or 0), height=int(item.get('height') or 0)))
    if not rows:
        raise ValueError("Workload Profile CSV is empty")
    return rows


def generate_tasks(count=30, interval_ms=70.0, seed=42, deadline_ms=500.0,
                   profile=None):
    if not 1 <= count <= 500 or not isfinite(interval_ms) or not isfinite(deadline_ms) or interval_ms <= 0 or deadline_ms <= 0:
        raise ValueError("invalid task configuration")
    rng = random.Random(seed)
    # These are DEMO assumptions, NOT InsightFace measurements.
    demos = [(0.25, 1, 65.0), (0.8, 2, 130.0),
             (1.5, 4, 210.0), (3.0, 6, 330.0)]
    source = profile if profile is not None else demos
    if not source:
        raise ValueError("profile must not be empty")
    tasks = []
    if profile is not None and count > len(profile):
        raise ValueError('任務數超過成功量測圖片數；請減少任務數或建立較大的 Profile')
    measured = rng.sample(profile, count) if profile is not None else None
    for task_id in range(count):
        if measured is not None:
            tasks.append(Task(task_id=task_id, arrival_ms=task_id*interval_ms,
                              deadline_ms=deadline_ms, **measured[task_id]))
        else:
            image_size_mb, face_count, inference_ms = rng.choice(source)
            tasks.append(Task(task_id, image_size_mb, face_count,
                              inference_ms, task_id * interval_ms, deadline_ms))
    return tasks
