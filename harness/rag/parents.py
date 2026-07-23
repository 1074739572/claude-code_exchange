"""Parent chunk lookup and child-hit context expansion."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from harness.rag.config import INDEX_DIR

PARENTS_PATH = INDEX_DIR / "parents.json"

_lock = threading.Lock()
_parent_map: dict[str, dict] = {}


def is_parent(chunk: dict) -> bool:
    return chunk.get("level") == "parent"


def is_searchable(chunk: dict) -> bool:
    """Chunks indexed and searched: children, captions, and legacy flat chunks."""
    level = chunk.get("level")
    if level == "parent":
        return False
    return True


def split_chunks(chunks: list[dict]) -> tuple[list[dict], list[dict]]:
    parents = [chunk for chunk in chunks if is_parent(chunk)]
    searchable = [chunk for chunk in chunks if is_searchable(chunk)]
    return parents, searchable


def build_parent_map(chunks: list[dict]) -> dict[str, dict]:
    return {chunk["id"]: chunk for chunk in chunks if is_parent(chunk)}


def persist_parents(parents: list[dict]) -> None:
    global _parent_map
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    merged = load_parent_map()
    merged.update(build_parent_map(parents))
    PARENTS_PATH.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with _lock:
        _parent_map = merged


def replace_parents(parents: list[dict]) -> None:
    """Atomically replace parent context with the active index snapshot."""
    global _parent_map
    payload = build_parent_map(parents)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    PARENTS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with _lock:
        _parent_map = payload


def remove_sources_from_parents(sources: set[str]) -> None:
    global _parent_map
    if not sources:
        return
    merged = load_parent_map()
    merged = {
        chunk_id: chunk
        for chunk_id, chunk in merged.items()
        if chunk.get("source") not in sources
    }
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    PARENTS_PATH.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with _lock:
        _parent_map = merged


def load_parent_map() -> dict[str, dict]:
    global _parent_map
    with _lock:
        if _parent_map:
            return dict(_parent_map)
    if not PARENTS_PATH.exists():
        return {}
    data = json.loads(PARENTS_PATH.read_text(encoding="utf-8"))
    with _lock:
        _parent_map = data
    return dict(data)


def reset_parent_cache() -> None:
    global _parent_map
    with _lock:
        _parent_map = {}


def _parent_char_limit() -> int:
    raw = os.getenv("HARNESS_RAG_PARENT_CHARS", "4000").strip()
    try:
        return max(800, int(raw))
    except ValueError:
        return 4000


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20] + "\n…[parent truncated]"


def attach_parent_context(hits: list[dict]) -> list[dict]:
    parents = load_parent_map()
    if not parents:
        return hits

    enriched: list[dict] = []
    for hit in hits:
        parent_id = hit.get("parent_id")
        if not parent_id:
            enriched.append(hit)
            continue
        parent = parents.get(parent_id)
        if not parent:
            enriched.append(hit)
            continue
        limit = _parent_char_limit()
        enriched.append(
            {
                **hit,
                "parent_id": parent_id,
                "parent_heading_path": parent.get("heading_path", ""),
                "parent_text": _truncate(parent.get("text", ""), limit),
                "parent_char_count": parent.get("char_count", 0),
            }
        )
    return enriched
