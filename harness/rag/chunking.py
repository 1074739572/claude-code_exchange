"""Document chunk representation and splitting helpers."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field

from harness.rag.config import (
    MAX_CHUNK_CHARS,
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
        }


def _make_id(source: str, heading_path: str, chunk_index: int, text: str) -> str:
    digest = hashlib.sha1(f"{source}|{heading_path}|{chunk_index}|{text[:64]}".encode()).hexdigest()
    return digest[:16]


def _heading_path(stack: list[tuple[int, str]]) -> str:
    return " > ".join(title for _, title in stack) if stack else "(root)"


def _chapter_section(stack: list[tuple[int, str]]) -> tuple[str, str]:
    if not stack:
        return "", ""
    chapter = stack[0][1]
    section = stack[1][1] if len(stack) > 1 else ""
    return chapter, section


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

    for piece in _split_long_text(merged):
        if len(piece) < MIN_CHUNK_CHARS and not is_caption:
            continue
        display = piece
        if heading and heading != "(root)":
            display = f"{heading}\n\n{piece}"
        chunks.append(
            Chunk(
                id=_make_id(source, heading, index, piece),
                text=display,
                source=source,
                heading_path=heading,
                chapter=chapter,
                section=section,
                style=style,
                char_count=len(piece),
                is_caption=is_caption,
                chunk_index=index,
            )
        )
        index += 1
    return chunks, index


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
    return chunks


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
    return chunks
