"""Persist and restore CLI conversation history."""

from __future__ import annotations

import json
from pathlib import Path

from harness.messages.sanitize import block_to_dict, sanitize_messages_for_api
from harness.prompts.ephemeral import is_ephemeral_session_message
from harness.settings import PROJECT_DIR

HISTORY_PATH = PROJECT_DIR / "history.json"


def _block_to_dict(block) -> dict:
    return block_to_dict(block)


def serialize_messages(messages: list) -> list[dict]:
    serialized = []
    for message in messages:
        if is_ephemeral_session_message(message):
            continue
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


def messages_for_api(messages: list) -> list[dict]:
    """Serialize and sanitize for LLM provider requests."""
    return sanitize_messages_for_api(serialize_messages(messages))


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
