"""Dedicated offloading experiment API; existing image detection stays local."""
import os
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from typing import Literal
from pydantic import BaseModel, Field
from .experiment import experiment
from .models import NodeConfig
from .workload import load_profile
from . import profiles

router = APIRouter(prefix="/api/offloading", tags=["offloading"])


class NodeParameters(BaseModel):
    speed: float = Field(gt=0, le=100)
    rtt_ms: float = Field(ge=0, le=5000)
    bandwidth_mbps: float = Field(gt=0, le=100000)


class ExperimentRequest(BaseModel):
    strategies: list[str] = Field(default_factory=lambda: [
        "local_only", "edge_only", "cloud_only", "load_threshold", "latency_aware"])
    count: int = Field(default=30, ge=1, le=500)
    interval_ms: float = Field(default=70, gt=0, le=60_000)
    deadline_ms: float = Field(default=500, gt=0, le=120_000)
    seed: int = Field(default=42, ge=0, le=2**31-1)
    include_decision_overhead: bool = True
    use_measured_profile: bool = False
    workload_mode: Literal['measured', 'synthetic'] | None = None
    profile_id: str | None = None
    nodes: dict[str, NodeParameters] | None = None


@router.get("/status")
def offloading_status():
    profile_path = Path(os.getenv("WORKLOAD_PROFILE_PATH", "/datasets/offloading_profile.csv"))
    return {
        "simulation": "SimPy - independent from physical image inference",
        "available_strategies": ["local_only", "edge_only", "cloud_only",
                                 "load_threshold", "latency_aware", "laya"],
        "not_implemented": ["dqn", "ddqn"],
        "measured_profile_available": any(p['status']=='completed' for p in profiles.listing()),
        "laya_service": "optional; docker compose -f compose.yaml -f compose.ai.yaml up -d --build",
    }


@router.post("/experiments")
def run_experiment(request: ExperimentRequest):
    if not request.strategies:
        raise HTTPException(status_code=422, detail="Choose at least one strategy")
    if len(request.strategies) > 6:
        raise HTTPException(status_code=422, detail="Too many strategies")
    if "laya" in request.strategies and request.count > 50:
        raise HTTPException(status_code=422, detail="Laya is limited to 50 tasks per request")
    if request.nodes is not None and set(request.nodes) != {"local", "edge", "cloud"}:
        raise HTTPException(status_code=422, detail="nodes must contain exactly local, edge, cloud")
    if request.nodes and (request.nodes['local'].speed != 1 or request.nodes['local'].rtt_ms != 0):
        raise HTTPException(422, 'Local 必須維持實測參考算力 1 與 RTT 0')
    try:
        profile = None
        meta = None
        mode = request.workload_mode or ('measured' if request.use_measured_profile else 'synthetic')
        if mode == 'synthetic' and (request.profile_id or request.use_measured_profile):
            raise ValueError('Synthetic 模式不可同時指定實測 Profile')
        if mode == 'measured':
            if not request.profile_id:
                raise ValueError('請先完成量測並選擇 Profile；不會切換為合成資料')
            meta, profile = profiles.load(request.profile_id)
        result = experiment(strategies=request.strategies,
                          count=request.count, interval_ms=request.interval_ms,
                          seed=request.seed, deadline_ms=request.deadline_ms,
                          include_decision_overhead=request.include_decision_overhead,
                          profile=profile,
                          nodes={k: NodeConfig(**v.model_dump()) for k, v in request.nodes.items()}
                          if request.nodes else None)
        result['profile'] = meta
        return result
    except (ValueError, FileNotFoundError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

class ProfileRequest(BaseModel):
    dataset: Literal['lfw', 'wider_train', 'wider_val']
    count: int = Field(default=30, ge=1, le=500)
    seed: int = Field(default=42, ge=0, le=2**31-1)
    repeats: int = Field(default=3, ge=3, le=20)

@router.get('/profiles')
def list_profiles():
    return profiles.listing()

@router.post('/profiles', status_code=202)
def create_profile(request: ProfileRequest):
    try:
        return profiles.start(**request.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc

@router.get('/profiles/{identifier}')
def get_profile(identifier: str):
    try:
        return profiles.get(identifier)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(404, str(exc)) from exc

@router.get('/profiles/{identifier}/csv')
def profile_csv(identifier: str):
    get_profile(identifier)
    path = profiles.path_for(identifier, '.csv')
    if not path.is_file():
        raise HTTPException(404, 'CSV 尚未產生')
    return FileResponse(path, media_type='text/csv', filename=identifier+'.csv')
