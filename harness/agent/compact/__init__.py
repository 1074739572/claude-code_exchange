"""Layered context compaction before each LLM call.

Public API is stable at ``harness.agent.compact``; implementation lives in
sizing / messages / persist / layers / summarize / pipeline.
"""

from __future__ import annotations

from harness.agent.compact.layers import (
    COMPACT_TAIL_COUNT,
    keep_tail,
    micro_compact,
    snip_compact,
    tool_result_budget,
)
from harness.agent.compact.messages import (
    LATEST_USER_FOCUS_MARKER,
    collect_tool_results,
    find_latest_user_text,
    focus_latest_user_message,
    is_tool_result_message,
    message_has_tool_use,
)
from harness.agent.compact.persist import (
    persist_large_output,
    persist_recallable_output,
)
from harness.agent.compact.pipeline import (
    compact_history,
    prepare_context,
    reactive_compact,
    write_transcript,
)
from harness.agent.compact.sizing import (
    _safe_input_budget,
    autocompact_threshold_tokens,
    estimate_size,
    estimate_tokens,
    model_context_window,
    should_autocompact,
)
from harness.agent.compact.summarize import (
    _structured_summary_instruction,
    summarize_history,
)
from harness.settings import TOOL_RESULTS_DIR

# Alias kept for older call sites / tests
_keep_tail = keep_tail

__all__ = [
    "COMPACT_TAIL_COUNT",
    "LATEST_USER_FOCUS_MARKER",
    "TOOL_RESULTS_DIR",
    "_keep_tail",
    "_safe_input_budget",
    "_structured_summary_instruction",
    "autocompact_threshold_tokens",
    "collect_tool_results",
    "compact_history",
    "estimate_size",
    "estimate_tokens",
    "find_latest_user_text",
    "focus_latest_user_message",
    "is_tool_result_message",
    "keep_tail",
    "message_has_tool_use",
    "micro_compact",
    "model_context_window",
    "persist_large_output",
    "persist_recallable_output",
    "prepare_context",
    "reactive_compact",
    "should_autocompact",
    "snip_compact",
    "summarize_history",
    "tool_result_budget",
    "write_transcript",
]
