"""Format and persist eval reports."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from evals.types import EvalReport

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def _icon(status: str) -> str:
    return {
        "pass": "PASS",
        "fail": "FAIL",
        "skip": "SKIP",
        "warn": "WARN",
    }.get(status, status.upper())


def format_report(report: EvalReport) -> str:
    lines = [
        "=" * 64,
        " improved_harness · mini-eval",
        f" live={report.live}  score={report.score:.0f}%  "
        f"pass={report.passed} fail={report.failed} "
        f"warn={report.warned} skip={report.skipped}",
        "=" * 64,
        "",
    ]
    current_cat = None
    for r in report.results:
        if r.category != current_cat:
            current_cat = r.category
            lines.append(f"[{current_cat}]")
        detail = f" — {r.detail}" if r.detail else ""
        lines.append(
            f"  {_icon(r.status):4}  {r.id:<28} {r.name}{detail}"
            f"  ({r.duration_ms:.0f}ms)"
        )
    lines.extend(
        [
            "",
            "Scoring: pass/fail only (warn+skip excluded).",
            "Re-run: python -m evals",
            "Live LLM: python -m evals --live",
            "",
        ]
    )
    text = "\n".join(lines)
    # Windows consoles may be GBK; keep ASCII-safe separators.
    return text.replace("—", "-").replace("·", "-")


def save_report(report: EvalReport) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "generated_at": stamp,
        "live": report.live,
        "score": report.score,
        "passed": report.passed,
        "failed": report.failed,
        "warned": report.warned,
        "skipped": report.skipped,
        "results": [r.to_dict() for r in report.results],
    }
    latest = RESULTS_DIR / "latest.json"
    stamped = RESULTS_DIR / f"report_{stamp}.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    latest.write_text(text, encoding="utf-8")
    stamped.write_text(text, encoding="utf-8")
    return latest
