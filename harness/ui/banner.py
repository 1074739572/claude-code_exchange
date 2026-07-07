"""Welcome hero art — multiple visual styles."""

from __future__ import annotations

import os
import time
from typing import Literal

from harness.ui import theme

try:
    from rich.align import Align
    from rich.columns import Columns
    from rich.console import Console, Group, RenderableType
    from rich.panel import Panel
    from rich.text import Text

    _RICH = True
except ImportError:
    _RICH = False

BannerStyle = Literal["classic", "emoji", "typewriter", "shadow3d"]

BANNER_STYLES: tuple[BannerStyle, ...] = (
    "classic",
    "emoji",
    "typewriter",
    "shadow3d",
)

TAGLINE = "improved_harness · agent CLI"
DEFAULT_BANNER_STYLE: BannerStyle = "classic"

SMILEY: list[str] = [
    "    ████████████    ",
    "  ██            ██  ",
    " ██   ██    ██   ██ ",
    " ██              ██ ",
    " ██    ██████    ██ ",
    "  ██            ██  ",
    "    ████████████    ",
]

HELLO_AGENT: list[str] = [
    " ██╗  ██╗███████╗██╗     ██╗      ██████╗ ",
    " ██║  ██║██╔════╝██║     ██║     ██╔═══██╗",
    " ███████║█████╗  ██║     ██║     ██║   ██║",
    " ██╔══██║██╔══╝  ██║     ██║     ██║   ██║",
    " ██║  ██║███████╗███████╗███████╗╚██████╔╝",
    " ╚═╝  ╚═╝╚══════╝╚══════╝╚══════╝ ╚═════╝ ",
    "",
    "  █████╗ ██████╗ ███████╗███╗   ██╗████████╗",
    " ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝",
    " ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   ",
    " ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   ",
    " ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   ",
    " ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   ",
]


def get_banner_style() -> BannerStyle:
    raw = (os.getenv("HARNESS_BANNER") or DEFAULT_BANNER_STYLE).strip().lower()
    if raw in BANNER_STYLES:
        return raw  # type: ignore[return-value]
    return DEFAULT_BANNER_STYLE


def _plain_lines(style: BannerStyle) -> list[str]:
    return ["", "  (:  HELLO AGENT  :)", f"  {TAGLINE}", ""]


def gradient_block(lines: list[str]) -> Text:
    shades = ["bright_cyan", "cyan", f"bold {theme.ACCENT}", "dim cyan"]
    block = Text()
    for idx, line in enumerate(lines):
        if not line.strip():
            block.append("\n")
            continue
        block.append(line + "\n", style=shades[idx % len(shades)])
    return block


def _gradient_block(lines: list[str]) -> Text:
    return gradient_block(lines)


def _block_smiley() -> Text:
    face = Text()
    for i, row in enumerate(SMILEY):
        styled = Text(row + "\n")
        if i == 0 or i == len(SMILEY) - 1:
            styled.stylize(f"bold {theme.ACCENT}")
        elif "██████" in row:
            styled.stylize("bold red")
        elif "██    ██" in row or row.count("██") >= 4:
            styled.stylize("bold yellow")
        else:
            styled.stylize(f"bold {theme.ACCENT}")
        face.append_text(styled)
    return face


def _tagline_text() -> Text:
    tag = Text(TAGLINE, style=theme.MUTED)
    tag.justify = "center"
    return tag


def _classic_renderable(*, wide: bool) -> RenderableType:
    title = _gradient_block(HELLO_AGENT)
    smiley = _block_smiley()
    if wide:
        body = Columns(
            [
                Align.center(smiley, vertical="middle"),
                Align.center(title, vertical="middle"),
            ],
            expand=True,
            equal=False,
            padding=(0, 4),
        )
    else:
        body = Group(Align.center(smiley), "", Align.center(title))
    return Group(Align.center(body), "", Align.center(_tagline_text()))


def _emoji_renderable() -> RenderableType:
    headline = Text("HELLO AGENT", style=f"bold bright_{theme.ACCENT}")
    headline.justify = "center"
    return Group(
        "",
        Align.center(_block_smiley()),
        "",
        Align.center(headline),
        "",
        Align.center(_tagline_text()),
        "",
    )


def _shadow3d_lines(console: Console, lines: list[str], *, shadow_shift: int = 2) -> None:
    """Extruded block letters: dim shadow row, then bright front row."""
    pad = " " * shadow_shift
    shades = ["bright_cyan", "cyan", f"bold {theme.ACCENT}"]
    idx = 0
    for line in lines:
        if not line.strip():
            console.print()
            continue
        style = shades[idx % len(shades)]
        console.print(pad + line, style="dim")
        console.print(line, style=style)
        idx += 1


def _typewriter_chars(
    console: Console,
    text: str,
    *,
    style: str,
    char_delay: float = 0.028,
) -> None:
    for char in text:
        console.print(char, end="", style=style)
        time.sleep(char_delay)
    console.print()


def _typewriter_lines(
    console: Console,
    lines: list[str],
    *,
    line_delay: float = 0.09,
    char_delay: float = 0.0015,
) -> None:
    shades = ["bright_cyan", "cyan", f"bold {theme.ACCENT}", "dim cyan"]
    idx = 0
    for line in lines:
        if not line.strip():
            console.print()
            time.sleep(line_delay * 0.35)
            continue
        style = shades[idx % len(shades)]
        for char in line:
            console.print(char, end="", style=style)
            time.sleep(char_delay)
        console.print()
        idx += 1
        time.sleep(line_delay)


def _style_label(style: BannerStyle) -> str:
    labels = {
        "classic": "Classic · block smiley + gradient title",
        "emoji": "Emoji · smiley + title",
        "typewriter": "Typewriter · animated reveal",
        "shadow3d": "Shadow 3D · extruded block letters",
    }
    return labels.get(style, style)


def print_hero(
    console: Console,
    *,
    style: BannerStyle | None = None,
    width: int = 80,
) -> None:
    """Print one hero banner. Typewriter style animates on the calling thread."""
    chosen = style or get_banner_style()
    wide = width >= 100

    if not _RICH:
        for line in _plain_lines(chosen):
            print(line)
        return

    if chosen == "typewriter":
        _print_typewriter(console)
        return

    if chosen == "shadow3d":
        console.print()
        _shadow3d_lines(console, HELLO_AGENT)
        console.print()
        console.print(Align.center(_tagline_text()))
        console.print()
        return

    art: RenderableType
    if chosen == "emoji":
        art = _emoji_renderable()
    else:
        art = _classic_renderable(wide=wide)

    console.print(art)


def _print_typewriter(console: Console) -> None:
    console.print()
    _typewriter_chars(console, "▸ HELLO AGENT", style=f"bold bright_{theme.ACCENT}")
    console.print()
    _typewriter_lines(console, HELLO_AGENT)
    console.print()
    _typewriter_chars(console, TAGLINE, style=theme.MUTED, char_delay=0.022)
    console.print()


def run_banner_demo(console: Console | None = None) -> None:
    """Preview every banner style in sequence."""
    if not _RICH:
        for style in BANNER_STYLES:
            print(f"\n=== {style} ===")
            for line in _plain_lines(style):
                print(line)
        print("\nInstall rich for full previews.")
        return

    console = console or Console(highlight=False, legacy_windows=False)
    width = console.size.width

    console.print()
    console.print(
        Panel(
            "Banner preview — four styles\n"
            "Pick one: set env [bold]HARNESS_BANNER[/]=classic|emoji|typewriter|shadow3d",
            title="Banner demo",
            border_style=theme.ACCENT,
            padding=(1, 2),
        )
    )
    console.print()

    for style in BANNER_STYLES:
        console.rule(f"[bold {theme.ACCENT}]{_style_label(style)}[/]")
        console.print()
        print_hero(console, style=style, width=width)
        if style != BANNER_STYLES[-1]:
            console.print()
            time.sleep(0.35)

    console.print()
    console.rule("[dim]end of demo[/]")
    console.print()
