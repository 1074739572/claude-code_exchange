"""Interactive CLI entry for the improved harness."""

from __future__ import annotations

import threading

import harness.console as console
from harness.agent.cron import consume_cron_queue
from harness.context import update_context
from harness.hooks import trigger_hooks
from harness.loop import agent_loop, agent_lock
from harness.mcp.pool import bootstrap_mcp_servers
from harness.settings import CLI_PROMPT
from harness.teams import consume_lead_inbox


def print_turn_assistants(messages: list, turn_start: int) -> None:
    for msg in messages[turn_start:]:
        if msg.get("role") != "assistant":
            continue
        for block in msg.get("content", []):
            if getattr(block, "type", None) == "text":
                console.terminal_print(block.text)


def cron_autorun_loop(history: list, context: dict) -> None:
    while True:
        time.sleep(1)
        fired = consume_cron_queue()
        if not fired:
            continue
        with agent_lock:
            turn_start = len(history)
            for job in fired:
                history.append(
                    {"role": "user", "content": f"[Scheduled] {job.prompt}"}
                )
                console.terminal_print(f"  \033[35m[cron auto] {job.prompt[:60]}\033[0m")
            agent_loop(history, context)
            context.update(update_context(context, history))
            print_turn_assistants(history, turn_start)


def run_cli() -> None:
    console.CLI_ACTIVE = True
    print("improved_harness: comprehensive agent")
    print("Enter a question, press Enter to send. Type q to quit.\n")

    bootstrap_results = bootstrap_mcp_servers()
    for line in bootstrap_results:
        if "Connected" in line:
            print(f"  {line}")

    history: list = []
    context = update_context({}, [])
    threading.Thread(
        target=cron_autorun_loop, args=(history, context), daemon=True
    ).start()

    while True:
        try:
            query = input(CLI_PROMPT)
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        trigger_hooks("UserPromptSubmit", query)
        turn_start = len(history)
        history.append({"role": "user", "content": query})
        with agent_lock:
            agent_loop(history, context)
            context = update_context(context, history)
            print_turn_assistants(history, turn_start)

        inbox = consume_lead_inbox(route_protocol=True)
        if inbox:
            def inbox_label(msg: dict) -> str:
                req_id = msg.get("metadata", {}).get("request_id", "")
                suffix = f" req:{req_id}" if req_id else ""
                return f"{msg.get('type', 'message')}{suffix}"

            inbox_text = "\n".join(
                f"From {m['from']} [{inbox_label(m)}]: {m['content'][:200]}"
                for m in inbox
            )
            history.append({"role": "user", "content": f"[Inbox]\n{inbox_text}"})
        print()
