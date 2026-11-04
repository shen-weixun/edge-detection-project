import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select, func, text
from .db import Base, engine, Session, Sample, Run
from .datasets import safe_path
from . import inference
from .execution import Strategy, execute_local
from .offloading.api import router as offloading_router

@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    yield

app = FastAPI(title="FaceLab API", lifespan=lifespan)
app.include_router(offloading_router)
root = Path(os.getenv("DATASET_ROOT", "/datasets")).resolve()

def run(kind, fn, strategy: Strategy = 'fixed'):
    if strategy != 'fixed':
        raise HTTPException(422, '此端點僅執行本機 InsightFace；請到模擬器選擇卸載策略。DQN/DDQN 尚未實作。')
    try:
        result = execute_local(fn, strategy)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        logging.exception("Inference failed")
        raise HTTPException(503, "模型尚未就緒或推論失敗，請檢查模型下載及後端日誌") from exc
    with Session.begin() as session:
        record = Run(kind=kind, result=result)
        session.add(record)
        session.flush()
        return {**result, "run_id": record.id}

def read_upload(file):
    return inference.decode(file.file.read(inference.MAX_BYTES + 1))

@app.get("/api/health")
def health():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"database": "ready", "model": "ready" if inference.model is not None else "loads_on_first_request"}

@app.post("/api/detect")
def detect(file: UploadFile = File(...), strategy: Strategy = Form('fixed')):
    return run("detect", lambda: inference.detection(read_upload(file)), strategy)

@app.post("/api/verify")
def verify(first: UploadFile = File(...), second: UploadFile = File(...), threshold: float = Form(0.4, ge=-1, le=1), strategy: Strategy = Form('fixed')):
    return run("verify", lambda: inference.verify(read_upload(first), read_upload(second), threshold), strategy)

@app.get("/api/datasets")
def datasets():
    with Session() as session:
        return [{"name": name, "count": count} for name, count in session.execute(select(Sample.dataset, func.count()).group_by(Sample.dataset))]

@app.get("/api/samples")
def samples(dataset: str = "lfw", offset: int = Query(0, ge=0), limit: int = Query(24, ge=1, le=100)):
    with Session() as session:
        rows = session.scalars(select(Sample).where(Sample.dataset == dataset).order_by(Sample.id).offset(offset).limit(limit))
        return [{"id": r.id, "label": r.label, "boxes": r.boxes, "url": f"/api/samples/{r.id}/image"} for r in rows]

def sample_path(id):
    with Session() as session:
        record = session.get(Sample, id)
        if not record:
            raise HTTPException(404, "找不到圖片")
        try:
            path = safe_path(root, record.path)
        except ValueError as exc:
            raise HTTPException(404, "圖片路徑無效") from exc
        if not path.is_file():
            raise HTTPException(404, "資料集圖片已移除")
        return path

@app.get("/api/samples/{id}/image")
def sample_image(id: int):
    return FileResponse(sample_path(id))

@app.post("/api/samples/{id}/detect")
def sample_detect(id: int, strategy: Strategy = Form('fixed')):
    path = sample_path(id)
    def action():
        with path.open("rb") as stream:
            return inference.detection(inference.decode(stream.read(inference.MAX_BYTES + 1)))
    return run("detect", action, strategy)

@app.get("/api/history")
def history():
    with Session() as session:
        return [{"id": r.id, "kind": r.kind, "result": r.result, "created_at": r.created_at.isoformat()} for r in session.scalars(select(Run).order_by(Run.id.desc()).limit(30))]
