"""Phase 2 — Multi-Asset Analytics request models."""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class BatchQuoteRequest(BaseModel):
    symbols: List[str] = Field(..., min_length=1, max_length=50)
    source: Optional[str] = Field(default="yfinance", pattern="^(yfinance|polygon|finnhub)$")


class HistoryRequest(BaseModel):
    start: Optional[str] = Field(default="2024-01-01", examples=["2024-01-01"])
    end: Optional[str] = Field(default=None, examples=["2025-01-01"])
    interval: Optional[str] = Field(default="1d", examples=["1d", "1h", "5m"])
    source: Optional[str] = Field(default="yfinance")


class DCFRequest(BaseModel):
    growth_rate: Optional[float] = Field(default=None, ge=-1.0, le=5.0)
    discount_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    terminal_growth: Optional[float] = Field(default=0.025, ge=0.0, le=0.2)
    projection_years: Optional[int] = Field(default=5, ge=1, le=20)


class PortfolioOptimizeRequest(BaseModel):
    symbols: List[str] = Field(..., min_length=2)
    method: str = Field(
        default="mean_variance",
        pattern="^(mean_variance|risk_parity|black_litterman|min_variance)$",
    )
    constraints: Optional[Dict[str, Any]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class PortfolioMetricsRequest(BaseModel):
    holdings: List[Dict[str, Any]] = Field(..., description="[{symbol, weight}]")
    start_date: str
    end_date: str
    benchmark: Optional[str] = Field(default="SPY")


class PortfolioBacktestRequest(BaseModel):
    holdings: List[Dict[str, Any]]
    start_date: str
    end_date: str
    rebalance_freq: Optional[str] = Field(default="monthly", pattern="^(monthly|quarterly|annual)$")


class PortfolioVaRRequest(BaseModel):
    holdings: List[Dict[str, Any]]
    confidence_level: float = Field(default=0.95, ge=0.9, le=0.999)
    method: str = Field(default="historical", pattern="^(historical|parametric|monte_carlo)$")


class GreeksRequest(BaseModel):
    S: float = Field(..., gt=0, description="Spot price")
    K: float = Field(..., gt=0, description="Strike price")
    T: float = Field(..., gt=0, description="Time to expiry (years)")
    r: float = Field(..., description="Risk-free rate")
    sigma: float = Field(..., gt=0, description="Volatility")
    q: float = Field(default=0.0, description="Dividend yield")
    option_type: str = Field(..., pattern="^(call|put)$")
    model: Optional[str] = Field(default="bsm", pattern="^(bsm|binomial)$")


class ImpliedVolRequest(BaseModel):
    S: float = Field(..., gt=0)
    K: float = Field(..., gt=0)
    T: float = Field(..., gt=0)
    r: float
    market_price: float = Field(..., gt=0)
    option_type: str = Field(..., pattern="^(call|put)$")
    q: float = Field(default=0.0)


class TechnicalIndicatorsRequest(BaseModel):
    symbol: str
    indicators: List[str] = Field(default=["RSI", "MACD", "BB", "EMA20", "SMA50"])
    period: Optional[str] = Field(default="1y")
    interval: Optional[str] = Field(default="1d")


class TechnicalSignalsRequest(BaseModel):
    symbol: str
    strategy: Optional[str] = Field(default="momentum", pattern="^(momentum|mean_reversion|breakout)$")
