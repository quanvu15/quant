"""
LLM Router — multi-model selection và validation.

Vấn đề cần giải quyết:
1. Validate API key trước khi spawn subprocess (fail fast, không chờ 120s)
2. Chọn model phù hợp theo task type:
   - thinking/reasoning → model mạnh (gpt-4o, claude-3-5-sonnet, deepseek-r1)
   - quick answer → model nhanh/rẻ (gpt-4o-mini, llama-3.1-8b, groq)
   - streaming chat → model có streaming tốt
   - structured output → model hỗ trợ JSON mode
3. Fallback khi model chính fail

──────────────────────────────────────────────────────────────────────────────
LLM Integration Approach — Design Decision (Task 2.1)
──────────────────────────────────────────────────────────────────────────────
Decision: Use httpx-based OpenAI-compatible proxy (NOT LiteLLM).

Rationale:
  - LiteLLM adds ~50+ transitive dependencies and significant install weight,
    which conflicts with the lightweight self-hosted deployment goal.
  - All target LLM providers (OpenAI, Anthropic via proxy, Groq, DeepSeek,
    Together, OpenRouter, Mistral, Ollama/local) expose an OpenAI-compatible
    /chat/completions endpoint, so a thin httpx wrapper is sufficient.
  - The httpx wrapper is implemented in `app/routers/chat.py` (_call_llm_non_stream,
    _stream_llm) and handles both streaming SSE and non-streaming responses.
  - This module (llm_router.py) provides provider detection, model selection,
    and config validation — the "routing" layer above the raw httpx calls.

To add a new provider: add an entry to MODEL_PROFILES and update
detect_provider() in app/routers/chat.py if needed.
──────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


# ── Task types ────────────────────────────────────────────────────────────────

class TaskType(str, Enum):
    """Loại task để chọn model phù hợp."""
    QUICK = "quick"           # Trả lời nhanh, đơn giản (< 1s)
    STANDARD = "standard"     # Phân tích thông thường (1-10s)
    THINKING = "thinking"     # Reasoning phức tạp, cần suy nghĩ sâu (10-60s)
    STREAMING = "streaming"   # SSE streaming, cần latency thấp
    STRUCTURED = "structured" # JSON output, cần model hỗ trợ function calling
    FINANCIAL = "financial"   # Phân tích tài chính chuyên sâu


# ── Model profiles ────────────────────────────────────────────────────────────

# Mỗi profile định nghĩa model phù hợp cho từng task type
# Key = provider (auto-detected từ base_url)
MODEL_PROFILES = {
    "openai": {
        TaskType.QUICK:      "gpt-4o-mini",
        TaskType.STANDARD:   "gpt-4o-mini",
        TaskType.THINKING:   "gpt-4o",
        TaskType.STREAMING:  "gpt-4o-mini",
        TaskType.STRUCTURED: "gpt-4o-mini",
        TaskType.FINANCIAL:  "gpt-4o",
    },
    "anthropic": {
        TaskType.QUICK:      "claude-3-haiku-20240307",
        TaskType.STANDARD:   "claude-3-5-haiku-20241022",
        TaskType.THINKING:   "claude-3-5-sonnet-20241022",
        TaskType.STREAMING:  "claude-3-5-haiku-20241022",
        TaskType.STRUCTURED: "claude-3-5-sonnet-20241022",
        TaskType.FINANCIAL:  "claude-3-5-sonnet-20241022",
    },
    "groq": {
        # Groq = ultra-fast inference, tốt cho quick/streaming
        TaskType.QUICK:      "llama-3.1-8b-instant",
        TaskType.STANDARD:   "llama-3.1-70b-versatile",
        TaskType.THINKING:   "llama-3.3-70b-versatile",
        TaskType.STREAMING:  "llama-3.1-8b-instant",
        TaskType.STRUCTURED: "llama-3.1-70b-versatile",
        TaskType.FINANCIAL:  "llama-3.3-70b-versatile",
    },
    "together": {
        TaskType.QUICK:      "meta-llama/Llama-3.2-11B-Vision-Instruct-Turbo",
        TaskType.STANDARD:   "meta-llama/Llama-3.1-70B-Instruct-Turbo",
        TaskType.THINKING:   "meta-llama/Llama-3.1-405B-Instruct-Turbo",
        TaskType.STREAMING:  "meta-llama/Llama-3.2-11B-Vision-Instruct-Turbo",
        TaskType.STRUCTURED: "meta-llama/Llama-3.1-70B-Instruct-Turbo",
        TaskType.FINANCIAL:  "meta-llama/Llama-3.1-405B-Instruct-Turbo",
    },
    "deepseek": {
        TaskType.QUICK:      "deepseek-chat",
        TaskType.STANDARD:   "deepseek-chat",
        TaskType.THINKING:   "deepseek-reasoner",   # DeepSeek-R1 — thinking model
        TaskType.STREAMING:  "deepseek-chat",
        TaskType.STRUCTURED: "deepseek-chat",
        TaskType.FINANCIAL:  "deepseek-reasoner",
    },
    "openrouter": {
        # OpenRouter cho phép dùng nhiều model qua 1 API key
        TaskType.QUICK:      "google/gemini-flash-1.5",
        TaskType.STANDARD:   "anthropic/claude-3.5-haiku",
        TaskType.THINKING:   "anthropic/claude-3.5-sonnet",
        TaskType.STREAMING:  "google/gemini-flash-1.5",
        TaskType.STRUCTURED: "openai/gpt-4o-mini",
        TaskType.FINANCIAL:  "anthropic/claude-3.5-sonnet",
    },
    "mistral": {
        TaskType.QUICK:      "mistral-small-latest",
        TaskType.STANDARD:   "mistral-large-latest",
        TaskType.THINKING:   "mistral-large-latest",
        TaskType.STREAMING:  "mistral-small-latest",
        TaskType.STRUCTURED: "mistral-large-latest",
        TaskType.FINANCIAL:  "mistral-large-latest",
    },
    # Local models — dùng model được cấu hình, không override
    "openai_local": {  # Ollama, LM Studio, vLLM
        TaskType.QUICK:      None,  # dùng model từ config
        TaskType.STANDARD:   None,
        TaskType.THINKING:   None,
        TaskType.STREAMING:  None,
        TaskType.STRUCTURED: None,
        TaskType.FINANCIAL:  None,
    },
}


# ── Task type detection từ action name ───────────────────────────────────────

_THINKING_ACTIONS = {
    "execute_plan", "generate_dynamic_plan", "portfolio_rebal",
    "risk_assessment", "sector_rotation", "run_team", "execute_multi_query",
    "agentic_start_task",
}
_QUICK_ACTIONS = {
    "discover_agents", "list_agents", "paper_get_portfolio",
    "paper_get_positions", "get_session", "list_tasks",
}
_FINANCIAL_ACTIONS = {
    "stock_analysis", "earnings_brief", "macro_scan",
    "portfolio_rebal", "risk_assessment",
}
_STRUCTURED_ACTIONS = {
    "run_structured", "create_stock_plan", "create_portfolio_plan",
}


def detect_task_type(action: str) -> TaskType:
    """Detect task type từ action name để chọn model phù hợp."""
    if action in _THINKING_ACTIONS:
        return TaskType.THINKING
    if action in _QUICK_ACTIONS:
        return TaskType.QUICK
    if action in _FINANCIAL_ACTIONS:
        return TaskType.FINANCIAL
    if action in _STRUCTURED_ACTIONS:
        return TaskType.STRUCTURED
    return TaskType.STANDARD


def get_recommended_model(provider: str, task_type: TaskType) -> Optional[str]:
    """
    Trả về model được recommend cho provider + task type.
    None = dùng model từ config (local models).
    """
    profile = MODEL_PROFILES.get(provider, {})
    if not profile:
        return None
    return profile.get(task_type)


# ── API key validation ────────────────────────────────────────────────────────

def validate_llm_config(model: str, api_key: str, base_url: str, provider: str) -> tuple[bool, str]:
    """
    Validate LLM config trước khi spawn subprocess.
    Fail fast thay vì chờ 120s timeout.

    Returns: (is_valid, error_message)
    """
    # 1. Model phải có
    if not model or not model.strip():
        return False, "LLM model is required"

    # 2. API key — local models không cần key thực
    is_local = "localhost" in base_url or "127.0.0.1" in base_url
    if not is_local:
        if not api_key or not api_key.strip():
            return False, f"API key is required for provider '{provider}'"

        # Basic format check (không gọi API, chỉ check format)
        key = api_key.strip()
        # Chỉ check format key khi là OpenAI native (không phải custom endpoint)
        is_openai_native = provider == "openai" and ("openai.com" in base_url or not base_url)
        if is_openai_native and not (key.startswith("sk-") or key.startswith("sk-proj-")):
            return False, "OpenAI API key must start with 'sk-'"
        if provider == "anthropic" and not key.startswith("sk-ant-"):
            return False, "Anthropic API key must start with 'sk-ant-'"
        if provider == "groq" and not key.startswith("gsk_"):
            return False, "Groq API key must start with 'gsk_'"
        if len(key) < 10:
            return False, "API key appears too short"

    # 3. base_url format
    if not base_url.startswith(("http://", "https://")):
        return False, f"base_url must start with http:// or https://, got: {base_url}"

    return True, ""


def build_active_llm(
    model: str,
    api_key: str,
    base_url: str,
    provider: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    action: str = "",
    auto_select_model: bool = True,
) -> dict:
    """
    Build active_llm dict cho finagent_core/main.py.

    Nếu auto_select_model=True, tự động chọn model phù hợp với task type.
    User vẫn có thể override bằng cách truyền model cụ thể.
    """
    final_model = model

    # Auto-select model theo task type nếu user không chỉ định model cụ thể
    # (chỉ auto-select khi model là default/generic)
    if auto_select_model and action:
        task_type = detect_task_type(action)
        recommended = get_recommended_model(provider, task_type)
        if recommended and model in ("gpt-4o-mini", "gpt-4o", ""):
            # Chỉ override nếu user đang dùng model generic
            # Không override nếu user đã chọn model cụ thể
            final_model = recommended
            logger.debug(
                "llm_router.auto_select",
                action=action,
                task_type=task_type,
                original_model=model,
                selected_model=final_model,
            )

    return {
        "provider": provider if provider != "openai_compat" else "openai",
        "model_id": final_model,
        "api_key": api_key,
        "base_url": base_url,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
