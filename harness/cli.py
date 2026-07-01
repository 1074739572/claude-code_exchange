"""Interactive CLI entry for the improved harness."""

from __future__ import annotations

import threading
import time

import harness.console as console
from harness.agent.cron import consume_cron_queue
from harness.context import update_context
from harness.hooks import trigger_hooks
from harness.loop import agent_loop, agent_lock
from harness.mcp.pool import bootstrap_mcp_servers
from harness.models import format_model_status, handle_model_command
from harness.project.resume import checkpoint_history, resume_banner, resume_context_message
from harness.project.session_store import bootstrap_session
from harness.project.tools import (
    run_project_clear,
    run_project_import_transcript,
    run_project_list_transcripts,
    run_project_status,
)
from harness.providers.config import load_providers, provider_key_status
from harness.settings import CLI_PROMPT
from harness.teams import consume_lead_inbox


def _assistant_text_blocks(content) -> list[str]:
    if isinstance(content, str):
        return [content] if content else []
    if not isinstance(content, list):
        return [str(content)] if content else []
    texts: list[str] = []
    for block in content:
        if isinstance(block, dict):
            if block.get("type") == "text" and block.get("text"):
                texts.append(block["text"])
            continue
        if getattr(block, "type", None) == "text" and getattr(block, "text", None):
            texts.append(block.text)
    return texts


def print_turn_assistants(messages: list, turn_start: int) -> None:
    for msg in messages[turn_start:]:
        if msg.get("role") != "assistant":
            continue
        for text in _assistant_text_blocks(msg.get("content")):
            console.terminal_print(text)


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
            checkpoint_history(history)


def run_cli() -> None:
    console.CLI_ACTIVE = True
    print("improved_harness: comprehensive agent")
    print(format_model_status())
    ready = [
        load_providers()[pid].label
        for pid, ok in provider_key_status().items()
        if ok
    ]
    if ready:
        print(f"Providers ready: {', '.join(ready)}")

    history, session_source = bootstrap_session()
    context = update_context({}, history if history else [])

    banner = resume_banner()
    if banner:
        print()
        print(banner)
        if session_source:
            print(f"Continued: {session_source}")
        should_inject = not history or (
            len(history) <= 2
            and not any(
                isinstance(m.get("content"), str)
                and (
                    m["content"].startswith("[Compacted]")
                    or m["content"].startswith("[Reactive compact]")
                    or m["content"].startswith("[Session resumed]")
                )
                for m in history
                if m.get("role") == "user"
            )
        )
        if should_inject:
            resume_msg = resume_context_message()
            if resume_msg:
                history.append({"role": "user", "content": resume_msg})
                history.append(
                    {
                        "role": "assistant",
                        "content": "Resumed. I have the saved progress and conversation. "
                        "Say which chapter to continue, or I will proceed with the current chapter.",
                    }
                )
                checkpoint_history(history)
    else:
        print("Tip: sessions persist in .project/session.jsonl (auto-continue on restart)")

    print("Enter a question, press Enter to send. Type q to quit.")
    print("Commands: /model  /resume  /clear  /import-transcript  /transcripts\n")

    bootstrap_results = bootstrap_mcp_servers()
    for line in bootstrap_results:
        if "Connected" in line:
            print(f"  {line}")

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
        if query.strip().lower().startswith("/model"):
            print(handle_model_command(query))
            print()
            continue
        if query.strip().lower() in ("/resume", "/project"):
            print(run_project_status())
            print()
            continue
        if query.strip().lower() in ("/clear",):
            print(run_project_clear())
            history.clear()
            context = update_context({}, [])
            print()
            continue
        if query.strip().lower() in ("/transcripts", "/list-transcripts"):
            print(run_project_list_transcripts())
            print()
            continue
        if query.strip().lower().startswith("/import-transcript"):
            parts = query.strip().split(maxsplit=2)
            mode = "summary"
            path = ""
            if len(parts) > 1:
                arg = parts[1]
                if arg.lower() == "full":
                    mode = "full"
                elif arg.lower() == "merge":
                    mode = "summary"
                else:
                    path = arg
            if len(parts) > 2 and parts[2].lower() == "full":
                mode = "full"
            merge = "merge" in query.lower()
            print(run_project_import_transcript(path=path, mode=mode, merge=merge))
            history[:] = bootstrap_session()[0]
            context = update_context(context, history)
            print()
            continue
        trigger_hooks("UserPromptSubmit", query)
        turn_start = len(history)
        history.append({"role": "user", "content": query})
        with agent_lock:
            agent_loop(history, context)
            context = update_context(context, history)
            print_turn_assistants(history, turn_start)
            checkpoint_history(history)

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
            checkpoint_history(history)
        print()
