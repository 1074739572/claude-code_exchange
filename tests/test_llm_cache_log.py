"""Cache usage logging stays silent unless HARNESS_VERBOSE=1."""

from types import SimpleNamespace
from unittest.mock import patch

from harness.llm import _log_cache_usage


def _response(*, hit: int = 8, miss: int = 2, out: int = 3):
    usage = SimpleNamespace(
        prompt_cache_hit_tokens=hit,
        prompt_cache_miss_tokens=miss,
        output_tokens=out,
    )
    return SimpleNamespace(usage=usage)


def test_cache_usage_silenced_by_default(monkeypatch):
    monkeypatch.delenv("HARNESS_VERBOSE", raising=False)
    with (
        patch("harness.llm.record_usage") as record,
        patch("harness.llm.renderer") as renderer,
    ):
        _log_cache_usage(_response(), model_id="qwen-max")
        record.assert_called_once()
        renderer.muted.assert_not_called()


def test_cache_usage_prints_when_verbose(monkeypatch):
    monkeypatch.setenv("HARNESS_VERBOSE", "1")
    with (
        patch("harness.llm.record_usage"),
        patch("harness.llm.renderer") as renderer,
    ):
        _log_cache_usage(_response(), model_id="qwen-max")
        renderer.muted.assert_called_once()
        assert "hit=" in renderer.muted.call_args.args[0]
