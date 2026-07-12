"""Document chunk representation and splitting helpers."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass

from harness.rag.config import (
    MAX_CHUNK_CHARS,
    MAX_PARENT_CHARS,
    MIN_CHUNK_CHARS,
    OVERLAP_CHARS,
    TARGET_CHUNK_CHARS,
)

HEADING_STYLE_LEVELS = {
    "Heading 1": 1,
    "Heading 2": 2,
    "Heading 3": 3,
    "Heading 4": 4,
    "Heading 5": 5,
    "Heading 6": 6,
    "Title": 1,
}

MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")

LEVEL_PARENT = "parent"
LEVEL_CHILD = "child"


@dataclass
class Chunk:
    id: str
    text: str
    source: str
    heading_path: str
    chapter: str
    section: str
    style: str
    char_count: int
    is_caption: bool = False
    chunk_index: int = 0
    level: str = LEVEL_CHILD
    parent_id: str | None = None
    child_index: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    def to_metadata(self) -> dict:
        return {
            "source": self.source,
            "heading_path": self.heading_path,
            "chapter": self.chapter,
            "section": self.section,
            "style": self.style,
            "char_count": self.char_count,
            "is_caption": self.is_caption,
            "chunk_index": self.chunk_index,
            "level": self.level,
            "parent_id": self.parent_id or "",
            "child_index": self.child_index,
        }


def _make_id(source: str, heading_path: str, chunk_index: int, text: str) -> str:
    digest = hashlib.sha1(
        f"{source}|{heading_path}|{chunk_index}|{text[:64]}".encode()
    ).hexdigest()
    return digest[:16]


def _make_parent_id(source: str, heading_path: str) -> str:
    digest = hashlib.sha1(f"parent|{source}|{heading_path}".encode()).hexdigest()
    return f"p_{digest[:14]}"


def _heading_path(stack: list[tuple[int, str]]) -> str:
    return " > ".join(title for _, title in stack) if stack else "(root)"


def _chapter_section(stack: list[tuple[int, str]]) -> tuple[str, str]:
    if not stack:
        return "", ""
    chapter = stack[0][1]
    section = stack[1][1] if len(stack) > 1 else ""
    return chapter, section


def _format_display(heading: str, body: str) -> str:
    if heading and heading != "(root)":
        return f"{heading}\n\n{body}"
    return body


def _split_long_text(text: str) -> list[str]:
    if len(text) <= MAX_CHUNK_CHARS:
        return [text] if text.strip() else []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        paragraphs = [text]

    pieces: list[str] = []
    current = ""
    for para in paragraphs:
        if len(para) > MAX_CHUNK_CHARS:
            if current:
                pieces.append(current)
                current = ""
            start = 0
            while start < len(para):
                end = min(start + TARGET_CHUNK_CHARS, len(para))
                pieces.append(para[start:end])
                if end >= len(para):
                    break
                start = max(end - OVERLAP_CHARS, start + 1)
            continue
        candidate = f"{current}\n\n{para}".strip() if current else para
        if len(candidate) <= TARGET_CHUNK_CHARS:
            current = candidate
        else:
            if current:
                pieces.append(current)
            current = para
    if current:
        pieces.append(current)
    return pieces


def _truncate_parent_body(body: str) -> str:
    if len(body) <= MAX_PARENT_CHARS:
        return body
    return body[: MAX_PARENT_CHARS - 20] + "\n…[section truncated]"


def _emit_chunks(
    *,
    source: str,
    stack: list[tuple[int, str]],
    body: str,
    style: str,
    is_caption: bool,
    start_index: int,
) -> tuple[list[Chunk], int]:
    heading = _heading_path(stack)
    chapter, section = _chapter_section(stack)
    chunks: list[Chunk] = []
    index = start_index

    merged = body.strip()
    if not merged:
        return chunks, index
    if len(merged) < MIN_CHUNK_CHARS and not is_caption:
        return chunks, index

    if is_caption:
        display = _format_display(heading, merged)
        chunks.append(
            Chunk(
                id=_make_id(source, heading, index, merged),
                text=display,
                source=source,
                heading_path=heading,
                chapter=chapter,
                section=section,
                style=style,
                char_count=len(merged),
                is_caption=True,
                chunk_index=index,
                level=LEVEL_CHILD,
                parent_id=None,
                child_index=0,
            )
        )
        return chunks, index + 1

    parent_id = _make_parent_id(source, heading)
    parent_body = _truncate_parent_body(merged)
    parent_display = _format_display(heading, parent_body)
    chunks.append(
        Chunk(
            id=parent_id,
            text=parent_display,
            source=source,
            heading_path=heading,
            chapter=chapter,
            section=section,
            style=style,
            char_count=len(parent_body),
            is_caption=False,
            chunk_index=index,
            level=LEVEL_PARENT,
            parent_id=None,
            child_index=-1,
        )
    )

    child_pieces = _split_long_text(merged)
    child_index = 0
    for piece in child_pieces:
        if len(piece) < MIN_CHUNK_CHARS:
            continue
        display = _format_display(heading, piece)
        chunks.append(
            Chunk(
                id=_make_id(source, heading, index + child_index, piece),
                text=display,
                source=source,
                heading_path=heading,
                chapter=chapter,
                section=section,
                style=style,
                char_count=len(piece),
                is_caption=False,
                chunk_index=index + child_index,
                level=LEVEL_CHILD,
                parent_id=parent_id,
                child_index=child_index,
            )
        )
        child_index += 1

    if child_index == 0:
        display = _format_display(heading, merged)
        chunks.append(
            Chunk(
                id=_make_id(source, heading, index, merged),
                text=display,
                source=source,
                heading_path=heading,
                chapter=chapter,
                section=section,
                style=style,
                char_count=len(merged),
                is_caption=False,
                chunk_index=index,
                level=LEVEL_CHILD,
                parent_id=parent_id,
                child_index=0,
            )
        )
        child_index = 1

    return chunks, index + child_index


def chunk_markdown(source: str, text: str) -> list[Chunk]:
    stack: list[tuple[int, str]] = []
    body_lines: list[str] = []
    chunks: list[Chunk] = []
    chunk_index = 0

    def flush_body() -> None:
        nonlocal chunk_index, body_lines
        if not body_lines:
            return
        new_chunks, chunk_index = _emit_chunks(
            source=source,
            stack=stack,
            body="\n".join(body_lines),
            style="markdown",
            is_caption=False,
            start_index=chunk_index,
        )
        chunks.extend(new_chunks)
        body_lines = []

    for line in text.splitlines():
        match = MD_HEADING_RE.match(line.strip())
        if match:
            flush_body()
            level = len(match.group(1))
            title = match.group(2).strip()
            stack = [(lvl, name) for lvl, name in stack if lvl < level]
            stack.append((level, title))
            continue
        if line.strip():
            body_lines.append(line.rstrip())
    flush_body()
    return merge_short_chunks(chunks)


def chunk_docx(source: str, path) -> list[Chunk]:
    from docx import Document

    doc = Document(path)
    stack: list[tuple[int, str]] = []
    body_lines: list[str] = []
    chunks: list[Chunk] = []
    chunk_index = 0

    def flush_body(style: str = "Body Text") -> None:
        nonlocal chunk_index, body_lines
        if not body_lines:
            return
        new_chunks, chunk_index = _emit_chunks(
            source=source,
            stack=stack,
            body="\n".join(body_lines),
            style=style,
            is_caption=False,
            start_index=chunk_index,
        )
        chunks.extend(new_chunks)
        body_lines = []

    skip_prefixes = ("编 号", "版 本", "文档控制")

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        if any(text.startswith(prefix) for prefix in skip_prefixes):
            continue

        style = para.style.name if para.style else "Normal"
        if style in HEADING_STYLE_LEVELS:
            flush_body()
            level = HEADING_STYLE_LEVELS[style]
            stack = [(lvl, name) for lvl, name in stack if lvl < level]
            stack.append((level, text))
            continue

        if style == "Caption":
            flush_body()
            caption_chunks, chunk_index = _emit_chunks(
                source=source,
                stack=stack,
                body=text,
                style="Caption",
                is_caption=True,
                start_index=chunk_index,
            )
            chunks.extend(caption_chunks)
            continue

        if style in ("Body Text", "Normal", "List Paragraph"):
            body_lines.append(text)
            continue

        if style in ("Header", "Footer"):
            continue

        body_lines.append(text)

    flush_body()
    return merge_short_chunks(chunks)


def merge_short_chunks(chunks: list[Chunk]) -> list[Chunk]:
    """Merge adjacent short child chunks under the same parent."""
    if not chunks:
        return chunks

    parents = [chunk for chunk in chunks if chunk.level == LEVEL_PARENT]
    children = [chunk for chunk in chunks if chunk.level != LEVEL_PARENT]
    merged_children = _merge_short_children(children)
    return parents + merged_children


def _merge_short_children(children: list[Chunk]) -> list[Chunk]:
    if not children:
        return children

    merged: list[Chunk] = []
    buffer: Chunk | None = None

    def flush_buffer() -> None:
        nonlocal buffer
        if buffer is not None:
            merged.append(buffer)
            buffer = None

    for chunk in children:
        if chunk.is_caption or not chunk.parent_id:
            flush_buffer()
            merged.append(chunk)
            continue

        if buffer is None:
            if len(chunk.text) < MIN_CHUNK_CHARS:
                buffer = chunk
            else:
                merged.append(chunk)
            continue

        same_parent = (
            buffer.parent_id == chunk.parent_id
            and buffer.heading_path == chunk.heading_path
            and buffer.source == chunk.source
        )
        combined_len = len(buffer.text) + len(chunk.text)
        if same_parent and combined_len <= MAX_CHUNK_CHARS:
            buffer = _join_chunks(buffer, chunk)
            if len(buffer.text) >= MIN_CHUNK_CHARS:
                flush_buffer()
            continue

        flush_buffer()
        if len(chunk.text) < MIN_CHUNK_CHARS:
            buffer = chunk
        else:
            merged.append(chunk)

    flush_buffer()
    return merged


def merge_short_chunk_dicts(chunks: list[dict]) -> list[dict]:
    if not chunks:
        return chunks
    objects = [
        Chunk(
            id=item["id"],
            text=item["text"],
            source=item["source"],
            heading_path=item["heading_path"],
            chapter=item["chapter"],
            section=item["section"],
            style=item["style"],
            char_count=item["char_count"],
            is_caption=bool(item.get("is_caption")),
            chunk_index=int(item.get("chunk_index", 0)),
            level=item.get("level", LEVEL_CHILD),
            parent_id=item.get("parent_id"),
            child_index=int(item.get("child_index", 0)),
        )
        for item in chunks
    ]
    return [chunk.to_dict() for chunk in merge_short_chunks(objects)]


def _join_chunks(left: Chunk, right: Chunk) -> Chunk:
    body_left = left.text.split("\n\n", 1)[-1] if "\n\n" in left.text else left.text
    body_right = right.text.split("\n\n", 1)[-1] if "\n\n" in right.text else right.text
    combined_body = f"{body_left}\n\n{body_right}".strip()
    heading = left.heading_path
    display = _format_display(heading, combined_body)
    return Chunk(
        id=left.id,
        text=display,
        source=left.source,
        heading_path=left.heading_path,
        chapter=left.chapter,
        section=left.section,
        style=left.style,
        char_count=len(combined_body),
        is_caption=False,
        chunk_index=left.chunk_index,
        level=LEVEL_CHILD,
        parent_id=left.parent_id,
        child_index=left.child_index,
    )
