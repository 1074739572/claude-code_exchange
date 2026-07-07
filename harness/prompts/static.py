"""Stable system prompt — kept identical across LLM calls when skills catalog unchanged."""

from __future__ import annotations

from harness.prompts.sections import PROMPT_SECTIONS
from harness.skills_loader import list_skills


def assemble_static_system_prompt() -> str:
    """Identity, tools, workspace, and skills catalog only (no per-turn session state)."""
    sections = [
        PROMPT_SECTIONS["identity"],
        PROMPT_SECTIONS["tools"],
        PROMPT_SECTIONS["workspace"],
        (
            "Skills catalog:\n"
            + list_skills()
            + "\nUse load_skill(name) when a skill is relevant."
        ),
    ]
    return "\n\n".join(sections)
