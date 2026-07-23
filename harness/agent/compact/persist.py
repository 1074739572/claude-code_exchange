"""Persist large / compacted tool results to disk for later read_file."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re

from harness.settings import PERSIST_THRESHOLD, TOOL_RESULTS_DIR

_MICRO_COMPACT_MIN_CHARS = 120
_PERSISTED_PREFIX = "<persisted-output"
DEFAULT_TOOL_RESULT_MAX_CHARS = 12_000
DEFAULT_TOOL_ROUND_MAX_CHARS = 40_000
_MIN_TOOL_RESULT_MAX_CHARS = 1_000
_SAFE_TOOL_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def is_persisted_output(text: str) -> bool:
    """True when output is already a persisted-output wrapper."""
    stripped = str(text).strip()
    return stripped.startswith(_PERSISTED_PREFIX) and "</persisted-output>" in stripped


def _positive_env_int(name: str, default: int, *, minimum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(minimum, value)


def tool_result_max_chars() -> int:
    """Maximum model-facing characters for one tool result."""
    return _positive_env_int(
        "HARNESS_TOOL_RESULT_MAX_CHARS",
        DEFAULT_TOOL_RESULT_MAX_CHARS,
        minimum=_MIN_TOOL_RESULT_MAX_CHARS,
    )


def tool_round_max_chars() -> int:
    """Maximum model-facing characters shared by one parallel tool round."""
    return _positive_env_int(
        "HARNESS_TOOL_ROUND_MAX_CHARS",
        DEFAULT_TOOL_ROUND_MAX_CHARS,
        minimum=_MIN_TOOL_RESULT_MAX_CHARS,
    )


def _tool_result_path(tool_use_id: str) -> Path:
    raw_id = str(tool_use_id or "unknown")
    if _SAFE_TOOL_ID_RE.fullmatch(raw_id):
        filename = raw_id
    else:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "-", raw_id).strip(".-")[:80] or "unknown"
        digest = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:10]
        filename = f"{safe}-{digest}"
    return TOOL_RESULTS_DIR / f"{filename}.txt"


def _write_tool_result_to_disk(tool_use_id: str, output: str) -> Path:
    TOOL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = _tool_result_path(tool_use_id)
    # Tool IDs should be unique, but overwrite defensively so a collision across
    # resumed sessions can never point at stale output.
    path.write_text(output, encoding="utf-8")
    return path


def _bounded_persisted_output(
    tool_use_id: str,
    output: str,
    *,
    max_chars: int,
    tool_name: str = "",
) -> str:
    """Persist full output and return a deterministic head/tail preview."""
    path = _write_tool_result_to_disk(tool_use_id, output)
    tool_attr = f' tool="{tool_name}"' if tool_name else ""
    opening = (
        f'<persisted-output truncated original_chars="{len(output)}"{tool_attr}>\n'
        f"Full output: {path}\n"
        "Preview:\n"
    )
    closing = "\n</persisted-output>"
    omission_template = "\n--- omitted {count} chars; use read_file for full output ---\n"
    fixed_size = len(opening) + len(closing) + len(
        omission_template.format(count=len(output))
    )
    preview_budget = max(256, max_chars - fixed_size)
    head_chars = max(1, int(preview_budget * 0.65))
    tail_chars = max(1, preview_budget - head_chars)
    omitted = max(0, len(output) - head_chars - tail_chars)
    omission = omission_template.format(count=omitted)
    return (
        f"{opening}{output[:head_chars]}{omission}{output[-tail_chars:]}{closing}"
    )


def stabilize_tool_output(
    tool_use_id: str,
    output: object,
    *,
    tool_name: str = "",
    max_chars: int | None = None,
) -> str:
    """
    Freeze a tool result before it first enters conversation history.

    Oversized output is persisted once and represented by a stable head/tail
    preview. Historical messages therefore never need progressive rewriting.
    """
    text = str(output)
    if is_persisted_output(text):
        return text
    limit = max(
        _MIN_TOOL_RESULT_MAX_CHARS,
        max_chars if max_chars is not None else tool_result_max_chars(),
    )
    if len(text) <= limit:
        return text
    return _bounded_persisted_output(
        tool_use_id,
        text,
        max_chars=limit,
        tool_name=tool_name,
    )


def stabilize_tool_results(results: list[dict]) -> list[dict]:
    """Normalize a complete tool round before appending it to history."""
    tool_blocks = [
        block
        for block in results
        if isinstance(block, dict) and block.get("type") == "tool_result"
    ]
    if not tool_blocks:
        return results

    per_result_limit = min(
        tool_result_max_chars(),
        max(_MIN_TOOL_RESULT_MAX_CHARS, tool_round_max_chars() // len(tool_blocks)),
    )
    normalized: list[dict] = []
    for block in results:
        if not isinstance(block, dict) or block.get("type") != "tool_result":
            normalized.append(block)
            continue
        copied = dict(block)
        copied["content"] = stabilize_tool_output(
            str(block.get("tool_use_id") or "unknown"),
            block.get("content", ""),
            max_chars=per_result_limit,
        )
        normalized.append(copied)
    return normalized


def persist_large_output(tool_use_id: str, output: str) -> str:
    if is_persisted_output(output):
        return output
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
    if is_persisted_output(output):
        return output
    if len(output) <= min_len:
        return output
    path = _write_tool_result_to_disk(tool_use_id, output)
    return (
        f"<persisted-output compacted>\nFull output: {path}\n"
        f"Preview:\n{output[:preview_chars]}\n</persisted-output>"
    )
