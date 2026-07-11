"""Normalize provider usage / cache token fields across APIs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CacheUsage:
    hit_tokens: int
    miss_tokens: int
    output_tokens: int | None
    source: str

    @property
    def input_tokens(self) -> int:
        return self.hit_tokens + self.miss_tokens

    @property
    def hit_rate(self) -> float:
        total = self.input_tokens
        return self.hit_tokens / total if total else 0.0


def parse_cache_usage(usage) -> CacheUsage | None:
    """Extract cache hit/miss from Anthropic or DeepSeek-compatible usage objects."""
    if usage is None:
        return None

    output = getattr(usage, "output_tokens", None)

    # DeepSeek / Anthropic prompt caching (Messages API)
    read = getattr(usage, "cache_read_input_tokens", None)
    create = getattr(usage, "cache_creation_input_tokens", None)
    input_tokens = getattr(usage, "input_tokens", None)
    if read is not None or create is not None:
        hit = int(read or 0)
        billed_input = int(input_tokens or 0)
        # When cache_read is reported, input_tokens is typically the uncached tail.
        miss = billed_input
        if hit == 0 and create:
            miss = max(miss, int(create))
        return CacheUsage(
            hit_tokens=hit,
            miss_tokens=miss,
            output_tokens=output,
            source="cache_read_input_tokens",
        )

    hit = getattr(usage, "prompt_cache_hit_tokens", None)
    miss = getattr(usage, "prompt_cache_miss_tokens", None)
    if hit is not None or miss is not None:
        return CacheUsage(
            hit_tokens=int(hit or 0),
            miss_tokens=int(miss or 0),
            output_tokens=output,
            source="prompt_cache_hit_tokens",
        )

    if input_tokens is not None:
        return CacheUsage(
            hit_tokens=0,
            miss_tokens=int(input_tokens),
            output_tokens=output,
            source="input_tokens_only",
        )
    return None
