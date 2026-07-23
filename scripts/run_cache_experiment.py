"""Run offline prompt-cache simulations or a live DeepSeek append-only A/B test."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import harness.settings  # noqa: E402,F401 - load repository .env
import harness.agent.compact.persist as persist_mod  # noqa: E402
from harness.agent.compact import (  # noqa: E402
    persist_recallable_output,
    stabilize_tool_output,
)
from harness.models import get_model_profile, initialize_model  # noqa: E402
from harness.prompts.cache_experiment import (  # noqa: E402
    format_results_table,
    run_all_simulations,
)
from harness.providers.router import create_provider_message  # noqa: E402
from harness.usage import parse_cache_usage  # noqa: E402


@dataclass
class LiveRound:
    round_index: int
    hit_tokens: int
    miss_tokens: int
    hit_rate: float


@dataclass
class LiveResult:
    strategy: str
    rounds: list[LiveRound]

    @property
    def warm_hit_tokens(self) -> int:
        return sum(item.hit_tokens for item in self.rounds[1:])

    @property
    def warm_miss_tokens(self) -> int:
        return sum(item.miss_tokens for item in self.rounds[1:])

    @property
    def warm_hit_rate(self) -> float:
        total = self.warm_hit_tokens + self.warm_miss_tokens
        return self.warm_hit_tokens / total if total else 0.0


def _tool_schema(name: str) -> list[dict]:
    return [
        {
            "name": name,
            "description": "Synthetic read tool used only for prompt-cache measurement.",
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        }
    ]


def _append_synthetic_tool_round(
    messages: list[dict],
    *,
    strategy: str,
    tool_name: str,
    index: int,
    result_chars: int,
) -> None:
    tool_id = f"{strategy}-tool-{index}"
    messages.append(
        {
            "role": "assistant",
            "content": f"Synthetic tool request {index}: {tool_name}(fixture-{index}.txt)",
        }
    )
    raw_result = (
        f"<synthetic-tool-result id={tool_id}>\n"
        f"synthetic result {index} begin\n"
        + (chr(65 + index % 26) * result_chars)
        + f"\nsynthetic result {index} end\n"
        f"</synthetic-tool-result>"
    )
    result = (
        stabilize_tool_output(tool_id, raw_result, tool_name=tool_name)
        if strategy == "append_only"
        else raw_result
    )
    messages.append({"role": "user", "content": result})


def _legacy_progressive_compact(messages: list[dict]) -> None:
    candidates = [
        message
        for message in messages
        if message.get("role") == "user"
        and isinstance(message.get("content"), str)
        and message["content"].startswith("<synthetic-tool-result")
    ]
    for message in candidates[:-3]:
        text = message["content"]
        if text.startswith("<persisted-output"):
            continue
        marker = text.partition("id=")[2].partition(">")[0] or "legacy"
        message["content"] = persist_recallable_output(marker, text)


def _run_live_strategy(
    strategy: str,
    *,
    model_id: str,
    rounds: int,
    result_chars: int,
) -> LiveResult:
    marker = uuid.uuid4().hex
    tool_name = f"read_fixture_{strategy}_{marker[:8]}"
    tools = _tool_schema(tool_name)
    system = (
        f"Prompt cache A/B experiment {marker}. Reply only OK; never call tools.\n"
        + ("This is deterministic stable prefix material for cache measurement.\n" * 350)
    )
    messages: list[dict] = [
        {"role": "user", "content": f"Start cache experiment {marker}. Reply OK."}
    ]
    profile = get_model_profile(model_id)
    measured: list[LiveRound] = []

    for index in range(rounds):
        if strategy == "legacy_mutating":
            _legacy_progressive_compact(messages)

        response = create_provider_message(
            profile=profile,
            messages=messages,
            max_tokens=8,
            system=system,
            tools=tools,
        )
        cache = parse_cache_usage(getattr(response, "usage", None))
        if cache is None:
            raise RuntimeError("Provider response did not include input/cache usage.")
        measured.append(
            LiveRound(
                round_index=index + 1,
                hit_tokens=cache.hit_tokens,
                miss_tokens=cache.miss_tokens,
                hit_rate=cache.hit_rate,
            )
        )
        if index < rounds - 1:
            _append_synthetic_tool_round(
                messages,
                strategy=strategy,
                tool_name=tool_name,
                index=index,
                result_chars=result_chars,
            )
    return LiveResult(strategy=strategy, rounds=measured)


def run_live_ab(
    *,
    model_id: str,
    rounds: int = 7,
    result_chars: int = 20_000,
) -> list[LiveResult]:
    """Compare the old progressive micro-compaction with append-only ingress."""
    initialize_model(model_id)
    with tempfile.TemporaryDirectory(prefix="harness-cache-ab-") as tmp:
        original_dir = persist_mod.TOOL_RESULTS_DIR
        persist_mod.TOOL_RESULTS_DIR = Path(tmp)
        try:
            return [
                _run_live_strategy(
                    strategy,
                    model_id=model_id,
                    rounds=rounds,
                    result_chars=result_chars,
                )
                for strategy in ("legacy_mutating", "append_only")
            ]
        finally:
            persist_mod.TOOL_RESULTS_DIR = original_dir


def _format_live(results: list[LiveResult]) -> str:
    lines: list[str] = []
    for result in results:
        lines.append(f"\n{result.strategy}")
        lines.append("round  hit  miss  rate")
        for item in result.rounds:
            lines.append(
                f"{item.round_index:>5}  {item.hit_tokens:>5}  "
                f"{item.miss_tokens:>5}  {100 * item.hit_rate:>5.1f}%"
            )
        lines.append(
            f"warm total: hit={result.warm_hit_tokens} "
            f"miss={result.warm_miss_tokens} "
            f"rate={100 * result.warm_hit_rate:.1f}%"
        )
    if len(results) == 2:
        delta = 100 * (results[1].warm_hit_rate - results[0].warm_hit_rate)
        lines.append(f"\nwarm hit-rate delta: {delta:+.1f} percentage points")
    return "\n".join(lines).lstrip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=8)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--result-chars", type=int, default=20_000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if not args.live:
        print(format_results_table(run_all_simulations(rounds=args.rounds)))
        return 0

    results = run_live_ab(
        model_id=args.model,
        rounds=args.rounds,
        result_chars=args.result_chars,
    )
    print(_format_live(results))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model": args.model,
            "rounds": args.rounds,
            "result_chars": args.result_chars,
            "results": [
                {
                    **asdict(result),
                    "warm_hit_tokens": result.warm_hit_tokens,
                    "warm_miss_tokens": result.warm_miss_tokens,
                    "warm_hit_rate": result.warm_hit_rate,
                }
                for result in results
            ],
        }
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
