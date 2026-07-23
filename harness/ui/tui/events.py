"""Structured events exchanged between agent workers and the Textual UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ToolPhase = Literal["running", "ok", "failed", "blocked", "repeat"]
BackgroundPhase = Literal["running", "completed", "failed"]
PermissionDecision = Literal["allow", "deny", "cancel"]


@dataclass(frozen=True)
class ToolEvent:
    tool_use_id: str
    name: str
    summary: str = ""
    phase: ToolPhase = "running"
    preview: str = ""
    streak: int = 1


@dataclass(frozen=True)
class BackgroundEvent:
    task_id: str
    command: str
    phase: BackgroundPhase
    preview: str = ""


@dataclass(frozen=True)
class PermissionRequest:
    request_id: str
    title: str
    detail: str
    editable: bool = False
    placeholder: str = ""


@dataclass(frozen=True)
class PermissionResponse:
    request_id: str
    decision: PermissionDecision
    value: str = ""

    @property
    def allowed(self) -> bool:
        return self.decision == "allow"


@dataclass(frozen=True)
class RuntimeMetrics:
    cache_hit_tokens: int = 0
    cache_miss_tokens: int = 0
    context_tokens: int = 0
    context_window: int = 0

    @property
    def cache_hit_rate(self) -> float:
        total = self.cache_hit_tokens + self.cache_miss_tokens
        return self.cache_hit_tokens / total if total else 0.0

    @property
    def context_rate(self) -> float:
        return self.context_tokens / self.context_window if self.context_window else 0.0
