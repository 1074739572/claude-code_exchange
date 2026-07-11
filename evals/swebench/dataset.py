"""Load SWE-bench Lite instances (local fixture / parquet / HuggingFace)."""

from __future__ import annotations

import json
import ssl
import urllib.request
from pathlib import Path
from typing import Any

DATASET_NAME = "princeton-nlp/SWE-bench_Lite"
SPLIT = "test"

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SMOKE_JSON = FIXTURES / "smoke_instances.json"
PARQUET_PATH = FIXTURES / "swebench_lite_test.parquet"
PARQUET_URL = (
    "https://huggingface.co/datasets/princeton-nlp/SWE-bench_Lite/"
    "resolve/main/data/test-00000-of-00001.parquet"
)


def _download_parquet() -> Path:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    if PARQUET_PATH.exists() and PARQUET_PATH.stat().st_size > 1000:
        return PARQUET_PATH
    print(f"Downloading SWE-bench Lite parquet → {PARQUET_PATH} ...")
    ctx = ssl._create_unverified_context()
    req = urllib.request.Request(PARQUET_URL, headers={"User-Agent": "improved-harness"})
    with urllib.request.urlopen(req, timeout=180, context=ctx) as resp:
        PARQUET_PATH.write_bytes(resp.read())
    return PARQUET_PATH


def _rows_from_parquet() -> list[dict[str, Any]]:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError(
            "pyarrow required for SWE-bench parquet. "
            "Run: pip install -r requirements-eval.txt"
        ) from exc
    path = _download_parquet()
    return pq.read_table(path).to_pylist()


def _rows_from_smoke() -> list[dict[str, Any]]:
    if not SMOKE_JSON.exists():
        raise FileNotFoundError(f"Missing smoke fixture: {SMOKE_JSON}")
    return json.loads(SMOKE_JSON.read_text(encoding="utf-8"))


def _rows_from_hf() -> list[dict[str, Any]]:
    from datasets import load_dataset

    ds = load_dataset(DATASET_NAME, split=SPLIT)
    return [dict(row) for row in ds]


def load_instances(
    *,
    limit: int | None = None,
    instance_ids: list[str] | None = None,
    source: str = "auto",
) -> list[dict[str, Any]]:
    """
    source:
      auto  — parquet (download if needed), else smoke JSON, else HF datasets
      parquet / smoke / hf — force that source
    """
    source = (source or "auto").lower()
    rows: list[dict[str, Any]]
    if source == "smoke":
        rows = _rows_from_smoke()
    elif source == "parquet":
        rows = _rows_from_parquet()
    elif source == "hf":
        rows = _rows_from_hf()
    else:
        try:
            rows = _rows_from_parquet()
        except Exception as exc:
            print(f"[swebench] parquet load failed ({exc}); trying smoke fixture")
            try:
                rows = _rows_from_smoke()
            except Exception:
                rows = _rows_from_hf()

    if instance_ids:
        wanted = set(instance_ids)
        rows = [r for r in rows if r["instance_id"] in wanted]
        missing = wanted - {r["instance_id"] for r in rows}
        if missing:
            raise ValueError(f"Unknown instance_id(s): {sorted(missing)}")

    if limit is not None:
        rows = rows[: max(0, limit)]
    return rows
