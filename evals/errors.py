"""Shared eval exceptions."""

from __future__ import annotations


class EvalSkip(Exception):
    """Case should be marked SKIP."""


class EvalWarn(Exception):
    """Case should be marked WARN (known gap / soft check)."""
