"""End-to-end RAG index and search pipeline."""

from __future__ import annotations

import threading

from harness.rag.chunking import merge_short_chunk_dicts
from harness.rag.config import RETRIEVAL_SCHEMA_VERSION, retrieval_settings
from harness.rag.embeddings.backends import get_embedding_backend
from harness.rag.ingest import load_chunks_for_source, load_manifest, save_manifest
from harness.rag.lexical import index_chunks as index_lexical
from harness.rag.lexical import rag_status_dict as lexical_status
from harness.rag.parents import attach_parent_context, is_searchable, reset_parent_cache
from harness.rag.retriever import hybrid_search
from harness.rag.stores.vector import get_vector_store, reset_vector_store

_lock = threading.Lock()
_embedder = None


def _get_embedder():
    global _embedder
    if _embedder is None:
        settings = retrieval_settings()
        _embedder = get_embedding_backend(settings.embedding)
    return _embedder


def reset_runtime() -> None:
    global _embedder
    with _lock:
        _embedder = None
        reset_vector_store()
        reset_parent_cache()


def _load_all_chunks(sources: list[str]) -> list[dict]:
    chunks: list[dict] = []
    for source in sources:
        chunks.extend(load_chunks_for_source(source))
    return merge_short_chunk_dicts(chunks)


def _searchable_chunks(chunks: list[dict]) -> list[dict]:
    return [chunk for chunk in chunks if is_searchable(chunk)]


def build_index(sources: list[str] | None = None) -> dict:
    """Build lexical + vector indexes from chunk JSONL artifacts."""
    with _lock:
        manifest = load_manifest()
        # A build is a snapshot of the manifest, not an incremental append.
        # This prevents deleted sources from surviving in BM25, Chroma, or
        # parent context artifacts.
        all_sources = list(manifest.get("sources", {}).keys())
        if not all_sources:
            raise RuntimeError("No chunks to index. Run rag_index first.")

        all_chunks = _load_all_chunks(all_sources)
        searchable = _searchable_chunks(all_chunks)
        lexical_result = index_lexical(all_sources)

        embedder = _get_embedder()
        store = get_vector_store()
        store.reset()

        if searchable:
            embeddings = embedder.embed_documents(
                [chunk["text"] for chunk in searchable]
            )
            vector_count = store.upsert_chunks(searchable, embeddings)
        else:
            vector_count = 0

        manifest = load_manifest()
        manifest["embedding_model"] = embedder.model_name
        manifest["embedding_backend"] = embedder.backend_id
        manifest["retrieval_mode"] = retrieval_settings().mode
        manifest["rerank_enabled"] = retrieval_settings().rerank
        manifest["retrieval_schema_version"] = RETRIEVAL_SCHEMA_VERSION
        manifest["vector_count"] = vector_count
        manifest["indexed_chunks"] = lexical_result.get("indexed_chunks", len(searchable))
        manifest["parent_count"] = lexical_result.get("parent_chunks", 0)
        manifest["child_count"] = len(searchable)
        save_manifest(manifest)

        return {
            "indexed_chunks": lexical_result.get("indexed_chunks", len(searchable)),
            "parent_chunks": lexical_result.get("parent_chunks", 0),
            "vector_count": vector_count,
            "sources": all_sources,
            "embedding_model": embedder.model_name,
            "embedding_backend": embedder.backend_id,
            "retrieval_mode": retrieval_settings().mode,
        }


def search(
    query: str,
    *,
    top_k: int = 8,
    source: str | None = None,
    sources: list[str] | None = None,
    chapter: str | None = None,
    include_captions: bool = True,
) -> list[dict]:
    embedder = _get_embedder()
    hits = hybrid_search(
        query,
        embedder=embedder,
        top_k=top_k,
        source=source,
        sources=sources,
        chapter=chapter,
        include_captions=include_captions,
    )
    return attach_parent_context(hits)


def rag_status_dict() -> dict:
    status = lexical_status()
    try:
        status["vector_store_count"] = get_vector_store().count()
    except Exception:
        status["vector_store_count"] = 0
    settings = retrieval_settings()
    status["retrieval_mode"] = settings.mode
    status["rerank_enabled"] = settings.rerank
    status["embedding"] = settings.embedding
    manifest = load_manifest()
    status["vision_model"] = manifest.get("vision_model")
    status["vision_stats"] = manifest.get("vision_stats", {})
    status["pdf_ocr_mode"] = manifest.get("pdf_ocr_mode", "off")
    return status
