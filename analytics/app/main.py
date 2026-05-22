"""
Analytics Microservice — FastAPI entry point
Phase 0: Foundation & Setup

Registers only the 4 routers needed for Phase 1-4:
  /news      — Phase 1 (news fetcher + NLP)
  /chat      — Phase 2 (chatbot)
  /agents    — Phase 3 (AI agent runs)
  /analytics — Phase 4 (stock analysis)

Routers NOT registered (out of scope for Phase 1-4):
  quantlib, intelligence, quant_lab
"""

import asyncio
import sys
from contextlib import asynccontextmanager

# ── Windows: asyncio subprocess cần ProactorEventLoop ────────────────────────
# SelectorEventLoop (default trên Windows) không hỗ trợ create_subprocess_exec.
# Phải set trước khi bất kỳ event loop nào được tạo.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import structlog
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.middleware import AuditLogMiddleware, LoggingMiddleware, RateLimitMiddleware
from app.openapi import custom_openapi
from core.auth import get_current_user
from core.cache import cache
from core.errors import FinceptAPIError, error_handler
from core.logging_setup import configure_logging
from core.script_catalog import catalog

# Configure logging at import time
configure_logging()

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("analytics.startup", version=settings.VERSION, env=settings.ENV)

    # Validate script catalog on startup
    missing = catalog.validate()
    if missing:
        logger.warning("script_catalog.missing_scripts", scripts=missing)

    # Connect Redis cache
    await cache.connect()
    logger.info("redis.connected", url=settings.REDIS_URL)

    yield

    # Graceful shutdown
    await cache.disconnect()
    logger.info("analytics.shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Analytics",
        description=(
            "Analytics microservice for QuantDinger. "
            "Provides News pipeline, Chatbot, AI Agents, and Stock Analytics. "
            "Phase 1-4 capabilities only."
        ),
        version=settings.VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ── Middleware ────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(AuditLogMiddleware)

    # ── Exception handlers ────────────────────────────────────────────────────
    @app.exception_handler(FinceptAPIError)
    async def fincept_error_handler(request: Request, exc: FinceptAPIError):
        return error_handler(exc)

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception):
        logger.error("unhandled_exception", error=str(exc), exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred.",
                    "details": {},
                }
            },
        )

    # ── Routers (Phase 1-4 only) ──────────────────────────────────────────────
    # Phase 1 — News REST API (task 1.5) + WebSocket (task 1.6)
    from app.routers import news
    app.include_router(news.router, prefix="/api/v1/news", tags=["News"])
    # WebSocket endpoint at /ws/news (no /api/v1 prefix — WS path)
    app.include_router(news.ws_router, prefix="/ws", tags=["News WebSocket"])

    # Phase 2 — Chat / Chatbot (stub; full implementation in task 2.2 / 2.3)
    from app.routers import chat
    app.include_router(chat.router, prefix="/api/v1/chat", tags=["Chat"])

    # Phase 3 — AI Agents (already implemented)
    from app.routers import agents
    app.include_router(agents.router, prefix="/api/v1/agents", tags=["AI Agents"])

    # Phase 4 — Stock Analytics (already implemented)
    from app.routers import analytics
    app.include_router(analytics.router, prefix="/api/v1", tags=["Multi-Asset Analytics"])

    # Routers intentionally NOT registered for Phase 1-4:
    #   quantlib   — QuantLib Suite (out of scope)
    #   intelligence — Global Intelligence (out of scope)
    #   quant_lab  — AI Quant Lab (out of scope)

    # ── Custom OpenAPI schema ─────────────────────────────────────────────────
    app.openapi = lambda: custom_openapi(app)  # type: ignore[method-assign]

    # ── Prometheus metrics ────────────────────────────────────────────────────
    from fastapi.responses import Response
    from core.metrics import get_metrics_response

    @app.get("/metrics", include_in_schema=False, tags=["System"])
    async def prometheus_metrics():
        """Prometheus metrics endpoint — scrape with Prometheus or Grafana Agent."""
        data, content_type = get_metrics_response()
        return Response(content=data, media_type=content_type)

    # ── Health check ──────────────────────────────────────────────────────────
    import time as _time
    _startup_time = _time.time()

    @app.get("/health", tags=["System"])
    async def health():
        redis_ok = await cache.ping()
        return {
            "status": "ok",
            "service": settings.SERVICE_NAME,
            "version": settings.VERSION,
            "env": settings.ENV,
            "redis": "ok" if redis_ok else "degraded",
        }

    @app.get("/api/v1/health", tags=["System"])
    async def health_v1(user: dict = Depends(get_current_user)):
        """
        Authenticated health endpoint (Requirement 10.4).

        Requires a valid Bearer token (QD JWT or Analytics-native JWT).
        Returns status, version, and uptime_seconds.
        """
        redis_ok = await cache.ping()
        uptime = round(_time.time() - _startup_time, 1)
        return {
            "status": "ok",
            "version": settings.VERSION,
            "uptime_seconds": uptime,
            "redis": "ok" if redis_ok else "degraded",
        }

    @app.get("/debug/config", include_in_schema=False)
    async def debug_config():
        """Dev-only: show resolved paths (never expose in production)."""
        from pathlib import Path
        return {
            "SCRIPTS_DIR": settings.SCRIPTS_DIR,
            "SCRIPTS_DIR_exists": Path(settings.SCRIPTS_DIR).exists() if settings.SCRIPTS_DIR else False,
            "VENV_NUMPY2_PYTHON": settings.VENV_NUMPY2_PYTHON,
            "VENV_NUMPY2_exists": Path(settings.VENV_NUMPY2_PYTHON).exists() if settings.VENV_NUMPY2_PYTHON else False,
            "fallback_python": sys.executable,
            "ENV": settings.ENV,
        }

    @app.get("/", include_in_schema=False)
    async def root():
        return {"message": "Analytics Microservice", "docs": "/docs"}

    return app


app = create_app()
