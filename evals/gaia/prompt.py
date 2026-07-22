"""GAIA question prompts — scoring format only; research discipline is shared.

Research / lookup rules live in `harness.prompts.lookup` (RESEARCH_DISCIPLINE +
LOOKUP_CONSTRAINT + ANSWER_BOUNDARY_CHECK) so daily CLI and GAIA eval share one
capability path. This module only adds leaderboard answer formatting.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harness.prompts.lookup import ANSWER_BOUNDARY_CHECK, append_lookup_constraint

# Official answer template from GAIA leaderboard content.py (scoring-specific).
GAIA_ANSWER_INSTRUCTIONS = """You are a general AI assistant. I will ask you a question. Report your thoughts, and finish your answer with the following template: FINAL ANSWER: [YOUR FINAL ANSWER]. YOUR FINAL ANSWER should be a number OR as few words as possible OR a comma separated list of numbers and/or strings. If you are asked for a number, don't use comma to write your number neither use units such as $ or percent sign unless specified otherwise. If you are asked for a string, don't use articles, neither abbreviations (e.g. for cities), and write the digits in plain text unless specified otherwise. If you are asked for a comma separated list, apply the above rules depending of whether the element to be put in the list is a number or a string.

Before solving, restate in one short line (then proceed):
- WHAT is asked (exact quantity / name / title / list)
- UNIT & FORMAT: e.g. "how many thousand X" → answer in thousands; round-to-N; no comma; "First M. Last"; "as it appears in..."
- What counts as a valid answer (number only? full title? comma list?)

Before writing FINAL ANSWER, verify:
1. Re-read the question. Does your answer match the asked UNIT?
   ("how many thousand hours" → 17, not 17000)
2. Number: no commas, no units ($/%) unless asked.
3. String: no articles (a/the), no abbreviations, digits in plain text.
4. List: comma-separated, each element following the above rules.
5. Type match: asked for a title → full exact title; asked for a name → that name form."""

# Thin eval-only reminders on top of shared LOOKUP_CONSTRAINT.
GAIA_SCORING_REMINDER = f"""GAIA scoring (eval only):
- You MUST end with exactly one line: FINAL ANSWER: <short answer>
  Empty is worse than wrong for scoring — always output a best-effort answer.
- Never install browsers or run long background installs during this task.
- After the shared lookup budget is exhausted / LookupGuard blocks, commit to
  your best answer from evidence already in this conversation.
{ANSWER_BOUNDARY_CHECK}"""

FORCE_FINAL_ANSWER_PROMPT = f"""STOP. Do not call any tools.

Based ONLY on evidence already fetched/read in this conversation (not unverified memory), output exactly one line and nothing else after it:
FINAL ANSWER: <your best short answer>

{ANSWER_BOUNDARY_CHECK}
If you never found a solid source, still give your best guess in that format."""


def build_user_prompt(task: dict[str, Any], attachment: Path | None) -> str:
    """Build the user message: scoring template + question + shared lookup rules."""
    parts = [
        GAIA_ANSWER_INSTRUCTIONS,
        "",
        GAIA_SCORING_REMINDER,
        "",
        f"Task id: {task['task_id']}",
        f"Level: {task['Level']}",
        "",
        "Question:",
        task["Question"].strip(),
    ]
    if attachment is not None:
        parts.extend(
            [
                "",
                "An attachment file is provided for this question.",
                f"Attachment path (absolute): {attachment}",
                "Use tools (read_file / bash / web_search / etc.) as needed to inspect it.",
            ]
        )
    parts.extend(
        [
            "",
            "Start by restating WHAT / UNIT&FORMAT / valid answer shape in one line, "
            "then solve. End with exactly:",
            "FINAL ANSWER: <your short answer>",
        ]
    )
    # Same constraint block daily CLI appends on lookup queries.
    return append_lookup_constraint("\n".join(parts))
