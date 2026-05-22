"""
OpenAPI 3.0 customization — rich descriptions, examples, tags, error schemas.
Applied to the FastAPI app in main.py via app.openapi = custom_openapi.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

# ── Tag descriptions ──────────────────────────────────────────────────────────

TAGS_METADATA = [
    {
        "name": "System",
        "description": "Health check and system status endpoints.",
    },
    {
        "name": "AI Agents",
        "description": (
            "Expose `finagent_core/main.py` as REST + SSE streaming API.\n\n"
            "**LLM Config** — OpenAI-compatible: pass `model`, `api_key`, `base_url`.\n"
            "Provider is auto-detected from `base_url` (OpenAI, Groq, Together, DeepSeek, "
            "Anthropic, Ollama, LM Studio, OpenRouter, Mistral, ...).\n\n"
            "**Streaming** — `POST /run/stream` returns `text/event-stream` (SSE).\n"
            "Events: `{type: thinking|token|tool|done|error, content: string}`\n\n"
            "**Auth** — All write endpoints require `X-API-Key` header."
        ),
    },
    {
        "name": "Multi-Asset Analytics",
        "description": (
            "Market data, equity research, portfolio analytics, derivatives pricing.\n\n"
            "**Cache TTLs:** quotes=5s · history=30s/300s · equity info=1h · DCF=30min\n\n"
            "**Scripts wrapped:** yfinance_data.py · polygon_io_data.py · finnhub_data.py · "
            "derivatives_pricing.py · optimize_portfolio_weights.py · quantstats_analysis.py · "
            "compute_technicals.py"
        ),
    },
    {
        "name": "QuantLib Suite",
        "description": (
            "Quantitative finance: option pricing, fixed income, risk models, stochastic simulations.\n\n"
            "**Option models:** BSM · Binomial · Monte Carlo · Garman-Kohlhagen (FX)\n\n"
            "**Fixed income:** Bond price/YTM/duration · Yield curve bootstrap\n\n"
            "**Risk:** VaR (historical/parametric/MC) · Stress testing · Credit risk (EL/UL/CVA/RWA)\n\n"
            "**Stochastic:** GBM · Heston · Hull-White · Vol surface · SABR\n\n"
            "**Scripts wrapped:** derivatives_pricing.py · financepy_wrapper.py"
        ),
    },
    {
        "name": "Global Intelligence",
        "description": (
            "Geopolitics, maritime tracking, macroeconomics, government data, energy.\n\n"
            "**Geopolitics:** ACLED conflict events · HDX humanitarian data\n\n"
            "**Maritime:** Vessel position/history · Area search (AIS)\n\n"
            "**Economics:** FRED · World Bank · IMF · OECD · 12 central banks · Economic calendar\n\n"
            "**Gov Data:** BLS · Census · Eurostat · EIA energy · CO2 emissions\n\n"
            "**Cache TTLs:** events=2min · economics=1h · environment=24h"
        ),
    },
    {
        "name": "AI Quant Lab",
        "description": (
            "Qlib ML models, backtesting, factor discovery, RL trading.\n\n"
            "**Async job pattern:** Long-running tasks return `{job_id, status: queued}` (HTTP 202).\n"
            "Poll `GET /jobs/{id}` for status, `GET /jobs/{id}/result` for output.\n"
            "Stream progress via `WS /jobs/{id}/stream`.\n\n"
            "**Sync endpoints:** predict, portfolio/optimize, report/factor-attribution\n\n"
            "**Scripts wrapped:** qlib_service.py · qlib_advanced_backtest.py · qlib_rl.py · "
            "qlib_portfolio_opt.py · qlib_feature_engineering.py · qlib_reporting.py"
        ),
    },
]

# ── Error response schema ─────────────────────────────────────────────────────

ERROR_SCHEMA = {
    "ErrorResponse": {
        "type": "object",
        "properties": {
            "error": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "enum": [
                            "AUTH_REQUIRED",
                            "RATE_LIMITED",
                            "SCRIPT_TIMEOUT",
                            "SCRIPT_ERROR",
                            "INVALID_PARAMS",
                            "EXTERNAL_API_ERROR",
                            "MISSING_API_KEY",
                            "JOB_NOT_FOUND",
                            "JOB_FAILED",
                            "INTERNAL_ERROR",
                        ],
                        "description": "Machine-readable error code",
                    },
                    "message": {"type": "string", "description": "Human-readable error message"},
                    "details": {"type": "object", "description": "Additional error context"},
                    "request_id": {"type": "string", "format": "uuid"},
                },
                "required": ["code", "message"],
            }
        },
    }
}

# ── Common response examples ──────────────────────────────────────────────────

COMMON_RESPONSES: Dict[str, Any] = {
    "401": {
        "description": "Authentication required — missing or invalid `X-API-Key`",
        "content": {
            "application/json": {
                "example": {
                    "error": {
                        "code": "AUTH_REQUIRED",
                        "message": "X-API-Key header is required.",
                        "details": {},
                        "request_id": "550e8400-e29b-41d4-a716-446655440000",
                    }
                }
            }
        },
    },
    "422": {
        "description": "Request validation failed",
        "content": {
            "application/json": {
                "example": {
                    "error": {
                        "code": "INVALID_PARAMS",
                        "message": "Request validation failed.",
                        "details": {"field": "symbol", "issue": "field required"},
                    }
                }
            }
        },
    },
    "429": {
        "description": "Rate limit exceeded",
        "content": {
            "application/json": {
                "example": {
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": "Rate limit exceeded. Max 60 requests/minute.",
                        "details": {"limit": 60, "window": "1m"},
                    }
                }
            }
        },
    },
    "502": {
        "description": "Python script returned an error",
        "content": {
            "application/json": {
                "example": {
                    "error": {
                        "code": "SCRIPT_ERROR",
                        "message": "Script 'yfinance_data.py' returned an error.",
                        "details": {"exit_code": 1, "stderr": "..."},
                    }
                }
            }
        },
    },
    "504": {
        "description": "Script execution timed out",
        "content": {
            "application/json": {
                "example": {
                    "error": {
                        "code": "SCRIPT_TIMEOUT",
                        "message": "Script timed out after 120s.",
                        "details": {"timeout_seconds": 120},
                    }
                }
            }
        },
    },
}


def custom_openapi(app: FastAPI) -> Dict[str, Any]:
    """Generate enriched OpenAPI schema with descriptions, examples, error schemas."""
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title="Fincept Terminal API",
        version="1.0.0",
        summary="REST + WebSocket API for Fincept Terminal's 5 core modules",
        description=_API_DESCRIPTION,
        routes=app.routes,
        tags=TAGS_METADATA,
    )

    # Inject error schemas into components
    schema.setdefault("components", {}).setdefault("schemas", {}).update(ERROR_SCHEMA)

    # Add common security scheme
    schema["components"].setdefault("securitySchemes", {}).update(
        {
            "ApiKeyAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
                "description": "API key in format: `fincept_<tier>_<key>`",
            },
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "JWT token obtained from auth endpoint",
            },
        }
    )

    # Apply security globally (except health)
    schema["security"] = [{"ApiKeyAuth": []}, {"BearerAuth": []}]

    app.openapi_schema = schema
    return schema


_API_DESCRIPTION = """
## Fincept Terminal API

REST + WebSocket API exposing Fincept Terminal's 5 core modules to external projects.

### Modules

| Module | Base Path | Description |
|--------|-----------|-------------|
| AI Agents | `/api/v1/agents` | LLM-powered financial agents, SSE streaming |
| Multi-Asset Analytics | `/api/v1/market`, `/api/v1/equity`, `/api/v1/portfolio` | Market data, equity research, portfolio analytics |
| QuantLib Suite | `/api/v1/quant` | Option pricing, fixed income, risk models |
| Global Intelligence | `/api/v1/intelligence` | Geopolitics, maritime, economics, gov data |
| AI Quant Lab | `/api/v1/quant-lab` | Qlib ML models, backtesting, RL trading |

### Authentication

All endpoints except `GET /health` require authentication:

```
X-API-Key: fincept_free_<your_key>
```

Or JWT Bearer:
```
Authorization: Bearer <jwt_token>
```

### LLM Configuration (OpenAI-compatible)

All agent endpoints accept an `llm_config` object using OpenAI-compatible format:

```json
{
  "model": "gpt-4o",
  "api_key": "sk-...",
  "base_url": "https://api.openai.com/v1"
}
```

Provider is **auto-detected** from `base_url`. Supported providers:
- **OpenAI**: `https://api.openai.com/v1`
- **Groq**: `https://api.groq.com/openai/v1`
- **Together**: `https://api.together.xyz/v1`
- **DeepSeek**: `https://api.deepseek.com/v1`
- **Anthropic**: `https://api.anthropic.com`
- **Ollama** (local): `http://localhost:11434/v1`
- **LM Studio** (local): `http://localhost:1234/v1`
- **OpenRouter**: `https://openrouter.ai/api/v1`

### Rate Limits

| Tier | Limit | Header |
|------|-------|--------|
| Free | 60 req/min | `X-RateLimit-Limit: 60` |
| Paid | 600 req/min | `X-RateLimit-Limit: 600` |

### Error Codes

| Code | HTTP | Description |
|------|------|-------------|
| `AUTH_REQUIRED` | 401 | Missing or invalid API key |
| `RATE_LIMITED` | 429 | Too many requests |
| `SCRIPT_TIMEOUT` | 504 | Python script timed out |
| `SCRIPT_ERROR` | 502 | Python script returned error |
| `INVALID_PARAMS` | 422 | Request validation failed |
| `EXTERNAL_API_ERROR` | 502 | Upstream data source error |
| `MISSING_API_KEY` | 400 | Required external API key not configured |
| `JOB_NOT_FOUND` | 404 | Async job ID not found |
| `JOB_FAILED` | 200 | Async job failed (check job.error) |

### Async Job Pattern (AI Quant Lab)

Long-running tasks use an async job pattern:

```
POST /api/v1/quant-lab/backtest  →  {job_id: "abc123", status: "queued"}  [HTTP 202]
GET  /api/v1/quant-lab/jobs/abc123  →  {status: "running", progress: 45}
GET  /api/v1/quant-lab/jobs/abc123/result  →  {status: "completed", result: {...}}
WS   /api/v1/quant-lab/jobs/abc123/stream  →  real-time progress events
```
"""
