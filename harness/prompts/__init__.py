"""System prompt assembly: static prefix (cache-friendly) + ephemeral session context."""

from harness.prompts.dynamic import build_session_context
from harness.prompts.ephemeral import (
    EPHEMERAL_MARKER,
    build_ephemeral_user_message,
    is_ephemeral_session_message,
    messages_with_ephemeral_context,
)
from harness.prompts.project_md import (
    apply_project_instructions,
    find_project_md,
    format_project_instructions_block,
)
from harness.prompts.sections import PROMPT_SECTIONS
from harness.prompts.static import assemble_static_system_prompt


def assemble_system_prompt(context: dict) -> str:
    """Full system string (static + dynamic). Prefer static + ephemeral for LLM calls."""
    static = assemble_static_system_prompt()
    dynamic = build_session_context(context).strip()
    if not dynamic:
        return static
    return f"{static}\n\n{dynamic}"


__all__ = [
    "EPHEMERAL_MARKER",
    "PROMPT_SECTIONS",
    "apply_project_instructions",
    "assemble_static_system_prompt",
    "assemble_system_prompt",
    "build_ephemeral_user_message",
    "build_session_context",
    "find_project_md",
    "format_project_instructions_block",
    "is_ephemeral_session_message",
    "messages_with_ephemeral_context",
]
