"""Context compaction eval cases."""

from __future__ import annotations

from harness.agent.compact import (
    COMPACT_TAIL_COUNT,
    LATEST_USER_FOCUS_MARKER,
    find_latest_user_text,
    micro_compact,
)

from evals.types import EvalCase


def case_tail_count_positive() -> None:
    assert COMPACT_TAIL_COUNT >= 1


def case_find_latest_user() -> None:
    messages = [
        {"role": "user", "content": "old goal: refactor auth"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "new goal: fix typo only"},
    ]
    text = find_latest_user_text(messages)
    assert "fix typo only" in text
    assert "refactor auth" not in text


def case_micro_compact_persists() -> None:
    from harness.settings import KEEP_RECENT_TOOL_RESULTS

    big = "x" * 8000
    # Need more than KEEP_RECENT_TOOL_RESULTS tool_results so older ones compact.
    messages = []
    n = KEEP_RECENT_TOOL_RESULTS + 2
    for i in range(n):
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": f"tu_eval_{i}",
                        "content": big if i < 2 else "short",
                    }
                ],
            }
        )
    out = micro_compact(messages)
    first = str(out[0]["content"][0]["content"])
    assert len(first) < len(big), first[:200]
    assert "persisted-output" in first or "Full output" in first


def case_focus_marker_defined() -> None:
    assert LATEST_USER_FOCUS_MARKER
    assert "user" in LATEST_USER_FOCUS_MARKER.lower() or "Current" in LATEST_USER_FOCUS_MARKER


CASES = [
    EvalCase(
        "compact.tail_count",
        "compact keeps a positive message tail",
        "compact",
        case_tail_count_positive,
    ),
    EvalCase(
        "compact.latest_user",
        "find_latest_user_text picks newest user turn",
        "compact",
        case_find_latest_user,
    ),
    EvalCase(
        "compact.micro_persist",
        "micro_compact shrinks large tool_result",
        "compact",
        case_micro_compact_persists,
    ),
    EvalCase(
        "compact.focus_marker",
        "latest-user focus marker exists",
        "compact",
        case_focus_marker_defined,
    ),
]
