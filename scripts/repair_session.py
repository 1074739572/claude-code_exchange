"""Repair the active session history in-place (orphan tool_use cleanup)."""

from __future__ import annotations

import argparse
import sys

from harness.project.session_store import bootstrap_session, replace_session
from harness.messages.repair import repair_tool_pairing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report fixes without writing session/history",
    )
    args = parser.parse_args()

    messages, source = bootstrap_session()
    before = len(messages)
    _, fixes = repair_tool_pairing(messages)
    after = len(messages)

    print(f"Session source: {source}")
    print(f"Messages: {before} -> {after} ({fixes} fix(es))")
    if fixes and not args.dry_run:
        replace_session(messages, archive=True)
        print("Saved repaired session.")
    elif fixes:
        print("Dry run — no files written.")
    else:
        print("No repairs needed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
