"""One-shot subagent — implementation lives in ``harness.agents.runner``.

Kept as a compatibility re-export so older ``harness.agent.subagent`` imports
keep working.
"""

from harness.agents.runner import run_agent_task, spawn_subagent

__all__ = ["run_agent_task", "spawn_subagent"]
