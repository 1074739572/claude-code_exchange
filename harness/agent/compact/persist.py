"""Persist large / compacted tool results to disk for later read_file."""

from __future__ import annotations

from pathlib import Path

from harness.settings import PERSIST_THRESHOLD, TOOL_RESULTS_DIR

_MICRO_COMPACT_MIN_CHARS = 120


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
