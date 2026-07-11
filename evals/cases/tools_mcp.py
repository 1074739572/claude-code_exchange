"""Builtin tool pool / MCP config eval cases."""

from __future__ import annotations

from harness.mcp.config import load_mcp_config
from harness.mcp.pool import mcp_bootstrap_warnings
from harness.tools.registry import BUILTIN_HANDLERS, BUILTIN_TOOLS, get_tool_pool

from evals.types import EvalCase


REQUIRED_TOOLS = {
    "bash",
    "read_file",
    "write_file",
    "edit_file",
    "glob",
    "todo_write",
    "connect_mcp",
    "compact",
}


def case_builtin_schema_handler_parity() -> None:
    schema_names = {t["name"] for t in BUILTIN_TOOLS}
    # compact is schema-only (handled in loop)
    handler_names = set(BUILTIN_HANDLERS)
    missing_handlers = (schema_names - {"compact"}) - handler_names
    assert not missing_handlers, f"schemas without handlers: {missing_handlers}"
    orphan = handler_names - schema_names
    assert not orphan, f"handlers without schemas: {orphan}"


def case_required_tools_present() -> None:
    names = {t["name"] for t in BUILTIN_TOOLS}
    missing = REQUIRED_TOOLS - names
    assert not missing, missing


def case_get_tool_pool_direct() -> None:
    from harness.modes import set_mode

    set_mode("direct")
    tools, handlers = get_tool_pool()
    names = {t["name"] for t in tools}
    for req in ("bash", "read_file", "write_file"):
        assert req in names and req in handlers


def case_mcp_config_servers() -> None:
    cfg = load_mcp_config()
    assert "fetch" in cfg, f"expected fetch in mcp.json, got {list(cfg)}"
    assert "playwright" in cfg, f"expected playwright in mcp.json, got {list(cfg)}"
    assert "github" not in cfg, "github MCP should be removed"


def case_mcp_warning_filter() -> None:
    lines = [
        "Connected to MCP server 'fetch' (stdio). Discovered 1 tools: fetch",
        "MCP connection failed (playwright): boom",
        "MCP server 'x' already connected",
    ]
    warns = mcp_bootstrap_warnings(lines)
    assert warns == ["MCP connection failed (playwright): boom"], warns


CASES = [
    EvalCase(
        "tools.schema_handlers",
        "BUILTIN_TOOLS vs HANDLERS parity (ex compact)",
        "tools",
        case_builtin_schema_handler_parity,
    ),
    EvalCase(
        "tools.required_present",
        "core coding tools registered",
        "tools",
        case_required_tools_present,
    ),
    EvalCase(
        "tools.pool_direct",
        "get_tool_pool works in direct mode",
        "tools",
        case_get_tool_pool_direct,
    ),
    EvalCase(
        "mcp.config_servers",
        "mcp.json has fetch+playwright, no github",
        "mcp",
        case_mcp_config_servers,
    ),
    EvalCase(
        "mcp.warning_filter",
        "bootstrap only surfaces failures",
        "mcp",
        case_mcp_warning_filter,
    ),
]
