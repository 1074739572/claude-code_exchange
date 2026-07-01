"""Import compact backup transcripts into persisted conversation history."""

from __future__ import annotations

import json
import re
from pathlib import Path

from harness.project.session import deserialize_messages, load_history, serialize_messages
from harness.project.session_store import replace_session
from harness.settings import TRANSCRIPT_DIR, WORKDIR

COMPACT_PREFIXES = ("[Compacted]", "[Reactive compact]")
_TOOL_USE_RE = re.compile(
    r"ToolUseBlock\(type='tool_use', id='([^']+)', name='([^']+)'"
)
_MAX_TOOL_RESULT_CHARS = 6000


def list_transcripts() -> list[Path]:
    if not TRANSCRIPT_DIR.exists():
        return []
    return sorted(TRANSCRIPT_DIR.glob("transcript_*.jsonl"), key=lambda p: p.stat().st_mtime)


def latest_transcript() -> Path | None:
    transcripts = list_transcripts()
    return transcripts[-1] if transcripts else None


def load_transcript_jsonl(path: Path | str) -> list[dict]:
    file_path = Path(path)
    if not file_path.is_absolute():
        candidate = WORKDIR / file_path
        if candidate.exists():
            file_path = candidate
    if not file_path.exists():
        raise FileNotFoundError(f"Transcript not found: {path}")

    messages: list[dict] = []
    for line_no, line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            messages.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON on line {line_no} of {file_path}") from exc
    return messages


def _is_compact_summary(content: str) -> bool:
    return any(content.startswith(prefix) for prefix in COMPACT_PREFIXES)


def _truncate_tool_results(content) -> list | str:
    if isinstance(content, str):
        if content.startswith("<reminder>"):
            return content
        if len(content) > _MAX_TOOL_RESULT_CHARS:
            return content[:_MAX_TOOL_RESULT_CHARS] + "\n...[truncated on import]"
        return content
    if not isinstance(content, list):
        return content

    blocks = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_result":
            text = str(block.get("content", ""))
            if len(text) > _MAX_TOOL_RESULT_CHARS:
                block = {
                    **block,
                    "content": text[:_MAX_TOOL_RESULT_CHARS]
                    + "\n...[truncated on import]",
                }
        blocks.append(block)
    return blocks


def _normalize_assistant_content(content) -> list | str | None:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)

    normalized = []
    for block in content:
        if isinstance(block, dict):
            block_type = block.get("type")
            if block_type == "text" and block.get("text"):
                normalized.append(block)
            elif block_type == "tool_use":
                normalized.append(block)
            continue
        if isinstance(block, str) and "ToolUseBlock(" in block:
            match = _TOOL_USE_RE.search(block)
            if match:
                tool_id, name = match.groups()
                normalized.append(
                    {
                        "type": "tool_use",
                        "id": tool_id,
                        "name": name,
                        "input": {},
                    }
                )
            continue
        text = getattr(block, "text", None)
        if getattr(block, "type", None) == "text" and text:
            normalized.append({"type": "text", "text": text})
        elif getattr(block, "type", None) == "tool_use":
            normalized.append(
                {
                    "type": "tool_use",
                    "id": getattr(block, "id", ""),
                    "name": getattr(block, "name", ""),
                    "input": getattr(block, "input", {}) or {},
                }
            )
    return normalized or None


def normalize_transcript_messages(
    raw_messages: list[dict], mode: str = "summary"
) -> list:
    if mode == "summary":
        for message in raw_messages:
            content = message.get("content", "")
            if message.get("role") == "user" and isinstance(content, str):
                if _is_compact_summary(content):
                    return [
                        {"role": "user", "content": content},
                        {
                            "role": "assistant",
                            "content": "Restored from compact transcript backup. "
                            "Continue from the saved summary without re-planning.",
                        },
                    ]
        raise ValueError(
            "No [Compacted] or [Reactive compact] summary found. "
            "Use mode=full or pick a transcript saved before compaction."
        )

    restored = []
    for message in raw_messages:
        role = message.get("role")
        content = message.get("content")
        if role == "assistant":
            normalized = _normalize_assistant_content(content)
            if not normalized:
                continue
            restored.append({"role": "assistant", "content": normalized})
            continue
        if role == "user":
            if isinstance(content, str) and content.startswith("<reminder>"):
                continue
            restored.append(
                {"role": "user", "content": _truncate_tool_results(content)}
            )
    if not restored:
        raise ValueError("Transcript contained no restorable messages.")
    return deserialize_messages(restored)


def import_transcript(
    path: str | None = None,
    mode: str = "summary",
    merge: bool = False,
) -> str:
    file_path = Path(path) if path else latest_transcript()
    if file_path is None:
        return "No transcripts found under .transcripts/"

    raw = load_transcript_jsonl(file_path)
    restored = normalize_transcript_messages(raw, mode=mode)

    if merge:
        existing = load_history() or []
        restored = existing + restored

    replace_session(restored, archive=True)
    user_turns = sum(1 for m in restored if m.get("role") == "user")
    return (
        f"Imported transcript → session.jsonl\n"
        f"  Source: {file_path}\n"
        f"  Mode: {mode}\n"
        f"  Messages: {len(restored)} ({user_turns} user prompts)\n"
        f"Restart harness or continue chatting to use restored context."
    )


def format_transcript_hint() -> str | None:
    latest = latest_transcript()
    if latest is None:
        return None
    history = load_history()
    if history and len(history) > 4:
        return None
    return (
        f"Transcript backup available: {latest.name}\n"
        f"Run: /import-transcript   (or /import-transcript full)"
    )
