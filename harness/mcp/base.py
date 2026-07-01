"""MCP client base types."""

from __future__ import annotations

from typing import Protocol


class MCPClientProtocol(Protocol):
    name: str
    tools: list[dict]

    def call_tool(self, tool_name: str, args: dict) -> str: ...


class MockMCPClient:
    """In-process mock for teaching and offline development."""

    def __init__(self, name: str):
        self.name = name
        self.tools: list[dict] = []
        self._handlers: dict[str, callable] = {}

    def register(self, tool_defs: list[dict], handlers: dict[str, callable]) -> None:
        self.tools = tool_defs
        self._handlers = handlers

    def call_tool(self, tool_name: str, args: dict) -> str:
        handler = self._handlers.get(tool_name)
        if not handler:
            return f"MCP error: unknown tool '{tool_name}'"
        try:
            return handler(**args)
        except Exception as exc:
            return f"MCP error: {exc}"
