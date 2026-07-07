"""Interactive CLI entry for the improved harness."""

from __future__ import annotations

import threading
import time

import harness.console as console
from harness import terminal_state
from harness.agent.cancel import clear_cancel, request_cancel
from harness.agent.cron import consume_cron_queue
from harness.context import update_context
from harness.hooks import trigger_hooks
from harness.loop import agent_loop, agent_lock
from harness.mcp.pool import bootstrap_mcp_servers
from harness.messages.repair import repair_tool_pairing
from harness.models import handle_model_command
from harness.modes import format_mode_status, set_mode
from harness.modes.registry import format_mode_catalog
from harness.ui.mode_picker import run_mode_picker
from harness.project.resume import (
    checkpoint_history,
    inject_project_context,
    resume_banner,
    run_resume_command,
    should_auto_inject_project_on_startup,
)
from harness.project.session_store import bootstrap_session
from harness.tasks import reconcile_task_board
from harness.todos.state import load_todos_from_disk
from harness.project.session_undo import abort_inflight_turn, undo_last_turn
from harness.project.tools import (
    run_project_clear,
    run_project_import_transcript,
    run_project_list_transcripts,
    run_project_status,
)
from harness.teams import consume_lead_inbox
from harness.ui.banner import BANNER_STYLES, get_banner_style, print_hero, run_banner_demo
from harness.ui.interrupt_listener import InterruptListener
from harness.ui.model_picker import run_model_picker
from harness.ui.prompt_input import read_cli_query
from harness.ui.renderer import renderer
from harness.ui.welcome import render_welcome


def _match_cli_command(query: str, command: str) -> bool:
    """True for `/cmd` or `/cmd args` — avoids `/model` matching `/mode`."""
    text = query.strip().lower()
    command = command.lower()
    return text == command or text.startswith(command + " ")


def _help_text() -> str:
    return """Commands:
  /model                   pick model (↑↓ Enter) or /model <id>
  /mode [id]               pick mode (↑↓ Enter) — edit config/modes.json to add
  /undo                    cancel last completed question + reply
  Esc / Ctrl+C             stop in-flight turn; roll back to edit/resend question
  /resume [session|project]  session status; project = opt-in thesis context
  /project                   thesis chapter table (same as /resume project view)
  /clear [session]         OpenCode 模式：默认清 session+todos+state.json；/clear session 仅清对话
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
    reconciled = reconcile_task_board()
    if reconciled:
        renderer.warn(
            f"Archived {reconciled} completed task(s) left on the active board from a prior run."
        )
    _, repair_fixes = repair_tool_pairing(history)
    if repair_fixes:
        checkpoint_history(history)
        renderer.warn(f"Repaired {repair_fixes} broken tool message(s) in saved session.")
    context = update_context({}, history if history else [])

    render_welcome(session_source=session_source)

    banner = resume_banner()
    if banner:
        renderer.plain(banner)
        print()

    if should_auto_inject_project_on_startup():
        ok, note = inject_project_context(history, checkpoint=True)
        if ok:
            renderer.info(note)
            context = update_context(context, history)

    bootstrap_results = bootstrap_mcp_servers()
    for line in bootstrap_results:
        if "Connected" in line:
            renderer.info(line.strip())

    threading.Thread(
        target=cron_autorun_loop, args=(history, context), daemon=True
    ).start()

    redo_query: str | None = None

    while True:
        try:
            query = read_cli_query(redo=redo_query)
            redo_query = None
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        if _match_cli_command(query, "/model"):
            parts = query.strip().split(maxsplit=1)
            if len(parts) == 1 or parts[1].lower() in ("list", "pick", "picker"):
                renderer.plain(run_model_picker())
            else:
                renderer.plain(handle_model_command(query))
            print()
            continue
        if _match_cli_command(query, "/mode"):
            parts = query.strip().split(maxsplit=1)
            if len(parts) == 1 or parts[1].lower() in ("list", "pick", "picker"):
                renderer.plain(run_mode_picker())
            elif parts[1].lower() == "help":
                renderer.plain(format_mode_catalog())
            else:
                renderer.plain(set_mode(parts[1]))
            print()
            continue
        if query.strip().lower() in ("/undo", "/u"):
            with agent_lock:
                ok, message = undo_last_turn(history)
                context = update_context(context, history)
            renderer.plain(message)
            print()
            continue
        if query.strip().lower() in ("/project",):
            renderer.plain(run_project_status())
            print()
            continue
        if _match_cli_command(query, "/resume"):
            parts = query.strip().split(maxsplit=1)
            sub = parts[1] if len(parts) > 1 else ""
            with agent_lock:
                renderer.plain(run_resume_command(sub, messages=history))
                context = update_context(context, history)
            print()
            continue
        if _match_cli_command(query, "/clear"):
            parts = query.strip().split(maxsplit=1)
            sub = parts[1].lower() if len(parts) > 1 else ""
            # OpenCode 模式：默认全清（session + todos + state.json）
            # /clear session  → 只清对话，保留 state.json
            keep_project = sub in ("session", "chat", "history")
            renderer.plain(run_project_clear(clear_project=not keep_project))
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
        repair_tool_pairing(history)
        renderer.user(query)
        turn_start = len(history)
        history.append({"role": "user", "content": query})
        context["latest_user_query"] = query

        listener = InterruptListener()
        interrupted = False

        def _on_interrupt() -> None:
            request_cancel()
            renderer.warn("Stopping… (Esc or Ctrl+C)")

        listener.start(_on_interrupt)
        clear_cancel()
        try:
            with agent_lock:
                try:
                    interrupted = agent_loop(history, context, turn_start=turn_start)
                except KeyboardInterrupt:
                    request_cancel()
                    interrupted = True
        finally:
            listener.stop()
            clear_cancel()

        if interrupted:
            message, rolled_back = abort_inflight_turn(history, turn_start)
            renderer.plain(message)
            context = update_context(context, history)
            if rolled_back:
                redo_query = rolled_back
        else:
            with agent_lock:
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
