"""
Phase 2 — Chat / Chatbot API router.

Tasks implemented:
  2.2 — Chat completions (LLM proxy, streaming SSE)
  2.3 — Session CRUD (Postgres persist, ownership check)
  2.4 — Token accounting (tokens_in/tokens_out/latency_ms per message,
                          GET /sessions/{id}/usage aggregate)
  2.5 — System prompt presets (YAML-backed, injected on session create)
  2.6 — Auto-inject conversation history (server-side memory)

Endpoints:
  POST /api/v1/chat/completions                    — OpenAI-compatible chat completions
  POST /api/v1/chat/sessions                       — create session
  GET  /api/v1/chat/sessions                       — list sessions for current user
  GET  /api/v1/chat/sessions/{id}                  — session detail + messages
  DELETE /api/v1/chat/sessions/{id}                — delete session
  POST /api/v1/chat/sessions/{id}/messages         — add message manually
  GET  /api/v1/chat/sessions/{id}/usage            — aggregate token usage (task 2.4)
  GET  /api/v1/chat/presets                        — list system prompt presets (task 2.5)
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx
import structlog
import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import JwtUserDep
from core.database import get_db
from core.metrics import record_chat_tokens
from models.db.chat import ChatMessage, ChatSession

# ── Presets loader (loaded once at module import time) ────────────────────────

_PRESETS_FILE = Path(__file__).parent.parent.parent / "domains" / "chat" / "presets.yaml"

def _load_presets() -> Dict[str, dict]:
    """Load presets from YAML file. Returns a dict keyed by preset id."""
    try:
        with open(_PRESETS_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return {p["id"]: p for p in data.get("presets", [])}
    except Exception as exc:
        structlog.get_logger(__name__).warning("presets.load_failed", error=str(exc))
        return {}

# Module-level cache — loaded once on startup
_PRESETS_CACHE: Dict[str, dict] = _load_presets()

logger = structlog.get_logger(__name__)

router = APIRouter()


# ── Request / Response models ─────────────────────────────────────────────────

class LLMConfig(BaseModel):
    """OpenAI-compatible LLM configuration."""
    model: str = Field(..., description="Model name, e.g. gpt-4o, deepseek-chat")
    api_key: str = Field(..., description="Provider API key")
    base_url: str = Field(
        default="https://api.openai.com/v1",
        description="OpenAI-compatible base URL",
    )
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1, le=128000)


class MessageIn(BaseModel):
    role: str = Field(..., pattern="^(system|user|assistant|tool)$")
    content: str = Field(..., min_length=1)


class ChatCompletionRequest(BaseModel):
    model: Optional[str] = None
    messages: List[MessageIn]
    stream: bool = False
    llm_config: LLMConfig
    session_id: Optional[str] = Field(None, description="Persist messages to this session")
    history_limit: int = Field(
        default=20,
        ge=0,
        le=100,
        description=(
            "Number of past messages to auto-inject from session history before the new messages. "
            "0 = disable history injection. Default 20. "
            "Server-side memory: client only needs to send the latest message(s)."
        ),
    )


class CreateSessionRequest(BaseModel):
    title: Optional[str] = None
    persona_id: Optional[str] = None
    llm_config: Optional[LLMConfig] = None
    preset_id: Optional[str] = Field(None, description="System prompt preset ID to inject as first message")


class AddMessageRequest(BaseModel):
    role: str = Field(..., pattern="^(system|user|assistant|tool)$")
    content: str = Field(..., min_length=1)
    tokens_in: Optional[int] = Field(None, ge=0)
    tokens_out: Optional[int] = Field(None, ge=0)
    latency_ms: Optional[int] = Field(None, ge=0)


class MessageOut(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    tokens_in: Optional[int]
    tokens_out: Optional[int]
    latency_ms: Optional[int]
    created_at: str


class SessionOut(BaseModel):
    session_id: str
    title: Optional[str]
    persona_id: Optional[str]
    model: Optional[str]
    created_at: str
    messages: Optional[List[MessageOut]] = None


class SessionUsageOut(BaseModel):
    """Aggregate token usage for a session — task 2.4."""
    session_id: str
    total_tokens_in: int
    total_tokens_out: int
    total_tokens: int
    message_count: int


class PresetOut(BaseModel):
    """Public preset info — system_prompt is intentionally excluded."""
    id: str
    name: str
    name_vi: str
    description: str


# ── LLM proxy helpers ─────────────────────────────────────────────────────────

def _build_openai_payload(request: ChatCompletionRequest) -> dict:
    """Build the JSON body for an OpenAI-compatible completions call."""
    cfg = request.llm_config
    return {
        "model": request.model or cfg.model,
        "messages": [m.model_dump() for m in request.messages],
        "temperature": cfg.temperature,
        "max_tokens": cfg.max_tokens,
        "stream": request.stream,
    }


def _auth_headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def _detect_provider(base_url: str) -> str:
    """Detect LLM provider name from base_url for metrics labeling."""
    url = (base_url or "").lower()
    if "openai.com" in url:
        return "openai"
    if "groq.com" in url:
        return "groq"
    if "anthropic.com" in url:
        return "anthropic"
    if "together.ai" in url:
        return "together"
    if "mistral.ai" in url:
        return "mistral"
    if "cohere.com" in url:
        return "cohere"
    if "localhost" in url or "127.0.0.1" in url:
        return "ollama"
    return "openai_compat"


async def _call_llm_non_stream(
    request: ChatCompletionRequest,
) -> tuple[dict, int, int, int]:
    """
    Call LLM provider (non-streaming).

    Returns: (response_json, tokens_in, tokens_out, latency_ms)
    """
    cfg = request.llm_config
    url = cfg.base_url.rstrip("/") + "/chat/completions"
    payload = _build_openai_payload(request)

    t0 = time.monotonic()
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, json=payload, headers=_auth_headers(cfg.api_key))

    latency_ms = int((time.monotonic() - t0) * 1000)

    if resp.status_code != 200:
        logger.warning(
            "llm.error",
            status=resp.status_code,
            body=resp.text[:500],
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "LLM_PROVIDER_ERROR",
                "message": f"LLM provider returned {resp.status_code}",
                "details": {"body": resp.text[:500]},
            },
        )

    data = resp.json()
    usage = data.get("usage") or {}
    tokens_in = usage.get("prompt_tokens") or 0
    tokens_out = usage.get("completion_tokens") or 0

    return data, tokens_in, tokens_out, latency_ms


async def _stream_llm(
    request: ChatCompletionRequest,
) -> AsyncIterator[tuple[str, int, int, int]]:
    """
    Stream LLM provider response as SSE chunks.

    Yields: (sse_line, tokens_in, tokens_out, latency_ms)
    The token counts are only non-zero on the final [DONE] chunk (if provider sends usage).
    """
    cfg = request.llm_config
    url = cfg.base_url.rstrip("/") + "/chat/completions"
    payload = _build_openai_payload(request)

    tokens_in = 0
    tokens_out = 0
    t0 = time.monotonic()

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST", url, json=payload, headers=_auth_headers(cfg.api_key)
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail={
                        "code": "LLM_PROVIDER_ERROR",
                        "message": f"LLM provider returned {resp.status_code}",
                    },
                )

            async for raw_line in resp.aiter_lines():
                if not raw_line:
                    continue
                if raw_line.startswith("data:"):
                    chunk_str = raw_line[5:].strip()
                    if chunk_str == "[DONE]":
                        latency_ms = int((time.monotonic() - t0) * 1000)
                        yield f"data: [DONE]\n\n", tokens_in, tokens_out, latency_ms
                        return
                    try:
                        chunk = json.loads(chunk_str)
                        # Some providers send usage in the final streaming chunk
                        usage = chunk.get("usage") or {}
                        if usage.get("prompt_tokens"):
                            tokens_in = usage["prompt_tokens"]
                        if usage.get("completion_tokens"):
                            tokens_out = usage["completion_tokens"]
                    except json.JSONDecodeError:
                        pass
                    yield f"{raw_line}\n\n", tokens_in, tokens_out, 0


# ── DB helpers ────────────────────────────────────────────────────────────────

def _session_to_out(session: ChatSession, include_messages: bool = False) -> SessionOut:
    out = SessionOut(
        session_id=str(session.id),
        title=session.title,
        persona_id=session.persona_id,
        model=session.model,
        created_at=session.created_at.isoformat(),
    )
    if include_messages:
        out.messages = [_message_to_out(m) for m in (session.messages or [])]
    return out


def _message_to_out(msg: ChatMessage) -> MessageOut:
    return MessageOut(
        id=str(msg.id),
        session_id=str(msg.session_id),
        role=msg.role,
        content=msg.content,
        tokens_in=msg.tokens_in,
        tokens_out=msg.tokens_out,
        latency_ms=msg.latency_ms,
        created_at=msg.created_at.isoformat(),
    )


async def _get_session_owned(
    session_id: str,
    user_id: str,
    db: AsyncSession,
) -> ChatSession:
    """Fetch session by ID; raise 404 if not found or not owned by user."""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND", "message": "Session not found"})

    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == sid,
            ChatSession.user_id == user_id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND", "message": "Session not found"})
    return session


async def _persist_message(
    db: AsyncSession,
    session_id: uuid.UUID,
    role: str,
    content: str,
    tokens_in: Optional[int] = None,
    tokens_out: Optional[int] = None,
    latency_ms: Optional[int] = None,
) -> ChatMessage:
    """Insert a ChatMessage row and return it."""
    msg = ChatMessage(
        session_id=session_id,
        role=role,
        content=content,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency_ms,
    )
    db.add(msg)
    await db.flush()  # get generated id without committing
    return msg


async def _load_session_history(
    db: AsyncSession,
    session_id: uuid.UUID,
    limit: int,
) -> List[dict]:
    """
    Load the last `limit` messages from a session, ordered oldest-first.

    Returns a list of {"role": ..., "content": ...} dicts ready to prepend
    to the LLM messages array.

    This is the core of server-side memory: the client only needs to send
    the latest message(s); the server automatically injects conversation
    history so the LLM has full context.

    System messages are always included (they define persona/preset).
    Non-system messages are limited to the last `limit` entries.
    """
    if limit <= 0:
        return []

    # Load system messages (always include — they define the persona/preset)
    system_result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.session_id == session_id,
            ChatMessage.role == "system",
        )
        .order_by(ChatMessage.created_at)
    )
    system_msgs = list(system_result.scalars().all())

    # Load last N non-system messages (user + assistant turns)
    history_result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.session_id == session_id,
            ChatMessage.role != "system",
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )
    # Reverse to get chronological order (oldest first)
    history_msgs = list(reversed(history_result.scalars().all()))

    # Combine: system first, then history
    all_msgs = system_msgs + history_msgs
    return [{"role": m.role, "content": m.content} for m in all_msgs]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "/completions",
    summary="Chat completions with server-side memory (OpenAI-compatible)",
    description=(
        "OpenAI-compatible chat completions endpoint with **server-side conversation memory**. "
        "\n\n"
        "**Memory behavior:** When `session_id` is provided, the server automatically loads "
        "the last `history_limit` messages from the session and prepends them to the LLM call. "
        "The client only needs to send the **latest message(s)** — no need to manage history manually. "
        "\n\n"
        "**Message order sent to LLM:** `[system prompt] + [last N history] + [new messages from client]`"
        "\n\n"
        "Supports streaming SSE via `stream=true`. "
        "Token usage is tracked per message and aggregated via `GET /sessions/{id}/usage`."
    ),
    tags=["Chat"],
)
async def chat_completions(
    body: ChatCompletionRequest,
    current_user: JwtUserDep,
    db: AsyncSession = Depends(get_db),
):
    """
    LLM proxy with token accounting.

    - Forwards request to the configured LLM provider (OpenAI-compatible).
    - Parses usage.prompt_tokens / usage.completion_tokens from response.
    - If session_id is given, persists user messages + assistant reply with token counts.
    """
    user_id = current_user.get("sub") or current_user.get("user_id", "")

    # Validate session ownership if session_id provided
    session: Optional[ChatSession] = None
    if body.session_id:
        session = await _get_session_owned(body.session_id, user_id, db)

    # ── Server-side memory: inject conversation history ───────────────────────
    # When a session_id is provided and history_limit > 0, load past messages
    # from DB and prepend them to the LLM call. This means the client only
    # needs to send the latest message(s) — the server handles memory.
    #
    # Message order sent to LLM:
    #   [system prompt (from preset)] + [last N history messages] + [new messages from client]
    effective_messages = list(body.messages)
    if session is not None and body.history_limit > 0:
        history = await _load_session_history(db, session.id, limit=body.history_limit)
        if history:
            # Prepend history, but avoid duplicating system messages if client already sent one
            client_has_system = any(m.role == "system" for m in body.messages)
            if client_has_system:
                # Filter out system messages from history to avoid conflict
                history = [h for h in history if h["role"] != "system"]
            effective_messages = [MessageIn(**h) for h in history] + list(body.messages)
            logger.debug(
                "chat.history_injected",
                session_id=body.session_id,
                history_count=len(history),
                new_messages=len(body.messages),
                total_messages=len(effective_messages),
            )

    # Build a modified request with the full message history for the LLM call
    # (we keep body.messages for persistence — only save the NEW messages, not history)
    llm_request = body.model_copy(update={"messages": effective_messages})

    if body.stream:
        # ── Streaming path ────────────────────────────────────────────────────
        # We need to collect the full assistant response to persist it after streaming.
        # We buffer the content and token counts, then write to DB after the stream ends.
        collected_content: list[str] = []
        final_tokens_in = 0
        final_tokens_out = 0
        final_latency_ms = 0

        async def _generate():
            nonlocal final_tokens_in, final_tokens_out, final_latency_ms
            try:
                async for sse_line, t_in, t_out, lat in _stream_llm(llm_request):
                    # Accumulate token counts from streaming chunks
                    if t_in:
                        final_tokens_in = t_in
                    if t_out:
                        final_tokens_out = t_out
                    if lat:
                        final_latency_ms = lat

                    # Extract content from delta for buffering
                    if sse_line.startswith("data:") and "[DONE]" not in sse_line:
                        try:
                            chunk_str = sse_line[5:].strip()
                            if chunk_str:
                                chunk = json.loads(chunk_str)
                                delta = (
                                    chunk.get("choices", [{}])[0]
                                    .get("delta", {})
                                    .get("content", "")
                                ) or ""
                                if delta:
                                    collected_content.append(delta)
                        except (json.JSONDecodeError, IndexError, KeyError):
                            pass

                    yield sse_line

            except HTTPException as exc:
                err = json.dumps({"error": exc.detail})
                yield f"data: {err}\n\n"
                return

            # After stream ends — persist ONLY the new messages to DB (not history)
            if session is not None:
                try:
                    # Persist only the new user messages (body.messages, not history)
                    for msg in body.messages:
                        if msg.role == "user":
                            await _persist_message(
                                db, session.id, msg.role, msg.content,
                                tokens_in=None, tokens_out=None, latency_ms=None,
                            )
                    # Persist assistant reply with token accounting
                    assistant_content = "".join(collected_content)
                    if assistant_content:
                        await _persist_message(
                            db, session.id, "assistant", assistant_content,
                            tokens_in=final_tokens_in,
                            tokens_out=final_tokens_out,
                            latency_ms=final_latency_ms,
                        )
                    await db.commit()
                except Exception as e:
                    logger.error("chat.persist_stream_error", error=str(e))
                    await db.rollback()

            # Record Prometheus token metric after stream completes
            total_tokens = final_tokens_in + final_tokens_out
            if total_tokens > 0:
                provider = _detect_provider(body.llm_config.base_url)
                model = body.model or body.llm_config.model
                record_chat_tokens(provider=provider, model=model, tokens=total_tokens)

        return StreamingResponse(
            _generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    else:
        # ── Non-streaming path ────────────────────────────────────────────────
        data, tokens_in, tokens_out, latency_ms = await _call_llm_non_stream(llm_request)

        # Record Prometheus token metric
        provider = _detect_provider(body.llm_config.base_url)
        model = body.model or body.llm_config.model
        total_tokens = tokens_in + tokens_out
        if total_tokens > 0:
            record_chat_tokens(provider=provider, model=model, tokens=total_tokens)

        # Persist ONLY the new messages to DB (not history)
        if session is not None:
            try:
                # Persist only new user messages (body.messages, not history)
                for msg in body.messages:
                    if msg.role == "user":
                        await _persist_message(
                            db, session.id, msg.role, msg.content,
                            tokens_in=None, tokens_out=None, latency_ms=None,
                        )
                # Persist assistant reply with token accounting
                assistant_content = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                ) or ""
                if assistant_content:
                    await _persist_message(
                        db, session.id, "assistant", assistant_content,
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        latency_ms=latency_ms,
                    )
                await db.commit()
            except Exception as e:
                logger.error("chat.persist_error", error=str(e))
                await db.rollback()

        # Inject token accounting into response for transparency
        if "usage" not in data:
            data["usage"] = {}
        data["usage"]["prompt_tokens"] = tokens_in
        data["usage"]["completion_tokens"] = tokens_out
        data["usage"]["total_tokens"] = tokens_in + tokens_out
        data["_latency_ms"] = latency_ms
        # Inform client how many history messages were injected
        data["_history_injected"] = len(effective_messages) - len(body.messages)

        return data


@router.post(
    "/sessions",
    summary="Create a chat session",
    status_code=201,
    tags=["Chat"],
)
async def create_session(
    body: CreateSessionRequest,
    current_user: JwtUserDep,
    db: AsyncSession = Depends(get_db),
) -> SessionOut:
    """Create a new persistent chat session owned by the authenticated user.

    If `preset_id` is provided, the corresponding system prompt is injected
    as the first message (role=system) in the session.
    """
    user_id = current_user.get("sub") or current_user.get("user_id", "")
    if not user_id:
        raise HTTPException(status_code=400, detail={"code": "INVALID_PARAMS", "message": "Invalid user_id in token"})

    # Validate preset_id if provided
    preset_system_prompt: Optional[str] = None
    if body.preset_id is not None:
        preset = _PRESETS_CACHE.get(body.preset_id)
        if preset is None:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "INVALID_PARAMS",
                    "message": f"Unknown preset_id '{body.preset_id}'. "
                               f"Valid values: {list(_PRESETS_CACHE.keys())}",
                },
            )
        preset_system_prompt = preset.get("system_prompt", "")

    session = ChatSession(
        user_id=user_id,
        title=body.title,
        persona_id=body.persona_id,
        model=body.llm_config.model if body.llm_config else None,
        base_url=body.llm_config.base_url if body.llm_config else None,
    )
    db.add(session)
    await db.flush()  # get session.id before inserting message

    # Inject system prompt as first message when preset is specified
    if preset_system_prompt:
        await _persist_message(
            db, session.id, "system", preset_system_prompt.strip(),
        )

    await db.commit()
    await db.refresh(session)

    logger.info(
        "chat.session_created",
        session_id=str(session.id),
        user_id=user_id,
        preset_id=body.preset_id,
    )
    return _session_to_out(session)


@router.get(
    "/sessions",
    summary="List chat sessions",
    tags=["Chat"],
)
async def list_sessions(
    current_user: JwtUserDep,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Dict[str, Any]:
    """Return all sessions owned by the authenticated user, newest first."""
    user_id = current_user.get("sub") or current_user.get("user_id", "")
    if not user_id:
        return {"sessions": [], "total": 0}

    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user_id)
        .order_by(ChatSession.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    sessions = result.scalars().all()
    return {"sessions": [_session_to_out(s) for s in sessions], "total": len(sessions)}


@router.get(
    "/sessions/{session_id}",
    summary="Get chat session detail",
    tags=["Chat"],
)
async def get_session(
    session_id: str,
    current_user: JwtUserDep,
    db: AsyncSession = Depends(get_db),
) -> SessionOut:
    """Return session metadata and message history. Returns 404 if session belongs to another user."""
    user_id = current_user.get("sub") or current_user.get("user_id", "")
    session = await _get_session_owned(session_id, user_id, db)

    # Eagerly load messages
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at)
    )
    session.messages = list(result.scalars().all())

    return _session_to_out(session, include_messages=True)


@router.delete(
    "/sessions/{session_id}",
    summary="Delete a chat session",
    status_code=204,
    tags=["Chat"],
)
async def delete_session(
    session_id: str,
    current_user: JwtUserDep,
    db: AsyncSession = Depends(get_db),
):
    """Delete session and all its messages (cascade)."""
    user_id = current_user.get("sub") or current_user.get("user_id", "")
    session = await _get_session_owned(session_id, user_id, db)
    await db.delete(session)
    await db.commit()
    logger.info("chat.session_deleted", session_id=session_id, user_id=user_id)
    return None


@router.post(
    "/sessions/{session_id}/messages",
    summary="Add a message to a session",
    tags=["Chat"],
)
async def add_message(
    session_id: str,
    body: AddMessageRequest,
    current_user: JwtUserDep,
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    """Manually append a message to an existing session."""
    user_id = current_user.get("sub") or current_user.get("user_id", "")
    session = await _get_session_owned(session_id, user_id, db)

    msg = await _persist_message(
        db, session.id, body.role, body.content,
        tokens_in=body.tokens_in,
        tokens_out=body.tokens_out,
        latency_ms=body.latency_ms,
    )
    await db.commit()
    await db.refresh(msg)
    return _message_to_out(msg)


@router.get(
    "/sessions/{session_id}/usage",
    summary="Get aggregate token usage for a session",
    description=(
        "Returns the sum of tokens_in, tokens_out, and total tokens across all messages "
        "in the session. **Validates: Requirements 2.3 (token accounting)**."
    ),
    tags=["Chat"],
)
async def get_session_usage(
    session_id: str,
    current_user: JwtUserDep,
    db: AsyncSession = Depends(get_db),
) -> SessionUsageOut:
    """
    Aggregate token usage for a session.

    **Property 8 (design.md):** tokens_in + tokens_out >= 0;
    cumulative sum per session matches sum of individual messages.
    """
    user_id = current_user.get("sub") or current_user.get("user_id", "")
    # Ownership check — raises 404 if not found or not owned
    session = await _get_session_owned(session_id, user_id, db)

    # Aggregate query: SUM(tokens_in), SUM(tokens_out), COUNT(*)
    result = await db.execute(
        select(
            func.coalesce(func.sum(ChatMessage.tokens_in), 0).label("total_tokens_in"),
            func.coalesce(func.sum(ChatMessage.tokens_out), 0).label("total_tokens_out"),
            func.count(ChatMessage.id).label("message_count"),
        ).where(ChatMessage.session_id == session.id)
    )
    row = result.one()

    total_in = int(row.total_tokens_in)
    total_out = int(row.total_tokens_out)

    return SessionUsageOut(
        session_id=session_id,
        total_tokens_in=total_in,
        total_tokens_out=total_out,
        total_tokens=total_in + total_out,
        message_count=int(row.message_count),
    )


@router.get(
    "/presets",
    summary="List system prompt presets",
    description=(
        "Returns available system prompt presets (stock_analysis, macro_outlook, etc.). "
        "The `system_prompt` field is intentionally excluded from the response. "
        "**Validates: Requirements 2.4**."
    ),
    tags=["Chat"],
)
async def list_presets() -> Dict[str, Any]:
    """
    Return all available system prompt presets loaded from YAML.

    Presets are cached in memory at startup. The `system_prompt` field is
    not exposed in the response to avoid leaking prompt engineering details.
    """
    presets_out = [
        PresetOut(
            id=p["id"],
            name=p["name"],
            name_vi=p["name_vi"],
            description=p["description"],
        ).model_dump()
        for p in _PRESETS_CACHE.values()
    ]
    return {"presets": presets_out}
