"""Hybrid retrieval: BM25 + vector with reciprocal rank fusion."""

from __future__ import annotations

import os

from harness.rag.lexical import search_chunks as bm25_search
from harness.rag.rerank import rerank_hits
from harness.rag.stores.vector import get_vector_store


def retrieval_mode() -> str:
    return os.getenv("HARNESS_RAG_MODE", "hybrid").strip().lower()


def fetch_k(default: int = 20) -> int:
    raw = os.getenv("HARNESS_RAG_FETCH_K", str(default)).strip()
    try:
        return max(5, min(int(raw), 50))
    except ValueError:
        return default


def rrf_k() -> int:
    raw = os.getenv("HARNESS_RAG_RRF_K", "60").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 60


def reciprocal_rank_fusion(
    ranked_lists: list[list[dict]],
    *,
    k: int | None = None,
    id_key: str = "id",
) -> list[dict]:
    """Merge multiple ranked lists with RRF."""
    constant = k or rrf_k()
    fused_scores: dict[str, float] = {}
    by_id: dict[str, dict] = {}

    for ranked in ranked_lists:
        for rank, hit in enumerate(ranked, start=1):
            chunk_id = hit.get(id_key) or _fallback_id(hit)
            fused_scores[chunk_id] = fused_scores.get(chunk_id, 0.0) + 1.0 / (
                constant + rank
            )
            if chunk_id not in by_id:
                by_id[chunk_id] = hit

    ordered = sorted(fused_scores.items(), key=lambda item: item[1], reverse=True)
    merged: list[dict] = []
    for chunk_id, score in ordered:
        hit = {**by_id[chunk_id], "score": round(score, 4), "retrieval": "hybrid"}
        merged.append(hit)
    return merged


def _fallback_id(hit: dict) -> str:
    return (
        f"{hit.get('source', '')}|{hit.get('heading_path', '')}|"
        f"{hit.get('chunk_index', hit.get('char_count', 0))}"
    )


def _annotate(hits: list[dict], retrieval: str) -> list[dict]:
    return [{**hit, "retrieval": retrieval} for hit in hits]


def hybrid_search(
    query: str,
    *,
    embedder,
    top_k: int = 8,
    source: str | None = None,
    sources: list[str] | None = None,
    chapter: str | None = None,
    include_captions: bool = True,
) -> list[dict]:
    mode = retrieval_mode()
    candidate_k = max(fetch_k(), top_k * 2)
    filters = {
        "source": source,
        "sources": sources,
        "chapter": chapter,
        "include_captions": include_captions,
    }

    if mode == "bm25":
        hits = bm25_search(query, top_k=candidate_k, **filters)
        return rerank_hits(query, _annotate(hits, "bm25"), top_k=top_k)

    if mode == "vector":
        query_vec = embedder.embed_query(query)
        hits = get_vector_store().search(query_vec, top_k=candidate_k, **filters)
        return rerank_hits(query, hits, top_k=top_k)

    bm25_hits = bm25_search(query, top_k=candidate_k, **filters)
    query_vec = embedder.embed_query(query)
    vector_hits = get_vector_store().search(query_vec, top_k=candidate_k, **filters)

    for hit in bm25_hits:
        hit.setdefault("id", _fallback_id(hit))
    for hit in vector_hits:
        hit.setdefault("id", hit.get("id") or _fallback_id(hit))

    fused = reciprocal_rank_fusion(
        [_annotate(bm25_hits, "bm25"), _annotate(vector_hits, "vector")]
    )
    return rerank_hits(query, fused, top_k=top_k)
