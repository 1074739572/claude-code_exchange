"""Hook registry and default permission pipeline."""

from __future__ import annotations

from harness.mcp.pool import mcp_tool_meta
from harness.messages.blocks import block_field
from harness.settings import WORKDIR
from harness.tools.filesystem import safe_path

HOOKS: dict[str, list] = {
    "UserPromptSubmit": [],
    "PreToolUse": [],
    "PostToolUse": [],
    "Stop": [],
}

DENY_LIST = ["rm -rf /", "sudo", "shutdown", "reboot", "mkfs", "dd if="]
DESTRUCTIVE = ["rm ", "> /etc/", "chmod 777"]


def register_hook(event: str, callback) -> None:
    HOOKS[event].append(callback)


def trigger_hooks(event: str, *args):
    for callback in HOOKS[event]:
        result = callback(*args)
        if result is not None:
            return result
    return None


def permission_hook(block):
    name = block_field(block, "name", "")
    tool_input = block_field(block, "input", {}) or {}
    if name == "bash":
        command = tool_input.get("command", "")
        for pattern in DENY_LIST:
            if pattern in command:
                return f"Permission denied: '{pattern}' is on the deny list"
        if any(token in command for token in DESTRUCTIVE):
            print("\n\033[33m[permission] destructive command\033[0m")
            print(f"  {command}")
            choice = input("  Allow? [y/N] ").strip().lower()
            if choice not in ("y", "yes"):
                return "Permission denied by user"
    if name in ("write_file", "edit_file"):
        path = tool_input.get("path", "")
        try:
            safe_path(path)
        except Exception:
            return f"Permission denied: path escapes workspace: {path}"
    if name.startswith("mcp__"):
        meta = mcp_tool_meta.get(name, {})
        if meta.get("destructive"):
            print(
                f"\n\033[33m[permission] MCP destructive tool: {name}\033[0m"
            )
            choice = input("  Allow? [y/N] ").strip().lower()
            if choice not in ("y", "yes"):
                return "Permission denied by user"
    return None


def log_hook(block):
    from harness.ui.tool_display import hooks_verbose

    if not hooks_verbose():
        return None
    print(f"\033[90m[HOOK] {block_field(block, 'name', '')}\033[0m")
    return None


def large_output_hook(block, output):
    if len(str(output)) > 100000:
        print(
            f"\033[33m[HOOK] large output from {block_field(block, 'name', '')}: "
            f"{len(str(output))} chars\033[0m"
        )
    return None


def user_prompt_hook(query: str):
    from harness.ui.tool_display import hooks_verbose

    if not hooks_verbose():
        return None
    print(f"\033[90m[HOOK] UserPromptSubmit: {WORKDIR}\033[0m")
    return None


def stop_hook(messages: list):
    from harness.ui.tool_display import hooks_verbose

    if not hooks_verbose():
        return None
    tool_count = 0
    for message in messages:
        content = message.get("content")
        if isinstance(content, list):
            tool_count += sum(
                1
                for item in content
                if isinstance(item, dict) and item.get("type") == "tool_result"
            )
    print(f"\033[90m[HOOK] Stop: {tool_count} tool result(s)\033[0m")
    return None


def project_write_hook(block, output):
    name = block_field(block, "name", "")
    tool_input = block_field(block, "input", {}) or {}
    if name in ("write_file", "edit_file"):
        path = tool_input.get("path", "")
        if path:
            try:
                from harness.project.resume import on_write_file

                on_write_file(path)
            except Exception:
                pass
    return None


register_hook("UserPromptSubmit", user_prompt_hook)
register_hook("PreToolUse", permission_hook)
register_hook("PreToolUse", log_hook)
register_hook("PostToolUse", large_output_hook)
register_hook("PostToolUse", project_write_hook)
register_hook("Stop", stop_hook)
