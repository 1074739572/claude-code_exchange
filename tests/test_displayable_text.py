"""Tests for assistant displayable text detection."""

from harness.messages.blocks import has_displayable_text


def test_has_displayable_text_plain_string():
    assert has_displayable_text("hello")


def test_has_displayable_text_text_block():
    assert has_displayable_text([{"type": "text", "text": "找到了"}])


def test_thinking_only_is_not_displayable():
    content = [
        {"type": "thinking", "thinking": "let me analyze..."},
    ]
    assert not has_displayable_text(content)


def test_thinking_plus_text_is_displayable():
    content = [
        {"type": "thinking", "thinking": "internal"},
        {"type": "text", "text": "公开检索未找到。"},
    ]
    assert has_displayable_text(content)
