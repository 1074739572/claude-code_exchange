"""Tests for document selection and /rag ask Q&A."""

from pathlib import Path

import pytest

from harness.rag.commands import run_rag_ask_command, run_rag_select_command
from harness.rag.qa import answer_question, search_for_qa
from harness.rag.selection import get_active_sources, load_selection
from harness.rag.sources import format_docs_list, list_indexed_sources
from harness.rag.commands import run_rag_index_command
from tests.rag_fixtures import rag_env  # noqa: F401

FIXTURE = Path(__file__).resolve().parent.parent / "evals" / "rag" / "fixtures" / "tiny_corpus"
SAMPLE = FIXTURE / "sample_report.md"
METRICS = FIXTURE / "metrics.md"


@pytest.fixture()
def indexed_two_docs(rag_env, isolated_cwd):
    corpus = isolated_cwd / "files"
    corpus.mkdir()
    (corpus / "sample_report.md").write_text(
        SAMPLE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (corpus / "metrics.md").write_text(
        METRICS.read_text(encoding="utf-8"), encoding="utf-8"
    )
    run_rag_index_command("files")
    return isolated_cwd


@pytest.fixture()
def isolated_cwd(rag_env, tmp_path, monkeypatch):
    import harness.rag.ingest as ingest_mod
    import harness.settings as settings_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings_mod, "WORKDIR", tmp_path)
    monkeypatch.setattr(ingest_mod, "WORKDIR", tmp_path)
    return tmp_path


def test_docs_list_numbered(indexed_two_docs):
    text = format_docs_list()
    assert "sample_report.md" in text
    assert "metrics.md" in text
    assert "1." in text


def test_select_by_number(indexed_two_docs):
    rows = list_indexed_sources()
    metrics_idx = next(row["index"] for row in rows if row["source"] == "metrics.md")
    text = run_rag_select_command(str(metrics_idx))
    assert "metrics.md" in text
    assert load_selection() == ["metrics.md"]


def test_search_scoped_to_selection(indexed_two_docs):
    rows = list_indexed_sources()
    metrics_idx = next(row["index"] for row in rows if row["source"] == "metrics.md")
    run_rag_select_command(str(metrics_idx))
    hits = search_for_qa("性能指标 FY-4", top_k=3)
    assert hits
    assert all(hit.get("source") == "metrics.md" for hit in hits)


def test_ask_without_llm(indexed_two_docs, monkeypatch):
    monkeypatch.setenv("HARNESS_RAG_QA_LLM", "0")
    rows = list_indexed_sources()
    sample_idx = next(row["index"] for row in rows if row["source"] == "sample_report.md")
    run_rag_select_command(str(sample_idx))
    answer = answer_question("引言 编写目的是什么？")
    assert "检索到" in answer or "编写目的" in answer or "sample_report" in answer
    assert "sample_report.md" in answer or "编写目的" in answer


def test_ask_command_usage(indexed_two_docs):
    text = run_rag_ask_command("")
    assert "Usage: /rag ask" in text


def test_select_clear_searches_all(indexed_two_docs):
    run_rag_select_command("1")
    run_rag_select_command("clear")
    assert get_active_sources() is None
