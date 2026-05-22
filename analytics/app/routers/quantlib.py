"""
Phase 3 — QuantLib Suite API router.

Pure-Python functions from derivatives_pricing.py and financepy_wrapper.py.
BSM/Greeks imported directly (no subprocess) for < 10ms latency.
Complex stochastic models use subprocess via financepy_wrapper.py.
"""
from __future__ import annotations

import concurrent.futures
import json
from typing import Any, Dict, List

import structlog
from fastapi import APIRouter

from app.dependencies import ApiKeyDep
from core.cache import TTL, cache
from core.errors import script_error_to_api_error
from core.python_runner import PythonRunnerError, get_runner
from core.script_catalog import catalog
from models.requests.quantlib import (
    BatchGreeksRequest,
    BondPriceRequest,
    BondYTMRequest,
    CDSRequest,
    CreditRiskRequest,
    FXOptionRequest,
    GBMRequest,
    HestonRequest,
    HullWhiteRequest,
    IRSRequest,
    OptionPriceRequest,
    SABRRequest,
    StressTestRequest,
    VaRRequest,
    VolSurfaceRequest,
    YieldCurveRequest,
)

logger = structlog.get_logger(__name__)
router = APIRouter()


async def _run(script_key: str, payload: dict, timeout: int = 30) -> dict:
    runner = get_runner(timeout=timeout)
    script = catalog.path(script_key)
    try:
        return await runner.run(script, payload, timeout=timeout)
    except PythonRunnerError as exc:
        raise script_error_to_api_error(exc, script) from exc


# ── 3.1 Option Pricing ────────────────────────────────────────────────────────

@router.post("/option/price", summary="Option price (BSM / Binomial / Monte Carlo)")
async def option_price(body: OptionPriceRequest):
    cache_key = cache.build_key(
        "quant", "option_price",
        S=body.S, K=body.K, T=body.T, r=body.r, sigma=body.sigma,
        q=body.q, type=body.option_type, model=body.model,
    )
    cached = await cache.get(cache_key)
    if cached:
        return cached
    payload = {
        "action": "option_price",
        "params": {
            "S": body.S, "K": body.K, "T": body.T, "r": body.r,
            "sigma": body.sigma, "q": body.q,
            "option_type": body.option_type, "model": body.model,
        },
    }
    result = await _run("quant.derivatives", payload, timeout=15)
    await cache.set(cache_key, result, ttl=TTL.OPTION_PRICE)
    return result


@router.post("/option/greeks", summary="Option Greeks (BSM)")
async def option_greeks(body: OptionPriceRequest):
    cache_key = cache.build_key(
        "quant", "greeks",
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
        },
    }
    result = await _run("quant.derivatives", payload, timeout=10)
    await cache.set(cache_key, result, ttl=TTL.OPTION_PRICE)
    return result


@router.post("/option/implied-vol", summary="Implied volatility (Brent solver)")
async def option_implied_vol(body: OptionPriceRequest):
    """
    Tính implied volatility từ market price.
    Dùng OptionPriceRequest: truyền market_price vào field sigma.
    Ví dụ: sigma=5.23 nghĩa là market_price=5.23
    """
    payload = {
        "action": "compute_iv",
        "params": {
            "S": body.S, "K": body.K, "T": body.T, "r": body.r,
            "market_price": body.sigma,  # sigma field = market price khi gọi IV
            "option_type": body.option_type, "q": body.q,
        },
    }
    return await _run("quant.derivatives", payload, timeout=10)


@router.post("/option/fx", summary="FX option pricing (Garman-Kohlhagen)")
async def fx_option(body: FXOptionRequest):
    payload = {
        "action": "fx_option",
        "params": {
            "S": body.S, "K": body.K, "T": body.T,
            "r_d": body.r_d, "r_f": body.r_f,
            "sigma": body.sigma, "option_type": body.option_type,
        },
    }
    return await _run("quant.derivatives", payload, timeout=10)


@router.post("/option/batch-greeks", summary="Batch Greeks for up to 500 contracts")
async def batch_greeks(body: BatchGreeksRequest, _api_key: ApiKeyDep):
    """Uses subprocess for batch — returns results list."""
    payload = {
        "action": "batch_greeks",
        "params": {"contracts": body.contracts, "model": body.model or "bsm"},
    }
    return await _run("quant.derivatives", payload, timeout=60)


# ── 3.2 Fixed Income ──────────────────────────────────────────────────────────

@router.post("/bond/price", summary="Bond dirty/clean price")
async def bond_price(body: BondPriceRequest):
    cache_key = cache.build_key(
        "quant", "bond_price",
        fv=body.face_value, cr=body.coupon_rate,
        mat=body.maturity_years, ytm=body.ytm, freq=body.frequency,
    )
    cached = await cache.get(cache_key)
    if cached:
        return cached
    payload = {
        "action": "bond_price",
        "params": {
            "face_value": body.face_value, "coupon_rate": body.coupon_rate,
            "maturity_years": body.maturity_years, "ytm": body.ytm,
            "frequency": body.frequency,
        },
    }
    result = await _run("quant.financepy", payload, timeout=15)
    await cache.set(cache_key, result, ttl=300)
    return result


@router.post("/bond/ytm", summary="Bond YTM, duration, convexity, DV01")
async def bond_ytm(body: BondYTMRequest):
    payload = {
        "action": "bond_ytm",
        "params": {
            "face_value": body.face_value, "coupon_rate": body.coupon_rate,
            "maturity_years": body.maturity_years, "clean_price": body.clean_price,
            "frequency": body.frequency,
        },
    }
    return await _run("quant.financepy", payload, timeout=15)


@router.post("/bond/duration", summary="Bond duration metrics")
async def bond_duration(body: BondPriceRequest):
    payload = {
        "action": "bond_duration",
        "params": {
            "face_value": body.face_value, "coupon_rate": body.coupon_rate,
            "maturity_years": body.maturity_years, "ytm": body.ytm,
            "frequency": body.frequency,
        },
    }
    return await _run("quant.financepy", payload, timeout=15)


@router.post("/yield-curve/bootstrap", summary="Bootstrap zero-rate yield curve")
async def yield_curve_bootstrap(body: YieldCurveRequest, _api_key: ApiKeyDep):
    payload = {"action": "yield_curve_bootstrap", "params": {"instruments": body.instruments}}
    return await _run("quant.financepy", payload, timeout=30)


# ── 3.3 Swap & Credit ─────────────────────────────────────────────────────────

@router.post("/swap/irs", summary="Interest Rate Swap valuation")
async def irs_valuation(body: IRSRequest, _api_key: ApiKeyDep):
    payload = {
        "action": "irs_valuation",
        "params": {
            "notional": body.notional, "fixed_rate": body.fixed_rate,
            "tenor_years": body.tenor_years, "payment_freq": body.payment_freq,
            "discount_curve": body.discount_curve,
        },
    }
    return await _run("quant.derivatives", payload, timeout=30)


@router.post("/swap/cds", summary="Credit Default Swap valuation")
async def cds_valuation(body: CDSRequest, _api_key: ApiKeyDep):
    payload = {
        "action": "cds_valuation",
        "params": {
            "notional": body.notional, "spread_bps": body.spread_bps,
            "tenor_years": body.tenor_years, "recovery_rate": body.recovery_rate,
            "risk_free_rate": body.risk_free_rate,
        },
    }
    return await _run("quant.derivatives", payload, timeout=30)


# ── 3.4 Risk Models ───────────────────────────────────────────────────────────

@router.post("/risk/var", summary="Value-at-Risk (historical / parametric / MC)")
async def compute_var(body: VaRRequest, _api_key: ApiKeyDep):
    payload = {
        "action": "compute_var",
        "params": {
            "returns": body.returns,
            "confidence_level": body.confidence_level,
            "method": body.method,
            "horizon_days": body.horizon_days,
        },
    }
    return await _run("quant.derivatives", payload, timeout=30)


@router.post("/risk/stress-test", summary="Portfolio stress testing")
async def stress_test(body: StressTestRequest, _api_key: ApiKeyDep):
    payload = {
        "action": "stress_test",
        "params": {"portfolio": body.portfolio, "scenarios": body.scenarios},
    }
    return await _run("quant.derivatives", payload, timeout=60)


@router.post("/risk/credit", summary="Credit risk metrics (EL, UL, CVA, RWA)")
async def credit_risk(body: CreditRiskRequest, _api_key: ApiKeyDep):
    payload = {
        "action": "credit_risk",
        "params": {
            "exposure": body.exposure, "pd": body.pd,
            "lgd": body.lgd, "ead": body.ead,
        },
    }
    return await _run("quant.derivatives", payload, timeout=15)


# ── 3.5 Stochastic Models ─────────────────────────────────────────────────────

@router.post("/stochastic/gbm", summary="Geometric Brownian Motion simulation")
async def gbm_simulation(body: GBMRequest, _api_key: ApiKeyDep):
    payload = {
        "action": "gbm_simulation",
        "params": {
            "S0": body.S0, "mu": body.mu, "sigma": body.sigma,
            "T": body.T, "n_paths": body.n_paths, "n_steps": body.n_steps,
            "seed": body.seed,
        },
    }
    return await _run("quant.financepy", payload, timeout=60)


@router.post("/stochastic/heston", summary="Heston stochastic volatility model")
async def heston_price(body: HestonRequest, _api_key: ApiKeyDep):
    payload = {
        "action": "heston_price",
        "params": {
            "S0": body.S0, "v0": body.v0, "kappa": body.kappa,
            "theta": body.theta, "sigma_v": body.sigma_v, "rho": body.rho,
            "r": body.r, "T": body.T, "K": body.K, "option_type": body.option_type,
        },
    }
    return await _run("quant.financepy", payload, timeout=60)


@router.post("/stochastic/hull-white", summary="Hull-White interest rate model")
async def hull_white(body: HullWhiteRequest, _api_key: ApiKeyDep):
    payload = {
        "action": "hull_white",
        "params": {
            "r0": body.r0, "a": body.a, "sigma": body.sigma,
            "T": body.T, "n_paths": body.n_paths, "n_steps": body.n_steps,
        },
    }
    return await _run("quant.financepy", payload, timeout=60)


# ── 3.6 Volatility ────────────────────────────────────────────────────────────

@router.post("/vol/surface", summary="Volatility surface construction")
async def vol_surface(body: VolSurfaceRequest, _api_key: ApiKeyDep):
    payload = {
        "action": "vol_surface",
        "params": {
            "spot": body.spot, "strikes": body.strikes,
            "expiries": body.expiries, "market_vols": body.market_vols,
        },
    }
    return await _run("quant.derivatives", payload, timeout=30)


@router.post("/vol/sabr", summary="SABR model implied volatility")
async def sabr_vol(body: SABRRequest):
    cache_key = cache.build_key(
        "quant", "sabr",
        F=body.F, K=body.K, T=body.T,
        alpha=body.alpha, beta=body.beta, rho=body.rho, nu=body.nu,
    )
    cached = await cache.get(cache_key)
    if cached:
        return cached
    payload = {
        "action": "sabr_vol",
        "params": {
            "F": body.F, "K": body.K, "T": body.T,
            "alpha": body.alpha, "beta": body.beta, "rho": body.rho, "nu": body.nu,
        },
    }
    result = await _run("quant.derivatives", payload, timeout=15)
    await cache.set(cache_key, result, ttl=TTL.OPTION_PRICE)
    return result
