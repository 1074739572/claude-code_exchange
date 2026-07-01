"""Runtime system prompt assembly."""

from __future__ import annotations

from datetime import datetime

from harness.models import get_model, get_model_profile, model_label
from harness.providers.config import get_provider
from harness.mcp.pool import mcp_clients
from harness.settings import WORKDIR
from harness.skills_loader import list_skills

PROMPT_SECTIONS = {
    "identity": "You are a coding agent. Act, don't explain.",
    "tools": (
        "Available tools: bash, read_file, write_file, edit_file, glob, "
        "todo_write, task, load_skill, compact, "
        "create_task, list_tasks, get_task, claim_task, complete_task, "
        "schedule_cron, list_crons, cancel_cron, "
        "spawn_teammate, send_message, check_inbox, "
        "request_shutdown, request_plan, review_plan, "
        "create_worktree, remove_worktree, keep_worktree, "
        "connect_mcp, rag_index, rag_search, rag_status. "
        "MCP tools are prefixed mcp__{server}__{tool}. "
        "For long report/thesis 仿写/改写: load_skill(thesis-writing) first, then rag_index / rag_search per section."
    ),
    "workspace": f"Working directory: {WORKDIR}",
}


def assemble_system_prompt(context: dict) -> str:
    sections = [
        PROMPT_SECTIONS["identity"],
        PROMPT_SECTIONS["tools"],
        PROMPT_SECTIONS["workspace"],
    ]
    sections.append(f"Current time: {datetime.now().isoformat(timespec='seconds')}")
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
    sections.append(
        "Skills catalog:\n"
        + list_skills()
        + "\nUse load_skill(name) when a skill is relevant."
    )
    if context.get("memories"):
        sections.append(f"Relevant memories:\n{context['memories']}")
    mcp_names = list(mcp_clients.keys())
    if mcp_names:
        sections.append(f"Connected MCP servers: {', '.join(mcp_names)}")
    if context.get("active_teammates"):
        sections.append(
            "Active teammates: " + ", ".join(context["active_teammates"])
        )
    return "\n\n".join(sections)
