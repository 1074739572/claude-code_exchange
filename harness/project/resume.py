"""Resume: Claude Code-style session continue + opt-in project context."""

from __future__ import annotations

import os

from harness.project.session_store import (
    append_checkpoint,
    continue_session_on_startup,
    format_session_line,
    session_stats,
)
from harness.project.state import (
    format_status,
    load_state,
    sync_chapters_from_disk,
)
from harness.project.transcript import format_transcript_hint
from harness.settings import WORKDIR
from harness.todos.format import format_todos_for_cli
from harness.todos.state import get_todos

RESUME_CONTEXT_PREFIX = "[Resume context]"
LEGACY_SESSION_PREFIX = "[Session resumed]"


def auto_resume_mode() -> str:
    """
    off (default): reload session.jsonl only — no project/thesis injection.
    project:       also inject thesis chapter context on startup (legacy behavior).
    """
    return os.getenv("HARNESS_AUTO_RESUME", "off").strip().lower()


def should_auto_inject_project_on_startup() -> bool:
    return auto_resume_mode() in ("project", "thesis", "all", "1", "true", "yes")


def show_project_in_welcome() -> bool:
    if not load_state():
        return False
    flag = os.getenv("HARNESS_WELCOME_PROJECT", "0").strip().lower()
    return flag in ("1", "true", "yes", "on") or should_auto_inject_project_on_startup()


def is_resume_injection(message: dict) -> bool:
    if message.get("role") != "user":
        return False
    content = message.get("content")
    if not isinstance(content, str):
        return False
    text = content.strip()
    return text.startswith(RESUME_CONTEXT_PREFIX) or text.startswith(LEGACY_SESSION_PREFIX)


def project_context_message() -> str | None:
    """Opt-in thesis/project snapshot for the agent (not a user question)."""
    state = load_state()
    if state is None:
        return None
    state = sync_chapters_from_disk(state)
    done = sum(1 for c in state.chapters if c.status == "done")
    total = len(state.chapters)
    current = next((c for c in state.chapters if c.id == state.current_chapter), None)
    current_title = current.title if current else "(unset)"
    return (
        f"{RESUME_CONTEXT_PREFIX}\n"
        f"用户已选择继续以下论文/报告项目。"
        f"除非用户另有说明，否则不要当作无关新任务。\n\n"
        f"项目：{state.title}（{state.project_id}）\n"
        f"进度：{done}/{total} 章已完成\n"
        f"当前章节：{state.current_chapter} {current_title}\n"
        f"输出：{WORKDIR}/{state.output_dir}/\n"
        f"源文档：{state.source_doc}\n\n"
        f"写章节时可 load_skill(thesis-writing)。"
        f"完整章节表请调用 project_status。"
    )


def inject_project_context(messages: list, *, checkpoint: bool = True) -> tuple[bool, str]:
    """Append opt-in project context to the active session."""
    msg = project_context_message()
    if not msg:
        return False, "未找到 .project/state.json，无法恢复论文项目。"

    if messages and is_resume_injection(messages[-1]):
        return False, "论文恢复上下文已是最后一条消息，无需重复注入。"

    messages.append({"role": "user", "content": msg})
    if checkpoint:
        append_checkpoint(messages)
    return True, "已注入论文项目上下文。请继续输入你的问题。"


def resume_banner() -> str | None:
    """Optional startup banner (informational only — never auto-injects)."""
    stats = session_stats()
    state = load_state()
    if not stats["exists"] and state is None:
        return None

    lines = ["--- 会话 ---", format_session_line()]
    if state and show_project_in_welcome():
        state = sync_chapters_from_disk(state)
        done = sum(1 for c in state.chapters if c.status == "done")
        total = len(state.chapters)
        lines.append(
            f"磁盘上的论文项目：{state.title}（{done}/{total} 章）"
            f" — 输入 /resume project 继续"
        )
    lines.append("---")
    return "\n".join(lines)


def _continue_flag() -> str:
    return "1" if continue_session_on_startup() else "0"


def format_resume_status(*, include_project: bool = True) -> str:
    """Claude Code-style /resume output: session + todos + optional project."""
    lines = [
        "恢复状态",
        "========",
        "",
        format_session_line(),
    ]
    stats = session_stats()
    if stats["exists"]:
        lines.append(
            f"路径：{stats['path']}（{stats['size_kb']} KB，"
            f"{stats['compact_boundaries']} 次压缩边界）"
        )

    todos_block = format_todos_for_cli(get_todos())
    if todos_block:
        lines.extend(["", "当前任务（todo_write）：", todos_block])
    else:
        lines.extend(["", "当前任务：（无）"])

    hint = format_transcript_hint()
    if hint:
        lines.extend(["", hint])

    if include_project:
        state = load_state()
        if state:
            state = sync_chapters_from_disk(state)
            lines.extend(
                [
                    "",
                    "可选论文项目（.project/state.json）：",
                    format_status(state, include_resume_hints=False),
                    "",
                    "继续写论文：/resume project",
                ]
            )

    lines.extend(
        [
            "",
            "恢复机制说明（OpenCode 模式，借鉴 Claude Code）：",
            "  - 默认每次启动都是全新对话（不自动续 session.jsonl）",
            "  - 想重启续对话：设 HARNESS_CONTINUE_SESSION=1 后重启",
            "  - 想续论文：/resume project（手动 opt-in）",
            "  - 清空对话（默认连章节表一起清）：/clear",
            "  - 只清对话、保留章节表：/clear session",
            f"  - 环境变量：HARNESS_CONTINUE_SESSION={_continue_flag()}"
            f" | HARNESS_AUTO_RESUME={auto_resume_mode()}（off | project）",
        ]
    )
    return "\n".join(lines)


def run_resume_command(args: str = "", *, messages: list | None = None) -> str:
    """Handle /resume [session|project|status]."""
    sub = (args or "").strip().lower()

    if sub in ("", "status", "session"):
        return format_resume_status(include_project=True)

    if sub in ("project", "thesis", "chapters"):
        if messages is None:
            return "请在 CLI 中执行 /resume project，将论文上下文注入当前会话。"
        _ok, message = inject_project_context(messages, checkpoint=True)
        return message

    return (
        f"未知的 /resume 选项：{args!r}\n"
        "用法：\n"
        "  /resume           查看会话 + 任务（+ 可选论文摘要）\n"
        "  /resume project   注入论文章节上下文（手动 opt-in）\n"
        "  /resume session   同 /resume"
    )


# Backward-compatible alias used in tests/docs
def resume_context_message() -> str | None:
    if not should_auto_inject_project_on_startup():
        return None
    return project_context_message()


def on_write_file(path: str) -> None:
    """Update project state when agent writes under output/."""
    from harness.project.state import get_or_create_state, save_state

    state = get_or_create_state()
    rel = str(path).replace("\\", "/")
    try:
        rel_path = str((WORKDIR / path).resolve().relative_to(WORKDIR)).replace("\\", "/")
    except Exception:
        rel_path = rel

    if not rel_path.startswith(state.output_dir.rstrip("/") + "/") and rel_path != state.output_dir:
        if not rel_path.startswith("output/"):
            return

    for chapter in state.chapters:
        if chapter.path == rel_path or rel_path.startswith(f"{state.output_dir}/{chapter.id}"):
            chapter.path = rel_path
            chapter.status = "done"
            state.current_chapter = chapter.id
            save_state(state)
            return

    if state.current_chapter:
        for chapter in state.chapters:
            if chapter.id == state.current_chapter:
                chapter.path = rel_path
                chapter.status = "done"
                save_state(state)
                return


def checkpoint_history(messages: list) -> None:
    if messages:
        append_checkpoint(messages)
