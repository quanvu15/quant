"""
Phase 1 — AI Agents API request models.

LLM config dùng OpenAI-compatible API:
  - base_url: endpoint của bất kỳ provider nào (OpenAI, Groq, Together, Ollama, LM Studio...)
  - api_key: API key của provider
  - model: tên model (gpt-4o, llama-3.1-70b, mistral-large, v.v.)
  - provider: optional, chỉ dùng để hint cho finagent_core (mặc định "openai")
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


# ── LLM Config (OpenAI-compatible) ───────────────────────────────────────────

class LLMConfig(BaseModel):
    """
    OpenAI-compatible LLM configuration.

    Hỗ trợ mọi provider có OpenAI-compatible endpoint:
    - OpenAI:      base_url="https://api.openai.com/v1",  model="gpt-4o"
    - Groq:        base_url="https://api.groq.com/openai/v1", model="llama-3.1-70b-versatile"
    - Together:    base_url="https://api.together.xyz/v1", model="meta-llama/Llama-3-70b"
    - Ollama:      base_url="http://localhost:11434/v1",  model="llama3.2", api_key="ollama"
    - LM Studio:   base_url="http://localhost:1234/v1",   model="local-model", api_key="lm-studio"
    - DeepSeek:    base_url="https://api.deepseek.com/v1", model="deepseek-chat"
    - Anthropic*:  base_url="https://api.anthropic.com",  model="claude-3-5-sonnet-20241022"
      (*finagent_core tự detect provider từ base_url nếu cần)
    """

    model: str = Field(
        ...,
        description="Model name (e.g. gpt-4o, llama-3.1-70b-versatile, deepseek-chat)",
        examples=["gpt-4o", "gpt-4o-mini", "llama-3.1-70b-versatile", "deepseek-chat"],
    )
    api_key: str = Field(
        ...,
        description="API key for the provider. Use 'ollama' or 'lm-studio' for local models.",
    )
    base_url: str = Field(
        default="https://api.openai.com/v1",
        description="OpenAI-compatible API base URL",
        examples=[
            "https://api.openai.com/v1",
            "https://api.groq.com/openai/v1",
            "https://api.together.xyz/v1",
            "http://localhost:11434/v1",
        ],
    )
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1, le=128000)

    # provider là optional — auto-detected từ base_url nếu không truyền
    # finagent_core/main.py dùng field này để chọn SDK (openai / anthropic / google)
    provider: Optional[str] = Field(
        default=None,
        description=(
            "Provider hint (openai/anthropic/google/groq/...). "
            "Tự động detect từ base_url nếu để trống."
        ),
    )

    @model_validator(mode="after")
    def auto_detect_provider(self) -> "LLMConfig":
        """Tự động detect provider từ base_url nếu không được truyền."""
        if self.provider:
            return self
        url = self.base_url.lower()
        if "anthropic.com" in url:
            self.provider = "anthropic"
        elif "generativelanguage.googleapis.com" in url or "google" in url:
            self.provider = "google"
        elif "groq.com" in url:
            self.provider = "groq"
        elif "together.xyz" in url:
            self.provider = "together"
        elif "deepseek.com" in url:
            self.provider = "deepseek"
        elif "openrouter.ai" in url:
            self.provider = "openrouter"
        elif "mistral.ai" in url:
            self.provider = "mistral"
        elif "cohere.com" in url:
            self.provider = "cohere"
        elif "localhost" in url or "127.0.0.1" in url:
            # Local models (Ollama, LM Studio, vLLM, etc.)
            self.provider = "openai"
        else:
            # Default: treat as OpenAI-compatible
            self.provider = "openai"
        return self


# ── Agent Run ─────────────────────────────────────────────────────────────────

class AgentRunRequest(BaseModel):
    agent_id: Optional[str] = Field(None, description="Specific agent persona ID")
    query: str = Field(..., min_length=1, max_length=10000)
    session_id: Optional[str] = None
    llm_config: LLMConfig
    options: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional: {memory, reasoning, guardrails, tracing}",
    )


# ── Team / Multi-Agent ────────────────────────────────────────────────────────

class TeamMember(BaseModel):
    agent_id: str
    role: Optional[str] = None


class TeamConfig(BaseModel):
    name: str
    mode: str = Field(default="coordinate", examples=["coordinate", "route", "collaborate"])
    members: List[TeamMember]
    coordinator_model: Optional[LLMConfig] = None


class TeamRunRequest(BaseModel):
    team_config: TeamConfig
    query: str = Field(..., min_length=1)
    session_id: Optional[str] = None
    llm_config: LLMConfig


class MultiAgentRunRequest(BaseModel):
    query: str = Field(..., min_length=1)
    agent_ids: Optional[List[str]] = None
    llm_config: LLMConfig
    aggregate: bool = True


# ── Execution Planner ─────────────────────────────────────────────────────────

class StockPlanRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    llm_config: LLMConfig


class PortfolioPlanRequest(BaseModel):
    portfolio_id: str
    llm_config: LLMConfig


class ExecutePlanRequest(BaseModel):
    plan: Dict[str, Any]
    llm_config: LLMConfig


class DynamicPlanRequest(BaseModel):
    query: str = Field(..., min_length=1)
    llm_config: LLMConfig


# ── Financial Workflows ───────────────────────────────────────────────────────

class StockAnalysisRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    llm_config: LLMConfig
    session_id: Optional[str] = None


class PortfolioAnalysisRequest(BaseModel):
    portfolio_data: Dict[str, Any]
    llm_config: LLMConfig


class RiskAnalysisRequest(BaseModel):
    portfolio_data: Dict[str, Any]
    llm_config: LLMConfig


class MacroAnalysisRequest(BaseModel):
    llm_config: LLMConfig


class EarningsAnalysisRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    llm_config: LLMConfig


class SectorRotationRequest(BaseModel):
    llm_config: LLMConfig


# ── Paper Trading ─────────────────────────────────────────────────────────────

class PaperTradeRequest(BaseModel):
    portfolio_id: str
    symbol: str = Field(..., min_length=1, max_length=20)
    action: str = Field(..., pattern="^(buy|sell)$")
    quantity: float = Field(..., gt=0)
    price: float = Field(..., gt=0)


# ── Session Management ────────────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    agent_id: str
    user_id: Optional[str] = None


class AddMessageRequest(BaseModel):
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str = Field(..., min_length=1)



# ── Agent Run ─────────────────────────────────────────────────────────────────

class AgentRunRequest(BaseModel):
    agent_id: Optional[str] = Field(None, description="Specific agent persona ID")
    query: str = Field(..., min_length=1, max_length=10000)
    session_id: Optional[str] = None
    llm_config: LLMConfig
    options: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional: {memory, reasoning, guardrails, tracing}",
    )


# ── Team / Multi-Agent ────────────────────────────────────────────────────────

class TeamMember(BaseModel):
    agent_id: str
    role: Optional[str] = None


class TeamConfig(BaseModel):
    name: str
    mode: str = Field(default="coordinate", examples=["coordinate", "route", "collaborate"])
    members: List[TeamMember]
    coordinator_model: Optional[LLMConfig] = None


class TeamRunRequest(BaseModel):
    team_config: TeamConfig
    query: str = Field(..., min_length=1)
    session_id: Optional[str] = None
    llm_config: LLMConfig


class MultiAgentRunRequest(BaseModel):
    query: str = Field(..., min_length=1)
    agent_ids: Optional[List[str]] = None
    llm_config: LLMConfig
    aggregate: bool = True


# ── Execution Planner ─────────────────────────────────────────────────────────

class StockPlanRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    llm_config: LLMConfig


class PortfolioPlanRequest(BaseModel):
    portfolio_id: str
    llm_config: LLMConfig


class ExecutePlanRequest(BaseModel):
    plan: Dict[str, Any]
    llm_config: LLMConfig


class DynamicPlanRequest(BaseModel):
    query: str = Field(..., min_length=1)
    llm_config: LLMConfig


# ── Financial Workflows ───────────────────────────────────────────────────────

class StockAnalysisRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    llm_config: LLMConfig
    session_id: Optional[str] = None


class PortfolioAnalysisRequest(BaseModel):
    portfolio_data: Dict[str, Any]
    llm_config: LLMConfig


class RiskAnalysisRequest(BaseModel):
    portfolio_data: Dict[str, Any]
    llm_config: LLMConfig


class MacroAnalysisRequest(BaseModel):
    llm_config: LLMConfig


class EarningsAnalysisRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    llm_config: LLMConfig


class SectorRotationRequest(BaseModel):
    llm_config: LLMConfig


# ── Paper Trading ─────────────────────────────────────────────────────────────

class PaperTradeRequest(BaseModel):
    portfolio_id: str
    symbol: str = Field(..., min_length=1, max_length=20)
    action: str = Field(..., pattern="^(buy|sell)$")
    quantity: float = Field(..., gt=0)
    price: float = Field(..., gt=0)


# ── Session Management ────────────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    agent_id: str
    user_id: Optional[str] = None


class AddMessageRequest(BaseModel):
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str = Field(..., min_length=1)
