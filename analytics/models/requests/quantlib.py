"""Phase 3 — QuantLib Suite request models."""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class OptionPriceRequest(BaseModel):
    S: float = Field(..., gt=0)
    K: float = Field(..., gt=0)
    T: float = Field(..., gt=0)
    r: float
    sigma: float = Field(..., gt=0)
    q: float = Field(default=0.0)
    option_type: str = Field(..., pattern="^(call|put)$")
    model: str = Field(default="bsm", pattern="^(bsm|binomial|monte_carlo)$")


class BatchGreeksRequest(BaseModel):
    contracts: List[Dict[str, Any]] = Field(..., min_length=1, max_length=500)
    model: Optional[str] = Field(default="bsm")


class FXOptionRequest(BaseModel):
    S: float = Field(..., gt=0)
    K: float = Field(..., gt=0)
    T: float = Field(..., gt=0)
    r_d: float
    r_f: float
    sigma: float = Field(..., gt=0)
    option_type: str = Field(..., pattern="^(call|put)$")


class BondPriceRequest(BaseModel):
    face_value: float = Field(..., gt=0)
    coupon_rate: float = Field(..., ge=0.0, le=1.0)
    maturity_years: float = Field(..., gt=0)
    ytm: float = Field(..., gt=0)
    frequency: int = Field(default=2, pattern="^(1|2|4)$")


class BondYTMRequest(BaseModel):
    face_value: float = Field(..., gt=0)
    coupon_rate: float = Field(..., ge=0.0, le=1.0)
    maturity_years: float = Field(..., gt=0)
    clean_price: float = Field(..., gt=0)
    frequency: int = Field(default=2)


class YieldCurveRequest(BaseModel):
    instruments: List[Dict[str, Any]] = Field(..., min_length=2)


class IRSRequest(BaseModel):
    notional: float = Field(..., gt=0)
    fixed_rate: float = Field(..., gt=0)
    tenor_years: float = Field(..., gt=0)
    payment_freq: int = Field(default=2)
    discount_curve: Optional[List[Dict[str, Any]]] = None


class CDSRequest(BaseModel):
    notional: float = Field(..., gt=0)
    spread_bps: float = Field(..., gt=0)
    tenor_years: float = Field(..., gt=0)
    recovery_rate: float = Field(default=0.4, ge=0.0, le=1.0)
    risk_free_rate: float = Field(default=0.05)


class VaRRequest(BaseModel):
    returns: List[float] = Field(..., min_length=10)
    confidence_level: float = Field(default=0.95, ge=0.9, le=0.999)
    method: str = Field(default="historical", pattern="^(historical|parametric|monte_carlo)$")
    horizon_days: int = Field(default=1, ge=1)


class StressTestRequest(BaseModel):
    portfolio: List[Dict[str, Any]]
    scenarios: List[Dict[str, Any]] = Field(..., min_length=1)


class CreditRiskRequest(BaseModel):
    exposure: float = Field(..., gt=0)
    pd: float = Field(..., ge=0.0, le=1.0)
    lgd: float = Field(..., ge=0.0, le=1.0)
    ead: Optional[float] = None


class GBMRequest(BaseModel):
    S0: float = Field(..., gt=0)
    mu: float
    sigma: float = Field(..., gt=0)
    T: float = Field(..., gt=0)
    n_paths: int = Field(default=1000, ge=1, le=10000)
    n_steps: int = Field(default=252, ge=1, le=2520)
    seed: Optional[int] = None


class HestonRequest(BaseModel):
    S0: float = Field(..., gt=0)
    v0: float = Field(..., gt=0)
    kappa: float = Field(..., gt=0)
    theta: float = Field(..., gt=0)
    sigma_v: float = Field(..., gt=0)
    rho: float = Field(..., ge=-1.0, le=1.0)
    r: float
    T: float = Field(..., gt=0)
    K: float = Field(..., gt=0)
    option_type: str = Field(default="call", pattern="^(call|put)$")


class HullWhiteRequest(BaseModel):
    r0: float
    a: float = Field(..., gt=0)
    sigma: float = Field(..., gt=0)
    T: float = Field(..., gt=0)
    n_paths: int = Field(default=1000, ge=1, le=10000)
    n_steps: int = Field(default=252, ge=1)


class VolSurfaceRequest(BaseModel):
    spot: float = Field(..., gt=0)
    strikes: List[float] = Field(..., min_length=2)
    expiries: List[float] = Field(..., min_length=1)
    market_vols: List[List[float]]


class SABRRequest(BaseModel):
    F: float = Field(..., gt=0)
    K: float = Field(..., gt=0)
    T: float = Field(..., gt=0)
    alpha: float = Field(..., gt=0)
    beta: float = Field(..., ge=0.0, le=1.0)
    rho: float = Field(..., ge=-1.0, le=1.0)
    nu: float = Field(..., gt=0)
