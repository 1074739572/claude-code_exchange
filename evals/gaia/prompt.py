"""GAIA question prompts (official answer format + anti-thrash)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Official system / instruction template from GAIA leaderboard content.py
GAIA_ANSWER_INSTRUCTIONS = """You are a general AI assistant. I will ask you a question. Report your thoughts, and finish your answer with the following template: FINAL ANSWER: [YOUR FINAL ANSWER]. YOUR FINAL ANSWER should be a number OR as few words as possible OR a comma separated list of numbers and/or strings. If you are asked for a number, don't use comma to write your number neither use units such as $ or percent sign unless specified otherwise. If you are asked for a string, don't use articles, neither abbreviations (e.g. for cities), and write the digits in plain text unless specified otherwise. If you are asked for a comma separated list, apply the above rules depending of whether the element to be put in the list is a number or a string."""

GAIA_TOOL_DISCIPLINE = """Tool discipline (important):
- Prefer `web_search` to discover URLs; then fetch at most 1–2 promising pages.
- If the same site keeps failing (robots/empty/403) or results stay irrelevant, CHANGE strategy or stop — do not issue 10+ near-duplicate searches.
- After ~8–12 web calls without a clear answer, commit to your best guess.
- Never install browsers or run long background installs during this task.
- You MUST end with exactly one line: FINAL ANSWER: <short answer>
  Even if uncertain, still output a best-effort FINAL ANSWER (empty is worse than wrong for scoring)."""

FORCE_FINAL_ANSWER_PROMPT = """STOP. Do not call any tools.

Based ONLY on evidence already in this conversation, output exactly one line and nothing else after it:
FINAL ANSWER: <your best short answer>

If you never found a solid source, still give your best guess in that format."""


def build_user_prompt(task: dict[str, Any], attachment: Path | None) -> str:
    parts = [
        GAIA_ANSWER_INSTRUCTIONS,
        "",
        GAIA_TOOL_DISCIPLINE,
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
            "When finished, end with exactly:",
            "FINAL ANSWER: <your short answer>",
        ]
    )
    return "\n".join(parts)
