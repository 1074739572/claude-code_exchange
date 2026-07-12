"""Tests for WritingGuard."""

from harness.agent.writing_guard import WritingGuard, is_output_prose_path


def test_output_md_requires_rag():
    guard = WritingGuard(active=True)
    blocked, msg = guard.check_write("write_file", {"path": "output/01_引言.md", "content": "x"})
    assert blocked
    assert "WritingGuard" in msg


def test_output_after_rag_allowed():
    guard = WritingGuard(active=True)
    guard.note_tool("rag_search")
    blocked, _ = guard.check_write("write_file", {"path": "output/01.md", "content": "x"})
    assert not blocked


def test_harness_py_not_guarded():
    guard = WritingGuard(active=True)
    blocked, _ = guard.check_write("write_file", {"path": "harness/loop.py", "content": "x"})
    assert not blocked


def test_is_output_prose_path():
    assert is_output_prose_path("output/ch1.md")
    assert not is_output_prose_path("src/foo.md")
