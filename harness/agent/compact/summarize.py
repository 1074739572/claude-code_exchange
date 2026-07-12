"""LLM summarization for compacted conversation history."""

from __future__ import annotations

import json

from harness.agent.compact.sizing import _safe_input_budget
from harness.llm import create_message
from harness.models import get_model
from harness.settings import WORKDIR
from harness.tools.dispatch import extract_text

_STRUCTURED_SUMMARY_SECTIONS = (
    "## Goal",
    "## User Constraints",
    "## Changed Files",
    "## Key Findings",
    "## Remaining Work",
    "## Do NOT Forget",
)


def _structured_summary_instruction() -> str:
    sections = "\n".join(_STRUCTURED_SUMMARY_SECTIONS)
    return (
        f"Working directory: {WORKDIR}\n"
        "Python package lives at `harness/` in this repo (NOT `src/harness/`).\n"
        "Summarize this coding-agent conversation so work can continue after compaction.\n"
        "Use exactly these markdown headings and fill each section:\n"
        f"{sections}\n\n"
        "Guidelines:\n"
        "- Goal: MUST reflect the chronologically latest real user instruction, "
        "not an older task from earlier in the conversation.\n"
        "- If the latest user message conflicts with earlier goals or a previous "
        "summary, the latest user message wins — say so in Goal and Do NOT Forget.\n"
        "- User Constraints: explicit requirements, paths, formats, tone, deadlines.\n"
        "- Changed Files: bullet list of paths touched and what changed.\n"
        "- Key Findings: facts, errors, metrics, or decisions that must survive compaction.\n"
        "- Remaining Work: concrete next steps; include drift complaints or wrong paths.\n"
        "- For lookup / paper-search tasks: if sources failed or budget is spent, "
        "Remaining Work MUST be 'answer 有/没有 now' — never 'try more URLs'.\n"
        "- Do NOT Forget: non-negotiables the agent must not drop (e.g. sample doc paths).\n"
    )


def summarize_history(messages: list) -> str:
    budget = _safe_input_budget()
    conversation = json.dumps(messages, default=str)[:budget]
    prompt = (
        _structured_summary_instruction()
        + f"\n[Conversation trimmed to last {budget} chars for summarization]\n\n"
        + conversation
    )
    try:
        response = create_message(
            model_id=get_model(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
        )
        return extract_text(response.content) or "(empty summary)"
    except Exception as exc:
        return (
            f"[Compact summary unavailable: {exc}]\n"
            "Earlier conversation was trimmed to fit the model input limit. "
            "Re-issue your last instruction if the agent seems to have lost context."
        )
