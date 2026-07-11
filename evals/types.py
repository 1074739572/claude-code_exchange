"""Lightweight agent/harness evaluation suite."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Callable, Literal

Status = Literal["pass", "fail", "skip", "warn"]


@dataclass
class EvalCase:
    id: str
    name: str
    category: str
    run: Callable[[], None]
    requires_live: bool = False
    notes: str = ""


@dataclass
class EvalResult:
    id: str
    name: str
    category: str
    status: Status
    detail: str = ""
    duration_ms: float = 0.0
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EvalReport:
    results: list[EvalResult] = field(default_factory=list)
    live: bool = False

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == "pass")

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == "fail")

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.status == "skip")

    @property
    def warned(self) -> int:
        return sum(1 for r in self.results if r.status == "warn")

    @property
    def score(self) -> float:
        scored = [r for r in self.results if r.status in ("pass", "fail")]
        if not scored:
            return 0.0
        return 100.0 * sum(1 for r in scored if r.status == "pass") / len(scored)
