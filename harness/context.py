"""Per-turn runtime context for prompt assembly."""

from __future__ import annotations

from harness.mcp.pool import mcp_clients
from harness.settings import MEMORY_INDEX, WORKDIR
from harness.teams.bus import active_teammates


def update_context(context: dict, messages: list) -> dict:
    memories = ""
    if MEMORY_INDEX.exists():
        memories = MEMORY_INDEX.read_text(encoding="utf-8")[:2000]
    return {
        **context,
        "memories": memories,
        "connected_mcp": list(mcp_clients.keys()),
        "active_teammates": list(active_teammates.keys()),
    }
