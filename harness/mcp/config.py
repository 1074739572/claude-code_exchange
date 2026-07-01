"""Load MCP server definitions from config/mcp.json."""

from __future__ import annotations

import json

from harness.settings import MCP_CONFIG_PATH


def load_mcp_config() -> dict[str, dict]:
    if not MCP_CONFIG_PATH.exists():
        return {}
    try:
        data = json.loads(MCP_CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data.get("mcpServers", {})
