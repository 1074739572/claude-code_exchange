"""MCP connection manager and tool pool assembly."""

from __future__ import annotations

import re

from harness.mcp.base import MCPClientProtocol, MockMCPClient
from harness.mcp.client import create_real_client
from harness.mcp.config import load_mcp_config
from harness.mcp.mock import MOCK_SERVERS

mcp_clients: dict[str, MCPClientProtocol] = {}
mcp_tool_meta: dict[str, dict] = {}

_DISALLOWED_CHARS = re.compile(r"[^a-zA-Z0-9_-]")


def normalize_mcp_name(name: str) -> str:
    return _DISALLOWED_CHARS.sub("_", name)


def connect_mcp(name: str) -> str:
    if name in mcp_clients:
        return f"MCP server '{name}' already connected"

    config = load_mcp_config()
    if name in config:
        try:
            client = create_real_client(name, config[name])
            mcp_clients[name] = client
            tool_names = [tool["name"] for tool in client.tools]
            print(f"  \033[31m[mcp] connected (real): {name} → {tool_names}\033[0m")
            return (
                f"Connected to MCP server '{name}' (stdio). "
                f"Discovered {len(client.tools)} tools: {', '.join(tool_names)}"
            )
        except ImportError:
            return (
                "MCP SDK not installed. Run: pip install mcp\n"
                f"Then retry connect_mcp('{name}')."
            )
        except Exception as exc:
            return f"MCP connection failed: {exc}"

    factory = MOCK_SERVERS.get(name)
    if factory:
        client = factory()
        mcp_clients[name] = client
        tool_names = [tool["name"] for tool in client.tools]
        print(f"  \033[31m[mcp] connected (mock): {name} → {tool_names}\033[0m")
        return (
            f"Connected to mock MCP server '{name}'. "
            f"Discovered {len(client.tools)} tools: {', '.join(tool_names)}"
        )

    configured = ", ".join(config.keys()) or "(none)"
    mock_names = ", ".join(MOCK_SERVERS.keys())
    return (
        f"Unknown server '{name}'. "
        f"Configured in config/mcp.json: {configured}. "
        f"Mock servers: {mock_names}"
    )


def bootstrap_mcp_servers() -> list[str]:
    messages = []
    for name in load_mcp_config():
        messages.append(connect_mcp(name))
    return messages


def assemble_tool_pool(
    builtin_tools: list[dict],
    builtin_handlers: dict,
) -> tuple[list[dict], dict]:
    tools = list(builtin_tools)
    handlers = dict(builtin_handlers)
    mcp_tool_meta.clear()

    for server_name, mcp_client in mcp_clients.items():
        safe_server = normalize_mcp_name(server_name)
        for tool_def in mcp_client.tools:
            safe_tool = normalize_mcp_name(tool_def["name"])
            prefixed = f"mcp__{safe_server}__{safe_tool}"
            tools.append(
                {
                    "name": prefixed,
                    "description": tool_def.get("description", ""),
                    "input_schema": tool_def.get("inputSchema", {}),
                }
            )
            mcp_tool_meta[prefixed] = {
                "destructive": bool(tool_def.get("destructive")),
                "readOnly": bool(tool_def.get("readOnly")),
                "server": server_name,
                "tool": tool_def["name"],
            }
            handlers[prefixed] = (
                lambda *, c=mcp_client, t=tool_def["name"], **kw: c.call_tool(t, kw)
            )
    return tools, handlers
