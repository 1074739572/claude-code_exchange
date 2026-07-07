"""Run typed subagents with isolated context and bound models."""

from __future__ import annotations

import time

from harness.agents.registry import get_agent_profile, validate_agent_model
from harness.hooks import trigger_hooks
from harness.llm import create_message
from harness.messages.blocks import block_field, is_tool_use
from harness.project.session import serialize_messages
from harness.settings import WORKDIR
from harness.tools.dispatch import call_tool_handler, extract_text, has_tool_use
from harness.tools.filesystem import run_bash, run_edit, run_glob, run_read, run_write
from harness.ui.renderer import renderer

_BASE_TOOL_DEFS = {
    "bash": {
        "name": "bash",
        "description": "Run a shell command.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
    "read_file": {
        "name": "read_file",
        "description": "Read file contents.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "limit": {"type": "integer"},
                "offset": {"type": "integer"},
            },
            "required": ["path"],
        },
    },
    "write_file": {
        "name": "write_file",
        "description": "Write content to a file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    "edit_file": {
        "name": "edit_file",
        "description": "Replace exact text in a file once.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
    "glob": {
        "name": "glob",
        "description": "Find files matching a glob pattern.",
        "input_schema": {
            "type": "object",
            "properties": {"pattern": {"type": "string"}},
            "required": ["pattern"],
        },
    },
}

_BASE_HANDLERS = {
    "bash": run_bash,
    "read_file": run_read,
    "write_file": run_write,
    "edit_file": run_edit,
    "glob": run_glob,
}


def _tools_for_agent(allowed: list[str]) -> tuple[list[dict], dict]:
    tools = [_BASE_TOOL_DEFS[name] for name in allowed if name in _BASE_TOOL_DEFS]
    handlers = {name: _BASE_HANDLERS[name] for name in allowed if name in _BASE_HANDLERS}
    return tools, handlers


def run_agent_task(description: str, prompt: str, agent_type: str) -> str:
    error = validate_agent_model(agent_type)
    if error:
        return f"Error: {error}"

    profile = get_agent_profile(agent_type)
    assert profile is not None

    tools, handlers = _tools_for_agent(profile.tools)
    system = f"{profile.system}\n\nWorking directory: {WORKDIR}"
    messages = [{"role": "user", "content": prompt}]

    renderer.info(f"[task:{agent_type}] {description} → {profile.model_id}")
    started = time.time()
    tool_count = 0

    for _ in range(30):
        response = create_message(
            model_id=profile.model_id,
            system=system,
            messages=messages,
            tools=tools,
            max_tokens=8000,
        )
        messages.append(
            serialize_messages([{"role": "assistant", "content": response.content}])[0]
        )
        if not has_tool_use(response.content):
            break
        results = []
        for block in response.content:
            if not is_tool_use(block):
                continue
            tool_count += 1
            blocked = trigger_hooks("PreToolUse", block)
            if blocked:
                output = str(blocked)
            else:
                name = block_field(block, "name", "")
                tool_input = block_field(block, "input", {}) or {}
                handler = handlers.get(name)
                output = call_tool_handler(handler, tool_input, name)
                trigger_hooks("PostToolUse", block, output)
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block_field(block, "id", ""),
                    "content": str(output),
                }
            )
        messages.append({"role": "user", "content": results})

    elapsed = time.time() - started
    for msg in reversed(messages):
        if msg["role"] == "assistant":
            text = extract_text(msg["content"])
            if text:
                return (
                    f"[{agent_type} / {profile.model_id}] {description} "
                    f"({tool_count} tools, {elapsed:.1f}s)\n\n{text}"
                )
    return f"[{agent_type}] finished without summary ({tool_count} tools, {elapsed:.1f}s)"


def spawn_subagent(description: str) -> str:
    """Legacy entry: treat as explore task with description as prompt."""
    return run_agent_task(description, description, "explore")
