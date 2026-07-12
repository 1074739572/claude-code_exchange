"""Local RAG for long reference documents."""

from harness.rag.bootstrap import bootstrap_message, ensure_rag_indexed, index_is_empty
from harness.rag.eval import run_eval
from harness.rag.pipeline import build_index, search
from harness.rag.tools import run_rag_index, run_rag_search, run_rag_status

__all__ = [
    "bootstrap_message",
    "build_index",
    "ensure_rag_indexed",
    "index_is_empty",
    "run_eval",
    "run_rag_index",
    "run_rag_search",
    "run_rag_status",
    "search",
]
