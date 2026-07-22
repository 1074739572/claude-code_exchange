"""Estimate message size and model-aware compaction budgets.

Auto-compact threshold follows Claude Code style:

    estimated_tokens ≳  AUTOCOMPACT_PCT × context_window

Default ``AUTOCOMPACT_PCT = 0.835``. Token estimate is chars/4 (same heuristic
as the rest of this harness). Absolute override: ``HARNESS_CONTEXT_LIMIT``
(interpreted as **tokens**, not characters).
"""

from __future__ import annotations

import json
import os

# Fallback when models.json has no context_window and the id is unknown.
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
    "glm-5.1": 128_000,
    "glm-5.2": 1_000_000,
    "glm-5.2-flash": 1_000_000,
}

# Reserve for system prompt + tools + summary output when sizing summarize input.
_RESERVE_TOKENS = 12_000
_CHARS_PER_TOKEN = 4
_FALLBACK_CONTEXT_TOKENS = 128_000
DEFAULT_AUTOCOMPACT_PCT = 0.835


def estimate_size(messages: list) -> int:
    """JSON character length (legacy metric; still used for transcripts)."""
    return len(json.dumps(messages, default=str))


def estimate_tokens(messages: list) -> int:
    """Rough token count for compaction decisions (chars / 4)."""
    return max(1, estimate_size(messages) // _CHARS_PER_TOKEN)


def model_context_window(model_id: str | None = None) -> int:
    """Resolved context window in tokens for the active (or given) model.

    Priority: ``HARNESS_CONTEXT_WINDOW`` env → models.json ``context_window``
    → built-in map → 128K fallback.
    """
    raw = os.getenv("HARNESS_CONTEXT_WINDOW", "").strip()
    if raw:
        try:
            return max(8_000, int(raw))
        except ValueError:
            pass

    from harness.models import get_model, get_model_profile

    mid = model_id or get_model()
    profile = get_model_profile(mid)
    if profile.context_window and profile.context_window > 0:
        return max(8_000, int(profile.context_window))

    # Prefer api_model key when catalog id differs (e.g. glm-5.2-flash → glm-5.2).
    for key in (mid, profile.api_model):
        if key in _MODEL_CONTEXT_TOKENS:
            return _MODEL_CONTEXT_TOKENS[key]
    return _FALLBACK_CONTEXT_TOKENS


def autocompact_pct() -> float:
    """Fraction of context window that triggers auto-compact (default 0.835)."""
    raw = os.getenv("HARNESS_AUTOCOMPACT_PCT", "").strip()
    if not raw:
        return DEFAULT_AUTOCOMPACT_PCT
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_AUTOCOMPACT_PCT
    # Accept 83.5 as percent or 0.835 as fraction.
    if value > 1.0:
        value = value / 100.0
    return max(0.40, min(0.95, value))


def autocompact_threshold_tokens(model_id: str | None = None) -> int:
    """Token count at which ``prepare_context`` runs full ``compact_history``.

    Default: ``round(autocompact_pct() * model_context_window())``.

    Absolute override: ``HARNESS_CONTEXT_LIMIT`` as **tokens** (not chars).
    """
    raw = os.getenv("HARNESS_CONTEXT_LIMIT", "").strip()
    if raw:
        try:
            return max(4_000, int(raw))
        except ValueError:
            pass
    window = model_context_window(model_id)
    return max(4_000, int(window * autocompact_pct()))


def should_autocompact(messages: list, model_id: str | None = None) -> bool:
    return estimate_tokens(messages) >= autocompact_threshold_tokens(model_id)


def _model_context_tokens(model_id: str | None) -> int:
    """Alias kept for older call sites / tests."""
    return model_context_window(model_id)


def _safe_input_budget(model_id: str | None = None) -> int:
    """Char budget for the summarization prompt, adapted to the active model.

    Reserve headroom for system prompt / tools / summary output, then convert
    remaining tokens to chars (~4 chars/token). Floor at 12K chars.
    """
    from harness.models import get_model

    mid = model_id or get_model()
    available = max(model_context_window(mid) - _RESERVE_TOKENS, 3000)
    return max(available * _CHARS_PER_TOKEN, 12_000)
