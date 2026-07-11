"""Agent subsystem: compaction, recovery, cron, background, cancel.

Typed subagents live in ``harness.agents``; ``agent.subagent`` re-exports them
for compatibility.
"""

from __future__ import annotations

from harness.agent.background import (
    build_user_content,
    inject_background_notifications,
    should_run_background,
    start_background_task,
)
from harness.agent.cancel import clear_cancel, is_cancelled, request_cancel
from harness.agent.compact import (
    compact_history,
    prepare_context,
    reactive_compact,
)
from harness.agent.cron import consume_cron_queue
from harness.agent.recovery import (
    RecoveryState,
    is_prompt_too_long_error,
    with_retry,
)
from harness.agent.subagent import run_agent_task, spawn_subagent

__all__ = [
    "RecoveryState",
    "build_user_content",
    "clear_cancel",
    "compact_history",
    "consume_cron_queue",
    "inject_background_notifications",
    "is_cancelled",
    "is_prompt_too_long_error",
    "prepare_context",
    "reactive_compact",
    "request_cancel",
    "run_agent_task",
    "should_run_background",
    "spawn_subagent",
    "start_background_task",
    "with_retry",
]
