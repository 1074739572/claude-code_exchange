"""Real MCP client via official Python SDK (stdio transport)."""

from __future__ import annotations

import asyncio
import threading

from harness.mcp.base import MCPClientProtocol


class RealMCPClient:
  """Long-lived stdio MCP session in a background event loop."""

  def __init__(self, name: str, server_cfg: dict):
    self.name = name
    self.server_cfg = server_cfg
    self.tools: list[dict] = []
    self._loop = asyncio.new_event_loop()
    self._ready = threading.Event()
    self._error: Exception | None = None
    self._thread = threading.Thread(target=self._run, daemon=True, name=f"mcp-{name}")
    self._thread.start()
    if not self._ready.wait(timeout=60):
      raise TimeoutError(f"MCP server '{name}' failed to start within 60s")
    if self._error:
      raise self._error

  def _run(self) -> None:
    asyncio.set_event_loop(self._loop)
    try:
      self._loop.run_until_complete(self._connect_and_discover())
      self._ready.set()
      self._loop.run_forever()
    except Exception as exc:
      self._error = exc
      self._ready.set()

  async def _connect_and_discover(self) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
      command=self.server_cfg["command"],
      args=self.server_cfg.get("args", []),
      env=self.server_cfg.get("env"),
    )
    self._stdio_cm = stdio_client(params)
    read, write = await self._stdio_cm.__aenter__()
    self._session_cm = ClientSession(read, write)
    self._session = await self._session_cm.__aenter__()
    await self._session.initialize()

    result = await self._session.list_tools()
    self.tools = []
    for tool in result.tools:
      destructive = False
      read_only = False
      annotations = getattr(tool, "annotations", None)
      if annotations:
        destructive = bool(getattr(annotations, "destructiveHint", False))
        read_only = bool(getattr(annotations, "readOnlyHint", False))
      description = tool.description or ""
      if read_only and "(readOnly)" not in description:
        description += " (readOnly)"
      if destructive and "(destructive)" not in description:
        description += " (destructive)"
      self.tools.append(
        {
          "name": tool.name,
          "description": description,
          "inputSchema": tool.inputSchema or {"type": "object", "properties": {}},
          "destructive": destructive,
          "readOnly": read_only,
        }
      )

  def call_tool(self, tool_name: str, args: dict) -> str:
    future = asyncio.run_coroutine_threadsafe(
      self._call_tool_async(tool_name, args or {}),
      self._loop,
    )
    return future.result(timeout=120)

  async def _call_tool_async(self, tool_name: str, args: dict) -> str:
    result = await self._session.call_tool(tool_name, arguments=args)
    if getattr(result, "isError", False):
      return f"MCP error: {self._content_to_text(result.content)}"
    return self._content_to_text(result.content)

  @staticmethod
  def _content_to_text(content) -> str:
    parts = []
    for block in content or []:
      if getattr(block, "type", None) == "text":
        parts.append(block.text)
      else:
        parts.append(str(block))
    return "\n".join(parts) or "(empty result)"


def create_real_client(name: str, server_cfg: dict) -> MCPClientProtocol:
  return RealMCPClient(name, server_cfg)
