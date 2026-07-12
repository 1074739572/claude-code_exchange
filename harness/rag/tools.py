"""Agent tool handlers for local RAG."""

from __future__ import annotations

import os

from harness.rag.ingest import ingest_path
from harness.rag.lexical import index_chunks, rag_status_dict, search_chunks


def _hit_char_limit() -> int:
    raw = os.getenv("HARNESS_RAG_HIT_CHARS", "1500").strip()
    try:
        return max(400, int(raw))
    except ValueError:
        return 1500


def _truncate_hit_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20] + "\n…[truncated]"


def run_rag_index(path: str = "") -> str:
    try:
        result = ingest_path(path or None)
        index_result = index_chunks([item["source"] for item in result["files"]])
        lines = [
            f"Indexed corpus: {result['root']}",
            f"Files: {len(result['files'])}, chunks: {result['total_chunks']}, "
            f"vectors: {index_result['indexed_chunks']}",
        ]
        for item in result["files"]:
            lines.append(
                f"  - {item['source']}: {item['chunks']} chunks, {item['chars']} chars"
            )
        return "\n".join(lines)
    except Exception as exc:
        return f"rag_index failed: {type(exc).__name__}: {exc}"


def run_rag_search(
    query: str,
    top_k: int = 8,
    source: str = "",
    chapter: str = "",
    include_captions: bool = True,
) -> str:
    try:
        hits = search_chunks(
            query,
            top_k=max(1, min(top_k, 20)),
            source=source or None,
            chapter=chapter or None,
            include_captions=include_captions,
        )
        if not hits:
            return "No matching chunks found."
        hit_limit = _hit_char_limit()
        lines = [
            "【格式/内容参考】请学结构和表述方式，不要照抄原文。",
            "",
        ]
        for index, hit in enumerate(hits, start=1):
            caption = " [图注]" if hit.get("is_caption") else ""
            lines.append(
                f"[{index}] {hit.get('source')} › {hit.get('heading_path')}{caption} "
                f"(score={hit.get('score')})"
            )
            lines.append(_truncate_hit_text(hit["text"], hit_limit))
            lines.append("")
        return "\n".join(lines).strip()
    except Exception as exc:
        return f"rag_search failed: {type(exc).__name__}: {exc}"


def run_rag_status() -> str:
    try:
        status = rag_status_dict()
        sources = status.get("sources") or {}
        if not sources:
            return (
                "RAG index is empty.\n"
                "Run rag_index on files/样例 (or your corpus path) first."
            )
        lines = [
            f"Embedding: {status['embedding_model']}",
            f"Vectors: {status['vector_count']}",
            f"Corpus: {status.get('corpus_root') or '(unknown)'}",
            "Sources:",
        ]
        for name, meta in sources.items():
            lines.append(
                f"  - {name}: {meta.get('chunks', 0)} chunks, "
                f"{meta.get('chars', 0)} chars ({meta.get('suffix', '')})"
            )
        return "\n".join(lines)
    except Exception as exc:
        return f"rag_status failed: {type(exc).__name__}: {exc}"
