"""Tests for RAG bootstrap and retrieval on tiny fixture corpus."""

from pathlib import Path

import pytest

from harness.rag.bootstrap import ensure_rag_indexed
from harness.rag.lexical import search_chunks
from harness.rag.tools import run_rag_search

FIXTURE = Path(__file__).resolve().parent.parent / "evals" / "rag" / "fixtures" / "tiny_corpus"


@pytest.fixture()
def indexed_corpus(tmp_path, monkeypatch):
    import harness.rag.config as rag_config
    import harness.rag.ingest as ingest_mod
    import harness.rag.lexical as lexical_mod

    import harness.rag.tools as tools_mod

    rag_dir = tmp_path / ".rag"
    monkeypatch.setattr(rag_config, "RAG_DIR", rag_dir)
    monkeypatch.setattr(rag_config, "CHUNKS_DIR", rag_dir / "chunks")
    monkeypatch.setattr(rag_config, "INDEX_DIR", rag_dir / "index")
    monkeypatch.setattr(rag_config, "MANIFEST_PATH", rag_dir / "manifest.json")
    for mod in (ingest_mod, lexical_mod, tools_mod):
        monkeypatch.setattr(mod, "CHUNKS_DIR", rag_dir / "chunks", raising=False)
        monkeypatch.setattr(mod, "RAG_DIR", rag_dir, raising=False)
        monkeypatch.setattr(mod, "MANIFEST_PATH", rag_dir / "manifest.json", raising=False)
    monkeypatch.setattr(ingest_mod, "CHUNKS_DIR", rag_dir / "chunks")
    monkeypatch.setattr(lexical_mod, "INDEX_DIR", rag_dir / "index")
    monkeypatch.setattr(lexical_mod, "MANIFEST_PATH", rag_dir / "manifest.json")
    monkeypatch.setattr(lexical_mod, "CORPUS_PATH", rag_dir / "index" / "corpus.json")
    lexical_mod._corpus = []

    result = ensure_rag_indexed(str(FIXTURE))
    assert result["ok"], result.get("message")
    return result


def test_ensure_indexes_fixture(indexed_corpus):
    assert indexed_corpus["chunks"] >= 2
    assert indexed_corpus["sources"] >= 2


def test_search_intro_structure(indexed_corpus):
    hits = search_chunks("引言 编写目的 段落结构", top_k=3)
    assert hits
    blob = " ".join(h["text"] for h in hits)
    assert "编写目的" in blob or "引言" in blob


def test_search_delivery_metrics(indexed_corpus):
    text = run_rag_search("性能指标 FY-4 全通道", source="metrics.md")
    assert "FY-4" in text or "性能" in text
