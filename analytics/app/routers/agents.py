"""
Phase 1 — AI Agents API router.

Endpoints map to finagent_core/main.py actions via PythonRunner subprocess bridge.
All POST endpoints require X-API-Key authentication.
GET discovery endpoints are public.

Phase 3 addition: every agent run is recorded in analytics.agent_runs (audit log).
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime
from typing import Annotated, Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import and_, select

from app.config import settings
from app.dependencies import ApiKeyDep, JwtUserDep
from core.audit import record_audit
from core.cache import TTL, cache
from core.metrics import record_agent_run as _record_agent_run_metric
from core.database import AsyncSessionLocal
from core.errors import FinceptAPIError, MissingApiKeyError, script_error_to_api_error
from core.llm_router import build_active_llm, validate_llm_config
from core.python_runner import PythonRunner, PythonRunnerError, get_runner
from core.script_catalog import catalog
from models.db.agent import AgentRun
from models.requests.agents import (
    AddMessageRequest,
    AgentRunRequest,
    CreateSessionRequest,
    DynamicPlanRequest,
    EarningsAnalysisRequest,
    ExecutePlanRequest,
    MacroAnalysisRequest,
    MultiAgentRunRequest,
    PaperTradeRequest,
    PortfolioAnalysisRequest,
    PortfolioPlanRequest,
    RiskAnalysisRequest,
    SectorRotationRequest,
    StockAnalysisRequest,
    StockPlanRequest,
    TeamRunRequest,
)
from models.responses.agents import (
    AgentListResponse,
    AgentRunResponse,
    CreateSessionResponse,
    MultiAgentRunResponse,
    PaperTradeResponse,
    PlanExecuteResponse,
    PlanResponse,
    PortfolioResponse,
    SessionResponse,
)

logger = structlog.get_logger(__name__)


# ── Agent run audit helper ────────────────────────────────────────────────────

async def _record_agent_run(
    *,
    user_id: str,
    persona_id: str,
    query: Optional[str],
    response: Optional[str],
    duration_ms: int,
    status: str,  # 'ok' | 'error' | 'cancelled'
    tokens_in: Optional[int] = None,
    tokens_out: Optional[int] = None,
    error: Optional[dict] = None,
) -> None:
    """
    Fire-and-forget write to analytics.agent_runs.

    Called via asyncio.create_task() so it never blocks the HTTP response.
    Requirement 3.4 / Property 9: every run stored with user_id matching JWT claim.
    """
    try:
        uid: Optional[uuid.UUID] = None
        try:
            uid = uuid.UUID(user_id)
        except (ValueError, AttributeError):
            uid = uuid.uuid4()  # fallback — should not happen in practice

        run = AgentRun(
            user_id=uid,
            persona_id=persona_id,
            query=query,
            response=response,
            duration_ms=duration_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            status=status,
            error=error,
        )
        async with AsyncSessionLocal() as session:
            session.add(run)
            await session.commit()

        # Record Prometheus metric — analytics_agent_runs_total{persona_id,status}
        _record_agent_run_metric(persona_id=persona_id, status=status)

        logger.debug(
            "agent_run.recorded",
            user_id=user_id,
            persona_id=persona_id,
            status=status,
            duration_ms=duration_ms,
        )
    except Exception as exc:
        # Audit failures must never crash the application.
        logger.error("agent_run.record_failed", error=str(exc), user_id=user_id)

router = APIRouter()

_SCRIPT = "agents.main"  # catalog key → agents/finagent_core/main.py


# ── User ID resolution ────────────────────────────────────────────────────────

def _resolve_user_id(request: Request) -> str:
    """
    Extract user_id from request state (set by auth middleware or dependency).

    Priority:
      1. request.state.user["sub"] — set by get_current_user JWT dependency
      2. request.state.user_id    — set by some middleware paths
      3. Fallback: generate a deterministic placeholder (should not happen)

    Property 9: user_id must match JWT claim.
    """
    user: Optional[dict] = getattr(request.state, "user", None)
    if user and isinstance(user, dict):
        sub = user.get("sub")
        if sub:
            return str(sub)
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return str(user_id)
    # Last resort — anonymous placeholder
    return "anonymous"


async def _get_run_user(
    request: Request,
    _api_key: ApiKeyDep,
) -> str:
    """
    Dependency that resolves user_id for agent run endpoints.

    Validates the API key (via ApiKeyDep), then attempts to extract the JWT
    sub claim from the Bearer token if present.  This allows both auth paths:
      - API key only → user_id derived from key hash
      - JWT + API key → user_id from jwt.sub (Property 9)
    """
    from core.auth import verify_analytics_jwt, verify_quantdinger_jwt

    # Try to extract JWT sub from Bearer header (best-effort, non-blocking)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        claims = verify_analytics_jwt(token)
        if claims is None and settings.quantdinger_jwt_enabled:
            claims = verify_quantdinger_jwt(token)
        if claims:
            sub = claims.get("sub") or claims.get("user_id") or claims.get("id")
            if sub:
                # Store in request.state for middleware / audit log
                request.state.user = {"sub": str(sub), "_raw": claims}
                return str(sub)

    # Fallback: use API key identity (already validated by ApiKeyDep)
    return _resolve_user_id(request)


RunUserDep = Annotated[str, Depends(_get_run_user)]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_payload(action: str, params: dict, config: dict, llm_config) -> dict:
    """
    Build the JSON payload sent to finagent_core/main.py via stdin.

    - Validates LLM config (fail fast, không chờ 120s timeout)
    - Auto-selects model phù hợp với task type nếu cần
    - active_llm format: provider, model_id, api_key, base_url, temperature, max_tokens
    """
    model_id = getattr(llm_config, "model", None) or getattr(llm_config, "model_id", "")
    provider = getattr(llm_config, "provider", None) or "openai"
    base_url = getattr(llm_config, "base_url", None) or ""
    api_key = getattr(llm_config, "api_key", "") or ""
    temperature = getattr(llm_config, "temperature", 0.7)
    max_tokens = getattr(llm_config, "max_tokens", 4096)

    # Fallback về server-side defaults nếu client không truyền config
    if not model_id:
        model_id = settings.LLM_MODEL
    if not base_url:
        base_url = settings.LLM_BASE_URL
    if not api_key:
        api_key = settings.LLM_API_KEY

    # Auto-detect provider từ base_url nếu vẫn là default "openai"
    # Tránh validate format key sai khi dùng custom endpoint
    if provider == "openai" and base_url and "openai.com" not in base_url:
        provider = "openai_compat"  # treat as OpenAI-compatible, skip strict key format check

    # Validate trước khi spawn subprocess
    if model_id and api_key is not None:  # skip validation for NullLLM
        is_valid, err_msg = validate_llm_config(model_id, api_key, base_url, provider)
        if not is_valid and model_id:  # chỉ validate khi có model thực
            from core.errors import InvalidParamsError
            raise InvalidParamsError(f"Invalid LLM config: {err_msg}")

    # Build active_llm với auto model selection
    # Truyền "openai" vào build_active_llm thay vì "openai_compat"
    # vì ModelsRegistry trong subprocess không biết "openai_compat"
    llm_provider = "openai" if provider == "openai_compat" else provider
    active_llm = build_active_llm(
        model=model_id,
        api_key=api_key,
        base_url=base_url,
        provider=llm_provider,
        temperature=temperature,
        max_tokens=max_tokens,
        action=action,
        auto_select_model=False,  # User đã chọn model — không override
    )

    return {
        "action": action,
        "api_keys": {},  # LLM key đi qua active_llm, không log ở đây
        "params": params,
        "config": config,
        "active_llm": active_llm,
    }


def _script_path() -> str:
    """Return relative script path from catalog."""
    return catalog.path(_SCRIPT)


async def _run_agent(
    payload: dict,
    timeout: int = 120,
) -> dict:
    """Run agent script one-shot and return parsed JSON result."""
    runner = get_runner(timeout=timeout)
    script = _script_path()
    try:
        return await runner.run(script, payload, timeout=timeout)
    except PythonRunnerError as exc:
        raise script_error_to_api_error(exc, script) from exc
    except Exception as exc:
        raise script_error_to_api_error(exc, script) from exc


async def _stream_agent(payload: dict):
    """
    Async generator that yields SSE-formatted strings from agent stdout.

    stdout line format → SSE event:
      THINKING: ...  → {"type": "thinking", "content": "..."}
      TOKEN: ...     → {"type": "token",    "content": "..."}
      TOOL: ...      → {"type": "tool",     "content": "..."}
      DONE: ...      → {"type": "done",     "content": "..."}
      (other)        → {"type": "token",    "content": "..."}
    """
    runner = get_runner(timeout=settings.AGENT_RUN_TIMEOUT)
    script = _script_path()

    _PREFIX_MAP = {
        "THINKING:": "thinking",
        "TOKEN:": "token",
        "TOOL:": "tool",
        "DONE:": "done",
        "ERROR:": "error",
    }

    try:
        async with asyncio.timeout(settings.AGENT_RUN_TIMEOUT):
            async for line in runner.stream(script, payload):
                # Skip empty lines
                if not line.strip():
                    continue

                event_type = "token"
                content = line
                for prefix, etype in _PREFIX_MAP.items():
                    if line.startswith(prefix):
                        event_type = etype
                        content = line[len(prefix):].strip()
                        break

                # Skip lines that look like raw JSON output (subprocess final result)
                # These start with '{' and are not prefixed — they're not stream events
                if event_type == "token" and content.strip().startswith("{"):
                    continue

                event = json.dumps({"type": event_type, "content": content})
                yield f"data: {event}\n\n"

                # Stop streaming after DONE — no more events should follow
                if event_type == "done":
                    break
    except asyncio.TimeoutError:
        err = json.dumps({"type": "error", "content": f"Agent timed out after {settings.AGENT_RUN_TIMEOUT}s"})
        yield f"data: {err}\n\n"
    except Exception as exc:
        err = json.dumps({"type": "error", "content": str(exc)})
        yield f"data: {err}\n\n"


# ── Discovery / Listing ───────────────────────────────────────────────────────

@router.get(
    "/",
    summary="Discover all available agents",
    description="Public endpoint. Returns full agent catalog with TTL=300s cache.",
)
async def discover_agents():
    """GET /api/v1/agents — discover_agents action, cached 300s."""
    cache_key = cache.build_key("agents", "discover")

    async def _fetch():
        payload = _build_payload(
            action="discover_agents",
            params={},
            config={},
            llm_config=_NullLLM(),
        )
        # Tạo runner mới mỗi lần để tránh semaphore từ event loop cũ
        runner = PythonRunner(timeout=60)
        script = _script_path()
        try:
            return await runner.run(script, payload)
        except PythonRunnerError as exc:
            raise script_error_to_api_error(exc, script) from exc

    result = await cache.get_or_set(cache_key, _fetch, ttl=TTL.AGENTS_DISCOVER)
    # Script trả về {"success": true, "agents": [...], "count": N}
    # Unpack để match AgentListResponse schema
    if isinstance(result, dict) and "agents" in result:
        return result
    return {"agents": [], "categories": [], "count": 0}


@router.get(
    "/list",
    summary="List agents, optionally filtered by category",
    description="Public endpoint. TTL=60s cache per category.",
)
async def list_agents(
    category: Optional[str] = Query(default=None, description="Filter by agent category"),
):
    """GET /api/v1/agents/list — list_agents action, cached 60s."""
    cache_key = cache.agents_list_key(category or "")

    async def _fetch():
        payload = _build_payload(
            action="list_agents",
            params={"category": category or ""},
            config={},
            llm_config=_NullLLM(),
        )
        runner = get_runner()
        script = _script_path()
        try:
            return await runner.run(script, payload)
        except PythonRunnerError as exc:
            raise script_error_to_api_error(exc, script) from exc

    result = await cache.get_or_set(cache_key, _fetch, ttl=60)
    if isinstance(result, dict) and "agents" in result:
        return result
    return {"agents": [], "categories": [], "count": 0}


# ── Agent Run ─────────────────────────────────────────────────────────────────

@router.post(
    "/run",
    response_model=AgentRunResponse,
    summary="Run a single agent (one-shot)",
)
async def run_agent(
    request: Request,
    body: AgentRunRequest,
    user_id: RunUserDep,
):
    """POST /api/v1/agents/run — run action, timeout=120s.

    Phase 3: records audit entry in analytics.agent_runs after every run.
    user_id is extracted from JWT sub claim when available, otherwise falls
    back to the API key identity stored in request.state.
    """

    t0 = time.monotonic()
    persona_id = body.agent_id or "unknown"
    result: Optional[dict] = None
    run_status = "ok"
    run_error: Optional[dict] = None

    payload = _build_payload(
        action="run",
        params={
            "agent_id": body.agent_id,
            "query": body.query,
            "session_id": body.session_id,
            "options": body.options or {},
        },
        config={},
        llm_config=body.llm_config,
    )

    try:
        result = await _run_agent(payload, timeout=settings.AGENT_RUN_TIMEOUT)
        if not result.get("success", True):
            run_status = "error"
            run_error = {"message": str(result.get("error", "unknown error"))}
    except asyncio.CancelledError:
        run_status = "cancelled"
        elapsed_ms = (time.monotonic() - t0) * 1000
        asyncio.create_task(_record_agent_run(
            user_id=user_id,
            persona_id=persona_id,
            query=body.query,
            response=None,
            duration_ms=int(elapsed_ms),
            status="cancelled",
        ))
        raise
    except Exception as exc:
        run_status = "error"
        run_error = {"message": str(exc)}
        elapsed_ms = (time.monotonic() - t0) * 1000
        asyncio.create_task(_record_agent_run(
            user_id=user_id,
            persona_id=persona_id,
            query=body.query,
            response=None,
            duration_ms=int(elapsed_ms),
            status="error",
            error=run_error,
        ))
        raise

    elapsed_ms = (time.monotonic() - t0) * 1000

    # Fire-and-forget audit write (non-blocking)
    asyncio.create_task(_record_agent_run(
        user_id=user_id,
        persona_id=persona_id,
        query=body.query,
        response=result.get("response") or result.get("result") if result else None,
        duration_ms=int(elapsed_ms),
        status=run_status,
        tokens_in=result.get("tokens_in") if result else None,
        tokens_out=result.get("tokens_out") if result else None,
        error=run_error,
    ))

    return AgentRunResponse(
        success=result.get("success", True) if result else False,
        response=result.get("response") or result.get("result") if result else None,
        execution_time_ms=elapsed_ms,
        request_id=str(uuid.uuid4()),
        error=result.get("error") if result else run_error,
    )


@router.post(
    "/run/stream",
    summary="Run a single agent with SSE streaming",
    response_class=StreamingResponse,
)
async def run_agent_stream(
    request: Request,
    body: AgentRunRequest,
    user_id: RunUserDep,
):
    """POST /api/v1/agents/run/stream — run action with --stream --stdin, SSE output.

    Phase 3: records audit entry in analytics.agent_runs after stream completes.
    Cancelled (client disconnect) → status='cancelled'.
    Timeout/error → status='error'.
    """
    persona_id = body.agent_id or "unknown"

    payload = _build_payload(
        action="run",
        params={
            "agent_id": body.agent_id,
            "query": body.query,
            "session_id": body.session_id,
            "options": body.options or {},
        },
        config={},
        llm_config=body.llm_config,
    )

    async def _audited_stream():
        t0 = time.monotonic()
        collected_response: list[str] = []
        stream_status = "ok"
        stream_error: Optional[dict] = None

        try:
            async for chunk in _stream_agent(payload):
                # Detect error events emitted by _stream_agent
                if '"type": "error"' in chunk:
                    stream_status = "error"
                    try:
                        data_str = chunk.strip()
                        if data_str.startswith("data: "):
                            event = json.loads(data_str[6:])
                            stream_error = {"message": event.get("content", "stream error")}
                    except Exception:
                        stream_error = {"message": "stream error"}
                elif '"type": "done"' in chunk or '"type": "token"' in chunk:
                    try:
                        data_str = chunk.strip()
                        if data_str.startswith("data: "):
                            event = json.loads(data_str[6:])
                            if event.get("type") in ("token", "done"):
                                collected_response.append(event.get("content", ""))
                    except Exception:
                        pass
                yield chunk
        except asyncio.CancelledError:
            stream_status = "cancelled"
            elapsed_ms = (time.monotonic() - t0) * 1000
            asyncio.create_task(_record_agent_run(
                user_id=user_id,
                persona_id=persona_id,
                query=body.query,
                response=None,
                duration_ms=int(elapsed_ms),
                status="cancelled",
            ))
            return
        except Exception as exc:
            stream_status = "error"
            stream_error = {"message": str(exc)}

        elapsed_ms = (time.monotonic() - t0) * 1000
        asyncio.create_task(_record_agent_run(
            user_id=user_id,
            persona_id=persona_id,
            query=body.query,
            response="".join(collected_response) or None,
            duration_ms=int(elapsed_ms),
            status=stream_status,
            error=stream_error,
        ))

    return StreamingResponse(
        _audited_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Team / Multi-Agent ────────────────────────────────────────────────────────

@router.post(
    "/team/run",
    response_model=AgentRunResponse,
    summary="Run a multi-agent team",
)
async def run_team(body: TeamRunRequest, _api_key: ApiKeyDep):
    """POST /api/v1/agents/team/run — run_team action, timeout=120s."""
    t0 = time.monotonic()
    payload = _build_payload(
        action="run_team",
        params={
            "team_config": body.team_config.model_dump(),
            "query": body.query,
            "session_id": body.session_id,
        },
        config={},
        llm_config=body.llm_config,
    )
    result = await _run_agent(payload, timeout=settings.AGENT_RUN_TIMEOUT)
    elapsed_ms = (time.monotonic() - t0) * 1000
    return AgentRunResponse(
        success=result.get("success", True),
        response=result.get("response") or result.get("result"),
        execution_time_ms=elapsed_ms,
        request_id=str(uuid.uuid4()),
        error=result.get("error"),
    )


@router.post(
    "/multi/run",
    response_model=MultiAgentRunResponse,
    summary="Execute a query across multiple agents",
)
async def run_multi_agent(body: MultiAgentRunRequest, _api_key: ApiKeyDep):
    """POST /api/v1/agents/multi/run — execute_multi_query action, timeout=120s."""
    t0 = time.monotonic()
    payload = _build_payload(
        action="execute_multi_query",
        params={
            "query": body.query,
            "agent_ids": body.agent_ids or [],
            "aggregate": body.aggregate,
        },
        config={},
        llm_config=body.llm_config,
    )
    result = await _run_agent(payload, timeout=settings.AGENT_RUN_TIMEOUT)
    elapsed_ms = (time.monotonic() - t0) * 1000
    return MultiAgentRunResponse(
        success=result.get("success", True),
        responses=result.get("responses", []),
        aggregated=result.get("aggregated"),
        execution_time_ms=elapsed_ms,
    )


# ── Execution Planner ─────────────────────────────────────────────────────────

@router.post(
    "/plan/stock",
    response_model=PlanResponse,
    summary="Create a stock analysis execution plan",
)
async def create_stock_plan(body: StockPlanRequest, _api_key: ApiKeyDep):
    """POST /api/v1/agents/plan/stock — create_stock_plan action."""
    payload = _build_payload(
        action="create_stock_plan",
        params={"symbol": body.symbol},
        config={},
        llm_config=body.llm_config,
    )
    result = await _run_agent(payload, timeout=settings.AGENT_RUN_TIMEOUT)
    return PlanResponse(
        success=result.get("success", True),
        plan=result.get("plan"),
        error=result.get("error"),
    )


@router.post(
    "/plan/portfolio",
    response_model=PlanResponse,
    summary="Create a portfolio execution plan",
)
async def create_portfolio_plan(body: PortfolioPlanRequest, _api_key: ApiKeyDep):
    """POST /api/v1/agents/plan/portfolio — create_portfolio_plan action."""
    payload = _build_payload(
        action="create_portfolio_plan",
        params={"portfolio_id": body.portfolio_id},
        config={},
        llm_config=body.llm_config,
    )
    result = await _run_agent(payload, timeout=settings.AGENT_RUN_TIMEOUT)
    return PlanResponse(
        success=result.get("success", True),
        plan=result.get("plan"),
        error=result.get("error"),
    )


@router.post(
    "/plan/execute",
    response_model=PlanExecuteResponse,
    summary="Execute a previously created plan",
)
async def execute_plan(body: ExecutePlanRequest, _api_key: ApiKeyDep):
    """POST /api/v1/agents/plan/execute — execute_plan action, timeout=300s."""
    t0 = time.monotonic()
    payload = _build_payload(
        action="execute_plan",
        params={"plan": body.plan},
        config={},
        llm_config=body.llm_config,
    )
    result = await _run_agent(payload, timeout=settings.AGENT_PLAN_TIMEOUT)
    elapsed_ms = (time.monotonic() - t0) * 1000
    return PlanExecuteResponse(
        success=result.get("success", True),
        results=result.get("results", []),
        execution_time_ms=elapsed_ms,
    )


@router.post(
    "/plan/dynamic",
    response_model=PlanResponse,
    summary="Generate a dynamic execution plan from a natural language query",
)
async def generate_dynamic_plan(body: DynamicPlanRequest, _api_key: ApiKeyDep):
    """POST /api/v1/agents/plan/dynamic — generate_dynamic_plan action."""
    payload = _build_payload(
        action="generate_dynamic_plan",
        params={"query": body.query},
        config={},
        llm_config=body.llm_config,
    )
    result = await _run_agent(payload, timeout=settings.AGENT_RUN_TIMEOUT)
    return PlanResponse(
        success=result.get("success", True),
        plan=result.get("plan"),
        error=result.get("error"),
    )


# ── Financial Analysis Workflows ──────────────────────────────────────────────

@router.post(
    "/analyze/stock",
    response_model=AgentRunResponse,
    summary="Run full stock analysis workflow",
)
async def analyze_stock(body: StockAnalysisRequest, _api_key: ApiKeyDep):
    """POST /api/v1/agents/analyze/stock — stock_analysis action."""
    t0 = time.monotonic()
    payload = _build_payload(
        action="stock_analysis",
        params={"symbol": body.symbol, "session_id": body.session_id},
        config={},
        llm_config=body.llm_config,
    )
    result = await _run_agent(payload, timeout=settings.AGENT_RUN_TIMEOUT)
    elapsed_ms = (time.monotonic() - t0) * 1000
    return AgentRunResponse(
        success=result.get("success", True),
        response=result.get("response") or result.get("result"),
        execution_time_ms=elapsed_ms,
        request_id=str(uuid.uuid4()),
        error=result.get("error"),
    )


@router.post(
    "/analyze/portfolio",
    response_model=AgentRunResponse,
    summary="Run portfolio rebalancing analysis",
)
async def analyze_portfolio(body: PortfolioAnalysisRequest, _api_key: ApiKeyDep):
    """POST /api/v1/agents/analyze/portfolio — portfolio_rebal action."""
    t0 = time.monotonic()
    payload = _build_payload(
        action="portfolio_rebal",
        params={"portfolio_data": body.portfolio_data},
        config={},
        llm_config=body.llm_config,
    )
    result = await _run_agent(payload, timeout=settings.AGENT_RUN_TIMEOUT)
    elapsed_ms = (time.monotonic() - t0) * 1000
    return AgentRunResponse(
        success=result.get("success", True),
        response=result.get("response") or result.get("result"),
        execution_time_ms=elapsed_ms,
        request_id=str(uuid.uuid4()),
        error=result.get("error"),
    )


@router.post(
    "/analyze/risk",
    response_model=AgentRunResponse,
    summary="Run portfolio risk assessment",
)
async def analyze_risk(body: RiskAnalysisRequest, _api_key: ApiKeyDep):
    """POST /api/v1/agents/analyze/risk — risk_assessment action."""
    t0 = time.monotonic()
    payload = _build_payload(
        action="risk_assessment",
        params={"portfolio_data": body.portfolio_data},
        config={},
        llm_config=body.llm_config,
    )
    result = await _run_agent(payload, timeout=settings.AGENT_RUN_TIMEOUT)
    elapsed_ms = (time.monotonic() - t0) * 1000
    return AgentRunResponse(
        success=result.get("success", True),
        response=result.get("response") or result.get("result"),
        execution_time_ms=elapsed_ms,
        request_id=str(uuid.uuid4()),
        error=result.get("error"),
    )


@router.post(
    "/analyze/macro",
    response_model=AgentRunResponse,
    summary="Run macro environment scan",
)
async def analyze_macro(body: MacroAnalysisRequest, _api_key: ApiKeyDep):
    """POST /api/v1/agents/analyze/macro — macro_scan action."""
    t0 = time.monotonic()
    payload = _build_payload(
        action="macro_scan",
        params={},
        config={},
        llm_config=body.llm_config,
    )
    result = await _run_agent(payload, timeout=settings.AGENT_RUN_TIMEOUT)
    elapsed_ms = (time.monotonic() - t0) * 1000
    return AgentRunResponse(
        success=result.get("success", True),
        response=result.get("response") or result.get("result"),
        execution_time_ms=elapsed_ms,
        request_id=str(uuid.uuid4()),
        error=result.get("error"),
    )


@router.post(
    "/analyze/earnings",
    response_model=AgentRunResponse,
    summary="Generate earnings brief for a symbol",
)
async def analyze_earnings(body: EarningsAnalysisRequest, _api_key: ApiKeyDep):
    """POST /api/v1/agents/analyze/earnings — earnings_brief action."""
    t0 = time.monotonic()
    payload = _build_payload(
        action="earnings_brief",
        params={"symbol": body.symbol},
        config={},
        llm_config=body.llm_config,
    )
    result = await _run_agent(payload, timeout=settings.AGENT_RUN_TIMEOUT)
    elapsed_ms = (time.monotonic() - t0) * 1000
    return AgentRunResponse(
        success=result.get("success", True),
        response=result.get("response") or result.get("result"),
        execution_time_ms=elapsed_ms,
        request_id=str(uuid.uuid4()),
        error=result.get("error"),
    )


@router.post(
    "/analyze/sector-rotation",
    response_model=AgentRunResponse,
    summary="Run sector rotation analysis",
)
async def analyze_sector_rotation(body: SectorRotationRequest, _api_key: ApiKeyDep):
    """POST /api/v1/agents/analyze/sector-rotation — sector_rotation action."""
    t0 = time.monotonic()
    payload = _build_payload(
        action="sector_rotation",
        params={},
        config={},
        llm_config=body.llm_config,
    )
    result = await _run_agent(payload, timeout=settings.AGENT_RUN_TIMEOUT)
    elapsed_ms = (time.monotonic() - t0) * 1000
    return AgentRunResponse(
        success=result.get("success", True),
        response=result.get("response") or result.get("result"),
        execution_time_ms=elapsed_ms,
        request_id=str(uuid.uuid4()),
        error=result.get("error"),
    )


# ── Paper Trading ─────────────────────────────────────────────────────────────

@router.post(
    "/paper/trade",
    response_model=PaperTradeResponse,
    summary="Execute a paper trade",
)
async def paper_execute_trade(body: PaperTradeRequest, _api_key: ApiKeyDep):
    """POST /api/v1/agents/paper/trade — paper_execute_trade action."""
    payload = {
        "action": "paper_execute_trade",
        "api_keys": {},
        "params": {
            "portfolio_id": body.portfolio_id,
            "symbol": body.symbol,
            "action": body.action,
            "quantity": body.quantity,
            "price": body.price,
        },
        "config": {},
        "active_llm": {},
    }
    runner = get_runner(timeout=settings.AGENT_RUN_TIMEOUT)
    script = _script_path()
    try:
        result = await runner.run(script, payload, timeout=settings.AGENT_RUN_TIMEOUT)
    except PythonRunnerError as exc:
        raise script_error_to_api_error(exc, script) from exc
    return PaperTradeResponse(
        success=result.get("success", True),
        trade_id=result.get("trade_id"),
        error=result.get("error"),
    )


@router.get(
    "/paper/portfolio/{portfolio_id}",
    response_model=PortfolioResponse,
    summary="Get paper trading portfolio summary",
)
async def paper_get_portfolio(portfolio_id: str, _api_key: ApiKeyDep):
    """GET /api/v1/agents/paper/portfolio/{portfolio_id} — paper_get_portfolio action."""
    payload = {
        "action": "paper_get_portfolio",
        "api_keys": {},
        "params": {"portfolio_id": portfolio_id},
        "config": {},
        "active_llm": {},
    }
    runner = get_runner(timeout=settings.AGENT_RUN_TIMEOUT)
    script = _script_path()
    try:
        result = await runner.run(script, payload, timeout=settings.AGENT_RUN_TIMEOUT)
    except PythonRunnerError as exc:
        raise script_error_to_api_error(exc, script) from exc
    return PortfolioResponse(
        success=result.get("success", True),
        portfolio_value=result.get("portfolio_value"),
        cash=result.get("cash"),
        positions=result.get("positions", []),
    )


@router.get(
    "/paper/positions/{portfolio_id}",
    response_model=PortfolioResponse,
    summary="Get paper trading positions",
)
async def paper_get_positions(portfolio_id: str, _api_key: ApiKeyDep):
    """GET /api/v1/agents/paper/positions/{portfolio_id} — paper_get_positions action."""
    payload = {
        "action": "paper_get_positions",
        "api_keys": {},
        "params": {"portfolio_id": portfolio_id},
        "config": {},
        "active_llm": {},
    }
    runner = get_runner(timeout=settings.AGENT_RUN_TIMEOUT)
    script = _script_path()
    try:
        result = await runner.run(script, payload, timeout=settings.AGENT_RUN_TIMEOUT)
    except PythonRunnerError as exc:
        raise script_error_to_api_error(exc, script) from exc
    return PortfolioResponse(
        success=result.get("success", True),
        portfolio_value=result.get("portfolio_value"),
        cash=result.get("cash"),
        positions=result.get("positions", []),
    )


# ── Session Management ────────────────────────────────────────────────────────

@router.post(
    "/sessions",
    response_model=CreateSessionResponse,
    summary="Create a new agent session",
    status_code=201,
)
async def create_session(body: CreateSessionRequest, _api_key: ApiKeyDep):
    """POST /api/v1/agents/sessions — save_session action."""
    session_id = str(uuid.uuid4())
    payload = {
        "action": "save_session",
        "api_keys": {},
        "params": {
            "session_id": session_id,
            "agent_id": body.agent_id,
            "user_id": body.user_id,
            "messages": [],
        },
        "config": {},
        "active_llm": {},
    }
    runner = get_runner(timeout=settings.AGENT_RUN_TIMEOUT)
    script = _script_path()
    try:
        await runner.run(script, payload, timeout=settings.AGENT_RUN_TIMEOUT)
    except PythonRunnerError as exc:
        raise script_error_to_api_error(exc, script) from exc
    return CreateSessionResponse(session_id=session_id)


@router.get(
    "/sessions/{session_id}",
    response_model=SessionResponse,
    summary="Get an agent session",
)
async def get_session(session_id: str, _api_key: ApiKeyDep):
    """GET /api/v1/agents/sessions/{session_id} — get_session action."""
    payload = {
        "action": "get_session",
        "api_keys": {},
        "params": {"session_id": session_id},
        "config": {},
        "active_llm": {},
    }
    runner = get_runner(timeout=settings.AGENT_RUN_TIMEOUT)
    script = _script_path()
    try:
        result = await runner.run(script, payload, timeout=settings.AGENT_RUN_TIMEOUT)
    except PythonRunnerError as exc:
        raise script_error_to_api_error(exc, script) from exc
    return SessionResponse(
        session_id=session_id,
        agent_id=result.get("agent_id"),
        messages=result.get("messages", []),
        status=result.get("status", "active"),
    )


@router.post(
    "/sessions/{session_id}/messages",
    response_model=SessionResponse,
    summary="Add a message to a session",
)
async def add_message(session_id: str, body: AddMessageRequest, _api_key: ApiKeyDep):
    """POST /api/v1/agents/sessions/{session_id}/messages — add_message action."""
    payload = {
        "action": "add_message",
        "api_keys": {},
        "params": {
            "session_id": session_id,
            "role": body.role,
            "content": body.content,
        },
        "config": {},
        "active_llm": {},
    }
    runner = get_runner(timeout=settings.AGENT_RUN_TIMEOUT)
    script = _script_path()
    try:
        result = await runner.run(script, payload, timeout=settings.AGENT_RUN_TIMEOUT)
    except PythonRunnerError as exc:
        raise script_error_to_api_error(exc, script) from exc
    return SessionResponse(
        session_id=session_id,
        agent_id=result.get("agent_id"),
        messages=result.get("messages", []),
        status=result.get("status", "active"),
    )


@router.delete(
    "/sessions/{session_id}",
    summary="Delete an agent session",
    status_code=204,
)
async def delete_session(session_id: str, _api_key: ApiKeyDep):
    """DELETE /api/v1/agents/sessions/{session_id}."""
    payload = {
        "action": "delete_session",
        "api_keys": {},
        "params": {"session_id": session_id},
        "config": {},
        "active_llm": {},
    }
    runner = get_runner(timeout=settings.AGENT_RUN_TIMEOUT)
    script = _script_path()
    try:
        await runner.run(script, payload, timeout=settings.AGENT_RUN_TIMEOUT)
    except PythonRunnerError as exc:
        raise script_error_to_api_error(exc, script) from exc
    return None


# ── Agent Run History ─────────────────────────────────────────────────────────

class AgentRunSummary(BaseModel):
    """Summary of a single agent run returned in the history list."""

    id: str
    persona_id: str
    query: Optional[str]
    status: Optional[str]
    duration_ms: Optional[int]
    tokens_in: Optional[int]
    tokens_out: Optional[int]
    created_at: datetime


class AgentRunsResponse(BaseModel):
    """Paginated response for GET /api/v1/agents/runs."""

    runs: List[AgentRunSummary]
    total: int
    next_cursor: Optional[str]


_QUERY_TRUNCATE = 200  # chars — Requirement 3.4


@router.get(
    "/runs",
    response_model=AgentRunsResponse,
    summary="List agent run history for the current user",
    description=(
        "Returns paginated agent run history filtered to the authenticated user "
        "(user_id == jwt.sub). Supports optional date range and persona filters. "
        "Uses cursor-based pagination ordered by created_at DESC."
    ),
)
async def list_agent_runs(
    user: JwtUserDep,
    from_dt: Optional[datetime] = Query(
        default=None,
        alias="from",
        description="ISO 8601 datetime — only return runs created at or after this time.",
    ),
    to_dt: Optional[datetime] = Query(
        default=None,
        alias="to",
        description="ISO 8601 datetime — only return runs created before or at this time.",
    ),
    persona_id: Optional[str] = Query(
        default=None,
        description="Filter by persona / agent ID.",
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of runs to return (1–100, default 20).",
    ),
    cursor: Optional[str] = Query(
        default=None,
        description=(
            "UUID of the last run from the previous page. "
            "When provided, returns runs older than the cursor run."
        ),
    ),
) -> AgentRunsResponse:
    """
    GET /api/v1/agents/runs

    Requirement 3.4 / Property 9: only returns runs belonging to the
    authenticated user (user_id == jwt.sub).

    Cursor pagination: the cursor is the UUID of the last item on the
    previous page.  The next page contains runs whose created_at is
    strictly less than the cursor run's created_at (or, when timestamps
    tie, whose id is strictly less than the cursor id).  This guarantees
    stable, non-overlapping pages even when new runs are inserted.
    """
    user_id_str: str = user["sub"]

    # Parse user_id as UUID — fall back to string comparison if not a valid UUID
    try:
        user_uuid = uuid.UUID(user_id_str)
    except (ValueError, AttributeError):
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_PARAMS", "message": "Invalid user_id in JWT sub claim."},
        )

    async with AsyncSessionLocal() as session:
        # ── Build filter conditions ───────────────────────────────────────────
        conditions = [AgentRun.user_id == user_uuid]

        if persona_id:
            conditions.append(AgentRun.persona_id == persona_id)

        if from_dt:
            conditions.append(AgentRun.created_at >= from_dt)

        if to_dt:
            conditions.append(AgentRun.created_at <= to_dt)

        # ── Cursor pagination ─────────────────────────────────────────────────
        # Resolve the cursor run to get its created_at timestamp
        if cursor:
            try:
                cursor_uuid = uuid.UUID(cursor)
            except (ValueError, AttributeError):
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=400,
                    detail={"code": "INVALID_PARAMS", "message": "cursor must be a valid UUID."},
                )

            cursor_stmt = select(AgentRun.created_at, AgentRun.id).where(
                AgentRun.id == cursor_uuid
            )
            cursor_result = await session.execute(cursor_stmt)
            cursor_row = cursor_result.first()

            if cursor_row is not None:
                cursor_created_at, cursor_id = cursor_row
                # Return runs strictly older than the cursor run.
                # When two runs share the same created_at, use id as tiebreaker
                # (UUID comparison gives a stable, arbitrary but consistent order).
                conditions.append(
                    (AgentRun.created_at < cursor_created_at)
                    | (
                        (AgentRun.created_at == cursor_created_at)
                        & (AgentRun.id < cursor_id)
                    )
                )

        # ── Count total matching rows (without cursor / limit) ────────────────
        # We count with the date/persona filters but NOT the cursor condition
        # so that `total` reflects the full result set size.
        count_conditions = [AgentRun.user_id == user_uuid]
        if persona_id:
            count_conditions.append(AgentRun.persona_id == persona_id)
        if from_dt:
            count_conditions.append(AgentRun.created_at >= from_dt)
        if to_dt:
            count_conditions.append(AgentRun.created_at <= to_dt)

        from sqlalchemy import func as sa_func
        count_stmt = select(sa_func.count()).select_from(AgentRun).where(and_(*count_conditions))
        total: int = (await session.execute(count_stmt)).scalar_one()

        # ── Fetch page ────────────────────────────────────────────────────────
        stmt = (
            select(AgentRun)
            .where(and_(*conditions))
            .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        runs = result.scalars().all()

    # ── Build response ────────────────────────────────────────────────────────
    run_summaries: List[AgentRunSummary] = [
        AgentRunSummary(
            id=str(r.id),
            persona_id=r.persona_id,
            query=(r.query[:_QUERY_TRUNCATE] if r.query else None),
            status=r.status,
            duration_ms=r.duration_ms,
            tokens_in=r.tokens_in,
            tokens_out=r.tokens_out,
            created_at=r.created_at,
        )
        for r in runs
    ]

    # next_cursor is the id of the last item in this page (if there may be more)
    next_cursor: Optional[str] = None
    if len(runs) == limit:
        next_cursor = str(runs[-1].id)

    return AgentRunsResponse(
        runs=run_summaries,
        total=total,
        next_cursor=next_cursor,
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

class _NullLLM:
    """Placeholder LLM config for public endpoints that don't need an LLM."""
    provider = ""
    model_id = ""
    api_key = ""
    base_url = ""
    temperature = 0.0
    max_tokens = 0
