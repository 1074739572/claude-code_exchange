"""Indexed document listing helpers."""

from __future__ import annotations

from harness.rag.ingest import load_manifest
from harness.rag.selection import load_selection


def list_indexed_sources() -> list[dict]:
    manifest = load_manifest()
    sources = manifest.get("sources") or {}
    selected = set(load_selection())
    rows: list[dict] = []
    for index, (name, meta) in enumerate(sorted(sources.items()), start=1):
        rows.append(
            {
                "index": index,
                "source": name,
                "chunks": meta.get("chunks", 0),
                "parent_chunks": meta.get("parent_chunks", 0),
                "child_chunks": meta.get("child_chunks", 0),
                "chars": meta.get("chars", 0),
                "suffix": meta.get("suffix", ""),
                "selected": name in selected,
            }
        )
    return rows


def resolve_source_numbers(numbers: list[int]) -> list[str]:
    rows = list_indexed_sources()
    by_index = {row["index"]: row["source"] for row in rows}
    resolved: list[str] = []
    for number in numbers:
        source = by_index.get(number)
        if source and source not in resolved:
            resolved.append(source)
    return resolved


def format_docs_list() -> str:
    rows = list_indexed_sources()
    if not rows:
        return (
            "No indexed documents.\n"
            "Add files under files/ then run: /rag index files"
        )
    lines = ["Indexed documents (use numbers with /rag select or /rag pick):"]
    for row in rows:
        mark = "[x]" if row["selected"] else "[ ]"
        lines.append(
            f"  {row['index']:>2}. {mark} {row['source']} "
            f"({row.get('child_chunks', 0)} child chunks, {row.get('chars', 0)} chars)"
        )
    lines.append("")
    lines.append("Select: /rag pick  |  /rag select 1,3  |  /rag select all  |  /rag select clear")
    return "\n".join(lines)
