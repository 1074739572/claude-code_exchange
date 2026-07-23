"""Deterministic, offline RAG evaluation for retrieval, extraction and answers."""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

import yaml

from harness.rag.ingest import ingest_path, load_chunks_for_source
from harness.rag.pipeline import build_index, search

GOLD_PATH = Path(__file__).resolve().parents[2] / "evals" / "rag" / "gold_queries.yaml"
FIXTURE_CORPUS = Path(__file__).resolve().parents[2] / "evals" / "rag" / "fixtures" / "tiny_corpus"
DEFAULT_KS = (1, 3, 5, 10)


def load_gold_suite(path: Path | None = None) -> dict[str, Any]:
    gold_file = path or GOLD_PATH
    data = yaml.safe_load(gold_file.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"RAG gold suite must be a YAML mapping: {gold_file}")
    return data


def load_gold_queries(path: Path | None = None) -> list[dict[str, Any]]:
    """Load retrieval cases; keeps the original ``queries`` schema compatible."""
    return list(load_gold_suite(path).get("queries") or [])


def _expectations(case: dict) -> list[dict]:
    relevant = case.get("relevant")
    if relevant:
        return [dict(item) for item in relevant]
    legacy = {
        key: case[key]
        for key in ("expect_any", "expect_source", "expect_modality", "expect_page")
        if key in case
    }
    return [legacy] if legacy else []


def _matches_expectation(hit: dict, expectation: dict) -> bool:
    text_blob = " ".join(
        [
            hit.get("text", ""),
            hit.get("heading_path", ""),
            hit.get("chapter", ""),
            hit.get("source", ""),
        ]
    )
    expect_any = expectation.get("expect_any") or []
    if expect_any and not any(token in text_blob for token in expect_any):
        return False
    expect_all = expectation.get("expect_all") or []
    if expect_all and not all(token in text_blob for token in expect_all):
        return False
    expect_source = expectation.get("expect_source") or expectation.get("source")
    if expect_source and hit.get("source") != expect_source:
        return False
    expect_modality = expectation.get("expect_modality") or expectation.get("modality")
    if expect_modality and hit.get("modality", "text") != expect_modality:
        return False
    expect_page = expectation.get("expect_page", expectation.get("page"))
    if expect_page is not None and int(hit.get("page", 0)) != int(expect_page):
        return False
    return True


def _hit_matches(hit: dict, case: dict) -> bool:
    return any(_matches_expectation(hit, item) for item in _expectations(case))


def _gain(hit: dict, case: dict) -> float:
    grades = [
        float(item.get("grade", 1.0))
        for item in _expectations(case)
        if _matches_expectation(hit, item)
    ]
    return max(grades, default=0.0)


def _ranked_gains(hits: list[dict], case: dict) -> list[float]:
    """Assign each gold relevance target once so duplicate chunks cannot inflate nDCG."""
    expectations = _expectations(case)
    consumed: set[int] = set()
    gains: list[float] = []
    for hit in hits:
        matches = [
            (float(expectation.get("grade", 1.0)), index)
            for index, expectation in enumerate(expectations)
            if index not in consumed and _matches_expectation(hit, expectation)
        ]
        if not matches:
            gains.append(0.0)
            continue
        grade, index = max(matches)
        consumed.add(index)
        gains.append(grade)
    return gains


def _dcg(gains: list[float], k: int) -> float:
    return sum((2**gain - 1) / math.log2(rank + 2) for rank, gain in enumerate(gains[:k]))


def _ndcg(gains: list[float], ideal_gains: list[float], k: int) -> float:
    ideal = _dcg(sorted(ideal_gains, reverse=True), k)
    return _dcg(gains, k) / ideal if ideal else 0.0


def evaluate_query(
    case: dict,
    *,
    ks: tuple[int, ...] = DEFAULT_KS,
    search_fn=search,
) -> dict[str, Any]:
    """Evaluate one query with one retrieval call and multiple cutoff metrics."""
    requested_k = int(case.get("top_k") or max(ks))
    fetch_k = max(requested_k, max(ks))
    started = time.perf_counter()
    hits = search_fn(case["query"], top_k=fetch_k)
    latency_ms = (time.perf_counter() - started) * 1000
    gains = _ranked_gains(hits, case)
    first_rank = next((rank for rank, gain in enumerate(gains, start=1) if gain > 0), None)
    ideal_gains = [float(item.get("grade", 1.0)) for item in _expectations(case)]
    metrics: dict[str, float] = {}
    for k in ks:
        metrics[f"recall_at_{k}"] = 1.0 if any(gains[:k]) else 0.0
        metrics[f"ndcg_at_{k}"] = round(_ndcg(gains, ideal_gains, k), 6)

    return {
        "id": case.get("id", case["query"]),
        "query": case["query"],
        "category": case.get("category", "uncategorized"),
        "metrics": metrics,
        "recall": metrics.get(f"recall_at_{requested_k}", 1.0 if first_rank else 0.0),
        "mrr": 1.0 / first_rank if first_rank else 0.0,
        "first_rank": first_rank,
        "hits": len(hits),
        "latency_ms": round(latency_ms, 3),
        "top_hits": [
            {
                "source": hit.get("source"),
                "page": hit.get("page"),
                "modality": hit.get("modality", "text"),
                "score": hit.get("score"),
                "relevant": gain > 0,
            }
            for hit, gain in zip(hits[:requested_k], gains[:requested_k])
        ],
    }


def _mean(items: list[dict], path: tuple[str, ...]) -> float:
    values: list[float] = []
    for item in items:
        value: Any = item
        for key in path:
            value = value.get(key, {}) if isinstance(value, dict) else {}
        if isinstance(value, (int, float)):
            values.append(float(value))
    return round(sum(values) / len(values), 4) if values else 0.0


def _aggregate(results: list[dict], ks: tuple[int, ...]) -> dict[str, Any]:
    metrics = {"mrr": _mean(results, ("mrr",))}
    for k in ks:
        metrics[f"recall_at_{k}"] = _mean(results, ("metrics", f"recall_at_{k}"))
        metrics[f"ndcg_at_{k}"] = _mean(results, ("metrics", f"ndcg_at_{k}"))
    latencies = sorted(float(item["latency_ms"]) for item in results)
    metrics["latency_ms_mean"] = round(sum(latencies) / len(latencies), 3) if latencies else 0.0
    metrics["latency_ms_p95"] = (
        round(latencies[max(0, math.ceil(len(latencies) * 0.95) - 1)], 3) if latencies else 0.0
    )
    return metrics


def _threshold_failures(metrics: dict, thresholds: dict) -> list[str]:
    failures = []
    for name, expected in thresholds.items():
        actual = metrics.get(name)
        if actual is None:
            failures.append(f"unknown metric: {name}")
        elif name.startswith("latency_") and actual > float(expected):
            failures.append(f"{name}={actual} > {expected}")
        elif not name.startswith("latency_") and actual < float(expected):
            failures.append(f"{name}={actual} < {expected}")
    return failures


def evaluate_answer(answer: str, case: dict) -> dict[str, Any]:
    """Rule-based answer evaluation; deterministic and safe for CI."""
    rules = case.get("answer_expect") or case
    contains_all = list(rules.get("contains_all") or [])
    contains_any = list(rules.get("contains_any") or [])
    excludes = list(rules.get("excludes") or rules.get("forbidden") or [])
    citation = rules.get("citation") or {}
    checks = {
        "contains_all": all(token in answer for token in contains_all),
        "contains_any": not contains_any or any(token in answer for token in contains_any),
        "excludes": not any(token in answer for token in excludes),
        "citation_source": not citation.get("source") or citation["source"] in answer,
        "citation_page": citation.get("page") is None
        or str(citation["page"]) in answer,
    }
    return {
        "id": case.get("id", "answer"),
        "passed": all(checks.values()),
        "checks": checks,
    }


def evaluate_answers(cases: list[dict], answer_fn) -> dict[str, Any]:
    """Evaluate generated answers through an injected QA function (offline or live)."""
    results = []
    for case in cases:
        started = time.perf_counter()
        answer = answer_fn(case["query"])
        result = evaluate_answer(answer, case)
        result["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
        results.append(result)
    pass_rate = (
        round(sum(1 for result in results if result["passed"]) / len(results), 4)
        if results
        else 0.0
    )
    return {"cases": results, "pass_rate": pass_rate}


def evaluate_extraction(chunks: list[dict], case: dict) -> dict[str, Any]:
    """Check parsed chunks against source/page/modality/fact gold assertions."""
    source = case.get("source")
    scoped = [chunk for chunk in chunks if not source or chunk.get("source") == source]
    facts = []
    for fact in case.get("facts") or []:
        match = any(_matches_expectation(chunk, fact) for chunk in scoped)
        facts.append({"id": fact.get("id", str(fact.get("expect_any") or fact)), "passed": match})
    expected_modalities = case.get("modalities") or {}
    actual_modalities: dict[str, int] = {}
    for chunk in scoped:
        modality = chunk.get("modality", "text")
        actual_modalities[modality] = actual_modalities.get(modality, 0) + 1
    modality_checks = {
        modality: actual_modalities.get(modality, 0) >= int(minimum)
        for modality, minimum in expected_modalities.items()
    }
    return {
        "source": source,
        "passed": all(item["passed"] for item in facts) and all(modality_checks.values()),
        "facts": facts,
        "modality_checks": modality_checks,
        "actual_modalities": actual_modalities,
    }


def run_eval(
    corpus_path: str | Path | None = None,
    gold_path: Path | None = None,
    *,
    output_path: str | Path | None = None,
) -> dict:
    root = Path(corpus_path) if corpus_path else FIXTURE_CORPUS
    suite = load_gold_suite(gold_path)
    ks = tuple(int(k) for k in suite.get("ks", DEFAULT_KS))
    ingest = ingest_path(str(root))
    build_index([item["source"] for item in ingest["files"]])
    cases = list(suite.get("queries") or [])
    results = [evaluate_query(case, ks=ks) for case in cases]
    if not results:
        report = {"cases": [], "metrics": {}, "categories": {}, "passed": False}
        return report

    metrics = _aggregate(results, ks)
    extraction_cases = list(suite.get("extraction") or [])
    all_chunks = [
        chunk
        for item in ingest["files"]
        for chunk in load_chunks_for_source(item["source"])
    ]
    extraction_results = [
        evaluate_extraction(all_chunks, case) for case in extraction_cases
    ]
    if extraction_results:
        metrics["extraction_pass_rate"] = round(
            sum(1 for result in extraction_results if result["passed"])
            / len(extraction_results),
            4,
        )
    categories = {
        category: _aggregate([item for item in results if item["category"] == category], ks)
        for category in sorted({item["category"] for item in results})
    }
    thresholds = suite.get("thresholds") or {"recall_at_5": 0.75}
    failures = _threshold_failures(metrics, thresholds)
    report = {
        "schema_version": 2,
        "corpus": str(root),
        "cases": results,
        "extraction": {
            "cases": extraction_results,
            "pass_rate": metrics.get("extraction_pass_rate", 0.0),
        },
        "metrics": metrics,
        "categories": categories,
        "thresholds": thresholds,
        "failures": failures,
        "passed": not failures,
        # Compatibility for callers written against schema v1.
        "recall_at_k": metrics.get("recall_at_5", 0.0),
        "mrr": metrics["mrr"],
    }
    if output_path:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return report


def format_eval_report(report: dict) -> str:
    metrics = report.get("metrics") or {}
    lines = [
        f"RAG evaluation: {'PASS' if report.get('passed') else 'FAIL'}",
        f"Cases: {len(report.get('cases') or [])}",
        f"Recall@5: {metrics.get('recall_at_5', 0):.3f}",
        f"MRR: {metrics.get('mrr', 0):.3f}",
        f"nDCG@5: {metrics.get('ndcg_at_5', 0):.3f}",
        f"Extraction: {metrics.get('extraction_pass_rate', 0):.3f}",
        f"Latency p95: {metrics.get('latency_ms_p95', 0):.1f} ms",
    ]
    for category, values in (report.get("categories") or {}).items():
        lines.append(
            f"  - {category}: Recall@5={values.get('recall_at_5', 0):.3f}, "
            f"MRR={values.get('mrr', 0):.3f}"
        )
    if report.get("failures"):
        lines.append("Threshold failures:")
        lines.extend(f"  - {failure}" for failure in report["failures"])
    return "\n".join(lines)
