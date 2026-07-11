"""Agent / harness mini-eval suite.

Run offline (default)::

    python -m evals

Include live LLM smoke tests::

    python -m evals --live
"""

from evals.runner import main, run_evals

__all__ = ["main", "run_evals"]
