"""Core agent loop: one loop, full harness."""

from __future__ import annotations

import threading

from harness.agent.background import (
    build_user_content,
    inject_background_notifications,
    should_run_background,
    start_background_task,
)
from harness.agent.cancel import is_cancelled
from harness.agent.compact import compact_history, prepare_context, reactive_compact
from harness.agent.cron import consume_cron_queue
from harness.agent.recovery import (
    RecoveryState,
    is_prompt_too_long_error,
    with_retry,
)
from harness.agent.repeat_guard import RepeatGuard
from harness.context import update_context
from harness.hooks import trigger_hooks
from harness.llm import create_message
from harness.messages.blocks import block_field, block_text, is_text, is_tool_use
from harness.messages.repair import finalize_cancelled_tool_round, repair_tool_pairing
from harness.models import get_model
from harness.project.session import serialize_messages
from harness.prompts import assemble_static_system_prompt, messages_with_ephemeral_context
from harness.settings import (
    CONTINUATION_PROMPT,
    DEFAULT_MAX_TOKENS,
    ESCALATED_MAX_TOKENS,
    MAX_RECOVERY_RETRIES,
)
from harness.tools.dispatch import call_tool_handler, has_tool_use
from harness.tools.registry import get_tool_pool
from harness.todos.format import format_todo_reminder
from harness.todos.state import note_llm_round_without_todo_update, rounds_since_todo_update
from harness.ui.renderer import renderer
from harness.ui.tool_display import tool_ui_mode

agent_lock = threading.Lock()


def _append_assistant(messages: list, content) -> None:
    messages.append(serialize_messages([{"role": "assistant", "content": content}])[0])


def call_llm(messages: list, context: dict, tools: list, state: RecoveryState, max_tokens: int):
    system = assemble_static_system_prompt()
    api_messages = messages_with_ephemeral_context(messages, context)
    model_id = state.fallback_model or get_model()
    return with_retry(
        lambda: create_message(
            model_id=model_id,
            system=system,
            messages=api_messages,
            tools=tools,
            max_tokens=max_tokens,
        ),
        state,
    )


def agent_loop(
    messages: list,
    context: dict,
    *,
    turn_start: int | None = None,
    max_rounds: int | None = None,
) -> bool:
    """Run until the agent finishes or cancel is requested. Returns True if interrupted.

    max_rounds: optional cap on LLM turns (used by evals). None = unlimited.
    """
    from harness.prompts.ephemeral import reset_ephemeral_cache

    reset_ephemeral_cache()
    state = RecoveryState()
    max_tokens = DEFAULT_MAX_TOKENS
    llm_rounds = 0
    repeat_guard = RepeatGuard()

    while True:
        if is_cancelled():
            return True

        if max_rounds is not None and llm_rounds >= max_rounds:
            messages.append(
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": f"[Stopped] reached max_rounds={max_rounds}",
                        }
                    ],
                }
            )
            trigger_hooks("Stop", messages)
            return False

        fired = consume_cron_queue()
        for job in fired:
            messages.append({"role": "user", "content": f"[Scheduled] {job.prompt}"})
            renderer.hook("cron inject", job.prompt[:60])

        inject_background_notifications(messages)

        if rounds_since_todo_update >= 3:
            messages.append(
                {"role": "user", "content": format_todo_reminder()}
            )

        prepare_context(messages)
        repair_tool_pairing(messages)
        context = update_context(context, messages)
        tools, handlers = get_tool_pool()

        try:
            llm_rounds += 1
            response = call_llm(messages, context, tools, state, max_tokens)
        except Exception as exc:
            if is_cancelled():
                return True
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
            return False

        if is_cancelled():
            return True

        if response.stop_reason == "max_tokens":
            if not state.has_escalated:
                max_tokens = ESCALATED_MAX_TOKENS
                state.has_escalated = True
                renderer.warn(f"max_tokens: retry with {max_tokens}")
                continue
            _append_assistant(messages, response.content)
            if state.recovery_count < MAX_RECOVERY_RETRIES:
                messages.append({"role": "user", "content": CONTINUATION_PROMPT})
                state.recovery_count += 1
                continue
            return False

        max_tokens = DEFAULT_MAX_TOKENS
        state.has_escalated = False
        _append_assistant(messages, response.content)
        if not has_tool_use(response.content):
            trigger_hooks("Stop", messages)
            return False

        results = []
        compacted_now = False
        had_todo_write = False
        for block in response.content:
            if is_cancelled():
                finalize_cancelled_tool_round(messages, response.content, results)
                return True
            # Show the model's brief "why" text before tools (human UI only).
            if is_text(block):
                text = block_text(block).strip()
                if text and tool_ui_mode() != "off":
                    renderer.tool_intent(text)
                continue
            if not is_tool_use(block):
                continue
            name = block_field(block, "name", "")
            tool_input = block_field(block, "input", {}) or {}
            streak, should_block = repeat_guard.note(
                name, tool_input if isinstance(tool_input, dict) else {}
            )
            if streak > 1:
                renderer.tool_repeat(
                    name,
                    tool_input if isinstance(tool_input, dict) else None,
                    streak=streak,
                    blocked=should_block,
                )
            else:
                renderer.tool_start(
                    name, tool_input if isinstance(tool_input, dict) else None
                )

            if name == "compact":
                messages[:] = compact_history(messages)
                messages.append(
                    {
                        "role": "user",
                        "content": "[Compacted. Continue with summarized context.]",
                    }
                )
                compacted_now = True
                break

            if should_block and name != "compact":
                output = repeat_guard.block_message(name, streak)
                renderer.tool_result(
                    output,
                    name=name,
                    tool_input=tool_input if isinstance(tool_input, dict) else None,
                )
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block_field(block, "id", ""),
                        "content": output,
                    }
                )
                continue

            blocked = trigger_hooks("PreToolUse", block)
            if blocked:
                renderer.tool_result(
                    str(blocked),
                    name=name,
                    tool_input=tool_input if isinstance(tool_input, dict) else None,
                )
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block_field(block, "id", ""),
                        "content": str(blocked),
                    }
                )
                continue

            if should_run_background(name, tool_input):
                bg_id = start_background_task(block, handlers)
                output = (
                    f"[Background task {bg_id} started] "
                    "Result will arrive as a task_notification."
                )
                renderer.tool_result(
                    output,
                    name=name,
                    tool_input=tool_input if isinstance(tool_input, dict) else None,
                )
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block_field(block, "id", ""),
                        "content": output,
                    }
                )
                continue

            handler = handlers.get(name)
            output = call_tool_handler(handler, tool_input, name)
            trigger_hooks("PostToolUse", block, output)
            renderer.tool_result(
                str(output),
                name=name,
                tool_input=tool_input if isinstance(tool_input, dict) else None,
            )
            if name == "todo_write":
                had_todo_write = True
                from harness.prompts.ephemeral import reset_ephemeral_cache

                reset_ephemeral_cache()

            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block_field(block, "id", ""),
                    "content": output,
                }
            )

        if compacted_now:
            continue

        if is_cancelled():
            finalize_cancelled_tool_round(messages, response.content, results)
            return True

        if not had_todo_write:
            note_llm_round_without_todo_update()

        messages.append({"role": "user", "content": build_user_content(results)})
