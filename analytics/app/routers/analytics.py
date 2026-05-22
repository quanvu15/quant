"""
Phase 2 — Multi-Asset Analytics API router.

Wraps: yfinance_data.py, polygon_io_data.py, finnhub_data.py,
       derivatives_pricing.py, optimize_portfolio_weights.py,
       quantstats_analysis.py, compute_technicals.py, equity_talipp.py

Phase 4 addition: comprehensive analysis endpoint (task 4.1).
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.config import settings
from app.dependencies import JwtUserDep
from core.cache import TTL, cache
from core.errors import script_error_to_api_error
from core.python_runner import PythonRunnerError, get_runner
from core.script_catalog import catalog
from models.requests.analytics import (
    BatchQuoteRequest,
    DCFRequest,
    GreeksRequest,
    HistoryRequest,
    ImpliedVolRequest,
    PortfolioBacktestRequest,
    PortfolioMetricsRequest,
    PortfolioOptimizeRequest,
    PortfolioVaRRequest,
    TechnicalIndicatorsRequest,
    TechnicalSignalsRequest,
)


# ── Comprehensive analysis request/response models ────────────────────────────

class LLMConfig(BaseModel):
    """Optional LLM configuration for agent opinion section."""
    model: Optional[str] = None
    provider: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 2048


class ComprehensiveRequest(BaseModel):
    """
    Request body for POST /api/v1/analytics/comprehensive/{symbol}.

    All fields are optional — llm_config enables the agent opinion section.
    """
    llm_config: Optional[LLMConfig] = None
    dcf_growth_rate: Optional[float] = None
    dcf_discount_rate: Optional[float] = None
    dcf_terminal_growth: Optional[float] = 0.025
    dcf_projection_years: Optional[int] = 5
    technical_indicators: Optional[List[str]] = None
    technical_period: Optional[str] = "1y"
    technical_interval: Optional[str] = "1d"
    news_limit: int = 10
    agent_id: Optional[str] = "warren_buffett"

logger = structlog.get_logger(__name__)
router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _run(script_key: str, payload: dict, timeout: int = 60) -> dict:
    runner = get_runner(timeout=timeout)
    script = catalog.path(script_key)
    try:
        return await runner.run(script, payload, timeout=timeout)
    except PythonRunnerError as exc:
        raise script_error_to_api_error(exc, script) from exc


# ── 2.1 Market Data ───────────────────────────────────────────────────────────

@router.get("/market/quote/{symbol}", summary="Real-time quote for a symbol")
async def get_quote(
    symbol: str,
    _user: JwtUserDep,
    source: str = Query(default="yfinance", pattern="^(yfinance|polygon|finnhub)$"),
):
    """GET /api/v1/market/quote/{symbol} — TTL 5s cache."""
    cache_key = cache.quote_key(symbol)
    cached = await cache.get(cache_key)
    if cached:
        return cached

    payload = {"action": "get_quote", "params": {"symbol": symbol.upper(), "source": source}}
    result = await _run("market.yfinance", payload, timeout=30)
    await cache.set(cache_key, result, ttl=TTL.QUOTE)
    return result


@router.post("/market/quotes/batch", summary="Batch real-time quotes")
async def get_quotes_batch(body: BatchQuoteRequest, _user: JwtUserDep):
    """POST /api/v1/market/quotes/batch — TTL 5s cache."""
    payload = {
        "action": "get_batch_quotes",
        "params": {"symbols": [s.upper() for s in body.symbols], "source": body.source or "yfinance"},
    }
    result = await _run("market.yfinance", payload, timeout=30)
    return result


@router.get("/market/history/{symbol}", summary="Historical OHLCV bars")
async def get_history(
    symbol: str,
    _user: JwtUserDep,
    start: str = Query(default="2024-01-01"),
    end: Optional[str] = Query(default=None),
    interval: str = Query(default="1d"),
    source: str = Query(default="yfinance"),
):
    """GET /api/v1/market/history/{symbol} — TTL 300s (daily), 30s (intraday)."""
    ttl = TTL.INTRADAY if interval in ("1m", "5m", "15m", "30m", "1h") else TTL.DAILY_HISTORY
    cache_key = cache.history_key(symbol, interval, start, end or "latest")
    cached = await cache.get(cache_key)
    if cached:
        return cached

    payload = {
        "action": "get_history",
        "params": {"symbol": symbol.upper(), "start": start, "end": end, "interval": interval, "source": source},
    }
    result = await _run("market.yfinance", payload, timeout=30)
    await cache.set(cache_key, result, ttl=ttl)
    return result


@router.get("/market/search", summary="Search for symbols")
async def search_symbols(q: str = Query(..., min_length=1), limit: int = Query(default=10, le=50)):
    """GET /api/v1/market/search — no cache (live search)."""
    payload = {"action": "search_symbols", "params": {"query": q, "limit": limit}}
    return await _run("market.yfinance", payload, timeout=15)


@router.get("/market/sectors", summary="Sector performance overview")
async def get_sectors():
    """GET /api/v1/market/sectors — TTL 5 min."""
    cache_key = cache.build_key("market", "sectors")
    cached = await cache.get(cache_key)
    if cached:
        return cached
    payload = {"action": "get_sectors", "params": {}}
    result = await _run("market.yfinance", payload, timeout=30)
    await cache.set(cache_key, result, ttl=300)
    return result


# ── 2.2 Equity Research ───────────────────────────────────────────────────────

@router.get("/equity/{symbol}/info", summary="Company fundamentals & ratios")
async def get_equity_info(symbol: str, _user: JwtUserDep):
    """GET /api/v1/equity/{symbol}/info — TTL 1h."""
    cache_key = cache.equity_info_key(symbol)
    cached = await cache.get(cache_key)
    if cached:
        return cached
    payload = {"action": "get_info", "params": {"symbol": symbol.upper()}}
    result = await _run("market.yfinance", payload, timeout=30)
    await cache.set(cache_key, result, ttl=TTL.EQUITY_INFO)
    return result


@router.get("/equity/{symbol}/financials", summary="Income statement, balance sheet, cash flow")
async def get_financials(
    symbol: str,
    _user: JwtUserDep,
    period: str = Query(default="annual", pattern="^(annual|quarterly)$"),
    limit: int = Query(default=4, ge=1, le=20),
):
    """GET /api/v1/equity/{symbol}/financials — TTL 1h."""
    cache_key = cache.build_key("equity", "financials", symbol=symbol, period=period, limit=limit)
    cached = await cache.get(cache_key)
    if cached:
        return cached
    payload = {"action": "get_financials", "params": {"symbol": symbol.upper(), "period": period, "limit": limit}}
    result = await _run("market.yfinance", payload, timeout=30)
    await cache.set(cache_key, result, ttl=TTL.EQUITY_INFO)
    return result


@router.post("/equity/{symbol}/dcf", summary="DCF intrinsic value calculation")
async def run_dcf(symbol: str, body: DCFRequest, _user: JwtUserDep):
    """POST /api/v1/equity/{symbol}/dcf — TTL 30 min."""
    cache_key = cache.build_key(
        "equity", "dcf",
        symbol=symbol,
        growth=body.growth_rate,
        discount=body.discount_rate,
        terminal=body.terminal_growth,
        years=body.projection_years,
    )
    cached = await cache.get(cache_key)
    if cached:
        return cached
    payload = {
        "action": "run_dcf",
        "params": {
            "symbol": symbol.upper(),
            "growth_rate": body.growth_rate,
            "discount_rate": body.discount_rate,
            "terminal_growth": body.terminal_growth,
            "projection_years": body.projection_years,
        },
    }
    result = await _run("market.yfinance", payload, timeout=60)
    await cache.set(cache_key, result, ttl=TTL.DCF)
    return result


@router.get("/equity/{symbol}/news", summary="Latest news with sentiment")
async def get_equity_news(
    symbol: str,
    limit: int = Query(default=20, ge=1, le=100),
    source: str = Query(default="finnhub"),
):
    """GET /api/v1/equity/{symbol}/news — TTL 5 min."""
    cache_key = cache.build_key("equity", "news", symbol=symbol, limit=limit, source=source)
    cached = await cache.get(cache_key)
    if cached:
        return cached
    payload = {"action": "get_news", "params": {"symbol": symbol.upper(), "limit": limit, "source": source}}
    result = await _run("equity.news", payload, timeout=30)
    await cache.set(cache_key, result, ttl=TTL.NEWS)
    return result


@router.get("/equity/{symbol}/relationships", summary="Corporate relationship graph")
async def get_relationships(symbol: str):
    """GET /api/v1/equity/{symbol}/relationships — TTL 10 min."""
    cache_key = cache.build_key("equity", "relationships", symbol=symbol)
    cached = await cache.get(cache_key)
    if cached:
        return cached
    payload = {"action": "get_relationships", "params": {"ticker": symbol.upper()}}
    result = await _run("equity.relationships", payload, timeout=30)
    await cache.set(cache_key, result, ttl=600)
    return result


# ── 2.3 Portfolio Analytics ───────────────────────────────────────────────────

@router.post("/portfolio/optimize", summary="Portfolio weight optimization")
async def optimize_portfolio(body: PortfolioOptimizeRequest, _user: JwtUserDep):
    """POST /api/v1/portfolio/optimize."""
    payload = {
        "action": "optimize",
        "params": {
            "symbols": body.symbols,
            "method": body.method,
            "constraints": body.constraints or {},
            "start_date": body.start_date,
            "end_date": body.end_date,
        },
    }
    return await _run("portfolio.optimize", payload, timeout=120)


@router.post("/portfolio/metrics", summary="Portfolio performance metrics")
async def portfolio_metrics(body: PortfolioMetricsRequest, _user: JwtUserDep):
    """POST /api/v1/portfolio/metrics."""
    payload = {
        "action": "compute_metrics",
        "params": {
            "holdings": body.holdings,
            "start_date": body.start_date,
            "end_date": body.end_date,
            "benchmark": body.benchmark,
        },
    }
    return await _run("portfolio.quantstats", payload, timeout=120)


@router.post("/portfolio/backtest", summary="Portfolio backtest with equity curve")
async def portfolio_backtest(body: PortfolioBacktestRequest, _user: JwtUserDep):
    """POST /api/v1/portfolio/backtest."""
    payload = {
        "action": "backtest",
        "params": {
            "holdings": body.holdings,
            "start_date": body.start_date,
            "end_date": body.end_date,
            "rebalance_freq": body.rebalance_freq,
        },
    }
    return await _run("portfolio.quantstats", payload, timeout=120)


@router.post("/portfolio/var", summary="Portfolio Value-at-Risk")
async def portfolio_var(body: PortfolioVaRRequest, _user: JwtUserDep):
    """POST /api/v1/portfolio/var."""
    payload = {
        "action": "compute_var",
        "params": {
            "holdings": body.holdings,
            "confidence_level": body.confidence_level,
            "method": body.method,
        },
    }
    return await _run("portfolio.quantstats", payload, timeout=60)


# ── 2.4 Derivatives & F&O ─────────────────────────────────────────────────────

@router.get("/derivatives/chain/{symbol}", summary="Options chain with Greeks")
async def get_options_chain(
    symbol: str,
    expiry: Optional[str] = Query(default=None),
    broker: str = Query(default="zerodha"),
):
    """GET /api/v1/derivatives/chain/{symbol} — TTL 5s."""
    cache_key = cache.build_key("derivatives", "chain", symbol=symbol, expiry=expiry, broker=broker)
    cached = await cache.get(cache_key)
    if cached:
        return cached
    payload = {
        "action": "get_option_chain",
        "params": {"symbol": symbol.upper(), "expiry": expiry, "broker": broker},
    }
    result = await _run("derivatives.pricing", payload, timeout=30)
    await cache.set(cache_key, result, ttl=TTL.QUOTE)
    return result


@router.post("/derivatives/greeks", summary="Option Greeks (BSM)")
async def compute_greeks(body: GreeksRequest):
    """POST /api/v1/derivatives/greeks — TTL 60s."""
    cache_key = cache.build_key(
        "derivatives", "greeks",
        S=body.S, K=body.K, T=body.T, r=body.r, sigma=body.sigma,
        q=body.q, type=body.option_type,
    )
    cached = await cache.get(cache_key)
    if cached:
        return cached
    payload = {
        "action": "compute_greeks",
        "params": {
            "S": body.S, "K": body.K, "T": body.T, "r": body.r,
            "sigma": body.sigma, "q": body.q, "option_type": body.option_type,
            "model": body.model,
        },
    }
    result = await _run("derivatives.pricing", payload, timeout=15)
    await cache.set(cache_key, result, ttl=TTL.OPTION_PRICE)
    return result


@router.post("/derivatives/implied-vol", summary="Implied volatility (BSM solver)")
async def compute_implied_vol(body: ImpliedVolRequest):
    """POST /api/v1/derivatives/implied-vol."""
    payload = {
        "action": "compute_iv",
        "params": {
            "S": body.S, "K": body.K, "T": body.T, "r": body.r,
            "market_price": body.market_price, "option_type": body.option_type, "q": body.q,
        },
    }
    return await _run("derivatives.pricing", payload, timeout=15)


@router.get("/derivatives/fii-dii", summary="FII/DII activity data")
async def get_fii_dii(days: int = Query(default=30, ge=1, le=365)):
    """GET /api/v1/derivatives/fii-dii — TTL 30 min."""
    cache_key = cache.build_key("derivatives", "fii_dii", days=days)
    cached = await cache.get(cache_key)
    if cached:
        return cached
    payload = {"action": "get_fii_dii", "params": {"days": days}}
    result = await _run("derivatives.fii_dii", payload, timeout=30)
    await cache.set(cache_key, result, ttl=1800)
    return result


# ── 2.5 Technical Analysis ────────────────────────────────────────────────────

@router.post("/technical/indicators", summary="Compute technical indicators")
async def compute_indicators(body: TechnicalIndicatorsRequest, _user: JwtUserDep):
    """POST /api/v1/technical/indicators — TTL 1 min."""
    cache_key = cache.build_key(
        "technical", "indicators",
        symbol=body.symbol, indicators=sorted(body.indicators),
        period=body.period, interval=body.interval,
    )
    cached = await cache.get(cache_key)
    if cached:
        return cached
    payload = {
        "action": "compute_indicators",
        "params": {
            "symbol": body.symbol.upper(),
            "indicators": body.indicators,
            "period": body.period,
            "interval": body.interval,
        },
    }
    result = await _run("technical.compute", payload, timeout=30)
    await cache.set(cache_key, result, ttl=60)
    return result


@router.post("/technical/signals", summary="Trading signals from technical strategy")
async def compute_signals(body: TechnicalSignalsRequest, _user: JwtUserDep):
    """POST /api/v1/technical/signals — TTL 1 min."""
    cache_key = cache.build_key("technical", "signals", symbol=body.symbol, strategy=body.strategy)
    cached = await cache.get(cache_key)
    if cached:
        return cached
    payload = {
        "action": "compute_signals",
        "params": {"symbol": body.symbol.upper(), "strategy": body.strategy},
    }
    result = await _run("technical.compute", payload, timeout=30)
    await cache.set(cache_key, result, ttl=60)
    return result


# ── 4.5 Comprehensive Stock Analysis ─────────────────────────────────────────

async def _safe_call(coro, section: str) -> tuple[str, Any]:
    """
    Wrap a coroutine so that failures return an error dict instead of raising.

    Returns (section_name, result_or_error_dict).
    Enables graceful partial failures in asyncio.gather.
    """
    try:
        result = await coro
        return section, result
    except Exception as exc:
        logger.warning(
            "comprehensive.section_failed",
            section=section,
            error=str(exc),
        )
        return section, {"error": str(exc), "section": section}


async def _fetch_agent_opinion(symbol: str, llm_config: LLMConfig, agent_id: str) -> Dict[str, Any]:
    """
    Call the agent runner to get an AI opinion on the symbol.

    Uses the same subprocess bridge as the agents router.
    Returns a dict with the agent response or an error.
    """
    from core.llm_router import build_active_llm, validate_llm_config
    from core.python_runner import PythonRunner, PythonRunnerError

    model_id = llm_config.model or settings.LLM_MODEL or ""
    provider = llm_config.provider or "openai"
    base_url = llm_config.base_url or settings.LLM_BASE_URL or ""
    api_key = llm_config.api_key or settings.LLM_API_KEY or ""
    temperature = llm_config.temperature if llm_config.temperature is not None else 0.7
    max_tokens = llm_config.max_tokens or 2048

    # Auto-detect provider for custom endpoints
    if provider == "openai" and base_url and "openai.com" not in base_url:
        provider = "openai_compat"

    llm_provider = "openai" if provider == "openai_compat" else provider

    active_llm = build_active_llm(
        model=model_id,
        api_key=api_key,
        base_url=base_url,
        provider=llm_provider,
        temperature=temperature,
        max_tokens=max_tokens,
        action="stock_analysis",
        auto_select_model=False,
    )

    payload = {
        "action": "stock_analysis",
        "api_keys": {},
        "params": {"symbol": symbol.upper(), "session_id": None},
        "config": {},
        "active_llm": active_llm,
    }

    agents_script = catalog.path("agents.main")
    runner = PythonRunner(timeout=60)
    try:
        result = await runner.run(agents_script, payload, timeout=60)
        return {
            "agent_id": agent_id,
            "response": result.get("response") or result.get("result"),
            "success": result.get("success", True),
        }
    except PythonRunnerError as exc:
        raise exc


@router.post(
    "/analytics/comprehensive/{symbol}",
    summary="Comprehensive stock analysis — all sections in one call",
    description=(
        "Aggregates quote, equity info, DCF valuation, technical indicators, "
        "recent news (last 10), and optional AI agent opinion for a symbol. "
        "Uses asyncio.gather for concurrent sub-calls. "
        "Cache TTL: 60s. Response p95 target: < 8s. "
        "Partial failures are returned as error objects per section rather than "
        "failing the entire response. "
        "_Validates: Requirement 4.5_"
    ),
)
async def comprehensive_analysis(
    symbol: str,
    body: Optional[ComprehensiveRequest] = None,
):
    """
    POST /api/v1/analytics/comprehensive/{symbol}

    Concurrent calls via asyncio.gather:
      - GET /market/quote/{symbol}          (TTL 5s)
      - GET /equity/{symbol}/info           (TTL 1h)
      - POST /equity/{symbol}/dcf           (TTL 30min)
      - POST /technical/indicators          (RSI, MACD, BB)
      - GET /equity/{symbol}/news           (last 10 articles)
      - Agent opinion                       (only if llm_config provided)

    Cache aggregated result with TTL 60s.
    Graceful partial failure: if one section fails, the rest are still returned.
    """
    req = body or ComprehensiveRequest()
    sym = symbol.upper()

    # ── Cache check ───────────────────────────────────────────────────────────
    # Include llm_config presence in cache key so LLM/no-LLM responses are
    # cached separately (agent opinion is expensive and provider-specific).
    has_llm = req.llm_config is not None
    cache_key = cache.build_key(
        "analytics", "comprehensive",
        symbol=sym,
        has_llm=has_llm,
        dcf_growth=req.dcf_growth_rate,
        dcf_discount=req.dcf_discount_rate,
        dcf_terminal=req.dcf_terminal_growth,
        dcf_years=req.dcf_projection_years,
        indicators=sorted(req.technical_indicators or ["RSI", "MACD", "BB"]),
        period=req.technical_period,
        interval=req.technical_interval,
        news_limit=req.news_limit,
    )

    cached = await cache.get(cache_key)
    if cached:
        cached["_cached"] = True
        return cached

    t0 = time.monotonic()

    # ── Build sub-call coroutines ─────────────────────────────────────────────

    # 1. Real-time quote
    async def _quote():
        quote_cache_key = cache.quote_key(sym)
        hit = await cache.get(quote_cache_key)
        if hit:
            return hit
        payload = {"action": "get_quote", "params": {"symbol": sym, "source": "yfinance"}}
        result = await _run("market.yfinance", payload, timeout=30)
        await cache.set(quote_cache_key, result, ttl=TTL.QUOTE)
        return result

    # 2. Equity info / fundamentals
    async def _info():
        info_cache_key = cache.equity_info_key(sym)
        hit = await cache.get(info_cache_key)
        if hit:
            return hit
        payload = {"action": "get_info", "params": {"symbol": sym}}
        result = await _run("market.yfinance", payload, timeout=30)
        await cache.set(info_cache_key, result, ttl=TTL.EQUITY_INFO)
        return result

    # 3. DCF valuation
    async def _dcf():
        dcf_cache_key = cache.build_key(
            "equity", "dcf",
            symbol=sym,
            growth=req.dcf_growth_rate,
            discount=req.dcf_discount_rate,
            terminal=req.dcf_terminal_growth,
            years=req.dcf_projection_years,
        )
        hit = await cache.get(dcf_cache_key)
        if hit:
            return hit
        payload = {
            "action": "run_dcf",
            "params": {
                "symbol": sym,
                "growth_rate": req.dcf_growth_rate,
                "discount_rate": req.dcf_discount_rate,
                "terminal_growth": req.dcf_terminal_growth,
                "projection_years": req.dcf_projection_years,
            },
        }
        result = await _run("market.yfinance", payload, timeout=60)
        await cache.set(dcf_cache_key, result, ttl=TTL.DCF)
        return result

    # 4. Technical indicators (RSI, MACD, BB by default)
    indicators = req.technical_indicators or ["RSI", "MACD", "BB"]

    async def _technicals():
        tech_cache_key = cache.build_key(
            "technical", "indicators",
            symbol=sym,
            indicators=sorted(indicators),
            period=req.technical_period,
            interval=req.technical_interval,
        )
        hit = await cache.get(tech_cache_key)
        if hit:
            return hit
        payload = {
            "action": "compute_indicators",
            "params": {
                "symbol": sym,
                "indicators": indicators,
                "period": req.technical_period,
                "interval": req.technical_interval,
            },
        }
        result = await _run("technical.compute", payload, timeout=30)
        await cache.set(tech_cache_key, result, ttl=60)
        return result

    # 5. Recent news (last 10 articles)
    async def _news():
        news_cache_key = cache.build_key(
            "equity", "news",
            symbol=sym,
            limit=req.news_limit,
            source="finnhub",
        )
        hit = await cache.get(news_cache_key)
        if hit:
            return hit
        payload = {
            "action": "get_news",
            "params": {"symbol": sym, "limit": req.news_limit, "source": "finnhub"},
        }
        result = await _run("equity.news", payload, timeout=30)
        await cache.set(news_cache_key, result, ttl=TTL.NEWS)
        return result

    # ── Assemble concurrent tasks ─────────────────────────────────────────────
    tasks = [
        _safe_call(_quote(), "quote"),
        _safe_call(_info(), "info"),
        _safe_call(_dcf(), "dcf"),
        _safe_call(_technicals(), "technicals"),
        _safe_call(_news(), "news"),
    ]

    # 6. Agent opinion — only when llm_config is provided
    if req.llm_config is not None:
        agent_id = req.agent_id or "warren_buffett"
        tasks.append(
            _safe_call(
                _fetch_agent_opinion(sym, req.llm_config, agent_id),
                "agent_opinion",
            )
        )

    # ── Execute all concurrently ──────────────────────────────────────────────
    results = await asyncio.gather(*tasks)

    elapsed_ms = (time.monotonic() - t0) * 1000

    # ── Build response ────────────────────────────────────────────────────────
    response: Dict[str, Any] = {
        "symbol": sym,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_ms": round(elapsed_ms, 1),
        "_cached": False,
    }

    has_errors = False
    for section_name, section_result in results:
        response[section_name] = section_result
        if isinstance(section_result, dict) and "error" in section_result and len(section_result) <= 2:
            has_errors = True

    if has_errors:
        response["_partial"] = True

    # ── Cache aggregated result ───────────────────────────────────────────────
    # Only cache if no critical sections failed (quote + info must succeed).
    quote_ok = not (isinstance(response.get("quote"), dict) and "error" in response.get("quote", {}))
    info_ok = not (isinstance(response.get("info"), dict) and "error" in response.get("info", {}))

    if quote_ok and info_ok:
        await cache.set(cache_key, response, ttl=60)

    logger.info(
        "comprehensive.done",
        symbol=sym,
        elapsed_ms=round(elapsed_ms, 1),
        has_errors=has_errors,
        has_llm=has_llm,
    )

    return response
