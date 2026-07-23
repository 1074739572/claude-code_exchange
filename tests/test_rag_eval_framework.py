"""Regression tests for the layered, deterministic RAG evaluation framework."""

from __future__ import annotations

import json
from pathlib import Path

from harness.rag.eval import (
    evaluate_answer,
    evaluate_answers,
    evaluate_extraction,
    evaluate_query,
    run_eval,
)
from tests.rag_fixtures import rag_env  # noqa: F401


FIXTURE = Path(__file__).resolve().parent.parent / "evals" / "rag" / "fixtures" / "tiny_corpus"


def test_retrieval_metrics_support_multiple_relevance_targets_and_deduplicate():
    case = {
        "id": "table-facts",
        "query": "交付数量",
        "category": "table",
        "relevant": [
            {"source": "report.pdf", "page": 2, "modality": "table", "grade": 2},
            {"source": "report.pdf", "page": 3, "modality": "table", "grade": 1},
        ],
    }
    hits = [
        {"source": "noise.pdf", "page": 1, "modality": "text", "text": "交付数量"},
        {"source": "report.pdf", "page": 2, "modality": "table", "text": "12 套"},
        # Duplicate of the same gold target must not count as another relevant item.
        {"source": "report.pdf", "page": 2, "modality": "table", "text": "12 套"},
        {"source": "report.pdf", "page": 3, "modality": "table", "text": "8 套"},
    ]

    result = evaluate_query(case, ks=(1, 3, 5), search_fn=lambda _query, top_k: hits[:top_k])

    assert result["first_rank"] == 2
    assert result["metrics"]["recall_at_1"] == 0
    assert result["metrics"]["recall_at_3"] == 1
    assert 0 < result["metrics"]["ndcg_at_5"] <= 1


def test_extraction_eval_checks_facts_page_modality_and_counts():
    chunks = [
        {
            "source": "report.pdf",
            "page": 3,
            "modality": "table",
            "text": "| 交付数量 | 12 套 |",
        },
        {"source": "report.pdf", "page": 4, "modality": "image", "text": "收入持续增长"},
    ]
    case = {
        "source": "report.pdf",
        "modalities": {"table": 1, "image": 1},
        "facts": [
            {
                "id": "delivery",
                "expect_all": ["交付数量", "12 套"],
                "page": 3,
                "modality": "table",
            }
        ],
    }

    result = evaluate_extraction(chunks, case)

    assert result["passed"]
    assert result["actual_modalities"] == {"table": 1, "image": 1}


def test_answer_eval_is_rule_based_and_supports_injected_answer_provider():
    case = {
        "id": "delivery-answer",
        "query": "交付多少套？",
        "answer_expect": {
            "contains_all": ["12", "套"],
            "excludes": ["15 套"],
            "citation": {"source": "report.pdf", "page": 3},
        },
    }
    answer = "交付数量为 12 套。[report.pdf，第 3 页]"

    assert evaluate_answer(answer, case)["passed"]
    report = evaluate_answers([case], lambda _query: answer)
    assert report["pass_rate"] == 1.0


def test_full_eval_writes_versioned_report(rag_env, tmp_path: Path):
    output = tmp_path / "reports" / "rag.json"

    report = run_eval(FIXTURE, output_path=output)

    assert report["schema_version"] == 2
    assert report["passed"], report["failures"]
    assert report["metrics"]["recall_at_5"] == 1.0
    assert report["metrics"]["extraction_pass_rate"] == 1.0
    assert report["categories"]
    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted["metrics"] == report["metrics"]
