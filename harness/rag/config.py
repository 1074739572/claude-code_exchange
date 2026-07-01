"""RAG paths and default parameters."""

from __future__ import annotations

from pathlib import Path

from harness.settings import PACKAGE_ROOT, WORKDIR

RAG_DIR = WORKDIR / ".rag"
CHUNKS_DIR = RAG_DIR / "chunks"
INDEX_DIR = RAG_DIR / "index"
MANIFEST_PATH = RAG_DIR / "manifest.json"
DEFAULT_CORPUS = PACKAGE_ROOT / "files" / "样例"

EMBEDDING_MODEL = "bm25-lexical"
COLLECTION_NAME = "corpus"

TARGET_CHUNK_CHARS = 600
MAX_CHUNK_CHARS = 1200
MIN_CHUNK_CHARS = 80
OVERLAP_CHARS = 100

SUPPORTED_SUFFIXES = {".md", ".txt", ".docx"}
