"""Resume helpers: banner, context injection, write_file hook."""

from __future__ import annotations

from harness.project.session import load_history
from harness.project.session_store import append_checkpoint
from harness.project.state import (
    format_status,
    get_or_create_state,
    load_state,
    save_state,
    sync_chapters_from_disk,
)
from harness.settings import WORKDIR


def resume_banner() -> str | None:
    state = load_state()
    if state is None and load_history() is None:
        return None
    state = get_or_create_state()
    state = sync_chapters_from_disk(state)
    lines = ["--- Resume ---", format_status(state), "---"]
    return "\n".join(lines)


def resume_context_message() -> str | None:
    """Short message injected into agent context on startup when resuming."""
    state = load_state()
    history = load_history()
    if state is None and not history:
        return None
    state = get_or_create_state()
    state = sync_chapters_from_disk(state)
    done = sum(1 for c in state.chapters if c.status == "done")
    total = len(state.chapters)
    current = next((c for c in state.chapters if c.id == state.current_chapter), None)
    current_title = current.title if current else "(unset)"
    return (
        f"[Session resumed] Thesis project '{state.title}': "
        f"{done}/{total} chapters done. "
        f"Continue with chapter {state.current_chapter} {current_title}. "
        f"Output dir: {state.output_dir}/. "
        f"load_skill(thesis-writing) and proceed without re-planning from scratch."
    )


def on_write_file(path: str) -> None:
    """Update project state when agent writes under output/."""
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

    # Unknown file under output/: attach to current chapter if in progress
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
