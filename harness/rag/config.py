"""RAG paths and default parameters."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from harness.settings import PACKAGE_ROOT, WORKDIR

RAG_DIR = WORKDIR / ".rag"
CHUNKS_DIR = RAG_DIR / "chunks"
INDEX_DIR = RAG_DIR / "index"
CHROMA_DIR = RAG_DIR / "chroma"
MANIFEST_PATH = RAG_DIR / "manifest.json"
DEFAULT_CORPUS = PACKAGE_ROOT / "files" / "样例"

EMBEDDING_MODEL = "hash-bow-256"
COLLECTION_NAME = "corpus"

TARGET_CHUNK_CHARS = 600
MAX_CHUNK_CHARS = 1200
MAX_PARENT_CHARS = 8000
MIN_CHUNK_CHARS = 40
OVERLAP_CHARS = 100

SUPPORTED_SUFFIXES = {".md", ".txt", ".docx"}


@dataclass(frozen=True)
class RetrievalSettings:
    mode: str
    embedding: str
    rerank: bool
    fetch_k: int
    rrf_k: int


def retrieval_settings() -> RetrievalSettings:
    rerank_raw = os.getenv("HARNESS_RAG_RERANK", "1").strip().lower()
    fetch_raw = os.getenv("HARNESS_RAG_FETCH_K", "20").strip()
    rrf_raw = os.getenv("HARNESS_RAG_RRF_K", "60").strip()
    try:
        fetch_k = max(5, min(int(fetch_raw), 50))
    except ValueError:
        fetch_k = 20
    try:
        rrf_k = max(1, int(rrf_raw))
    except ValueError:
        rrf_k = 60
    return RetrievalSettings(
        mode=os.getenv("HARNESS_RAG_MODE", "hybrid").strip().lower(),
        embedding=os.getenv("HARNESS_RAG_EMBEDDING", "auto").strip().lower(),
        rerank=rerank_raw not in ("0", "false", "no"),
        fetch_k=fetch_k,
        rrf_k=rrf_k,
    )
