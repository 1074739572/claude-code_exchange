"""Attach per-turn session context to API messages without persisting to session history."""

from __future__ import annotations

import os

from harness.prompts.dynamic import build_session_context

EPHEMERAL_MARKER = "<session-context>"
EphemeralPolicy = str  # "always" | "if_unchanged"

_last_session_body: str | None = None


def ephemeral_policy() -> str:
    return os.getenv("HARNESS_EPHEMERAL_POLICY", "if_unchanged").strip().lower()


def reset_ephemeral_cache() -> None:
    global _last_session_body
    _last_session_body = None


def is_ephemeral_session_message(message: dict) -> bool:
    content = message.get("content")
    return isinstance(content, str) and content.startswith(EPHEMERAL_MARKER)


def build_ephemeral_user_message(context: dict) -> str | None:
    body = build_session_context(context).strip()
    if not body:
        return None
    return (
        f"{EPHEMERAL_MARKER}\n"
        "The following is current harness session state (not a new user request). "
        "Use it together with the conversation above.\n\n"
        f"{body}"
    )


def messages_with_ephemeral_context(
    messages: list,
    context: dict,
    *,
    policy: str | None = None,
) -> list:
    """Shallow copy of messages with session context appended for a single API call."""
    global _last_session_body

    body = build_session_context(context).strip()
    if not body:
        return list(messages)

    active_policy = (policy or ephemeral_policy()).lower()
    if active_policy == "if_unchanged" and body == _last_session_body:
        return list(messages)

    _last_session_body = body
    ephemeral = build_ephemeral_user_message(context)
    if not ephemeral:
        return list(messages)
    return [*messages, {"role": "user", "content": ephemeral}]
