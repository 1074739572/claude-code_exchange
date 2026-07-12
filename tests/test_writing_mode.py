"""Tests for writing-mode detection."""

from harness.prompts.lookup import is_lookup_query
from harness.prompts.writing import augment_query, is_writing_query


def test_thesis_rewrite_triggers():
    assert is_writing_query("仿照样例写第2章引言，参考 files/样例")


def test_lookup_does_not_trigger_writing():
    q = "查找一下 pu keyang icml 论文"
    assert is_lookup_query(q)
    assert not is_writing_query(q)


def test_code_task_does_not_trigger():
    assert not is_writing_query("改 harness/rag/tools.py 的 rag_search")


def test_augment_appends_constraint():
    q = "撰写结题报告第3章"
    out = augment_query(q)
    assert out.startswith(q)
    assert "[Writing mode" in out
