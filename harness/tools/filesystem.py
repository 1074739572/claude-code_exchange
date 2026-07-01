"""Filesystem and shell tools."""

from __future__ import annotations

import subprocess
from pathlib import Path

from harness.settings import WORKDIR


def safe_path(path: str, cwd: Path | None = None) -> Path:
    base = cwd or WORKDIR
    resolved = (base / path).resolve()
    if not resolved.is_relative_to(base):
        raise ValueError(f"Path escapes workspace: {path}")
    return resolved


def run_bash(
    command: str,
    cwd: Path | None = None,
    run_in_background: bool = False,
) -> str:
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd or WORKDIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        out = (result.stdout + result.stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"


def run_read(
    path: str,
    limit: int | None = None,
    offset: int = 0,
    cwd: Path | None = None,
) -> str:
    try:
        lines = safe_path(path, cwd).read_text(encoding="utf-8").splitlines()
        offset = max(int(offset or 0), 0)
        limit = int(limit) if limit is not None else None
        lines = lines[offset:]
        if limit is not None and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more lines)"]
        return "\n".join(lines)
    except Exception as exc:
        return f"Error: {exc}"


def run_write(path: str, content: str, cwd: Path | None = None) -> str:
    try:
        target = safe_path(path, cwd)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as exc:
        return f"Error: {exc}"


def run_edit(
    path: str,
    old_text: str,
    new_text: str,
    cwd: Path | None = None,
) -> str:
    try:
        target = safe_path(path, cwd)
        text = target.read_text(encoding="utf-8")
        if old_text not in text:
            return f"Error: text not found in {path}"
        target.write_text(text.replace(old_text, new_text, 1), encoding="utf-8")
        return f"Edited {path}"
    except Exception as exc:
        return f"Error: {exc}"


def run_glob(pattern: str, cwd: Path | None = None) -> str:
    import glob as globlib

    try:
        base = cwd or WORKDIR
        results = []
        for match in globlib.glob(pattern, root_dir=base):
            if (base / match).resolve().is_relative_to(base):
                results.append(match)
        return "\n".join(results) if results else "(no matches)"
    except Exception as exc:
        return f"Error: {exc}"
