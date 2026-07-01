"""Parse corpus files and write chunk JSONL artifacts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from harness.rag.chunking import chunk_docx, chunk_markdown
from harness.rag.config import (
    CHUNKS_DIR,
    DEFAULT_CORPUS,
    MANIFEST_PATH,
    RAG_DIR,
    SUPPORTED_SUFFIXES,
)
from harness.settings import PACKAGE_ROOT, WORKDIR


def resolve_path(path: str | None) -> Path:
    if not path:
        candidate = DEFAULT_CORPUS
        if candidate.exists():
            return candidate
        return WORKDIR / "files" / "样例"

    raw = Path(path)
    if raw.is_absolute():
        return raw
    for base in (WORKDIR, PACKAGE_ROOT):
        candidate = (base / raw).resolve()
        if candidate.exists():
            return candidate
    return (WORKDIR / raw).resolve()


def discover_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix.lower() in SUPPORTED_SUFFIXES else []
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
            files.append(path)
    return files


def _source_label(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return path.name


def parse_file(path: Path, source: str) -> list[dict]:
    suffix = path.suffix.lower()
    if suffix in (".md", ".txt"):
        text = path.read_text(encoding="utf-8", errors="replace")
        return [chunk.to_dict() for chunk in chunk_markdown(source, text)]
    if suffix == ".docx":
        return [chunk.to_dict() for chunk in chunk_docx(source, path)]
    return []


def load_chunks_for_source(source: str) -> list[dict]:
    safe_name = source.replace("/", "__").replace("\\", "__")
    path = CHUNKS_DIR / f"{safe_name}.chunks.jsonl"
    if not path.exists():
        return []
    chunks = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    return chunks


def write_chunks_jsonl(source: str, chunks: list[dict]) -> Path:
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = source.replace("/", "__").replace("\\", "__")
    out = CHUNKS_DIR / f"{safe_name}.chunks.jsonl"
    with out.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    return out


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {"sources": {}, "embedding_model": None}
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def save_manifest(manifest: dict) -> None:
    RAG_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def ingest_path(path: str | None = None) -> dict:
    root = resolve_path(path)
    if not root.exists():
        raise FileNotFoundError(f"Corpus path not found: {root}")

    files = discover_files(root)
    if not files:
        raise FileNotFoundError(f"No supported files (.md/.txt/.docx) under: {root}")

    manifest = load_manifest()
    manifest.setdefault("sources", {})
    indexed = []

    for file_path in files:
        source = _source_label(file_path, root)
        stat = file_path.stat()
        chunks = parse_file(file_path, source)
        write_chunks_jsonl(source, chunks)
        manifest["sources"][source] = {
            "path": str(file_path),
            "mtime": stat.st_mtime,
            "chars": sum(len(c["text"]) for c in chunks),
            "chunks": len(chunks),
            "suffix": file_path.suffix.lower(),
            "indexed_at": datetime.now(timezone.utc).isoformat(),
        }
        indexed.append(
            {
                "source": source,
                "chunks": len(chunks),
                "chars": sum(len(c["text"]) for c in chunks),
            }
        )

    manifest["corpus_root"] = str(root)
    manifest["indexed_at"] = datetime.now(timezone.utc).isoformat()
    save_manifest(manifest)
    return {"root": str(root), "files": indexed, "total_chunks": sum(f["chunks"] for f in indexed)}
