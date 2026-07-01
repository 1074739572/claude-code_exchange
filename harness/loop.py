"""Core agent loop: one loop, full harness."""

from __future__ import annotations

import threading

from harness.agent.background import (
    build_user_content,
    inject_background_notifications,
    should_run_background,
    start_background_task,
)
from harness.agent.compact import compact_history, prepare_context, reactive_compact
from harness.agent.cron import consume_cron_queue
from harness.agent.recovery import (
    RecoveryState,
    is_prompt_too_long_error,
    with_retry,
)
from harness.context import update_context
from harness.hooks import trigger_hooks
from harness.prompts import assemble_system_prompt
from harness.settings import (
    CONTINUATION_PROMPT,
    DEFAULT_MAX_TOKENS,
    ESCALATED_MAX_TOKENS,
    MAX_RECOVERY_RETRIES,
    client,
)
from harness.tools.dispatch import call_tool_handler, has_tool_use
from harness.tools.registry import get_tool_pool

rounds_since_todo = 0
agent_lock = threading.Lock()


def call_llm(messages: list, context: dict, tools: list, state: RecoveryState, max_tokens: int):
    system = assemble_system_prompt(context)
    return with_retry(
        lambda: client.messages.create(
            model=state.current_model,
            system=system,
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
        ),
        state,
    )


def agent_loop(messages: list, context: dict) -> None:
    global rounds_since_todo
    state = RecoveryState()
    max_tokens = DEFAULT_MAX_TOKENS

    while True:
        fired = consume_cron_queue()
        for job in fired:
            messages.append({"role": "user", "content": f"[Scheduled] {job.prompt}"})
            print(f"  \033[35m[cron inject] {job.prompt[:60]}\033[0m")

        inject_background_notifications(messages)

        if rounds_since_todo >= 3:
            messages.append(
                {"role": "user", "content": "<reminder>Update your todos.</reminder>"}
            )
            rounds_since_todo = 0

        prepare_context(messages)
        context = update_context(context, messages)
        tools, handlers = get_tool_pool()

        try:
            response = call_llm(messages, context, tools, state, max_tokens)
        except Exception as exc:
            if is_prompt_too_long_error(exc) and not state.has_attempted_reactive_compact:
                messages[:] = reactive_compact(messages)
                state.has_attempted_reactive_compact = True
                continue
            messages.append(
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": f"[Error] {type(exc).__name__}: {exc}"}],
                }
            )
            return

        if response.stop_reason == "max_tokens":
            if not state.has_escalated:
                max_tokens = ESCALATED_MAX_TOKENS
                state.has_escalated = True
                print(f"  \033[33m[max_tokens] retry with {max_tokens}\033[0m")
                continue
            messages.append({"role": "assistant", "content": response.content})
            if state.recovery_count < MAX_RECOVERY_RETRIES:
                messages.append({"role": "user", "content": CONTINUATION_PROMPT})
                state.recovery_count += 1
                continue
            return

        max_tokens = DEFAULT_MAX_TOKENS
        state.has_escalated = False
        messages.append({"role": "assistant", "content": response.content})
        if not has_tool_use(response.content):
            trigger_hooks("Stop", messages)
            return

        results = []
        compacted_now = False
        for block in response.content:
            if block.type != "tool_use":
                continue
            print(f"\033[36m> {block.name}\033[0m")

            if block.name == "compact":
                messages[:] = compact_history(messages)
                messages.append(
                    {
                        "role": "user",
                        "content": "[Compacted. Continue with summarized context.]",
                    }
                )
                compacted_now = True
                break

            blocked = trigger_hooks("PreToolUse", block)
            if blocked:
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(blocked),
                    }
                )
                continue

            if should_run_background(block.name, block.input):
                bg_id = start_background_task(block, handlers)
                output = (
                    f"[Background task {bg_id} started] "
                    "Result will arrive as a task_notification."
                )
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": output,
                    }
                )
                continue

            handler = handlers.get(block.name)
            output = call_tool_handler(handler, block.input, block.name)
            trigger_hooks("PostToolUse", block, output)
            print(str(output)[:300])

            if block.name == "todo_write":
                rounds_since_todo = 0
            else:
                rounds_since_todo += 1

            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                }
            )

        if compacted_now:
            continue

        messages.append({"role": "user", "content": build_user_content(results)})
