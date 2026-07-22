"""CLI: python -m evals.gaia --limit 3

Evaluates improved_harness on GAIA **validation** (answers available).
Scoring = official quasi-exact match (see ``evals.gaia.scorer``).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

from evals.gaia.agent_run import run_gaia_task
from evals.gaia.dataset import dataset_ready, load_validation
from evals.gaia.scorer import question_scorer

RESULTS_ROOT = Path(__file__).resolve().parent.parent / "results" / "gaia"


def _pct(n: int, d: int) -> float:
    return round(100.0 * n / d, 2) if d else 0.0


def _summarize(rows: list[dict]) -> dict:
    scored = [r for r in rows if r.get("status") == "ok"]
    correct = [r for r in scored if r.get("correct")]
    by_level: dict[str, dict] = {}
    for lvl in (1, 2, 3):
        subset = [r for r in scored if int(r.get("level", 0)) == lvl]
        hit = [r for r in subset if r.get("correct")]
        by_level[f"level_{lvl}"] = {
            "n": len(subset),
            "correct": len(hit),
            "accuracy_pct": _pct(len(hit), len(subset)),
        }
    return {
        "n_total": len(rows),
        "n_scored": len(scored),
        "n_correct": len(correct),
        "n_error": sum(1 for r in rows if r.get("status") == "error"),
        "accuracy_pct": _pct(len(correct), len(scored)),
        "by_level": by_level,
    }


def run_gaia_eval(
    *,
    limit: int | None = 3,
    level: int | None = None,
    task_ids: list[str] | None = None,
    max_rounds: int = 50,
    bootstrap_mcp: bool = True,
) -> dict:
    started = time.perf_counter()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RESULTS_ROOT / f"run_{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    tasks = load_validation(limit=limit, level=level, task_ids=task_ids)
    if not tasks:
        raise RuntimeError("No GAIA validation tasks selected")

    print(f"GAIA validation eval: {len(tasks)} task(s)")
    print(f"results -> {run_dir}")

    rows: list[dict] = []
    predictions: list[dict] = []

    for i, task in enumerate(tasks, 1):
        tid = task["task_id"]
        print(f"\n=== [{i}/{len(tasks)}] level={task['Level']} {tid} ===")
        print(f"Q: {task['Question'][:160]}{'…' if len(task['Question'])>160 else ''}")
        t0 = time.perf_counter()
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                out = run_gaia_task(
                    task,
                    max_rounds=max_rounds,
                    bootstrap_mcp=bootstrap_mcp and i == 1,
                )
            correct = bool(
                question_scorer(out["model_answer"], out["ground_truth"])
            )
            elapsed = round(time.perf_counter() - t0, 1)
            row = {
                "task_id": tid,
                "level": task["Level"],
                "status": "ok",
                "correct": correct,
                "model_answer": out["model_answer"],
                "ground_truth": out["ground_truth"],
                "tool_calls": out["tool_calls"],
                "hit_max_rounds": out.get("hit_max_rounds", False),
                "elapsed_s": elapsed,
                "attachment": out["attachment"],
            }
            pred = {
                "task_id": tid,
                "model_answer": out["model_answer"],
                "reasoning_trace": out["raw_assistant"][:8000],
            }
            # Persist full messages for debugging
            (run_dir / f"{tid}.messages.json").write_text(
                json.dumps(out["messages"], ensure_ascii=False, default=str, indent=2),
                encoding="utf-8",
            )
            mark = "PASS" if correct else "FAIL"
            print(
                f"{mark} pred={out['model_answer']!r} "
                f"gt={out['ground_truth']!r} tools={out['tool_calls']} {elapsed}s"
            )
        except KeyboardInterrupt:
            print("\nInterrupted — writing partial results…")
            rows.append(
                {
                    "task_id": tid,
                    "level": task["Level"],
                    "status": "error",
                    "correct": False,
                    "error": "KeyboardInterrupt",
                    "model_answer": "",
                    "ground_truth": task["Final answer"],
                    "tool_calls": 0,
                    "elapsed_s": round(time.perf_counter() - t0, 1),
                }
            )
            break
        except Exception as exc:  # noqa: BLE001
            elapsed = round(time.perf_counter() - t0, 1)
            row = {
                "task_id": tid,
                "level": task["Level"],
                "status": "error",
                "correct": False,
                "error": f"{type(exc).__name__}: {exc}",
                "model_answer": "",
                "ground_truth": task["Final answer"],
                "tool_calls": 0,
                "elapsed_s": elapsed,
            }
            pred = {"task_id": tid, "model_answer": "", "reasoning_trace": ""}
            print(f"ERROR: {type(exc).__name__}: {exc}")
            rows.append(row)
            predictions.append(pred)
            continue

        rows.append(row)
        predictions.append(pred)

    summary = _summarize(rows)
    summary["elapsed_s"] = round(time.perf_counter() - started, 1)
    summary["run_dir"] = str(run_dir)

    (run_dir / "results.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    (run_dir / "predictions.jsonl").write_text(
        "\n".join(json.dumps(p, ensure_ascii=False) for p in predictions) + "\n",
        encoding="utf-8",
    )
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\n======== GAIA validation summary ========")
    print(
        f"accuracy: {summary['n_correct']}/{summary['n_scored']} "
        f"= {summary['accuracy_pct']}%  "
        f"(errors={summary['n_error']}, {summary['elapsed_s']}s)"
    )
    for k, v in summary["by_level"].items():
        if v["n"]:
            print(f"  {k}: {v['correct']}/{v['n']} = {v['accuracy_pct']}%")
    print(f"saved: {run_dir}")
    return summary


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Evaluate harness on GAIA validation (answered split)"
    )
    p.add_argument(
        "--download",
        action="store_true",
        help="Download dataset via ModelScope then exit",
    )
    p.add_argument("--validation-only", action="store_true", help="With --download")
    p.add_argument("--no-attachments", action="store_true", help="With --download")
    p.add_argument("--limit", type=int, default=3, help="Max tasks (default 3)")
    p.add_argument("--all", action="store_true", help="Run full validation (165)")
    p.add_argument("--level", type=int, choices=[1, 2, 3], default=None)
    p.add_argument("--task-id", action="append", dest="task_ids", default=None)
    p.add_argument("--max-rounds", type=int, default=50)
    p.add_argument("--no-mcp", action="store_true", help="Skip MCP bootstrap")
    args = p.parse_args(argv)

    if args.download:
        from evals.gaia.download import download_gaia

        download_gaia(
            attachments=not args.no_attachments,
            validation_only=args.validation_only,
        )
        return 0

    if not dataset_ready():
        print(
            "GAIA dataset not found. Run:\n"
            "  python -m evals.gaia --download --validation-only"
        )
        return 2

    limit = None if args.all else args.limit
    run_gaia_eval(
        limit=limit,
        level=args.level,
        task_ids=args.task_ids,
        max_rounds=args.max_rounds,
        bootstrap_mcp=not args.no_mcp,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
