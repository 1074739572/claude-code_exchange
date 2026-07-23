"""CLI commands for manual RAG corpus management."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from harness.rag.bootstrap import ensure_rag_indexed
from harness.rag.config import SUPPORTED_SUFFIXES
from harness.rag.doc_picker import run_doc_picker
from harness.rag.ingest import resolve_path
from harness.rag.qa import answer_question
from harness.rag.selection import (
    SCOPE_ALL,
    clear_selection,
    format_selection_summary,
    load_selection,
    set_scope,
    set_selection,
)
from harness.rag.sources import format_docs_list, resolve_source_numbers
from harness.rag.tools import run_rag_index, run_rag_status


def _cwd() -> Path:
    return Path.cwd()


def _corpus_dir() -> Path:
    return _cwd() / "files"


def _rag_dir() -> Path:
    return _cwd() / ".rag"


def rag_help_text() -> str:
    corpus = _corpus_dir()
    return f"""RAG / file mode:

  /mode file                enter file mode (every turn: retrieve then answer)
  /mode direct              back to direct Agent mode

  /rag                      this help
  /rag status               index stats
  /rag docs                 list indexed documents (numbered)
  /rag pick                 multi-select docs for file-mode scope
  /rag select 1,3|all|clear set scope by number / all / clear(=all)
  /rag ask <question>       one-shot Q&A (in file mode just type the question)
  /rag index [path]         build or refresh index (default: files/)
  /rag add <file>           import external file into files/ then index
  /rag reset                wipe .rag/ (clean rebuild)

Corpus: {corpus}
Index:   {_rag_dir()}

Recommended: /rag index files -> /mode file -> ask questions -> /mode direct"""


def _normalize_user_path(raw: str) -> Path:
    text = raw.strip().strip('"').strip("'")
    path = Path(text)
    if path.is_absolute():
        return path
    return (_cwd() / path).resolve()


def run_rag_add(source: str) -> str:
    """Import a document into files/ (skip copy if already under files/) and re-index."""
    if not source.strip():
        return "Usage: /rag add <path-to-file.pdf|.docx|.md|.txt>"

    src = _normalize_user_path(source)
    if not src.exists():
        return f"rag add failed: file not found: {src}"
    if not src.is_file():
        return f"rag add failed: not a file: {src}"

    suffix = src.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        supported = ", ".join(sorted(SUPPORTED_SUFFIXES))
        return f"rag add failed: unsupported suffix {suffix!r} (supported: {supported})"

    dest_dir = _corpus_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    try:
        src.relative_to(dest_dir.resolve())
        already_inside = True
    except ValueError:
        already_inside = False

    if already_inside:
        lines.append(f"已在 files/ 内，不再复制: {src}")
        lines.append("提示：对 files/样例/ 里的文件请用 /rag index files，勿 /rag add（会在根目录再拷一份）。")
    else:
        dest = dest_dir / src.name
        if dest.exists() and dest.resolve() != src.resolve():
            lines.append(f"覆盖已有: {dest.name}")
        shutil.copy2(src, dest)
        lines.append(f"已导入: {dest}")

    lines.append("")
    result = ensure_rag_indexed("files")
    lines.append(result.get("message") or str(result))
    if not result.get("ok"):
        return "\n".join(lines)
    return "\n".join(lines)


def run_rag_reset() -> str:
    """Delete .rag/ artifacts so the next index starts clean."""
    import shutil as _shutil

    from harness.rag.config import RAG_DIR
    from harness.rag.pipeline import reset_runtime
    from harness.rag.selection import clear_selection

    reset_runtime()
    if RAG_DIR.exists():
        _shutil.rmtree(RAG_DIR, ignore_errors=True)
    clear_selection()
    return (
        f"已清空索引目录: {RAG_DIR}\n"
        "下一步：确认 files/ 语料无重复后，执行 /rag index files"
    )


def run_rag_index_command(path: str = "files") -> str:
    """Index a corpus path without going through the agent tool."""
    target = (path or "files").strip()
    if not target:
        target = "files"
    try:
        resolved = resolve_path(target)
    except Exception as exc:
        return f"rag index failed: {type(exc).__name__}: {exc}"

    if not resolved.exists():
        return (
            f"rag index failed: path not found: {resolved}\n"
            f"Create {_corpus_dir()} and add .md/.txt/.docx/.pdf, "
            "or use /rag add <file>."
        )

    result = ensure_rag_indexed(target)
    if result.get("ok"):
        return result.get("message") or run_rag_index(target)
    return result.get("message") or f"rag index failed: {result}"


def run_rag_select_command(spec: str = "") -> str:
    text = spec.strip()
    if not text:
        parts = [format_selection_summary(), "", format_docs_list()]
        return "\n".join(parts)

    lowered = text.lower()
    if lowered in ("clear", "none", "reset"):
        clear_selection()
        return "已设为搜全部已索引文档（selection cleared）。"
    if lowered == "all":
        set_scope(SCOPE_ALL)
        return "已设为搜全部已索引文档。"

    numbers: list[int] = []
    for token in re.split(r"[,;\s]+", text):
        token = token.strip()
        if token.isdigit():
            numbers.append(int(token))

    if not numbers:
        return (
            f"Unknown selection spec: {spec!r}\n"
            "Use: /rag select 1,3  |  /rag select all  |  /rag select clear"
        )

    resolved = resolve_source_numbers(numbers)
    if not resolved:
        return (
            f"No documents matched: {spec}\n"
            "Run /rag docs to see valid numbers."
        )

    chosen = set_selection(resolved)
    lines = [f"已指定 {len(chosen)} 个文档（文件模式只在这些里检索）:"]
    lines.extend(f"  - {name}" for name in chosen)
    return "\n".join(lines)


def run_rag_ask_command(question: str) -> str:
    if not question.strip():
        return (
            f"Usage: /rag ask <your question>\n\n{format_selection_summary()}\n\n"
            "Tip: /mode file 后可直接提问；或 /rag pick 指定文档。"
        )
    return answer_question(question)


def run_rag_cli_command(query: str) -> str:
    """Handle /rag and subcommands from the interactive CLI."""
    parts = query.strip().split()
    if len(parts) == 1:
        return rag_help_text()

    sub = parts[1].lower()
    if sub in ("help", "?"):
        return rag_help_text()
    if sub == "status":
        return run_rag_status()
    if sub == "docs":
        return format_docs_list()
    if sub == "pick":
        return run_doc_picker()
    if sub == "select":
        spec = query.strip().split(maxsplit=2)[2] if len(parts) > 2 else ""
        return run_rag_select_command(spec)
    if sub == "ask":
        question = query.strip().split(maxsplit=2)[2] if len(parts) > 2 else ""
        return run_rag_ask_command(question)
    if sub == "index":
        path = parts[2] if len(parts) > 2 else "files"
        return run_rag_index_command(path)
    if sub == "reset":
        return run_rag_reset()
    if sub == "add":
        if len(parts) < 3:
            return "Usage: /rag add <path-to-file>"
        path = query.strip().split(maxsplit=2)[2]
        return run_rag_add(path)

    return (
        f"Unknown /rag subcommand: {sub}\n\n"
        f"{rag_help_text()}"
    )
