"""Tests for manual /rag CLI commands."""

from pathlib import Path

import pytest

from harness.rag.commands import run_rag_add, run_rag_cli_command, run_rag_index_command
from tests.rag_fixtures import rag_env  # noqa: F401

FIXTURE = Path(__file__).resolve().parent.parent / "evals" / "rag" / "fixtures" / "tiny_corpus"
SAMPLE = FIXTURE / "sample_report.md"


def test_rag_help():
    text = run_rag_cli_command("/rag")
    assert "/rag index" in text
    assert "/rag add" in text


@pytest.fixture()
def isolated_cwd(rag_env, tmp_path, monkeypatch):
    import harness.rag.ingest as ingest_mod
    import harness.settings as settings_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings_mod, "WORKDIR", tmp_path)
    monkeypatch.setattr(ingest_mod, "WORKDIR", tmp_path)
    return tmp_path


def test_rag_index_fixture(isolated_cwd):
    corpus = isolated_cwd / "files"
    corpus.mkdir()
    (corpus / "sample_report.md").write_text(
        SAMPLE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    text = run_rag_index_command("files")
    assert "Indexed corpus" in text
    assert "sample_report.md" in text


def test_rag_status_after_index(isolated_cwd):
    corpus = isolated_cwd / "files"
    corpus.mkdir()
    (corpus / "metrics.md").write_text("## 指标\n\nFY-4 全通道。", encoding="utf-8")
    run_rag_index_command("files")
    text = run_rag_cli_command("/rag status")
    assert "metrics.md" in text


def test_rag_add_copies_and_indexes(isolated_cwd):
    external = isolated_cwd / "external.md"
    external.write_text(SAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    text = run_rag_add(str(external))
    assert "已导入:" in text
    assert (isolated_cwd / "files" / "external.md").exists()
    assert "Indexed corpus" in text
