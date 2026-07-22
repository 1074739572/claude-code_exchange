"""Official GAIA quasi-exact-match scorer (from gaia-benchmark/leaderboard)."""

from __future__ import annotations

import re
import string
import warnings


def normalize_number_str(number_str: str) -> float:
    for char in ["$", "%", ","]:
        number_str = number_str.replace(char, "")
    try:
        return float(number_str)
    except ValueError:
        return float("inf")


def split_string(
    s: str,
    char_list: list[str] | None = None,
) -> list[str]:
    if char_list is None:
        char_list = [",", ";"]
    pattern = f"[{''.join(char_list)}]"
    return re.split(pattern, s)


def normalize_str(input_str: str, remove_punct: bool = True) -> str:
    """Remove whitespace, optionally punctuation; lowercase."""
    no_spaces = re.sub(r"\s", "", input_str)
    if remove_punct:
        translator = str.maketrans("", "", string.punctuation)
        return no_spaces.lower().translate(translator)
    return no_spaces.lower()


def question_scorer(model_answer: str | None, ground_truth: str) -> bool:
    """Return True if model_answer matches ground_truth under GAIA rules."""

    def is_float(element: object) -> bool:
        try:
            float(element)  # type: ignore[arg-type]
            return True
        except (ValueError, TypeError):
            return False

    if model_answer is None:
        model_answer = "None"
    model_answer = str(model_answer).strip()
    ground_truth = str(ground_truth).strip()

    if is_float(ground_truth):
        return normalize_number_str(model_answer) == float(ground_truth)

    if any(char in ground_truth for char in [",", ";"]):
        gt_elems = split_string(ground_truth)
        ma_elems = split_string(model_answer)
        if len(gt_elems) != len(ma_elems):
            warnings.warn(
                "Answer lists have different lengths, returning False.",
                UserWarning,
                stacklevel=2,
            )
            return False
        comparisons = []
        for ma_elem, gt_elem in zip(ma_elems, gt_elems):
            if is_float(gt_elem):
                comparisons.append(
                    normalize_number_str(ma_elem) == float(gt_elem)
                )
            else:
                comparisons.append(
                    normalize_str(ma_elem, remove_punct=False)
                    == normalize_str(gt_elem, remove_punct=False)
                )
        return all(comparisons)

    return normalize_str(model_answer) == normalize_str(ground_truth)


def extract_final_answer(text: str) -> str:
    """Pull ``FINAL ANSWER: ...`` from agent prose; else last short line."""
    if not text:
        return ""
    if text.strip().startswith("[Stopped]"):
        return ""
    patterns = [
        r"FINAL\s+ANSWER\s*[:：]\s*(.+)",
        r"Final\s+Answer\s*[:：]\s*(.+)",
        r"答案\s*[:：]\s*(.+)",
    ]
    for pat in patterns:
        matches = re.findall(pat, text, flags=re.IGNORECASE)
        if matches:
            ans = matches[-1].strip()
            ans = re.split(r"[\n\r]", ans)[0].strip()
            ans = ans.strip("`\"' ")
            if ans.startswith("[Stopped]"):
                continue
            return ans

    # Fallback: last non-empty short line
    for line in reversed(text.strip().splitlines()):
        line = line.strip().strip("`\"' ")
        if not line or line.startswith("[Stopped]"):
            continue
        if line.lower().startswith(("i ", "let ", "the ", "based ", "here")):
            continue
        if len(line) <= 200:
            return line
    return ""


def extract_final_answer_from_messages(messages: list) -> str:
    """Scan assistant turns (newest first) for FINAL ANSWER; skip stop stubs."""
    from harness.tools.dispatch import extract_text

    for msg in reversed(messages):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if isinstance(content, list) and any(
            isinstance(b, dict) and b.get("type") == "tool_use" for b in content
        ):
            # Still allow FINAL ANSWER text alongside tools
            text = extract_text(content)
        else:
            text = extract_text(content)
        ans = extract_final_answer(text)
        if ans:
            return ans
    return ""
