"""Prepare a local git checkout for one SWE-bench instance."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def _run(cmd: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(
        cmd,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def prepare_workspace(instance: dict[str, Any], root: Path) -> Path:
    """Clone repo and checkout base_commit. Returns workspace path."""
    instance_id = instance["instance_id"]
    repo = instance["repo"]  # e.g. django/django
    base_commit = instance["base_commit"]
    dest = root / instance_id

    if dest.exists() and (dest / ".git").exists():
        # Reset to base commit for a clean run
        try:
            _run(["git", "reset", "--hard", base_commit], cwd=dest)
            _run(["git", "clean", "-fdx"], cwd=dest)
            return dest
        except subprocess.CalledProcessError:
            # Fall through to fresh clone
            pass

    dest.mkdir(parents=True, exist_ok=True)
    # Fresh shallow-ish fetch of the exact commit
    if (dest / ".git").exists():
        import shutil

        shutil.rmtree(dest)
        dest.mkdir(parents=True, exist_ok=True)

    url = f"https://github.com/{repo}.git"
    _run(["git", "init"], cwd=dest)
    _run(["git", "remote", "add", "origin", url], cwd=dest)
    try:
        _run(["git", "fetch", "--depth", "1", "origin", base_commit], cwd=dest)
    except subprocess.CalledProcessError:
        # Some hosts reject shallow fetch of arbitrary SHA — deepen
        _run(["git", "fetch", "origin", base_commit], cwd=dest)
    _run(["git", "checkout", "--force", "FETCH_HEAD"], cwd=dest)
    return dest


def git_diff_patch(workspace: Path) -> str:
    """Return unified diff of all local changes (tracked + untracked)."""
    # Intent-to-add untracked so they appear in diff, without lasting staging.
    subprocess.run(
        ["git", "add", "-A"],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    proc = subprocess.run(
        ["git", "diff", "--cached", "HEAD"],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    patch = proc.stdout or ""
    subprocess.run(
        ["git", "reset", "HEAD"],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    # Keep working tree edits; only unstage.
    return patch if patch.endswith("\n") or not patch else patch + "\n"


def patch_nonempty(patch: str) -> bool:
    return bool(patch.strip())
