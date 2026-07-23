"""Tests for HARNESS.md / AGENTS.md project instruction loading."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from harness.prompts.dynamic import build_session_context
from harness.prompts.project_md import (
    apply_project_instructions,
    find_project_md,
    format_project_instructions_block,
)


class TestProjectMd(unittest.TestCase):
    def test_prefers_harness_over_agents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text("# agents\nrun a", encoding="utf-8")
            (root / "HARNESS.md").write_text("# harness\nrun h", encoding="utf-8")
            with mock.patch.dict("os.environ", {"HARNESS_PROJECT_MD": "1"}, clear=False):
                result = find_project_md(root)
            self.assertEqual(result.source_name, "HARNESS.md")
            self.assertIn("run h", result.text)
            self.assertNotIn("run a", result.text)

    def test_falls_back_to_agents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text("# agents\npytest -q", encoding="utf-8")
            with mock.patch.dict("os.environ", {"HARNESS_PROJECT_MD": "1"}, clear=False):
                result = find_project_md(root)
            self.assertEqual(result.source_name, "AGENTS.md")
            self.assertIn("pytest -q", result.text)

    def test_nearest_wins_walk_up(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            child = root / "pkg" / "sub"
            child.mkdir(parents=True)
            (root / "HARNESS.md").write_text("ROOT_RULES", encoding="utf-8")
            (child / "HARNESS.md").write_text("CHILD_RULES", encoding="utf-8")
            with mock.patch.dict("os.environ", {"HARNESS_PROJECT_MD": "1"}, clear=False):
                result = find_project_md(child)
            self.assertEqual(result.text, "CHILD_RULES")
            self.assertTrue(str(result.path).endswith("HARNESS.md"))

    def test_stops_at_git_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            outer = Path(tmp)
            repo = outer / "repo"
            nested = repo / "src"
            nested.mkdir(parents=True)
            (outer / "HARNESS.md").write_text("OUTER", encoding="utf-8")
            (repo / ".git").mkdir()
            with mock.patch.dict("os.environ", {"HARNESS_PROJECT_MD": "1"}, clear=False):
                result = find_project_md(nested)
            self.assertEqual(result.status, "no project instructions")
            self.assertFalse(result.loaded)

    def test_disabled_via_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "HARNESS.md").write_text("SHOULD_NOT_LOAD", encoding="utf-8")
            with mock.patch.dict("os.environ", {"HARNESS_PROJECT_MD": "0"}, clear=False):
                result = find_project_md(root)
            self.assertFalse(result.enabled)
            self.assertFalse(result.loaded)
            self.assertIn("disabled", result.status)

    def test_truncates_and_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "HARNESS.md").write_text("X" * 5000, encoding="utf-8")
            with mock.patch.dict(
                "os.environ",
                {"HARNESS_PROJECT_MD": "1", "HARNESS_PROJECT_MD_MAX_CHARS": "100"},
                clear=False,
            ):
                result = find_project_md(root, max_chars=100)
            self.assertTrue(result.truncated)
            self.assertLessEqual(len(result.text), 101)
            self.assertIn("[truncated]", result.status)

    def test_apply_and_ephemeral_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "HARNESS.md").write_text(
                "# Overview\nDemo app\n\n# Commands\npytest\n",
                encoding="utf-8",
            )
            ctx: dict = {}
            with mock.patch.dict("os.environ", {"HARNESS_PROJECT_MD": "1"}, clear=False):
                apply_project_instructions(ctx, start=root)
            block = format_project_instructions_block(ctx)
            self.assertIn('<project-instructions source="HARNESS.md">', block)
            self.assertIn("Demo app", block)
            # Session context should include the block when present.
            with mock.patch(
                "harness.prompts.dynamic.mode_prompt_section",
                return_value="Mode: direct",
            ):
                with mock.patch(
                    "harness.prompts.dynamic.get_model",
                    return_value="test-model",
                ):
                    with mock.patch(
                        "harness.prompts.dynamic.get_model_profile",
                    ) as profile:
                        profile.return_value = mock.Mock(
                            provider="x",
                            api_model="test-model",
                            thinking=False,
                        )
                        with mock.patch(
                            "harness.prompts.dynamic.get_provider",
                        ) as provider:
                            provider.return_value = mock.Mock(label="X")
                            with mock.patch(
                                "harness.prompts.dynamic.model_label",
                                return_value="test-model",
                            ):
                                with mock.patch(
                                    "harness.prompts.dynamic.mode_lead_model_hint",
                                    return_value=None,
                                ):
                                    with mock.patch(
                                        "harness.prompts.dynamic.get_todos",
                                        return_value=[],
                                    ):
                                        text = build_session_context(
                                            ctx,
                                            include_time=False,
                                            include_memories=False,
                                            include_mcp=False,
                                            include_teammates=False,
                                        )
            self.assertIn("project-instructions", text)
            self.assertIn("Demo app", text)


if __name__ == "__main__":
    unittest.main()
