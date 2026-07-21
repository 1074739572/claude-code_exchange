"""Short usage strings for the TUI top bar."""

from __future__ import annotations

from datetime import date

from harness.usage.report import format_tokens
from harness.usage.store import date_range, totals_for_day, totals_for_days


def format_usage_bar() -> str:
    """Emoji header: today + last-7-days input/output."""
    today = totals_for_day(date.today())
    week = totals_for_days(date_range(date.today(), 7))
    return (
        f" 📊 今日  in {format_tokens(today.input_tokens)} · out {format_tokens(today.out)}"
        f"   ·   📅 本周  in {format_tokens(week.input_tokens)} · out {format_tokens(week.out)} "
    )
