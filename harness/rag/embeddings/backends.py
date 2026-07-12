"""Pluggable embedding backends: hash (CI), OpenAI API, local BGE."""

from __future__ import annotations

import hashlib
import math
import os
from typing import Protocol

from harness.rag.lexical import tokenize

HASH_EMBED_DIM = 256


class EmbeddingBackend(Protocol):
    model_name: str
    backend_id: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class HashEmbeddingBackend:
    """Deterministic bag-of-tokens vectors — no downloads, good for CI."""

    model_name = "hash-bow-256"
    backend_id = "hash"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [_hash_vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return _hash_vector(text)


def _hash_vector(text: str, dim: int = HASH_EMBED_DIM) -> list[float]:
    vec = [0.0] * dim
    tokens = tokenize(text)
    for token in tokens:
        bucket = int(hashlib.md5(token.encode()).hexdigest(), 16) % dim
        vec[bucket] += 1.0
    for index in range(len(tokens) - 1):
        bigram = f"{tokens[index]}_{tokens[index + 1]}"
        bucket = int(hashlib.md5(bigram.encode()).hexdigest(), 16) % dim
        vec[bucket] += 0.5
    norm = math.sqrt(sum(value * value for value in vec)) or 1.0
    return [value / norm for value in vec]


class OpenAIEmbeddingBackend:
    model_name = "text-embedding-3-small"
    backend_id = "openai"

    def __init__(self, model: str | None = None) -> None:
        self.model_name = model or os.getenv(
            "HARNESS_RAG_OPENAI_EMBED_MODEL", "text-embedding-3-small"
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed_batch(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embed_batch([text])[0]

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        from openai import OpenAI

        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("HARNESS_RAG_OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OpenAI embedding requires OPENAI_API_KEY or HARNESS_RAG_OPENAI_API_KEY"
            )
        base_url = os.getenv("OPENAI_BASE_URL")
        client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
        response = client.embeddings.create(model=self.model_name, input=texts)
        ordered = sorted(response.data, key=lambda item: item.index)
        return [item.embedding for item in ordered]


class LocalBgeEmbeddingBackend:
    """BAAI/bge-m3 via sentence-transformers (optional heavy dep)."""

    model_name = "BAAI/bge-m3"
    backend_id = "bge-m3"

    def __init__(self, model: str | None = None) -> None:
        self.model_name = model or os.getenv("HARNESS_RAG_LOCAL_EMBED_MODEL", "BAAI/bge-m3")
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    "Local BGE embedding requires: pip install sentence-transformers"
                ) from exc
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        vectors = model.encode(texts, normalize_embeddings=True)
        return [vector.tolist() for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        model = self._load()
        vector = model.encode([text], normalize_embeddings=True)[0]
        return vector.tolist()


def resolve_embedding_name() -> str:
    return os.getenv("HARNESS_RAG_EMBEDDING", "auto").strip().lower()


def get_embedding_backend(name: str | None = None) -> EmbeddingBackend:
    """Resolve embedding backend from env or explicit name."""
    choice = (name or resolve_embedding_name()).strip().lower()
    if choice == "auto":
        if os.getenv("OPENAI_API_KEY") or os.getenv("HARNESS_RAG_OPENAI_API_KEY"):
            return OpenAIEmbeddingBackend()
        local_model = os.getenv("HARNESS_RAG_LOCAL_EMBED_MODEL", "").strip()
        if local_model or os.getenv("HARNESS_RAG_EMBEDDING_FORCE_LOCAL") == "1":
            return LocalBgeEmbeddingBackend(local_model or None)
        return HashEmbeddingBackend()
    if choice in ("hash", "bow", "test"):
        return HashEmbeddingBackend()
    if choice in ("openai", "text-embedding-3-small"):
        return OpenAIEmbeddingBackend(
            None if choice == "openai" else "text-embedding-3-small"
        )
    if choice in ("bge-m3", "bge", "local"):
        return LocalBgeEmbeddingBackend()
    raise ValueError(
        f"Unknown HARNESS_RAG_EMBEDDING={choice!r}. "
        "Use auto, hash, openai, or bge-m3."
    )
