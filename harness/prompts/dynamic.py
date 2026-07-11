"""Per-turn session context (time, model, mode, todos, …) — not part of the static system prefix."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Literal

from harness.models import get_model, get_model_profile, model_label
from harness.modes import mode_lead_model_hint, mode_prompt_section
from harness.providers.config import get_provider
from harness.settings import WORKDIR
from harness.todos.format import format_todos_for_prompt
from harness.todos.state import get_todos

TimeGranularity = Literal["seconds", "minute"]


def _format_time(*, granularity: TimeGranularity) -> str:
    now = datetime.now()
    if granularity == "minute":
        now = now.replace(second=0, microsecond=0)
    return now.isoformat(timespec="seconds")


def default_time_granularity() -> TimeGranularity:
    """Minute by default so ephemeral context can skip unchanged turns."""
    raw = os.getenv("HARNESS_TIME_GRANULARITY", "minute").strip().lower()
    if raw in ("seconds", "second", "s"):
        return "seconds"
    return "minute"


def build_session_context(
    context: dict,
    *,
    include_time: bool = True,
    time_granularity: TimeGranularity | None = None,
    include_model: bool = True,
    include_mode: bool = True,
    include_memories: bool = True,
    include_mcp: bool = True,
    include_teammates: bool = True,
    include_todos: bool = True,
) -> str:
    """Dynamic harness state for the model (ephemeral message body, not static system)."""
    sections: list[str] = []
    granularity = time_granularity or default_time_granularity()

    if include_time:
        sections.append(f"Current time: {_format_time(granularity=granularity)}")

    if include_model:
        current = get_model()
        profile = get_model_profile(current)
        label = model_label(current)
        try:
            provider_label = get_provider(profile.provider).label
        except KeyError:
            provider_label = profile.provider
        model_line = f"Current model: {current} [{provider_label}]"
        if profile.api_model != current:
            model_line += f" (API: {profile.api_model})"
        if profile.thinking:
            model_line += " [thinking]"
        if label != current:
            model_line += f" — {label}"
        sections.append(model_line)

    if include_mode:
        sections.append(mode_prompt_section())
        hint = mode_lead_model_hint()
        current = get_model()
        if hint and current != hint:
            sections.append(
                f"Mode lead hint: {hint} is recommended for this mode "
                f"(current: {current}). Switch with /model if needed."
            )

    if include_memories and context.get("memories"):
        sections.append(f"Relevant memories:\n{context['memories']}")

    if include_mcp:
        mcp_names = context.get("connected_mcp") or []
        if mcp_names:
            sections.append(f"Connected MCP servers: {', '.join(mcp_names)}")

    if include_teammates and context.get("active_teammates"):
        sections.append(
            "Active teammates: " + ", ".join(context["active_teammates"])
        )

    if include_todos:
        todos_block = format_todos_for_prompt(get_todos())
        if todos_block:
            sections.append(todos_block)

    latest = (context.get("latest_user_query") or "").strip()
    if latest:
        sections.append(
            "Latest user request — respond ONLY to this unless they explicitly "
            f"ask to continue another task:\n{latest}\n"
            f"Project root: {WORKDIR}\n"
            "Python package path is `harness/` (there is no `src/harness/`)."
        )

    return "\n\n".join(sections)
