"""Tests for usage cache field normalization."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from harness.usage import parse_cache_usage


class TestParseCacheUsage(unittest.TestCase):
    def test_deepseek_cache_read(self) -> None:
        usage = SimpleNamespace(
            input_tokens=76,
            output_tokens=5,
            cache_read_input_tokens=3200,
            cache_creation_input_tokens=0,
        )
        parsed = parse_cache_usage(usage)
        assert parsed is not None
        self.assertEqual(parsed.hit_tokens, 3200)
        self.assertEqual(parsed.miss_tokens, 76)

    def test_prompt_cache_hit_fields(self) -> None:
        usage = SimpleNamespace(
            prompt_cache_hit_tokens=1000,
            prompt_cache_miss_tokens=200,
            output_tokens=10,
        )
        parsed = parse_cache_usage(usage)
        assert parsed is not None
        self.assertEqual(parsed.hit_tokens, 1000)
        self.assertEqual(parsed.miss_tokens, 200)


if __name__ == "__main__":
    unittest.main()
