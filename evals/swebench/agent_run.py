"""Run improved_harness agent against one SWE-bench workspace."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest import mock


def build_prompt(instance: dict[str, Any]) -> str:
    return f"""You are fixing a real GitHub issue in this repository (SWE-bench).

Repository: {instance['repo']}
Instance: {instance['instance_id']}

## Issue
{instance['problem_statement']}

## Instructions
- You are already at the buggy commit. Explore with read_file / glob / bash.
- Make a MINIMAL fix in the source code.
- Do NOT modify existing tests.
- Do NOT commit. Just edit files.
- When the fix is done, stop (no more tools).
"""


def run_agent_on_workspace(
    workspace: Path,
    instance: dict[str, Any],
    *,
    max_rounds: int = 25,
) -> list:
    """chdir into workspace so harness WORKDIR resolves there; run agent_loop."""
    # Import after we are about to chdir — but harness.settings already bound WORKDIR.
    # Patch WORKDIR across modules that cached the import.
    import harness.settings as settings
    import harness.tools.filesystem as filesystem
    import harness.hooks as hooks
    import harness.context as context_mod
    import harness.prompts.dynamic as dynamic
    import harness.prompts.sections as sections

    from harness.context import update_context
    from harness.loop import agent_loop
    from harness.modes import set_mode

    old_cwd = Path.cwd()
    old_workdir = settings.WORKDIR
    targets = [
        (settings, "WORKDIR"),
        (filesystem, "WORKDIR"),
        (hooks, "WORKDIR"),
        (context_mod, "WORKDIR"),
        (dynamic, "WORKDIR"),
        (sections, "WORKDIR"),
    ]
    saved = [(mod, name, getattr(mod, name)) for mod, name in targets]

    os.chdir(workspace)
    for mod, name in targets:
        setattr(mod, name, workspace)
    # Refresh static prompt workspace line
    sections.PROMPT_SECTIONS["workspace"] = f"Working directory: {workspace}"

    set_mode("direct")
    messages = [{"role": "user", "content": build_prompt(instance)}]
    ctx = update_context({}, messages)

    try:
        with mock.patch("builtins.input", return_value="y"):
            agent_loop(messages, ctx, max_rounds=max_rounds)
    finally:
        for mod, name, value in saved:
            setattr(mod, name, value)
        sections.PROMPT_SECTIONS["workspace"] = f"Working directory: {old_workdir}"
        os.chdir(old_cwd)

    return messages
