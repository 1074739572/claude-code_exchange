"""Persist and restore CLI conversation history."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from types import SimpleNamespace

from harness.settings import PROJECT_DIR

HISTORY_PATH = PROJECT_DIR / "history.json"


def _block_to_dict(block) -> dict:
    if isinstance(block, dict):
        return dict(block)
    if is_dataclass(block):
        return asdict(block)
    if isinstance(block, SimpleNamespace):
        return {key: value for key, value in vars(block).items() if value is not None}
    data = {"type": getattr(block, "type", None)}
    for key in ("text", "id", "name", "input", "tool_use_id", "content"):
        value = getattr(block, key, None)
        if value is not None:
            data[key] = value
    return data


def serialize_messages(messages: list) -> list[dict]:
    serialized = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if isinstance(content, str):
            serialized.append({"role": role, "content": content})
            continue
        if isinstance(content, list):
            serialized.append(
                {
                    "role": role,
                    "content": [_block_to_dict(block) for block in content],
                }
            )
            continue
        serialized.append({"role": role, "content": str(content)})
    return serialized


def deserialize_messages(data: list[dict]) -> list:
    messages = []
    for message in data:
        role = message["role"]
        content = message["content"]
        if isinstance(content, str):
            messages.append({"role": role, "content": content})
            continue
        if isinstance(content, list):
            messages.append(
                {
                    "role": role,
                    "content": [
                        dict(item) if isinstance(item, dict) else _block_to_dict(item)
                        for item in content
                    ],
                }
            )
            continue
        messages.append({"role": role, "content": content})
    return messages


def save_history(messages: list) -> None:
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "messages": serialize_messages(messages)}
    HISTORY_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def load_history() -> list | None:
    from harness.project.session_store import bootstrap_session

    messages, _ = bootstrap_session()
    return messages if messages else None


def clear_history() -> None:
    from harness.project.session_store import clear_session

    clear_session(archive=True)
