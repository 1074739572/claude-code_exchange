"""Layered context compaction before each LLM call."""

from __future__ import annotations

import json
import time
from pathlib import Path

from harness.models import get_model
from harness.settings import (
    CONTEXT_LIMIT,
    KEEP_RECENT_TOOL_RESULTS,
    PERSIST_THRESHOLD,
    TOOL_RESULTS_DIR,
    TRANSCRIPT_DIR,
    WORKDIR,
)
from harness.llm import create_message
from harness.messages.blocks import block_type
from harness.tools.dispatch import extract_text


def estimate_size(messages: list) -> int:
    return len(json.dumps(messages, default=str))


def message_has_tool_use(message: dict) -> bool:
    if message.get("role") != "assistant":
        return False
    content = message.get("content")
    if not isinstance(content, list):
        return False
    return any(block_type(block) == "tool_use" for block in content)


def is_tool_result_message(message: dict) -> bool:
    if message.get("role") != "user":
        return False
    content = message.get("content")
    if not isinstance(content, list):
        return False
    return any(
        isinstance(block, dict) and block.get("type") == "tool_result"
        for block in content
    )


def collect_tool_results(messages: list):
    found = []
    for message_index, message in enumerate(messages):
        content = message.get("content")
        if message.get("role") != "user" or not isinstance(content, list):
            continue
        for block_index, block in enumerate(content):
            if isinstance(block, dict) and block.get("type") == "tool_result":
                found.append((message_index, block_index, block))
    return found


COMPACT_TAIL_COUNT = 5
_MICRO_COMPACT_MIN_CHARS = 120

_STRUCTURED_SUMMARY_SECTIONS = (
    "## Goal",
    "## User Constraints",
    "## Changed Files",
    "## Key Findings",
    "## Remaining Work",
    "## Do NOT Forget",
)


def _write_tool_result_to_disk(tool_use_id: str, output: str) -> Path:
    TOOL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = TOOL_RESULTS_DIR / f"{tool_use_id}.txt"
    if not path.exists():
        path.write_text(output, encoding="utf-8")
    return path


def persist_large_output(tool_use_id: str, output: str) -> str:
    if len(output) <= PERSIST_THRESHOLD:
        return output
    path = _write_tool_result_to_disk(tool_use_id, output)
    return (
        f"<persisted-output>\nFull output: {path}\n"
        f"Preview:\n{output[:2000]}\n</persisted-output>"
    )


def persist_recallable_output(
    tool_use_id: str,
    output: str,
    *,
    min_len: int = _MICRO_COMPACT_MIN_CHARS,
    preview_chars: int = 500,
) -> str:
    """Persist compacted tool output so the agent can read_file the full text."""
    if len(output) <= min_len:
        return output
    path = _write_tool_result_to_disk(tool_use_id, output)
    return (
        f"<persisted-output compacted>\nFull output: {path}\n"
        f"Preview:\n{output[:preview_chars]}\n</persisted-output>"
    )


def tool_result_budget(messages: list, max_bytes: int = 200_000) -> list:
    if not messages:
        return messages
    last = messages[-1]
    content = last.get("content")
    if last.get("role") != "user" or not isinstance(content, list):
        return messages
    blocks = [
        (index, block)
        for index, block in enumerate(content)
        if isinstance(block, dict) and block.get("type") == "tool_result"
    ]
    total = sum(len(str(block.get("content", ""))) for _, block in blocks)
    if total <= max_bytes:
        return messages
    for _, block in sorted(
        blocks,
        key=lambda pair: len(str(pair[1].get("content", ""))),
        reverse=True,
    ):
        if total <= max_bytes:
            break
        text = str(block.get("content", ""))
        block["content"] = persist_large_output(block.get("tool_use_id", "unknown"), text)
        total = sum(len(str(item.get("content", ""))) for _, item in blocks)
    return messages


def snip_compact(messages: list, max_messages: int = 50) -> list:
    if len(messages) <= max_messages:
        return messages
    head_end = 3
    tail_start = len(messages) - (max_messages - 3)
    if head_end > 0 and message_has_tool_use(messages[head_end - 1]):
        while head_end < len(messages) and is_tool_result_message(messages[head_end]):
            head_end += 1
    if (
        tail_start > 0
        and tail_start < len(messages)
        and is_tool_result_message(messages[tail_start])
        and message_has_tool_use(messages[tail_start - 1])
    ):
        tail_start -= 1
    if head_end >= tail_start:
        return messages
    snipped = tail_start - head_end
    return (
        messages[:head_end]
        + [{"role": "user", "content": f"[snipped {snipped} messages]"}]
        + messages[tail_start:]
    )


def micro_compact(messages: list) -> list:
    tool_results = collect_tool_results(messages)
    if len(tool_results) <= KEEP_RECENT_TOOL_RESULTS:
        return messages
    for message_index, block_index, block in tool_results[:-KEEP_RECENT_TOOL_RESULTS]:
        text = str(block.get("content", ""))
        if len(text) <= _MICRO_COMPACT_MIN_CHARS:
            continue
        tool_id = block.get("tool_use_id") or f"micro-{message_index}-{block_index}"
        block["content"] = persist_recallable_output(tool_id, text)
    return messages


def write_transcript(messages: list) -> Path:
    from harness.project.session import serialize_messages

    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    path = TRANSCRIPT_DIR / f"transcript_{int(time.time())}.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for message in serialize_messages(messages):
            handle.write(json.dumps(message, ensure_ascii=False) + "\n")
    return path


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


def _structured_summary_instruction() -> str:
    sections = "\n".join(_STRUCTURED_SUMMARY_SECTIONS)
    return (
        f"Working directory: {WORKDIR}\n"
        "Python package lives at `harness/` in this repo (NOT `src/harness/`).\n"
        "Summarize this coding-agent conversation so work can continue after compaction.\n"
        "Use exactly these markdown headings and fill each section:\n"
        f"{sections}\n\n"
        "Guidelines:\n"
        "- Goal: one sentence on what the user is trying to accomplish now.\n"
        "- User Constraints: explicit requirements, paths, formats, tone, deadlines.\n"
        "- Changed Files: bullet list of paths touched and what changed.\n"
        "- Key Findings: facts, errors, metrics, or decisions that must survive compaction.\n"
        "- Remaining Work: concrete next steps; include drift complaints or wrong paths.\n"
        "- Do NOT Forget: non-negotiables the agent must not drop (e.g. sample doc paths).\n"
    )


def summarize_history(messages: list) -> str:
    budget = _safe_input_budget()
    conversation = json.dumps(messages, default=str)[:budget]
    prompt = (
        _structured_summary_instruction()
        + f"\n[Conversation trimmed to last {budget} chars for summarization]\n\n"
        + conversation
    )
    try:
        response = create_message(
            model_id=get_model(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
        )
        return extract_text(response.content) or "(empty summary)"
    except Exception as exc:
        return (
            f"[Compact summary unavailable: {exc}]\n"
            "Earlier conversation was trimmed to fit the model input limit. "
            "Re-issue your last instruction if the agent seems to have lost context."
        )


def _keep_tail(messages: list, count: int = 5) -> list:
    tail_start = max(0, len(messages) - count)
    if (
        tail_start > 0
        and tail_start < len(messages)
        and is_tool_result_message(messages[tail_start])
        and message_has_tool_use(messages[tail_start - 1])
    ):
        tail_start -= 1
    return messages[tail_start:]


def compact_history(messages: list) -> list:
    from harness.project.session_store import record_compact_boundary

    transcript = write_transcript(messages)
    print(f"  \033[36m[compact] transcript saved: {transcript}\033[0m")
    summary = summarize_history(messages)
    tail = _keep_tail(messages, count=COMPACT_TAIL_COUNT)
    compacted = [
        {"role": "user", "content": f"[Compacted]\n\n{summary}"},
        *tail,
    ]
    record_compact_boundary("auto", estimate_size(messages), transcript, compacted)
    return compacted


def reactive_compact(messages: list) -> list:
    from harness.project.session_store import record_compact_boundary

    transcript = write_transcript(messages)
    print(f"  \033[31m[reactive compact] transcript saved: {transcript}\033[0m")
    summary = summarize_history(messages)
    tail = _keep_tail(messages, count=COMPACT_TAIL_COUNT)
    compacted = [
        {"role": "user", "content": f"[Reactive compact]\n\n{summary}"},
        *tail,
    ]
    record_compact_boundary("reactive", estimate_size(messages), transcript, compacted)
    return compacted


def prepare_context(messages: list) -> list:
    messages[:] = tool_result_budget(messages)
    messages[:] = snip_compact(messages)
    messages[:] = micro_compact(messages)
    if estimate_size(messages) > CONTEXT_LIMIT:
        messages[:] = compact_history(messages)
    return messages
