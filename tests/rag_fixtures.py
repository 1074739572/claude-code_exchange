"""Shared pytest fixture for isolated RAG directories."""

from __future__ import annotations

import pytest

from harness.rag import pipeline as pipeline_mod
from harness.rag.parents import PARENTS_PATH, reset_parent_cache
from harness.rag.stores import vector as vector_mod


@pytest.fixture()
def rag_env(tmp_path, monkeypatch):
    import harness.rag.config as rag_config
    import harness.rag.ingest as ingest_mod
    import harness.rag.lexical as lexical_mod
    import harness.rag.tools as tools_mod

    rag_dir = tmp_path / ".rag"
    chroma_dir = rag_dir / "chroma"
    monkeypatch.setenv("HARNESS_RAG_EMBEDDING", "hash")
    monkeypatch.setenv("HARNESS_RAG_MODE", "hybrid")
    monkeypatch.setenv("HARNESS_RAG_RERANK", "1")

    monkeypatch.setattr(rag_config, "RAG_DIR", rag_dir)
    monkeypatch.setattr(rag_config, "CHUNKS_DIR", rag_dir / "chunks")
    monkeypatch.setattr(rag_config, "INDEX_DIR", rag_dir / "index")
    monkeypatch.setattr(rag_config, "CHROMA_DIR", chroma_dir)
    monkeypatch.setattr(rag_config, "MANIFEST_PATH", rag_dir / "manifest.json")

    for mod in (ingest_mod, lexical_mod, tools_mod, pipeline_mod):
        monkeypatch.setattr(mod, "CHUNKS_DIR", rag_dir / "chunks", raising=False)
        monkeypatch.setattr(mod, "RAG_DIR", rag_dir, raising=False)
        monkeypatch.setattr(mod, "MANIFEST_PATH", rag_dir / "manifest.json", raising=False)

    monkeypatch.setattr(ingest_mod, "CHUNKS_DIR", rag_dir / "chunks")
    monkeypatch.setattr(lexical_mod, "INDEX_DIR", rag_dir / "index")
    monkeypatch.setattr(lexical_mod, "MANIFEST_PATH", rag_dir / "manifest.json")
    monkeypatch.setattr(lexical_mod, "CORPUS_PATH", rag_dir / "index" / "corpus.json")
    import harness.rag.parents as parents_mod
    import harness.rag.selection as selection_mod

    monkeypatch.setattr(parents_mod, "PARENTS_PATH", rag_dir / "index" / "parents.json")
    monkeypatch.setattr(parents_mod, "INDEX_DIR", rag_dir / "index")
    monkeypatch.setattr(selection_mod, "SELECTION_PATH", rag_dir / "selection.json")
    monkeypatch.setattr(selection_mod, "RAG_DIR", rag_dir)
    lexical_mod._corpus = []

    pipeline_mod.reset_runtime()
    vector_mod.reset_vector_store()
    reset_parent_cache()

    return rag_dir
