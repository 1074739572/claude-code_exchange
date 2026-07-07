"""Claude Code-style session persistence: append-only session.jsonl + compact boundaries.

OpenCode mode (default): every launch is a fresh chat unless explicitly opted in
via ``HARNESS_CONTINUE_SESSION=1`` (Claude Code ``-c`` style).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from harness.project.session import (
    HISTORY_PATH,
    deserialize_messages,
    save_history,
    serialize_messages,
)
from harness.settings import PROJECT_DIR, TRANSCRIPT_DIR

SESSION_PATH = PROJECT_DIR / "session.jsonl"
SESSION_META_PATH = PROJECT_DIR / "session.meta.json"


def continue_session_on_startup() -> bool:
    """Whether ``bootstrap_session`` should reload ``session.jsonl`` on restart.

    OpenCode-style default: False (every launch is a fresh chat, like ``claude``
    without ``-c``). Set ``HARNESS_CONTINUE_SESSION=1`` to get the Claude Code
    ``-c`` behavior back.
    """
    flag = os.getenv("HARNESS_CONTINUE_SESSION", "0").strip().lower()
    return flag in ("1", "true", "yes", "on")


def bootstrap_from_transcript_enabled() -> bool:
    """Whether an empty session may pull context from ``.transcripts/``.

    Default off (OpenCode). ``HARNESS_BOOTSTRAP_TRANSCRIPT=1`` restores the old
    fallback that rehydrated the latest transcript into a new session.
    """
    flag = os.getenv("HARNESS_BOOTSTRAP_TRANSCRIPT", "0").strip().lower()
    return flag in ("1", "true", "yes", "on")


def _load_meta() -> dict:
    if not SESSION_META_PATH.exists():
        return {"active_persisted": 0}
    return json.loads(SESSION_META_PATH.read_text(encoding="utf-8"))


def _save_meta(meta: dict) -> None:
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    SESSION_META_PATH.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")


def _append_record(record: dict) -> None:
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    with SESSION_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read_records() -> list[dict]:
    if not SESSION_PATH.exists():
        return []
    records: list[dict] = []
    for line_no, line in enumerate(
        SESSION_PATH.read_text(encoding="utf-8").splitlines(), 1
    ):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid session JSONL line {line_no}") from exc
    return records


def _message_from_record(record: dict) -> dict | None:
    if record.get("type") != "message":
        return None
    role = record.get("role")
    if not role:
        return None
    return {"role": role, "content": record.get("content")}


def _active_start_index(records: list[dict]) -> int:
    last_boundary = -1
    for index, record in enumerate(records):
        if record.get("type") == "compact_boundary":
            last_boundary = index
    return last_boundary + 1


def load_session_messages() -> list | None:
    records = _read_records()
    if not records:
        return None

    raw_messages: list[dict] = []
    for record in records[_active_start_index(records) :]:
        message = _message_from_record(record)
        if message is not None:
            raw_messages.append(message)

    if not raw_messages:
        return None
    return deserialize_messages(raw_messages)


def session_stats() -> dict:
    records = _read_records()
    active_start = _active_start_index(records)
    active_messages = sum(
        1 for record in records[active_start:] if record.get("type") == "message"
    )
    boundaries = sum(1 for record in records if record.get("type") == "compact_boundary")
    return {
        "path": str(SESSION_PATH),
        "exists": SESSION_PATH.exists(),
        "total_records": len(records),
        "active_messages": active_messages,
        "compact_boundaries": boundaries,
        "size_kb": SESSION_PATH.stat().st_size // 1024 if SESSION_PATH.exists() else 0,
    }


def _append_message_records(serialized_messages: list[dict], start: int = 0) -> int:
    appended = 0
    for message in serialized_messages[start:]:
        _append_record({"type": "message", **message})
        appended += 1
    return appended


def append_checkpoint(messages: list) -> None:
    if not messages:
        return

    meta = _load_meta()
    persisted = int(meta.get("active_persisted", 0))
    if persisted > len(messages):
        persisted = 0

    serialized = serialize_messages(messages)
    _append_message_records(serialized, start=persisted)
    meta["active_persisted"] = len(messages)
    _save_meta(meta)
    save_history(messages)


def replace_session(messages: list, archive: bool = True) -> None:
    clear_session(archive=archive)
    if messages:
        append_checkpoint(messages)


def record_compact_boundary(
    mode: str,
    pre_tokens: int,
    transcript_path: str | Path,
    messages_after_compact: list,
) -> None:
    _append_record(
        {
            "type": "compact_boundary",
            "mode": mode,
            "pre_tokens": pre_tokens,
            "transcript": str(transcript_path).replace("\\", "/"),
            "ts": int(time.time()),
        }
    )
    serialized = serialize_messages(messages_after_compact)
    _append_message_records(serialized)
    _save_meta({"active_persisted": len(messages_after_compact)})
    save_history(messages_after_compact)


def _migrate_history_json() -> list | None:
    if not HISTORY_PATH.exists():
        return None
    payload = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    raw = payload.get("messages", [])
    if not raw:
        return None

    for message in raw:
        _append_record({"type": "message", **message})
    _save_meta({"active_persisted": len(raw), "migrated_from": "history.json"})
    return deserialize_messages(raw)


def _bootstrap_from_transcript() -> list | None:
    if not TRANSCRIPT_DIR.exists():
        return None
    transcripts = sorted(
        TRANSCRIPT_DIR.glob("transcript_*.jsonl"),
        key=lambda path: path.stat().st_mtime,
    )
    if not transcripts:
        return None

    from harness.project.transcript import normalize_transcript_messages

    latest = transcripts[-1]
    try:
        raw = []
        for line in latest.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                raw.append(json.loads(line))
        restored = normalize_transcript_messages(raw, mode="summary")
    except ValueError:
        return None

    for message in serialize_messages(restored):
        _append_record({"type": "message", **message})
    _save_meta(
        {
            "active_persisted": len(restored),
            "bootstrapped_from": latest.name,
        }
    )
    save_history(restored)
    return restored


def bootstrap_session() -> tuple[list, str | None]:
    """OpenCode-style bootstrap. Returns (messages, source note).

    By default this returns an empty session on every launch (OpenCode mode).
    Enable ``HARNESS_CONTINUE_SESSION=1`` to reload ``session.jsonl`` (Claude
    Code ``-c`` style) and optionally ``HARNESS_BOOTSTRAP_TRANSCRIPT=1`` to fall
    back to ``.transcripts/`` when no live session exists.
    """
    if not continue_session_on_startup():
        return [], None

    loaded = load_session_messages()
    if loaded:
        save_history(loaded)
        stats = session_stats()
        return loaded, f"session.jsonl（{stats['active_messages']} 条活跃消息）"

    migrated = _migrate_history_json()
    if migrated:
        return migrated, "已从 history.json 迁移至 session.jsonl"

    if bootstrap_from_transcript_enabled():
        from_transcript = _bootstrap_from_transcript()
        if from_transcript:
            meta = _load_meta()
            source = meta.get("bootstrapped_from", "transcript")
            return from_transcript, f"从 .transcripts/{source} 引导恢复"

    return [], None


def clear_session(archive: bool = True) -> str | None:
    archived_path: Path | None = None
    if archive and SESSION_PATH.exists():
        archived_path = PROJECT_DIR / f"session_{int(time.time())}.jsonl"
        SESSION_PATH.rename(archived_path)

    if SESSION_META_PATH.exists():
        SESSION_META_PATH.unlink()
    if HISTORY_PATH.exists():
        HISTORY_PATH.unlink()

    if archived_path:
        return str(archived_path)
    return None


def format_session_line() -> str:
    stats = session_stats()
    if not continue_session_on_startup():
        if stats["exists"]:
            return (
                f"会话：OpenCode 模式（不自动续）。"
                f"磁盘上有 {SESSION_PATH.name}（{stats['active_messages']} 条），"
                f"如需续请设 HARNESS_CONTINUE_SESSION=1 重启，或 /resume project 注入论文。"
            )
        return "会话：（空）OpenCode 模式 —— 每次启动都是全新对话"
    if not stats["exists"]:
        return "会话：（无）首条消息后将开始新对话"
    compact_part = ""
    if stats["compact_boundaries"]:
        compact_part = f"，{stats['compact_boundaries']} 次压缩"
    return (
        f"会话：{SESSION_PATH.name} "
        f"（{stats['active_messages']} 条消息{compact_part}）"
    )
