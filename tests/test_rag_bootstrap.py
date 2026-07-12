"""Tests for RAG bootstrap and retrieval on tiny fixture corpus."""

from pathlib import Path

import pytest

from harness.rag.bootstrap import ensure_rag_indexed
from harness.rag.pipeline import search
from harness.rag.tools import run_rag_search
from tests.rag_fixtures import rag_env  # noqa: F401

FIXTURE = Path(__file__).resolve().parent.parent / "evals" / "rag" / "fixtures" / "tiny_corpus"


@pytest.fixture()
def indexed_corpus(rag_env):
    result = ensure_rag_indexed(str(FIXTURE))
    assert result["ok"], result.get("message")
    return result


def test_ensure_indexes_fixture(indexed_corpus):
    assert indexed_corpus["chunks"] >= 2
    assert indexed_corpus["sources"] >= 2


def test_search_intro_structure(indexed_corpus):
    hits = search("引言 编写目的 段落结构", top_k=3)
    assert hits
    blob = " ".join(h["text"] for h in hits)
    assert "编写目的" in blob or "引言" in blob


def test_search_delivery_metrics(indexed_corpus):
    text = run_rag_search("性能指标 FY-4 全通道", source="metrics.md")
    assert "FY-4" in text or "性能" in text
