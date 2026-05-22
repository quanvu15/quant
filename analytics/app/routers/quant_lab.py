"""
Phase 5 — AI Quant Lab API router.

Long-running tasks (training, backtesting) use async job pattern:
  POST /backtest → {job_id, status: "queued"}
  GET  /jobs/{job_id} → {status, progress, ...}
  GET  /jobs/{job_id}/result → {result}
  WS   /jobs/{job_id}/stream → real-time progress (future)
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from app.dependencies import ApiKeyDep
from core.cache import cache
from core.errors import JobNotFoundError
from core.jobs import (
    JobStatus,
    cancel_job,
    create_job,
    get_job,
    list_jobs,
    run_job_async,
)
from core.python_runner import get_runner
from core.script_catalog import catalog

logger = structlog.get_logger(__name__)
router = APIRouter()


# ── 5.1 Job Management ────────────────────────────────────────────────────────

@router.get("/jobs", summary="List recent jobs")
async def list_all_jobs(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    _api_key: ApiKeyDep = None,
):
    jobs = await list_jobs(status=status, limit=limit)
    return {"jobs": jobs, "count": len(jobs)}


@router.get("/jobs/{job_id}", summary="Get job status and metadata")
async def get_job_status(job_id: str, _api_key: ApiKeyDep = None):
    job = await get_job(job_id)
    if not job:
        raise JobNotFoundError(job_id)
    # Return without result (use /result endpoint for that)
    return {k: v for k, v in job.items() if k != "result"}


@router.get("/jobs/{job_id}/result", summary="Get completed job result")
async def get_job_result(job_id: str, _api_key: ApiKeyDep = None):
    job = await get_job(job_id)
    if not job:
        raise JobNotFoundError(job_id)
    return {"job_id": job_id, "status": job["status"], "result": job.get("result")}


@router.delete("/jobs/{job_id}", summary="Cancel a queued or running job")
async def cancel_job_endpoint(job_id: str, _api_key: ApiKeyDep = None):
    cancelled = await cancel_job(job_id)
    return {"cancelled": cancelled, "job_id": job_id}


@router.websocket("/jobs/{job_id}/stream")
async def job_stream_ws(websocket: WebSocket, job_id: str):
    """WebSocket endpoint — streams job progress events until completion."""
    await websocket.accept()
    try:
        while True:
            job = await get_job(job_id)
            if not job:
                await websocket.send_json({"type": "error", "content": f"Job {job_id} not found"})
                break
            await websocket.send_json({
                "type": "progress",
                "job_id": job_id,
                "status": job["status"],
                "progress": job.get("progress", 0),
            })
            if job["status"] in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                await websocket.send_json({
                    "type": "done",
                    "job_id": job_id,
                    "status": job["status"],
                    "result": job.get("result"),
                    "error": job.get("error"),
                })
                break
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass


# ── 5.2 Backtesting ───────────────────────────────────────────────────────────

@router.post("/backtest", summary="Submit a backtest job", status_code=202)
async def submit_backtest(body: Dict[str, Any], _api_key: ApiKeyDep):
    """POST /api/v1/quant-lab/backtest → {job_id, status: queued}."""
    job_id = await create_job("backtest", body)
    payload = {"action": "run_backtest", "params": body}
    asyncio.create_task(run_job_async(job_id, "qlab.backtest", payload, timeout=600))
    return {"job_id": job_id, "status": JobStatus.QUEUED}


# ── 5.3 Model Training & Prediction ──────────────────────────────────────────

@router.post("/models/train", summary="Submit a model training job", status_code=202)
async def train_model(body: Dict[str, Any], _api_key: ApiKeyDep):
    """POST /api/v1/quant-lab/models/train → {job_id, status: queued}."""
    job_id = await create_job("model_train", body)
    payload = {"action": "train_model", "params": body}
    asyncio.create_task(run_job_async(job_id, "qlab.service", payload, timeout=3600))
    return {"job_id": job_id, "status": JobStatus.QUEUED}


@router.post("/models/{model_id}/predict", summary="Run prediction with a trained model")
async def predict(model_id: str, body: Dict[str, Any], _api_key: ApiKeyDep):
    """POST /api/v1/quant-lab/models/{model_id}/predict — synchronous (fast)."""
    payload = {"action": "predict", "params": {**body, "model_id": model_id}}
    runner = get_runner(timeout=120)
    script = catalog.path("qlab.service")
    from core.python_runner import PythonRunnerError
    from core.errors import script_error_to_api_error
    try:
        return await runner.run(script, payload, timeout=120)
    except PythonRunnerError as exc:
        raise script_error_to_api_error(exc, script) from exc


@router.get("/models", summary="List trained models")
async def list_models(_api_key: ApiKeyDep = None):
    payload = {"action": "list_models", "params": {}}
    runner = get_runner(timeout=30)
    script = catalog.path("qlab.service")
    from core.python_runner import PythonRunnerError
    from core.errors import script_error_to_api_error
    try:
        return await runner.run(script, payload, timeout=30)
    except PythonRunnerError as exc:
        raise script_error_to_api_error(exc, script) from exc


@router.get("/models/{model_id}", summary="Get model details and feature importance")
async def get_model(model_id: str, _api_key: ApiKeyDep = None):
    payload = {"action": "get_model", "params": {"model_id": model_id}}
    runner = get_runner(timeout=30)
    script = catalog.path("qlab.service")
    from core.python_runner import PythonRunnerError
    from core.errors import script_error_to_api_error
    try:
        return await runner.run(script, payload, timeout=30)
    except PythonRunnerError as exc:
        raise script_error_to_api_error(exc, script) from exc


# ── 5.4 Factor Discovery ──────────────────────────────────────────────────────

@router.post("/factors/discover", summary="Submit factor discovery job", status_code=202)
async def discover_factors(body: Dict[str, Any], _api_key: ApiKeyDep):
    job_id = await create_job("factor_discovery", body)
    payload = {"action": "discover_factors", "params": body}
    asyncio.create_task(run_job_async(job_id, "qlab.feature_eng", payload, timeout=1800))
    return {"job_id": job_id, "status": JobStatus.QUEUED}


@router.post("/factors/evaluate", summary="Submit factor evaluation job", status_code=202)
async def evaluate_factor(body: Dict[str, Any], _api_key: ApiKeyDep):
    job_id = await create_job("factor_evaluation", body)
    payload = {"action": "evaluate_factor", "params": body}
    asyncio.create_task(run_job_async(job_id, "qlab.evaluation", payload, timeout=600))
    return {"job_id": job_id, "status": JobStatus.QUEUED}


# ── 5.5 Portfolio Optimization (Qlib-based) ───────────────────────────────────

@router.post("/portfolio/optimize", summary="Qlib-based portfolio optimization")
async def qlab_portfolio_optimize(body: Dict[str, Any], _api_key: ApiKeyDep):
    """Synchronous — returns weights directly."""
    payload = {"action": "optimize_portfolio", "params": body}
    runner = get_runner(timeout=120)
    script = catalog.path("qlab.portfolio_opt")
    from core.python_runner import PythonRunnerError
    from core.errors import script_error_to_api_error
    try:
        return await runner.run(script, payload, timeout=120)
    except PythonRunnerError as exc:
        raise script_error_to_api_error(exc, script) from exc


# ── 5.6 RL Trading ────────────────────────────────────────────────────────────

@router.post("/rl/train", summary="Submit RL agent training job", status_code=202)
async def train_rl(body: Dict[str, Any], _api_key: ApiKeyDep):
    job_id = await create_job("rl_train", body)
    payload = {"action": "train_rl", "params": body}
    asyncio.create_task(run_job_async(job_id, "qlab.rl", payload, timeout=7200))
    return {"job_id": job_id, "status": JobStatus.QUEUED}


@router.post("/rl/{model_id}/backtest", summary="Submit RL model backtest job", status_code=202)
async def rl_backtest(model_id: str, body: Dict[str, Any], _api_key: ApiKeyDep):
    job_id = await create_job("rl_backtest", {**body, "model_id": model_id})
    payload = {"action": "rl_backtest", "params": {**body, "model_id": model_id}}
    asyncio.create_task(run_job_async(job_id, "qlab.rl", payload, timeout=600))
    return {"job_id": job_id, "status": JobStatus.QUEUED}


# ── 5.7 Reporting ─────────────────────────────────────────────────────────────

@router.post("/report/tearsheet", summary="Generate performance tearsheet", status_code=202)
async def generate_tearsheet(body: Dict[str, Any], _api_key: ApiKeyDep):
    job_id = await create_job("tearsheet", body)
    payload = {"action": "generate_tearsheet", "params": body}
    asyncio.create_task(run_job_async(job_id, "qlab.reporting", payload, timeout=300))
    return {"job_id": job_id, "status": JobStatus.QUEUED}


@router.post("/report/factor-attribution", summary="Factor attribution analysis")
async def factor_attribution(body: Dict[str, Any], _api_key: ApiKeyDep):
    """Synchronous — returns attribution directly."""
    payload = {"action": "factor_attribution", "params": body}
    runner = get_runner(timeout=120)
    script = catalog.path("qlab.reporting")
    from core.python_runner import PythonRunnerError
    from core.errors import script_error_to_api_error
    try:
        return await runner.run(script, payload, timeout=120)
    except PythonRunnerError as exc:
        raise script_error_to_api_error(exc, script) from exc
