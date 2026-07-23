"""Local BM25 lexical index — no model download required."""

from __future__ import annotations

import json
import math
import re
import threading
from functools import lru_cache
from pathlib import Path

from harness.rag.config import INDEX_DIR, MANIFEST_PATH
from harness.rag.ingest import load_chunks_for_source, load_manifest, save_manifest
from harness.rag.parents import (
    is_searchable,
    replace_parents,
    split_chunks,
)

_lock = threading.Lock()
_corpus: list[dict] = []
_idf: dict[str, float] = {}
_doc_freq: dict[str, int] = {}
_avg_dl = 1.0
_k1 = 1.5
_b = 0.75

CORPUS_PATH = INDEX_DIR / "corpus.json"
TOKEN_RE = re.compile(r"[\u4e00-\u9fff]+|[a-z0-9_]+(?:[.-][a-z0-9_]+)*", re.IGNORECASE)
CHINESE_RE = re.compile(r"^[\u4e00-\u9fff]+$")


@lru_cache(maxsize=1)
def _jieba_cut():
    try:
        import jieba
    except ImportError:
        return None
    return jieba.lcut


def tokenize(text: str) -> list[str]:
    """Tokenize mixed Chinese/Latin text for BM25 and deterministic embeddings.

    Chinese terms use jieba when installed and always include character bigrams,
    which keeps technical names and short query fragments recallable.
    """
    tokens: list[str] = []
    cutter = _jieba_cut()
    for run in TOKEN_RE.findall(text.lower()):
        if not CHINESE_RE.match(run):
            tokens.append(run)
            continue
        candidates: list[str] = []
        if cutter is not None:
            candidates.extend(part.strip() for part in cutter(run) if part.strip())
        if len(run) == 1:
            candidates.append(run)
        else:
            candidates.extend(run[index : index + 2] for index in range(len(run) - 1))
            if len(run) <= 8:
                candidates.append(run)
        seen: set[str] = set()
        for candidate in candidates:
            if candidate and candidate not in seen:
                seen.add(candidate)
                tokens.append(candidate)
    return tokens


def _build_index(chunks: list[dict]) -> None:
    global _corpus, _idf, _doc_freq, _avg_dl
    _corpus = chunks
    _doc_freq = {}
    doc_lens = []

    for chunk in chunks:
        tokens = tokenize(chunk["text"])
        doc_lens.append(len(tokens) or 1)
        seen = set(tokens)
        for token in seen:
            _doc_freq[token] = _doc_freq.get(token, 0) + 1

    n_docs = max(len(chunks), 1)
    _avg_dl = sum(doc_lens) / n_docs
    _idf = {
        token: math.log(1 + (n_docs - freq + 0.5) / (freq + 0.5))
        for token, freq in _doc_freq.items()
    }


def _score(query_tokens: list[str], chunk: dict) -> float:
    doc_tokens = tokenize(chunk["text"])
    if not doc_tokens:
        return 0.0
    dl = len(doc_tokens)
    tf_map: dict[str, int] = {}
    for token in doc_tokens:
        tf_map[token] = tf_map.get(token, 0) + 1

    score = 0.0
    for token in query_tokens:
        if token not in tf_map:
            continue
        tf = tf_map[token]
        idf = _idf.get(token, 0.0)
        denom = tf + _k1 * (1 - _b + _b * dl / _avg_dl)
        score += idf * (tf * (_k1 + 1)) / (denom or 1)
    return score


def _persist(chunks: list[dict]) -> None:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    CORPUS_PATH.write_text(json.dumps(chunks, ensure_ascii=False), encoding="utf-8")


def _ensure_loaded() -> None:
    global _corpus
    if _corpus:
        return
    if not CORPUS_PATH.exists():
        return
    _corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    _build_index(_corpus)


def index_chunks(sources: list[str] | None = None) -> dict:
    with _lock:
        manifest = load_manifest()
        all_sources = sources or list(manifest.get("sources", {}).keys())
        if not all_sources:
            raise RuntimeError("No chunks to index. Run rag_index first.")

        # Rebuild from the active manifest snapshot. Incremental merging kept
        # deleted corpus files searchable indefinitely.
        merged: list[dict] = []
        for source in all_sources:
            merged.extend(load_chunks_for_source(source))

        parents, searchable = split_chunks(merged)
        replace_parents(parents)

        _build_index(searchable)
        _persist(searchable)

        manifest["embedding_model"] = "bm25-lexical"
        manifest["embedding_backend"] = "bm25"
        manifest["vector_count"] = len(searchable)
        manifest["parent_count"] = len(parents)
        manifest["child_count"] = len(searchable)
        save_manifest(manifest)
        return {
            "indexed_chunks": len(searchable),
            "parent_chunks": len(parents),
            "sources": all_sources,
        }


def search_chunks(
    query: str,
    *,
    top_k: int = 8,
    source: str | None = None,
    sources: list[str] | None = None,
    chapter: str | None = None,
    include_captions: bool = True,
) -> list[dict]:
    with _lock:
        _ensure_loaded()
        if not _corpus:
            raise RuntimeError("RAG index is empty. Run rag_index first.")

        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        allowed = set(sources or [])
        if source:
            allowed = {source}

        scored = []
        for chunk in _corpus:
            if not is_searchable(chunk):
                continue
            chunk_source = chunk.get("source", "")
            if allowed and chunk_source not in allowed:
                continue
            if chapter and chunk.get("chapter") != chapter:
                continue
            if not include_captions and chunk.get("is_caption"):
                continue
            score = _score(query_tokens, chunk)
            if score <= 0:
                path_bonus = tokenize(
                    f"{chunk.get('heading_path', '')} {chunk.get('chapter', '')} {chunk.get('section', '')}"
                )
                overlap = len(set(query_tokens) & set(path_bonus))
                if overlap:
                    score = overlap * 0.5
            if score <= 0:
                continue
            scored.append({**chunk, "score": round(score, 4)})

        scored.sort(key=lambda item: item["score"], reverse=True)
        hits = []
        for item in scored[:top_k]:
            hits.append(
                {
                    "id": item.get("id", ""),
                    "text": item["text"],
                    "score": item["score"],
                    "source": item.get("source", ""),
                    "heading_path": item.get("heading_path", ""),
                    "chapter": item.get("chapter", ""),
                    "section": item.get("section", ""),
                    "style": item.get("style", ""),
                    "char_count": item.get("char_count", 0),
                    "is_caption": bool(item.get("is_caption")),
                    "chunk_index": item.get("chunk_index", 0),
                    "level": item.get("level", "child"),
                    "parent_id": item.get("parent_id"),
                    "child_index": item.get("child_index", 0),
                    "modality": item.get("modality", "text"),
                    "asset_uri": item.get("asset_uri", ""),
                    "page": item.get("page", 0),
                }
            )
        return hits


def rag_status_dict() -> dict:
    manifest = load_manifest()
    _ensure_loaded()
    return {
        "embedding_model": manifest.get("embedding_model") or "bm25-lexical",
        "embedding_backend": manifest.get("embedding_backend", "bm25"),
        "vector_count": len(_corpus),
        "parent_count": manifest.get("parent_count", 0),
        "child_count": manifest.get("child_count", len(_corpus)),
        "corpus_root": manifest.get("corpus_root"),
        "sources": manifest.get("sources", {}),
        "manifest_path": str(MANIFEST_PATH),
        "index_path": str(INDEX_DIR),
    }
