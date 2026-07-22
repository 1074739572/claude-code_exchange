"""GAIA validation eval for improved_harness.

Usage:
  python -m evals.gaia --download --validation-only
  python -m evals.gaia --limit 3
  python -m evals.gaia --level 1 --limit 5
  python -m evals.gaia --all
"""

from evals.gaia.run import main

__all__ = ["main"]
