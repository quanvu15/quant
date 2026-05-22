"""
Async job system for long-running tasks (Phase 5 — AI Quant Lab).

Uses Redis for job state persistence (TTL 24h).
Job lifecycle: queued → running → completed | failed

No Celery required — jobs run as asyncio tasks with subprocess bridge.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog

from app.config import settings
from core.cache import cache

logger = structlog.get_logger(__name__)

_JOB_TTL = 86400  # 24 hours


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


def _job_key(job_id: str) -> str:
    return f"{settings.REDIS_KEY_PREFIX}job:{job_id}"


async def create_job(job_type: str, params: Dict[str, Any]) -> str:
    """Create a new job record in Redis. Returns job_id."""
    job_id = str(uuid.uuid4())
    job = {
        "job_id": job_id,
        "type": job_type,
        "status": JobStatus.QUEUED,
        "progress": 0,
        "eta_seconds": None,
        "created_at": time.time(),
        "started_at": None,
        "completed_at": None,
        "error": None,
        "result": None,
        "params": params,
    }
    await cache.set(_job_key(job_id), job, ttl=_JOB_TTL)
    return job_id


async def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    return await cache.get(_job_key(job_id))


async def update_job(job_id: str, **fields) -> None:
    job = await get_job(job_id)
    if job:
        job.update(fields)
        await cache.set(_job_key(job_id), job, ttl=_JOB_TTL)


async def list_jobs(status: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """List recent jobs. Note: Redis KEYS scan — use only for dev/small scale."""
    try:
        if cache._redis is None:
            return []
        keys = await cache._redis.keys(f"{settings.REDIS_KEY_PREFIX}job:*")
        jobs = []
        for key in keys[:limit * 3]:  # over-fetch to allow filtering
            raw = await cache._redis.get(key)
            if raw:
                job = json.loads(raw)
                if status is None or job.get("status") == status:
                    jobs.append(job)
        jobs.sort(key=lambda j: j.get("created_at", 0), reverse=True)
        return jobs[:limit]
    except Exception as exc:
        logger.warning("jobs.list_error", error=str(exc))
        return []


async def cancel_job(job_id: str) -> bool:
    job = await get_job(job_id)
    if not job:
        return False
    if job["status"] in (JobStatus.QUEUED, JobStatus.RUNNING):
        await update_job(job_id, status=JobStatus.CANCELLED)
        return True
    return False


async def run_job_async(
    job_id: str,
    script_key: str,
    payload: Dict[str, Any],
    timeout: int = 3600,
) -> None:
    """
    Execute a job asynchronously. Updates job state in Redis.
    Called via asyncio.create_task() from the router.
    """
    from core.errors import script_error_to_api_error
    from core.python_runner import PythonRunnerError, get_runner
    from core.script_catalog import catalog

    await update_job(job_id, status=JobStatus.RUNNING, started_at=time.time(), progress=5)

    runner = get_runner(timeout=timeout)
    script = catalog.path(script_key)

    try:
        result = await runner.run(script, payload, timeout=timeout)
        await update_job(
            job_id,
            status=JobStatus.COMPLETED,
            completed_at=time.time(),
            progress=100,
            result=result,
        )
    except PythonRunnerError as exc:
        api_err = script_error_to_api_error(exc, script)
        await update_job(
            job_id,
            status=JobStatus.FAILED,
            completed_at=time.time(),
            error=str(api_err),
        )
    except asyncio.CancelledError:
        await update_job(job_id, status=JobStatus.CANCELLED, completed_at=time.time())
    except Exception as exc:
        await update_job(
            job_id,
            status=JobStatus.FAILED,
            completed_at=time.time(),
            error=str(exc),
        )


# ── Audit log cleanup job ─────────────────────────────────────────────────────

async def cleanup_audit_log_job(retention_days: Optional[int] = None) -> Dict[str, Any]:
    """
    Scheduled job: delete audit log entries older than the retention period.

    Wraps core.audit.cleanup_audit_log() with job-style logging so it can be
    called from a scheduler (APScheduler, cron endpoint, or startup task).

    Args:
        retention_days: Override for settings.AUDIT_LOG_RETENTION_DAYS.
                        Defaults to the configured value (90 days).

    Returns:
        Dict with ``deleted`` (row count) and ``retention_days`` used.
    """
    from core.audit import cleanup_audit_log  # local import avoids circular deps

    days = retention_days if retention_days is not None else settings.AUDIT_LOG_RETENTION_DAYS
    logger.info("audit_cleanup_job.start", retention_days=days)

    deleted = await cleanup_audit_log(retention_days=days)

    result = {"deleted": deleted, "retention_days": days}
    logger.info("audit_cleanup_job.done", **result)
    return result
