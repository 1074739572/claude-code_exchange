#!/usr/bin/env python3
"""Run the improved harness agent from the package root."""

import argparse
import sys


def _ensure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not reconfigure:
            continue
        try:
            if stream.encoding and stream.encoding.lower() not in ("utf-8", "utf8"):
                reconfigure(encoding="utf-8")
        except Exception:
            pass


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="improved_harness agent CLI")
    parser.add_argument(
        "--banner-demo",
        action="store_true",
        help="Preview all welcome banner styles (classic, emoji, typewriter, shadow3d)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    _ensure_utf8_stdio()
    args = _parse_args()

    if args.banner_demo:
        from harness.ui.banner import run_banner_demo

        run_banner_demo()
        raise SystemExit(0)

    from harness.cli import run_cli

    run_cli()
