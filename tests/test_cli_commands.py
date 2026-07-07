"""CLI command routing tests."""

from __future__ import annotations

import unittest

from harness.cli import _match_cli_command


class TestCliCommands(unittest.TestCase):
    def test_model_does_not_match_mode(self) -> None:
        self.assertTrue(_match_cli_command("/model", "/model"))
        self.assertFalse(_match_cli_command("/model", "/mode"))
        self.assertTrue(_match_cli_command("/model qwen-max", "/model"))

    def test_mode(self) -> None:
        self.assertTrue(_match_cli_command("/mode", "/mode"))
        self.assertTrue(_match_cli_command("/mode direct", "/mode"))
        self.assertFalse(_match_cli_command("/model", "/mode"))


if __name__ == "__main__":
    unittest.main()
