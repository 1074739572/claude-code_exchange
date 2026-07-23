"""Agent tool handlers for local RAG."""

from __future__ import annotations

import os

from harness.rag.ingest import ingest_path
from harness.rag.pipeline import build_index, rag_status_dict, search
from harness.rag.selection import get_active_sources


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


def format_rag_index_result(result: dict, index_result: dict) -> str:
    """Render a completed ingest/index operation without executing it again."""
    lines = [
        f"Indexed corpus: {result['root']}",
        f"Files: {len(result['files'])}, chunks: {result['total_chunks']}, "
        f"vectors: {index_result['vector_count']} "
        f"(parents: {index_result.get('parent_chunks', 0)}, "
        f"children: {index_result['indexed_chunks']})",
        f"Retrieval: {index_result['retrieval_mode']} "
        f"({index_result['embedding_backend']}: {index_result['embedding_model']})",
    ]
    for item in result["files"]:
        modality_summary = ", ".join(
            f"{name}={count}" for name, count in item.get("modalities", {}).items()
        )
        lines.append(
            f"  - {item['source']}: {item['chunks']} chunks "
            f"({item.get('parent_chunks', 0)} parent / "
            f"{item.get('child_chunks', 0)} child), {item['chars']} chars"
            f"{f'; {modality_summary}' if modality_summary else ''}"
        )
    for error in result.get("errors", []):
        lines.append(f"  - skipped {error['source']}: {error['error']}")
    return "\n".join(lines)


def run_rag_index(path: str = "") -> str:
    try:
        result = ingest_path(path or None)
        index_result = build_index([item["source"] for item in result["files"]])
        return format_rag_index_result(result, index_result)
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
        active_sources = None if source else get_active_sources()
        hits = search(
            query,
            top_k=max(1, min(top_k, 20)),
            source=source or None,
            sources=active_sources,
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
            modality = hit.get("modality", "text")
            modality_tag = "" if modality == "text" else f" [{modality}]"
            page_tag = f" [第{hit['page']}页]" if hit.get("page") else ""
            retrieval = hit.get("retrieval") or hit.get("rerank") or "search"
            child_tag = ""
            if hit.get("parent_id"):
                child_tag = f" [子块#{hit.get('child_index', 0)}]"
            lines.append(
                f"[{index}] {hit.get('source')} › {hit.get('heading_path')}"
                f"{caption}{modality_tag}{page_tag}{child_tag} "
                f"(score={hit.get('score')}, via={retrieval})"
            )
            lines.append(_truncate_hit_text(hit["text"], hit_limit))
            if hit.get("asset_uri"):
                lines.append(f"资产：{hit['asset_uri']}")
            if hit.get("parent_text"):
                lines.append("--- 父块（整节上下文）---")
                lines.append(hit["parent_text"])
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
            f"Embedding: {status['embedding_model']} ({status.get('embedding_backend', '')})",
            f"Retrieval: {status.get('retrieval_mode', 'hybrid')}, "
            f"rerank: {'on' if status.get('rerank_enabled') else 'off'}",
            f"Parents: {status.get('parent_count', 0)}, "
            f"children: {status.get('child_count', status.get('vector_count', 0))}, "
            f"vectors: {status.get('vector_store_count', status.get('vector_count', 0))}",
            f"Corpus: {status.get('corpus_root') or '(unknown)'}",
            "Sources:",
        ]
        lines.insert(3, f"PDF OCR: {status.get('pdf_ocr_mode', 'off')}")
        if status.get("vision_model"):
            vision = status.get("vision_stats", {})
            lines.insert(
                4,
                "Vision: "
                f"{status['vision_model']} (calls={vision.get('calls', 0)}, "
                f"budget_skips={vision.get('skipped_budget', 0)}, "
                f"failures={vision.get('failures', 0)})",
            )
        for name, meta in sources.items():
            modalities = ", ".join(
                f"{modality}={count}" for modality, count in meta.get("modalities", {}).items()
            )
            lines.append(
                f"  - {name}: {meta.get('chunks', 0)} chunks "
                f"({meta.get('parent_chunks', 0)} parent / "
                f"{meta.get('child_chunks', 0)} child), "
                f"{meta.get('chars', 0)} chars ({meta.get('suffix', '')})"
                f"{f'; {modalities}' if modalities else ''}"
            )
        return "\n".join(lines)
    except Exception as exc:
        return f"rag_status failed: {type(exc).__name__}: {exc}"
