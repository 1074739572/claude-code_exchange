"""Rerank retrieved candidates for final top-k."""

from __future__ import annotations

import os

from harness.rag.lexical import tokenize


def rerank_enabled() -> bool:
    return os.getenv("HARNESS_RAG_RERANK", "1").strip().lower() not in ("0", "false", "no")


def rerank_hits(query: str, hits: list[dict], *, top_k: int) -> list[dict]:
    if not hits:
        return []
    if not rerank_enabled():
        return hits[:top_k]

    cross = _cross_encoder_backend()
    if cross is not None:
        return cross.rerank(query, hits, top_k=top_k)

    return _lexical_rerank(query, hits, top_k=top_k)


def _lexical_rerank(query: str, hits: list[dict], *, top_k: int) -> list[dict]:
    query_tokens = set(tokenize(query))
    if not query_tokens:
        return hits[:top_k]

    scored: list[tuple[float, dict]] = []
    for hit in hits:
        text_tokens = set(tokenize(hit.get("text", "")))
        path_tokens = set(
            tokenize(
                f"{hit.get('heading_path', '')} {hit.get('chapter', '')} {hit.get('section', '')}"
            )
        )
        overlap = len(query_tokens & text_tokens)
        path_overlap = len(query_tokens & path_tokens)
        base = float(hit.get("score", 0.0))
        rerank_score = base + overlap * 0.15 + path_overlap * 0.25
        item = {**hit, "score": round(rerank_score, 4), "rerank": "lexical"}
        scored.append((rerank_score, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored[:top_k]]


class _CrossEncoderBackend:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name)
        return self._model

    def rerank(self, query: str, hits: list[dict], *, top_k: int) -> list[dict]:
        model = self._load()
        pairs = [(query, hit.get("text", "")) for hit in hits]
        scores = model.predict(pairs)
        scored = sorted(
            zip(scores, hits),
            key=lambda pair: float(pair[0]),
            reverse=True,
        )
        out: list[dict] = []
        for score, hit in scored[:top_k]:
            out.append(
                {
                    **hit,
                    "score": round(float(score), 4),
                    "rerank": f"cross-encoder:{self.model_name}",
                }
            )
        return out


_cross_encoder_singleton: _CrossEncoderBackend | None = None


def _cross_encoder_backend() -> _CrossEncoderBackend | None:
    global _cross_encoder_singleton
    model = os.getenv("HARNESS_RAG_RERANK_MODEL", "").strip()
    if not model:
        return None
    if _cross_encoder_singleton is None:
        try:
            _cross_encoder_singleton = _CrossEncoderBackend(model)
        except Exception:
            return None
    return _cross_encoder_singleton
