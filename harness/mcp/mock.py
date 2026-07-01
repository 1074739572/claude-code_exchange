"""Teaching mock MCP servers (docs, deploy)."""

from __future__ import annotations

from harness.mcp.base import MockMCPClient


def _mock_server_docs() -> MockMCPClient:
    client = MockMCPClient("docs")
    client.register(
        tool_defs=[
            {
                "name": "search",
                "description": "Search documentation. (readOnly)",
                "inputSchema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
            {
                "name": "get_version",
                "description": "Get API version. (readOnly)",
                "inputSchema": {"type": "object", "properties": {}, "required": []},
            },
        ],
        handlers={
            "search": lambda query: f"[docs] Found 3 results for '{query}'",
            "get_version": lambda: "[docs] API v2.1.0",
        },
    )
    return client


def _mock_server_deploy() -> MockMCPClient:
    client = MockMCPClient("deploy")
    client.register(
        tool_defs=[
            {
                "name": "trigger",
                "description": (
                    "Trigger a deployment. (destructive — requires approval)"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {"service": {"type": "string"}},
                    "required": ["service"],
                },
                "destructive": True,
            },
            {
                "name": "status",
                "description": "Check deployment status. (readOnly)",
                "inputSchema": {
                    "type": "object",
                    "properties": {"service": {"type": "string"}},
                    "required": ["service"],
                },
            },
        ],
        handlers={
            "trigger": lambda service: f"[deploy] Triggered: {service}",
            "status": lambda service: f"[deploy] {service}: running (v1.4.2)",
        },
    )
    return client


MOCK_SERVERS = {
    "docs": _mock_server_docs,
    "deploy": _mock_server_deploy,
}
