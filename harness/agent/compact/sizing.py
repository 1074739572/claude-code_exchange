"""Estimate message size and model-aware summarization input budgets."""

from __future__ import annotations

import json

_MODEL_CONTEXT_TOKENS = {
    # Qwen
    "qwen-max": 32_000,
    "qwen-max-latest": 32_000,
    "qwen3-max": 256_000,
    "qwen3.7-max": 1_000_000,
    "qwen3.7-plus": 1_000_000,
    "qwen-plus": 1_000_000,
    "qwen-flash": 1_000_000,
    "qwen-turbo": 128_000,
    "qwen-long": 10_000_000,
    # DeepSeek
    "deepseek-v4-flash": 1_000_000,
    "deepseek-v4-pro": 1_000_000,
    "deepseek-chat": 1_000_000,
    "deepseek-reasoner": 1_000_000,
    # GLM
    "glm-4-plus": 128_000,
    "glm-4-0520": 128_000,
    "glm-4-air": 128_000,
    "glm-4-airx": 8_000,
    "glm-4-long": 1_000_000,
    "glm-4-flashx": 128_000,
    "glm-4-flash": 128_000,
    "glm-5.2": 1_000_000,
}

# Reserve for system prompt + tool descriptions + summary output (tokens).
_RESERVE_TOKENS = 12_000
_CHARS_PER_TOKEN = 4
_FALLBACK_CONTEXT_TOKENS = 32_000


def estimate_size(messages: list) -> int:
    return len(json.dumps(messages, default=str))


def _model_context_tokens(model_id: str | None) -> int:
    if not model_id:
        return _FALLBACK_CONTEXT_TOKENS
    return _MODEL_CONTEXT_TOKENS.get(model_id, _FALLBACK_CONTEXT_TOKENS)


def _safe_input_budget(model_id: str | None = None) -> int:
    """Char budget for the summarization prompt, adapted to the active model.

    Conservative across the Qwen/DeepSeek/GLM families we ship. We reserve
    headroom for the system prompt, tool descriptions, and the 2000-token
    summary output, then convert remaining tokens to chars (~4 chars/token).
    For the small-context qwen-max (32K) this yields ~20K chars; for 1M-context
    models it yields ~250K chars. The 12K-char floor keeps tiny-context models
    like glm-4-airx (8K) safe.
    """
    from harness.models import get_model

    mid = model_id or get_model()
    available = max(_model_context_tokens(mid) - _RESERVE_TOKENS, 3000)
    return max(available * _CHARS_PER_TOKEN, 12_000)
