"""Tests for hybrid retrieval, rerank, and eval metrics."""

from pathlib import Path

import pytest

from harness.rag.bootstrap import ensure_rag_indexed
from harness.rag.chunking import LEVEL_CHILD, LEVEL_PARENT, chunk_markdown, merge_short_chunks
from harness.rag.eval import run_eval
from harness.rag.lexical import tokenize
from harness.rag.pipeline import search
from harness.rag.retrieval_policy import (
    expand_lexical_query,
    finalize_hits,
    preferred_modalities,
)
from harness.rag.retriever import reciprocal_rank_fusion
from harness.rag.tools import run_rag_search
from tests.rag_fixtures import rag_env  # noqa: F401

FIXTURE = Path(__file__).resolve().parent.parent / "evals" / "rag" / "fixtures" / "tiny_corpus"


@pytest.fixture()
def indexed_corpus(rag_env):
    result = ensure_rag_indexed(str(FIXTURE))
    assert result["ok"], result.get("message")
    return result


def test_hybrid_search_intro(indexed_corpus):
    hits = search("引言 编写目的 段落结构", top_k=3)
    assert hits
    blob = " ".join(h["text"] for h in hits)
    assert "编写目的" in blob or "引言" in blob


def test_hybrid_search_metrics_source_filter(indexed_corpus):
    text = run_rag_search("性能指标 FY-4 全通道", source="metrics.md")
    assert "FY-4" in text or "性能" in text


def test_agent_rag_search_respects_selected_document(indexed_corpus):
    from harness.rag.selection import set_selection

    set_selection(["metrics.md"])
    text = run_rag_search("性能指标 FY-4 全通道")
    assert "metrics.md" in text
    assert "sample_report.md" not in text


def test_rrf_merges_lists():
    bm25 = [{"id": "a", "text": "alpha", "score": 1.0}]
    vector = [{"id": "b", "text": "beta", "score": 0.9}]
    fused = reciprocal_rank_fusion([bm25, vector])
    assert len(fused) == 2
    assert fused[0]["id"] in {"a", "b"}


def test_chinese_tokenizer_supports_partial_technical_queries():
    tokens = tokenize("全通道性能指标增长趋势")
    assert "性能" in tokens
    assert "指标" in tokens
    assert "趋势" in tokens


def test_query_expansion_and_modality_routing():
    expanded = expand_lexical_query("交付数量增长趋势")
    assert "总数" in expanded
    assert "同比" in expanded
    assert preferred_modalities("表中数量是多少") == {"table"}
    assert preferred_modalities("图中曲线趋势如何") == {"image"}


def test_final_policy_boosts_table_and_deduplicates_page(monkeypatch):
    monkeypatch.setenv("HARNESS_RAG_MODALITY_BONUS", "0.2")
    hits = [
        {"id": "text", "text": "交付数量 12", "score": 1.0, "modality": "text"},
        {
            "id": "table",
            "text": "| 交付数量 | 12 |",
            "score": 0.95,
            "modality": "table",
            "source": "a.pdf",
            "page": 2,
        },
        {
            "id": "duplicate",
            "text": "| 交付数量 | 12 |",
            "score": 0.94,
            "modality": "table",
            "source": "a.pdf",
            "page": 2,
        },
    ]
    result = finalize_hits("表中交付数量是多少", hits, top_k=3)
    assert result[0]["id"] == "table"
    assert [hit["id"] for hit in result].count("duplicate") == 0


def test_merge_short_chunks_combines_neighbors():
    source = "demo.md"
    text = """# 章一

短段一。

短段二。

## 章二

这是一段足够长的正文内容，用于测试切块逻辑在合并短段之后仍然保留完整语义与章节结构信息。
"""
    chunks = chunk_markdown(source, text)
    assert chunks
    searchable = [c for c in chunks if c.level != LEVEL_PARENT]
    assert all(len(chunk.text) >= 40 or chunk.is_caption for chunk in searchable)


def test_eval_recall_on_fixture(rag_env):
    report = run_eval(FIXTURE)
    assert report["cases"]
    assert report["recall_at_k"] >= 0.75, report
    assert report["mrr"] > 0


def test_parent_child_hierarchy(indexed_corpus):
    from harness.rag.ingest import load_chunks_for_source

    chunks = load_chunks_for_source("sample_report.md")
    parents = [c for c in chunks if c.get("level") == LEVEL_PARENT]
    children = [c for c in chunks if c.get("level") == LEVEL_CHILD and c.get("parent_id")]
    assert parents, "expected parent chunks per section"
    assert children, "expected child chunks linked to parents"
    assert all(child["parent_id"] in {p["id"] for p in parents} for child in children)


def test_search_attaches_parent_context(indexed_corpus):
    hits = search("引言 编写目的 段落结构", top_k=3)
    assert hits
    with_parent = [hit for hit in hits if hit.get("parent_text")]
    assert with_parent, "child hits should expand parent section context"
    assert "编写目的" in with_parent[0]["parent_text"] or "引言" in with_parent[0]["parent_text"]
