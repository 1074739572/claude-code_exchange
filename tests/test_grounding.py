"""Tests for task grounding prompts and GroundingGuard."""

from harness.agent.grounding_guard import (
    BLOCK_MESSAGE,
    GroundingGuard,
    has_strong_deixis,
    looks_concrete,
    response_has_intent_text,
    strip_lookup_constraint,
)
from harness.prompts.lookup import LOOKUP_CONSTRAINT, augment_query
from harness.prompts.sections import PROMPT_SECTIONS
from harness.prompts.static import assemble_static_system_prompt


def test_identity_is_product_not_coding_only():
    """OpenHands/CC-style: thin product identity; coding is a mode, not the persona."""
    identity = PROMPT_SECTIONS["identity"]
    assert "You are Harness" in identity
    assert "<ROLE>" in identity
    assert "coding agent" not in identity.lower()
    assert "Match the request" in identity or "whatever the user actually asked" in identity
    assert "do not start editing" in identity.lower() or "unless they asked to" in identity
    assert "1–3 short sentences" in identity
    assert "Resolve → Act → Close" not in identity  # lives in DIRECT mode prompt


def test_static_prompt_includes_grounding():
    prompt = assemble_static_system_prompt()
    assert "You are Harness" in prompt
    assert "Task grounding" in prompt
    assert "Working goal" in prompt
    assert "Never put assumptions" in prompt
    assert prompt.index("You are Harness") < prompt.index("Task grounding")


def test_direct_mode_owns_resolve_act_close():
    from harness.modes import get_mode_profile

    direct = get_mode_profile("direct")
    assert direct is not None
    assert "Resolve → Act → Close" in direct.prompt


def test_lookup_constraint_asks_before_guessing_slots():
    assert "关键检索条件" in LOOKUP_CONSTRAINT
    assert "禁止用 fetch" in LOOKUP_CONSTRAINT
    assert "≤8 行" in LOOKUP_CONSTRAINT
    q = augment_query("查找 pu keyang ICML 2026 论文")
    assert "[Lookup mode — auto]" in q
    assert "先用纯文字问用户" in q


def test_has_strong_deixis():
    assert has_strong_deixis("这个指标是多少")
    assert has_strong_deixis("上面那个怎么改")
    assert has_strong_deixis("Look at that one again")
    assert not has_strong_deixis("打开 harness/loop.py 第 12 行")
    assert not has_strong_deixis("实现登录功能")


def test_looks_concrete_paths():
    assert looks_concrete("打开 harness/loop.py 第 12 行")
    assert looks_concrete("read `foo.py`")
    assert not looks_concrete("这个指标是多少")


def test_strip_lookup_constraint():
    raw = "查这个作者" + LOOKUP_CONSTRAINT
    assert strip_lookup_constraint(raw) == "查这个作者"
    assert has_strong_deixis(raw)


def test_guard_blocks_deixis_bare_tools():
    guard = GroundingGuard()
    messages = [{"role": "user", "content": "这个指标是多少？"}]
    content = [
        {
            "type": "tool_use",
            "id": "t1",
            "name": "rag_search",
            "input": {"query": "指标"},
        }
    ]
    block, msg = guard.evaluate(messages, content)
    assert block is True
    assert "GroundingGuard" in msg
    assert msg == BLOCK_MESSAGE
    assert guard.armed is False
    # Second batch never blocks again
    block2, _ = guard.evaluate(messages, content)
    assert block2 is False


def test_guard_allows_with_working_goal_text():
    guard = GroundingGuard()
    messages = [{"role": "user", "content": "这个指标是多少？"}]
    content = [
        {"type": "text", "text": "Working goal: 查 metrics.md 里的 FY-4 性能指标"},
        {
            "type": "tool_use",
            "id": "t1",
            "name": "rag_search",
            "input": {"query": "FY-4 性能指标"},
        },
    ]
    assert response_has_intent_text(content) is True
    block, _ = guard.evaluate(messages, content)
    assert block is False


def test_guard_allows_concrete_path_request():
    guard = GroundingGuard()
    # Even if somehow deixis appears with a path, concrete wins
    messages = [{"role": "user", "content": "看看这个 harness/loop.py:12"}]
    content = [
        {
            "type": "tool_use",
            "id": "t1",
            "name": "read_file",
            "input": {"path": "harness/loop.py"},
        }
    ]
    block, _ = guard.evaluate(messages, content)
    assert block is False


def test_guard_allows_no_deixis_bare_tools():
    guard = GroundingGuard()
    messages = [{"role": "user", "content": "列出 tests 目录下的文件"}]
    content = [
        {
            "type": "tool_use",
            "id": "t1",
            "name": "bash",
            "input": {"command": "ls tests"},
        }
    ]
    block, _ = guard.evaluate(messages, content)
    assert block is False
    assert guard.armed is False
