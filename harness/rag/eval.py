"""RAG retrieval evaluation helpers (Recall@k, MRR)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from harness.rag.pipeline import build_index, search
from harness.rag.ingest import ingest_path

GOLD_PATH = Path(__file__).resolve().parents[2] / "evals" / "rag" / "gold_queries.yaml"
FIXTURE_CORPUS = Path(__file__).resolve().parents[2] / "evals" / "rag" / "fixtures" / "tiny_corpus"


def load_gold_queries(path: Path | None = None) -> list[dict[str, Any]]:
    gold_file = path or GOLD_PATH
    data = yaml.safe_load(gold_file.read_text(encoding="utf-8"))
    return list(data.get("queries") or [])


def _hit_matches(hit: dict, case: dict) -> bool:
    text_blob = " ".join(
        [
            hit.get("text", ""),
            hit.get("heading_path", ""),
            hit.get("chapter", ""),
            hit.get("source", ""),
        ]
    )
    expect_any = case.get("expect_any") or []
    if expect_any and not any(token in text_blob for token in expect_any):
        return False
    expect_source = case.get("expect_source")
    if expect_source and hit.get("source") != expect_source:
        return False
    expect_modality = case.get("expect_modality")
    if expect_modality and hit.get("modality", "text") != expect_modality:
        return False
    expect_page = case.get("expect_page")
    if expect_page is not None and int(hit.get("page", 0)) != int(expect_page):
        return False
    return True


def evaluate_query(case: dict) -> dict[str, Any]:
    top_k = int(case.get("top_k") or 5)
    hits = search(case["query"], top_k=top_k)
    first_rank = None
    for rank, hit in enumerate(hits, start=1):
        if _hit_matches(hit, case):
            first_rank = rank
            break
    recall = 1.0 if first_rank is not None else 0.0
    mrr = 1.0 / first_rank if first_rank else 0.0
    return {
        "id": case.get("id", case["query"]),
        "query": case["query"],
        "recall": recall,
        "mrr": mrr,
        "first_rank": first_rank,
        "hits": len(hits),
    }


def run_eval(corpus_path: str | Path | None = None, gold_path: Path | None = None) -> dict:
    root = Path(corpus_path) if corpus_path else FIXTURE_CORPUS
    ingest = ingest_path(str(root))
    build_index([item["source"] for item in ingest["files"]])
    cases = load_gold_queries(gold_path)
    results = [evaluate_query(case) for case in cases]
    if not results:
        return {"cases": [], "recall_at_k": 0.0, "mrr": 0.0}
    recall = sum(item["recall"] for item in results) / len(results)
    mrr = sum(item["mrr"] for item in results) / len(results)
    return {
        "corpus": str(root),
        "cases": results,
        "recall_at_k": round(recall, 4),
        "mrr": round(mrr, 4),
        "passed": recall >= 0.75,
    }
