"""CLI: python -m evals.swebench --limit 1"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from evals.swebench.agent_run import run_agent_on_workspace
from evals.swebench.dataset import DATASET_NAME, load_instances
from evals.swebench.workspace import git_diff_patch, patch_nonempty, prepare_workspace

RESULTS_ROOT = Path(__file__).resolve().parent.parent / "results" / "swebench"
MODEL_NAME = "improved_harness"


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def run_swebench(
    *,
    limit: int | None = 1,
    instance_ids: list[str] | None = None,
    max_rounds: int = 25,
    do_eval: bool = False,
    source: str = "auto",
) -> dict:
    started = time.perf_counter()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RESULTS_ROOT / f"run_{stamp}"
    work_root = run_dir / "workspaces"
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading {DATASET_NAME} (source={source}) ...")
    instances = load_instances(
        limit=limit, instance_ids=instance_ids, source=source
    )
    if not instances:
        raise RuntimeError("No instances selected")

    predictions: list[dict] = []
    summaries: list[dict] = []

    for i, inst in enumerate(instances, 1):
        iid = inst["instance_id"]
        print(f"\n=== [{i}/{len(instances)}] {iid} ===")
        print(f"repo={inst['repo']} commit={inst['base_commit'][:12]}")
        t0 = time.perf_counter()
        try:
            ws = prepare_workspace(inst, work_root)
            print(f"workspace: {ws}")
            run_agent_on_workspace(ws, inst, max_rounds=max_rounds)
            patch = git_diff_patch(ws)
            (run_dir / f"{iid}.patch").write_text(patch, encoding="utf-8")
            pred = {
                "instance_id": iid,
                "model_name_or_path": MODEL_NAME,
                "model_patch": patch,
            }
            predictions.append(pred)
            summaries.append(
                {
                    "instance_id": iid,
                    "status": "ok",
                    "patch_chars": len(patch),
                    "patch_nonempty": patch_nonempty(patch),
                    "elapsed_s": round(time.perf_counter() - t0, 1),
                }
            )
            print(
                f"patch: {len(patch)} chars "
                f"({'non-empty' if patch_nonempty(patch) else 'EMPTY'})"
            )
        except Exception as exc:
            predictions.append(
                {
                    "instance_id": iid,
                    "model_name_or_path": MODEL_NAME,
                    "model_patch": "",
                }
            )
            summaries.append(
                {
                    "instance_id": iid,
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                    "patch_chars": 0,
                    "patch_nonempty": False,
                    "elapsed_s": round(time.perf_counter() - t0, 1),
                }
            )
            print(f"ERROR: {type(exc).__name__}: {exc}")

    preds_path = run_dir / "predictions.jsonl"
    _write_jsonl(preds_path, predictions)

    nonempty = sum(1 for s in summaries if s.get("patch_nonempty"))
    report = {
        "dataset": DATASET_NAME,
        "model": MODEL_NAME,
        "limit": limit,
        "instance_ids": [s["instance_id"] for s in summaries],
        "predictions_path": str(preds_path),
        "n": len(summaries),
        "patch_nonempty": nonempty,
        "patch_empty": len(summaries) - nonempty,
        "errors": sum(1 for s in summaries if s["status"] == "error"),
        "elapsed_s": round(time.perf_counter() - started, 1),
        "instances": summaries,
        "official_resolve": None,
        "note": (
            "patch_nonempty is a weak proxy only. "
            "Official resolved-rate needs Docker swebench harness (--eval)."
        ),
    }

    if do_eval:
        report["official_resolve"] = _try_official_eval(preds_path, run_dir)

    (run_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    latest = RESULTS_ROOT / "latest_report.json"
    latest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _print_report(report)
    print(f"\nWrote {run_dir / 'report.json'}")
    return report


def _try_official_eval(preds_path: Path, run_dir: Path) -> dict:
    """Best-effort official scoring via Docker (Linux). Skip if daemon down."""
    import shutil
    import subprocess

    if not shutil.which("docker"):
        return {"status": "skipped", "reason": "docker not installed"}
    probe = subprocess.run(
        ["docker", "info"],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode != 0:
        return {
            "status": "skipped",
            "reason": "Docker daemon not running (start Docker Desktop)",
        }

    # Run official harness inside python container (Unix resource module available)
    mount = str(preds_path.parent.resolve()).replace("\\", "/")
    # On Docker Desktop Windows, path often works as /run/desktop/mnt/host/...
    # Prefer current path; Docker Desktop usually mounts drives.
    out_name = "official_eval"
    cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{preds_path.parent.resolve()}:/work",
        "python:3.11-slim",
        "bash",
        "-lc",
        (
            "pip install -q swebench datasets && "
            "python -m swebench.harness.run_evaluation "
            f"--dataset_name {DATASET_NAME} "
            "--predictions_path /work/predictions.jsonl "
            f"--run_id {out_name} "
            "--max_workers 1"
        ),
    ]
    print("\nRunning official swebench eval in Docker (may pull images, slow)...")
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    log_path = run_dir / "official_eval.log"
    log_path.write_text(
        (proc.stdout or "") + "\n" + (proc.stderr or ""), encoding="utf-8"
    )
    return {
        "status": "finished" if proc.returncode == 0 else "failed",
        "returncode": proc.returncode,
        "log": str(log_path),
        "tail": ((proc.stdout or "") + (proc.stderr or ""))[-1500:],
    }


def _print_report(report: dict) -> None:
    print("\n" + "=" * 64)
    print(" SWE-bench Lite · improved_harness")
    print("=" * 64)
    print(f" instances: {report['n']}")
    print(f" patch non-empty: {report['patch_nonempty']}/{report['n']}")
    print(f" errors: {report['errors']}")
    print(f" elapsed: {report['elapsed_s']}s")
    for row in report["instances"]:
        flag = "PATCH" if row.get("patch_nonempty") else "EMPTY"
        err = f" ERR={row.get('error','')[:80]}" if row["status"] == "error" else ""
        print(
            f"  [{flag}] {row['instance_id']}  "
            f"{row.get('patch_chars', 0)} chars  {row.get('elapsed_s')}s{err}"
        )
    if report.get("official_resolve"):
        print(f" official_eval: {report['official_resolve'].get('status')}")
    print("=" * 64)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SWE-bench Lite via improved_harness")
    parser.add_argument("--limit", type=int, default=1, help="Number of instances (default 1)")
    parser.add_argument(
        "--instance-id",
        action="append",
        dest="instance_ids",
        help="Specific instance_id (repeatable)",
    )
    parser.add_argument(
        "--source",
        choices=["auto", "parquet", "smoke", "hf"],
        default="auto",
        help="Instance source (default auto: local parquet → smoke → HF)",
    )
    parser.add_argument("--max-rounds", type=int, default=25, help="Agent LLM round cap")
    parser.add_argument(
        "--eval",
        action="store_true",
        help="Also run official Docker swebench scoring (slow; needs Docker Desktop)",
    )
    args = parser.parse_args(argv)
    try:
        report = run_swebench(
            limit=args.limit if not args.instance_ids else None,
            instance_ids=args.instance_ids,
            max_rounds=args.max_rounds,
            do_eval=args.eval,
            source=args.source,
        )
    except Exception as exc:
        print(f"FATAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    # Weak gate: fail if all empty/error when we expected work
    if report["errors"] == report["n"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
