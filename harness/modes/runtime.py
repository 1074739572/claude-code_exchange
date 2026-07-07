"""Runtime mode selection (config-driven)."""

from __future__ import annotations

import os
import threading

from harness.modes.registry import (
    default_mode_id,
    format_mode_catalog,
    get_mode_profile,
    list_mode_ids,
)

_lock = threading.Lock()
_env_mode = os.getenv("HARNESS_MODE", "").strip().lower()
_current_mode: str = _env_mode if _env_mode else default_mode_id()
if _current_mode not in list_mode_ids():
    _current_mode = default_mode_id()


def get_mode() -> str:
    with _lock:
        return _current_mode


def get_current_mode_profile():
    profile = get_mode_profile(get_mode())
    if profile is None:
        return get_mode_profile(default_mode_id())
    return profile


def set_mode(mode: str) -> str:
    global _current_mode
    mode = mode.strip().lower()
    if mode not in list_mode_ids():
        return f"Unknown mode '{mode}'.\n\n{format_mode_catalog()}"
    with _lock:
        _current_mode = mode
    return format_mode_status()


def format_mode_status() -> str:
    profile = get_current_mode_profile()
    if profile is None:
        return f"Mode: {get_mode()}"
    parts = [f"Mode: {profile.id} — {profile.label}"]
    if profile.summary:
        parts.append(profile.summary)
    if profile.enable_task:
        parts.append("task() enabled → see config/agents.json")
    if profile.lead_model_hint:
        parts.append(f"recommended lead /model: {profile.lead_model_hint}")
    return "\n".join(parts)


def mode_prompt_section() -> str:
    profile = get_current_mode_profile()
    if profile is None:
        return ""
    return profile.prompt


def mode_disables_tool(tool_name: str) -> bool:
    profile = get_current_mode_profile()
    if profile is None:
        return False
    return tool_name in profile.disable_tools


def mode_enables_task() -> bool:
    profile = get_current_mode_profile()
    if profile is None:
        return False
    return profile.enable_task


def mode_lead_model_hint() -> str | None:
    profile = get_current_mode_profile()
    if profile is None:
        return None
    return profile.lead_model_hint
