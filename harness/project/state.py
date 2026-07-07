"""Persistent project state for long-running thesis/report workflows."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from harness.settings import PROJECT_DIR, WORKDIR

STATE_PATH = PROJECT_DIR / "state.json"
DEFAULT_OUTPUT_DIR = WORKDIR / "output"


@dataclass
class Chapter:
    id: str
    title: str
    status: str = "pending"  # pending | in_progress | done
    path: str | None = None
    notes: str = ""


@dataclass
class ProjectState:
    project_id: str = "thesis-rewrite"
    title: str = "研制报告改写"
    source_doc: str = "files/基于深度学习的对流云识别与外推算法研究_终稿_v1.docx"
    requirements_doc: str = "files/指标与交付要求.md"
    mapping_doc: str = "files/改写对照表.md"
    style_corpus: str = "files/样例"
    output_dir: str = "output"
    chapters: list[Chapter] = field(default_factory=list)
    current_chapter: str | None = None
    notes: str = ""
    updated_at: str = ""

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")


DEFAULT_CHAPTERS = [
    Chapter("01", "引言 / 编写目的"),
    Chapter("02", "研究目标"),
    Chapter("03", "数据与评价指标"),
    Chapter("04", "强对流识别（监测）模型"),
    Chapter("05", "强对流预警（外推）模型"),
    Chapter("06", "实验结果与分析"),
    Chapter("07", "总结与展望"),
    Chapter("08", "交付说明"),
]


def _chapter_from_dict(data: dict) -> Chapter:
    return Chapter(
        id=data["id"],
        title=data["title"],
        status=data.get("status", "pending"),
        path=data.get("path"),
        notes=data.get("notes", ""),
    )


def load_state() -> ProjectState | None:
    if not STATE_PATH.exists():
        return None
    data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    chapters = [_chapter_from_dict(c) for c in data.get("chapters", [])]
    return ProjectState(
        project_id=data.get("project_id", "thesis-rewrite"),
        title=data.get("title", "研制报告改写"),
        source_doc=data.get("source_doc", ""),
        requirements_doc=data.get("requirements_doc", "files/指标与交付要求.md"),
        mapping_doc=data.get("mapping_doc", "files/改写对照表.md"),
        style_corpus=data.get("style_corpus", "files/样例"),
        output_dir=data.get("output_dir", "output"),
        chapters=chapters,
        current_chapter=data.get("current_chapter"),
        notes=data.get("notes", ""),
        updated_at=data.get("updated_at", ""),
    )


def save_state(state: ProjectState) -> None:
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    state.touch()
    STATE_PATH.write_text(
        json.dumps(asdict(state), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def init_state(
    *,
    title: str = "研制报告改写",
    source_doc: str = "files/基于深度学习的对流云识别与外推算法研究_终稿_v1.docx",
    chapters: list[Chapter] | None = None,
) -> ProjectState:
    state = ProjectState(
        title=title,
        source_doc=source_doc,
        chapters=list(chapters or DEFAULT_CHAPTERS),
        current_chapter=(chapters or DEFAULT_CHAPTERS)[0].id,
    )
    save_state(state)
    return state


def get_or_create_state() -> ProjectState:
    state = load_state()
    if state is None:
        state = init_state()
    return state


def sync_chapters_from_disk(state: ProjectState) -> ProjectState:
    """Mark chapters done when matching output files exist."""
    out_root = WORKDIR / state.output_dir
    if not out_root.exists():
        return state
    for chapter in state.chapters:
        if chapter.path:
            candidate = WORKDIR / chapter.path
        else:
            candidate = out_root / f"{chapter.id}_{chapter.title.split()[0]}.md"
            for path in out_root.glob(f"{chapter.id}*.md"):
                candidate = path
                chapter.path = str(path.relative_to(WORKDIR)).replace("\\", "/")
                break
        if candidate.exists() and candidate.stat().st_size > 50:
            if chapter.status != "done":
                chapter.status = "done"
    save_state(state)
    return state


def format_status(state: ProjectState, *, include_resume_hints: bool = True) -> str:
    lines = [
        f"项目：{state.title}（{state.project_id}）",
        f"源文档：{state.source_doc}",
        f"输出目录：{state.output_dir}/",
        f"更新时间：{state.updated_at or '（从未）'}",
        "",
        "章节：",
    ]
    for ch in state.chapters:
        marker = {"done": "[x]", "in_progress": "[>]", "pending": "[ ]"}.get(ch.status, "[ ]")
        current = " ← 当前" if ch.id == state.current_chapter else ""
        path = f" → {ch.path}" if ch.path else ""
        lines.append(f"  {marker} {ch.id} {ch.title}{path}{current}")
    if state.notes:
        lines.extend(["", "备注：", state.notes])
    if include_resume_hints:
        lines.extend(
            [
                "",
                "继续本项目：/resume project",
                "重启会自动加载对话；论文上下文需手动 /resume project（默认不自动注入）。",
            ]
        )
    return "\n".join(lines)
