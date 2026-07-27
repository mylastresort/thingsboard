"""Langfuse observability integration for the ADK agent.

Provides after_model_callback that logs generation-level data (token usage,
cost, latency) to a self-hosted Langfuse instance. All Langfuse objects live
at module scope — they are NOT stored in ADK session state, which would break
JSON serialization.

Disable by omitting LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY env vars.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_response import LlmResponse

logger = logging.getLogger(__name__)

_lf_client: Any | None = None
_traces: dict[str, Any] = {}
_generation_seq: int = 0

_MODEL_PREFIX_RE = re.compile(r"^(?:ollama_chat/|ollama/)")


def _get_langfuse() -> Any | None:
    """Lazy-init singleton — returns None when unconfigured."""
    global _lf_client
    if _lf_client is not None:
        return _lf_client

    from langfuse import Langfuse

    public_key = None
    secret_key = None
    host = "http://langfuse:3000"

    # Pull from env at import time (settings module not wired here)
    import os
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    host = os.environ.get("LANGFUSE_HOST", host)

    if not public_key or not secret_key:
        logger.warning(
            "Langfuse disabled: LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY not set"
        )
        return None

    try:
        _lf_client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
            flush_at=15,
            flush_interval=1,
        )
        logger.info("Langfuse connected to %s", host)
    except Exception:
        logger.exception("Langfuse init failed — tracing disabled")
        _lf_client = None
    return _lf_client


def shutdown_langfuse() -> None:
    """Flush buffered events on process exit."""
    if _lf_client is not None:
        try:
            _lf_client.flush()
        except Exception:
            logger.debug("Langfuse flush error (non-fatal)")


# ---------------------------------------------------------------------------
# ADK callback: after_model_callback
# ---------------------------------------------------------------------------

async def after_model_callback(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> None:
    """Log every model call to Langfuse as a Generation trace."""
    lf = _get_langfuse()
    if lf is None:
        return

    usage = getattr(llm_response, "usage_metadata", None)
    if usage is None:
        return

    prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
    completion_tokens = getattr(usage, "candidates_token_count", 0) or 0
    total_tokens = getattr(usage, "total_token_count", 0) or 0
    cached_tokens = getattr(usage, "cached_content_token_count", 0) or 0

    # Model name from the LlmResponse or fall back to env
    model_name = getattr(llm_response, "model_version", None) or "unknown"
    model_name = _MODEL_PREFIX_RE.sub("", model_name)

    # Conversation ID from session state
    session_state = callback_context.state
    conversation_id = session_state.get("conversation_id", "unknown")
    user_id = session_state.get("user_id", "anonymous")

    # Agent name from invocation context
    agent_name = "thingsboard_ops_agent"
    if hasattr(callback_context, "invocation_context"):
        ic = callback_context.invocation_context
        if hasattr(ic, "agent_name"):
            agent_name = ic.agent_name

    # Extract text content from candidates
    text_parts: list[str] = []
    for candidate in getattr(llm_response, "content", None).parts if getattr(llm_response, "content", None) else []:
        if hasattr(candidate, "text") and candidate.text:
            text_parts.append(candidate.text)
    output_text = "\n".join(text_parts)[:4000] if text_parts else ""

    global _generation_seq
    _generation_seq += 1

    generation_name = f"{agent_name}:generation:{_generation_seq}"

    try:
        trace = _traces.get(conversation_id)
        if trace is None:
            trace = lf.trace(
                name=agent_name,
                session_id=conversation_id,
                user_id=user_id,
                metadata={"conversation_id": conversation_id},
            )
            _traces[conversation_id] = trace

        trace.generation(
            name=generation_name,
            model=model_name,
            input={"conversation_id": conversation_id},
            output=output_text or None,
            usage={
                "input": prompt_tokens,
                "output": completion_tokens,
                "total": total_tokens,
                "input_cached": cached_tokens,
            },
            metadata={
                "agent": agent_name,
                "conversation_id": conversation_id,
                "user_id": user_id,
                "cached_tokens": cached_tokens,
            },
        )
    except Exception:
        logger.debug("Langfuse generation log failed (non-fatal)", exc_info=True)

    return None
