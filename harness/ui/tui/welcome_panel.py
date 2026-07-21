"""TUI welcome: slim brand line + quote card + gradient rule (premium shell)."""

from __future__ import annotations

from dataclasses import dataclass

from harness.ui.banner import TAGLINE
from harness.ui.tui.quotes import get_daily_quote_item, maybe_refill_async

# Compact hollow face (amber) — not the old 7-line solid block.
SMILEY_SLIM: str = "\n".join(
    [
        " ╭───╮ ",
        " │· ·│ ",
        " │ ‿ │ ",
        " ╰───╯ ",
    ]
)

HELLO_LABEL = "HELLO"
NARROW_HELLO = "🙂  HELLO"


@dataclass(frozen=True)
class WelcomeParts:
    wide: bool
    smiley: str
    hello_title: str
    tagline: str
    narrow: str
    quote_label: str
    quote_body: str
    quote_source: str


def format_quote_card(text: str, source: str = "") -> tuple[str, str, str]:
    """Return (label, body, source_line) for the quote card."""
    body = (text or "").strip()
    if body and not (body.startswith("「") or body.startswith('"') or body.startswith("“")):
        body = f"“{body}”"
    src = (source or "").strip()
    if src and src != "fallback":
        source_line = f"— {src}"
    else:
        source_line = ""
    return "TODAY", body, source_line


def gradient_rule_markup(width: int) -> str:
    """Amber → cyan hairline using Textual markup spans."""
    width = max(12, min(width, 72))
    # Sample colors along amber (#E6B84D) → cyan (#7FDBFF)
    stops = [
        "#E6B84D",
        "#E0C05E",
        "#D4C878",
        "#C0D098",
        "#A8D8B8",
        "#90D8D0",
        "#7FDBFF",
    ]
    chars: list[str] = []
    last = len(stops) - 1
    for i in range(width):
        t = i / max(width - 1, 1)
        idx = min(last, int(round(t * last)))
        chars.append(f"[{stops[idx]}]━[/{stops[idx]}]")
    return "".join(chars)


def build_welcome_parts(*, wide: bool) -> WelcomeParts:
    maybe_refill_async()
    item = get_daily_quote_item()
    label, body, source_line = format_quote_card(
        item.get("hitokoto") or "",
        item.get("from") or "",
    )
    if wide:
        return WelcomeParts(
            wide=True,
            smiley=SMILEY_SLIM,
            hello_title=HELLO_LABEL,
            tagline=TAGLINE,
            narrow="",
            quote_label=label,
            quote_body=body,
            quote_source=source_line,
        )
    return WelcomeParts(
        wide=False,
        smiley="",
        hello_title="",
        tagline=TAGLINE,
        narrow=f"{NARROW_HELLO}\n{TAGLINE}",
        quote_label=label,
        quote_body=body,
        quote_source=source_line,
    )
