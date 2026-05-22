"""
Phase 1 — AI Agents API response models.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class AgentInfo(BaseModel):
    model_config = {"extra": "ignore"}  # bỏ qua fields lạ từ agent configs

    id: str
    name: str
    description: str
    category: str
    version: str = "1.0.0"
    provider: str = "local"
    capabilities: List[str] = []
    config: Dict[str, Any] = {}


class AgentListResponse(BaseModel):
    agents: List[AgentInfo]
    categories: List[str]
    count: int


class AgentRunResponse(BaseModel):
    success: bool
    response: Optional[str] = None
    execution_time_ms: Optional[float] = None
    request_id: Optional[str] = None
    error: Optional[str] = None


class MultiAgentRunResponse(BaseModel):
    success: bool
    responses: List[Dict[str, Any]] = []
    aggregated: Optional[str] = None
    execution_time_ms: Optional[float] = None


class PlanResponse(BaseModel):
    success: bool
    plan: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class PlanExecuteResponse(BaseModel):
    success: bool
    results: List[Any] = []
    execution_time_ms: Optional[float] = None


class PaperTradeResponse(BaseModel):
    success: bool
    trade_id: Optional[str] = None
    error: Optional[str] = None


class PortfolioResponse(BaseModel):
    success: bool
    portfolio_value: Optional[float] = None
    cash: Optional[float] = None
    positions: List[Dict[str, Any]] = []


class SessionResponse(BaseModel):
    session_id: str
    agent_id: Optional[str] = None
    messages: List[Dict[str, Any]] = []
    status: str = "active"


class CreateSessionResponse(BaseModel):
    session_id: str
