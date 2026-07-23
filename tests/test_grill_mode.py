"""Tests for /mode grill (confirm-before-execute + builtin grill-me)."""

from __future__ import annotations

import unittest

from harness.modes import (
    get_mode_profile,
    is_execute_unlocked,
    list_mode_ids,
    looks_like_execute_confirm,
    looks_like_execute_relock,
    mode_builtin_skills_section,
    mode_disables_tool,
    mode_prompt_section,
    note_user_query_for_mode,
    set_execute_unlocked,
    set_mode,
)


class GrillModeTests(unittest.TestCase):
    def setUp(self) -> None:
        set_mode("direct")
        set_execute_unlocked(False)

    def tearDown(self) -> None:
        set_mode("direct")
        set_execute_unlocked(False)

    def test_grill_mode_is_registered(self) -> None:
        self.assertIn("grill", list_mode_ids())
        profile = get_mode_profile("grill")
        assert profile is not None
        self.assertTrue(profile.confirm_before_execute)
        self.assertEqual(profile.builtin_skills, ("grill-me",))
        self.assertIn("write_file", profile.disable_tools)

    def test_enter_grill_locks_and_shows_banner(self) -> None:
        set_execute_unlocked(True)
        note = set_mode("grill")
        self.assertFalse(is_execute_unlocked())
        self.assertIn("grill-me", note)
        self.assertIn("确认执行", note)
        self.assertTrue(mode_disables_tool("write_file"))
        self.assertTrue(mode_disables_tool("bash"))
        self.assertFalse(mode_disables_tool("read_file"))

    def test_confirm_unlocks_mutating_tools(self) -> None:
        set_mode("grill")
        self.assertTrue(mode_disables_tool("edit_file"))
        status = note_user_query_for_mode("确认执行，按刚才说的做")
        self.assertIsNotNone(status)
        self.assertTrue(is_execute_unlocked())
        self.assertFalse(mode_disables_tool("edit_file"))
        self.assertFalse(mode_disables_tool("bash"))
        prompt = mode_prompt_section()
        self.assertIn("UNLOCKED", prompt)

    def test_weak_affirmation_does_not_unlock(self) -> None:
        set_mode("grill")
        self.assertFalse(looks_like_execute_confirm("嗯"))
        self.assertFalse(looks_like_execute_confirm("好"))
        note_user_query_for_mode("嗯")
        self.assertFalse(is_execute_unlocked())

    def test_relock_phrase(self) -> None:
        set_mode("grill")
        note_user_query_for_mode("go ahead")
        self.assertTrue(is_execute_unlocked())
        self.assertTrue(looks_like_execute_relock("重新拷问"))
        note_user_query_for_mode("重新拷问一下边界情况")
        self.assertFalse(is_execute_unlocked())
        self.assertTrue(mode_disables_tool("write_file"))

    def test_builtin_skill_injected(self) -> None:
        set_mode("grill")
        body = mode_builtin_skills_section()
        self.assertIn("Builtin skill: grill-me", body)
        self.assertIn("One question at a time", body)


if __name__ == "__main__":
    unittest.main()
