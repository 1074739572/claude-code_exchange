"""Download GAIA via ModelScope (no Hugging Face login)."""

from __future__ import annotations

import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

from evals.gaia.dataset import DEFAULT_DATASET_ROOT

MS_BASE = (
    "https://modelscope.cn/api/v1/datasets/AI-ModelScope/GAIA/"
    "repo?Revision=master&FilePath="
)

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

META_FILES = [
    "README.md",
    "2023/validation/metadata.parquet",
    "2023/test/metadata.parquet",
]


def _download(rel: str, out: Path, *, force: bool = False) -> Path:
    dest = out / rel
    if dest.exists() and dest.stat().st_size > 0 and not force:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = MS_BASE + rel.replace("/", "%2F")
    print(f"DL {rel}", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, context=SSL_CTX, timeout=180) as resp:
        data = resp.read()
    dest.write_bytes(data)
    print(f"  -> {dest} ({len(data)} bytes)", flush=True)
    return dest


def _attachment_paths(out: Path, split: str) -> list[str]:
    meta = out / f"2023/{split}/metadata.parquet"
    if not meta.is_file():
        return []
    df = pd.read_parquet(meta)
    paths: set[str] = set()
    for _, row in df.iterrows():
        fp = row.get("file_path")
        fn = row.get("file_name")
        if isinstance(fp, str) and fp.strip():
            paths.add(fp.replace("\\", "/").lstrip("./"))
        elif isinstance(fn, str) and fn.strip():
            paths.add(f"2023/{split}/{fn}")
    return sorted(paths)


def download_gaia(
    out: Path | None = None,
    *,
    attachments: bool = True,
    validation_only: bool = False,
) -> Path:
    out = out or DEFAULT_DATASET_ROOT
    out.mkdir(parents=True, exist_ok=True)
    print(f"Downloading GAIA via ModelScope -> {out}")
    for rel in META_FILES:
        if validation_only and "/test/" in rel:
            continue
        try:
            _download(rel, out)
        except urllib.error.HTTPError as e:
            print(f"  FAIL {rel}: HTTP {e.code}", flush=True)
            raise

    if attachments:
        splits = ("validation",) if validation_only else ("validation", "test")
        ok = fail = 0
        for split in splits:
            paths = _attachment_paths(out, split)
            print(f"\n{split}: {len(paths)} attachments", flush=True)
            for i, rel in enumerate(paths):
                try:
                    _download(rel, out)
                    ok += 1
                except Exception as e:  # noqa: BLE001
                    fail += 1
                    print(f"  FAIL {rel}: {type(e).__name__}: {e}", flush=True)
                if (i + 1) % 25 == 0:
                    print(f"  ... {i + 1}/{len(paths)}", flush=True)
        print(f"attachments ok={ok} fail={fail}")

    v = pd.read_parquet(out / "2023/validation/metadata.parquet")
    print(f"validation questions: {len(v)}")
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Download GAIA (ModelScope)")
    p.add_argument("--validation-only", action="store_true")
    p.add_argument("--no-attachments", action="store_true")
    args = p.parse_args(argv)
    download_gaia(
        attachments=not args.no_attachments,
        validation_only=args.validation_only,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
