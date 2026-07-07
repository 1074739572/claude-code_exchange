"""Interactive CLI entry for the improved harness."""

from __future__ import annotations

import threading
import time

import harness.console as console
from harness import terminal_state
from harness.agent.cron import consume_cron_queue
from harness.context import update_context
from harness.hooks import trigger_hooks
from harness.loop import agent_loop, agent_lock
from harness.mcp.pool import bootstrap_mcp_servers
from harness.models import handle_model_command
from harness.project.resume import checkpoint_history, resume_banner, resume_context_message
from harness.project.session_store import bootstrap_session
from harness.todos.state import load_todos_from_disk
from harness.project.tools import (
    run_project_clear,
    run_project_import_transcript,
    run_project_list_transcripts,
    run_project_status,
)
from harness.settings import CLI_PROMPT
from harness.teams import consume_lead_inbox
from harness.ui.banner import BANNER_STYLES, get_banner_style, print_hero, run_banner_demo
from harness.ui.renderer import renderer
from harness.ui.welcome import render_welcome


def _help_text() -> str:
    return """Commands:
  /model [id]              switch or list models
  /resume, /project        chapter progress
  /clear                   reset session + project state
  /import-transcript [path] [full|merge]
  /transcripts             list .transcripts backups
  /banner [style|demo]     preview welcome art (classic|emoji|typewriter|shadow3d)
  /help                    this message
  q, exit                  quit"""


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
                renderer.hook("cron auto", job.prompt[:60])
            agent_loop(history, context)
            context.update(update_context(context, history))
            print_turn_assistants(history, turn_start)
            checkpoint_history(history)


def run_cli() -> None:
    terminal_state.CLI_ACTIVE = True

    history, session_source = bootstrap_session()
    load_todos_from_disk()
    context = update_context({}, history if history else [])

    render_welcome(session_source=session_source)

    banner = resume_banner()
    if banner:
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

    bootstrap_results = bootstrap_mcp_servers()
    for line in bootstrap_results:
        if "Connected" in line:
            renderer.info(line.strip())

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
            renderer.plain(handle_model_command(query))
            print()
            continue
        if query.strip().lower() in ("/resume", "/project"):
            renderer.plain(run_project_status())
            print()
            continue
        if query.strip().lower() in ("/clear",):
            renderer.plain(run_project_clear())
            history.clear()
            context = update_context({}, [])
            print()
            continue
        if query.strip().lower() in ("/transcripts", "/list-transcripts"):
            renderer.plain(run_project_list_transcripts())
            print()
            continue
        if query.strip().lower() in ("/help",):
            renderer.plain(_help_text())
            print()
            continue
        if query.strip().lower().startswith("/banner"):
            parts = query.strip().split()
            if len(parts) == 1 or parts[1].lower() == "demo":
                from rich.console import Console

                run_banner_demo(Console(highlight=False, legacy_windows=False))
            elif parts[1].lower() in BANNER_STYLES:
                from rich.console import Console

                c = Console(highlight=False, legacy_windows=False)
                print_hero(c, style=parts[1].lower(), width=c.size.width)  # type: ignore[arg-type]
            else:
                renderer.plain(
                    "Banner styles: " + ", ".join(BANNER_STYLES) + "\n"
                    "Usage: /banner demo  |  /banner emoji\n"
                    "Default: HARNESS_BANNER env (current: "
                    f"{get_banner_style()})"
                )
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
            renderer.plain(run_project_import_transcript(path=path, mode=mode, merge=merge))
            history[:] = bootstrap_session()[0]
            context = update_context(context, history)
            print()
            continue
        trigger_hooks("UserPromptSubmit", query)
        renderer.user(query)
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
