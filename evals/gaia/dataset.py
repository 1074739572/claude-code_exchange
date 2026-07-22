"""Load GAIA validation split (answers present)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_ROOT = REPO_ROOT / "test" / "gaia_dataset"
VALIDATION_META = Path("2023") / "validation" / "metadata.parquet"


def dataset_ready(root: Path | None = None) -> bool:
    root = root or DEFAULT_DATASET_ROOT
    return (root / VALIDATION_META).is_file()


def resolve_attachment(task: dict[str, Any], root: Path | None = None) -> Path | None:
    root = root or DEFAULT_DATASET_ROOT
    fp = task.get("file_path") or ""
    fn = task.get("file_name") or ""
    if isinstance(fp, str) and fp.strip():
        p = root / fp.replace("\\", "/").lstrip("./")
        if p.is_file():
            return p
    if isinstance(fn, str) and fn.strip():
        p = root / "2023" / "validation" / fn
        if p.is_file():
            return p
    return None


def load_validation(
    *,
    limit: int | None = None,
    level: int | None = None,
    task_ids: list[str] | None = None,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    """Load validation tasks that have a real Final answer (not ``?``)."""
    root = root or DEFAULT_DATASET_ROOT
    meta = root / VALIDATION_META
    if not meta.is_file():
        raise FileNotFoundError(
            f"GAIA validation metadata missing: {meta}\n"
            "Run: python -m evals.gaia --download"
        )

    df = pd.read_parquet(meta)
    # Keep only scored validation answers
    ans = df["Final answer"].fillna("").astype(str).str.strip()
    df = df[ans.ne("") & ans.ne("?")].copy()

    if level is not None:
        df = df[df["Level"].astype(int) == int(level)]
    if task_ids:
        wanted = set(task_ids)
        df = df[df["task_id"].astype(str).isin(wanted)]

    df = df.reset_index(drop=True)
    if limit is not None:
        df = df.head(int(limit))

    tasks: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        task = {c: row[c] for c in df.columns}
        # Annotator Metadata may be nested; keep as-is
        task["task_id"] = str(task["task_id"])
        task["Level"] = int(task["Level"])
        task["Final answer"] = str(task["Final answer"]).strip()
        task["Question"] = str(task["Question"])
        task["file_name"] = (
            "" if pd.isna(task.get("file_name")) else str(task["file_name"])
        )
        task["file_path"] = (
            "" if pd.isna(task.get("file_path")) else str(task["file_path"])
        )
        tasks.append(task)
    return tasks
