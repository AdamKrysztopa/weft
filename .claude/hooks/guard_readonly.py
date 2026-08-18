"""PreToolUse guard: refuse writes to material that must not be written.

Two targets, both easy to hit by accident and expensive to notice late.

**The reference symlink.** `reference/` points at a sibling `a prior project` checkout — a live
repository this project reads and lifts from. A path that resolves through it is
an edit to a *different project*, and since that checkout is not under version
control, the change would leave no trace.

**The frozen audit.** `docs/reference/` is a finished study of a fixed tree, cited
about ninety times by the plan. Its value is that it is a snapshot: editing it to
match a later belief destroys the evidence the plan rests on. If the study is
wrong, that is a finding to report, not a file to correct.

Blocking is a PreToolUse convention: exit 2, with the reason on stderr.
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

BLOCKED: tuple[tuple[Path, str], ...] = (
    (
        REPO / "docs" / "reference",
        "docs/reference/ is the frozen reference audit. It is a snapshot of a fixed tree and the plan "
        "cites it ~90 times; editing it destroys the evidence rather than correcting it. If the "
        "study is wrong, report the discrepancy — see the reference-audit skill.",
    ),
    (
        (REPO / "reference").resolve(),
        "That path resolves through the `reference` symlink into the a prior project checkout. Weft reads "
        "and lifts from the reference; it never writes to it, and that checkout is not under version "
        "control, so the change would leave no trace.",
    ),
)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    raw = payload.get("tool_input", {}).get("file_path")
    if not raw:
        return 0

    target = Path(raw).expanduser().resolve()

    for root, reason in BLOCKED:
        if target == root or root in target.parents:
            sys.stderr.write(f"Refused: {target}\n\n{reason}\n")
            return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
