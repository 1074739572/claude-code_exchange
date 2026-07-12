"""Auto-index local corpus when writing workflows start."""

from __future__ import annotations

from pathlib import Path

from harness.rag.ingest import ingest_path, resolve_path
from harness.rag.lexical import index_chunks, rag_status_dict
from harness.rag.tools import run_rag_index
from harness.settings import PACKAGE_ROOT, WORKDIR

DEFAULT_INDEX_PATH = "files"


def index_is_empty() -> bool:
    status = rag_status_dict()
    return not (status.get("sources") or {})


def corpus_root_exists(path: str = DEFAULT_INDEX_PATH) -> bool:
    try:
        root = resolve_path(path)
    except Exception:
        return False
    return root.exists()


def ensure_rag_indexed(path: str = DEFAULT_INDEX_PATH) -> dict:
    """Build or refresh the local index when corpus exists.

    Returns a dict with keys: ok, action, message, path, chunks, sources.
    """
    try:
        root = resolve_path(path)
    except Exception as e:
        return {
            "ok": False,
            "action": "error",
            "message": str(e),
            "path": path,
            "chunks": 0,
            "sources": 0,
        }

    if not root.exists():
        return {
            "ok": False,
            "action": "missing",
            "message": (
                f"Corpus not found: {root}\n"
                "Put reference .md/.txt/.docx under cwd/files/ "
                "(e.g. files/样例/, files/指标与交付要求.md), then retry."
            ),
            "path": str(root),
            "chunks": 0,
            "sources": 0,
        }

    was_empty = index_is_empty()
    try:
        result = ingest_path(path)
        index_result = index_chunks([item["source"] for item in result["files"]])
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "action": "empty",
            "message": str(exc),
            "path": str(root),
            "chunks": 0,
            "sources": 0,
        }
    except Exception as exc:
        return {
            "ok": False,
            "action": "error",
            "message": f"{type(exc).__name__}: {exc}",
            "path": str(root),
            "chunks": 0,
            "sources": 0,
        }

    action = "indexed" if was_empty else "refreshed"
    return {
        "ok": True,
        "action": action,
        "message": run_rag_index(path),
        "path": str(root),
        "chunks": index_result.get("indexed_chunks", result["total_chunks"]),
        "sources": len(result["files"]),
    }


def bootstrap_message(result: dict) -> str:
    if not result.get("ok"):
        return (
            "[RAG bootstrap]\n"
            f"{result.get('message', 'index failed')}\n"
            "Writing mode needs files under cwd/files/. "
            "Add samples then run rag_index path=\"files\" or reload the task."
        )
    action = result.get("action", "indexed")
    return (
        f"[RAG bootstrap — {action}]\n"
        f"Corpus: {result.get('path')}\n"
        f"Sources: {result.get('sources', 0)}, chunks: {result.get('chunks', 0)}\n"
        "Use rag_search before each output/*.md section. "
        "Do not read_file whole reference docx files."
    )


def suggested_corpus_dirs() -> list[Path]:
    candidates = [
        WORKDIR / "files",
        PACKAGE_ROOT / "files",
        WORKDIR / "files" / "样例",
        PACKAGE_ROOT / "files" / "样例",
    ]
    seen: set[str] = set()
    out: list[Path] = []
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.exists():
            out.append(path)
    return out
