"""Local daily usage ledger (JSONL under .project/usage/)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from harness.settings import PROJECT_DIR
from harness.usage.parse import CacheUsage

USAGE_DIR = PROJECT_DIR / "usage"


@dataclass
class UsageEvent:
    ts: str
    model: str
    hit: int
    miss: int
    out: int
    source: str = ""

    @property
    def input_tokens(self) -> int:
        return self.hit + self.miss

    def to_dict(self) -> dict:
        return {
            "ts": self.ts,
            "model": self.model,
            "hit": self.hit,
            "miss": self.miss,
            "out": self.out,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> UsageEvent:
        return cls(
            ts=str(data.get("ts", "")),
            model=str(data.get("model", "unknown")),
            hit=int(data.get("hit", 0) or 0),
            miss=int(data.get("miss", 0) or 0),
            out=int(data.get("out", 0) or 0),
            source=str(data.get("source", "")),
        )


@dataclass
class UsageTotals:
    hit: int = 0
    miss: int = 0
    out: int = 0
    calls: int = 0
    by_model: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def input_tokens(self) -> int:
        return self.hit + self.miss

    @property
    def hit_rate(self) -> float:
        total = self.input_tokens
        return self.hit / total if total else 0.0

    def add_event(self, event: UsageEvent) -> None:
        self.hit += event.hit
        self.miss += event.miss
        self.out += event.out
        self.calls += 1
        bucket = self.by_model.setdefault(
            event.model, {"hit": 0, "miss": 0, "out": 0, "calls": 0}
        )
        bucket["hit"] += event.hit
        bucket["miss"] += event.miss
        bucket["out"] += event.out
        bucket["calls"] += 1


def usage_dir() -> Path:
    USAGE_DIR.mkdir(parents=True, exist_ok=True)
    return USAGE_DIR


def day_path(day: date | None = None) -> Path:
    day = day or date.today()
    return usage_dir() / f"{day.isoformat()}.jsonl"


def record_usage(
    *,
    model: str,
    cache: CacheUsage | None,
    when: datetime | None = None,
) -> UsageEvent | None:
    """Append one API call to today's ledger. No-op if usage is missing."""
    if cache is None:
        return None
    now = when or datetime.now()
    event = UsageEvent(
        ts=now.strftime("%H:%M:%S"),
        model=model or "unknown",
        hit=cache.hit_tokens,
        miss=cache.miss_tokens,
        out=int(cache.output_tokens or 0),
        source=cache.source,
    )
    path = day_path(now.date())
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
    return event


def load_day_events(day: date) -> list[UsageEvent]:
    path = day_path(day)
    if not path.exists():
        return []
    events: list[UsageEvent] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            events.append(UsageEvent.from_dict(json.loads(line)))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid usage JSONL {path.name} line {line_no}") from exc
    return events


def sum_events(events: list[UsageEvent]) -> UsageTotals:
    totals = UsageTotals()
    for event in events:
        totals.add_event(event)
    return totals


def totals_for_day(day: date | None = None) -> UsageTotals:
    return sum_events(load_day_events(day or date.today()))


def daily_totals(days: list[date]) -> list[tuple[date, UsageTotals]]:
    return [(day, totals_for_day(day)) for day in days]


def date_range(end: date, count: int) -> list[date]:
    return [end - timedelta(days=offset) for offset in range(count - 1, -1, -1)]


def month_days(year: int, month: int) -> list[date]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    days: list[date] = []
    cursor = start
    while cursor < end:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def year_days(year: int) -> list[date]:
    days: list[date] = []
    for month in range(1, 13):
        days.extend(month_days(year, month))
    return days


def totals_for_days(days: list[date]) -> UsageTotals:
    totals = UsageTotals()
    for day in days:
        for event in load_day_events(day):
            totals.add_event(event)
    return totals


def list_usage_files() -> list[Path]:
    directory = usage_dir()
    return sorted(directory.glob("????-??-??.jsonl"))
