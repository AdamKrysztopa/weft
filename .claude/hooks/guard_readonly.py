"""PreToolUse guard: refuse writes to reading material this repository does not own.

Both targets are excluded from version control, and that is exactly what makes a
write to either expensive: it would leave no trace in any diff, so nobody reviewing
this repository could see that it happened or undo it. Reading is unrestricted;
only writing is refused.

The paths are named rather than derived because the property is about *these*
locations, and a rule computed from `.gitignore` would silently start refusing
writes to build output, caches and the virtualenv the moment those were added
to it. Both live under a single `_external-` prefix so that adding a third needs
one line here and no new vocabulary anywhere else.

Blocking is a PreToolUse convention: exit 2, with the reason on stderr.
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

BLOCKED: tuple[tuple[Path, str], ...] = (
    (
        REPO / "docs" / "_external-reading",
        "That directory is reading material kept on disk and excluded from version control. It "
        "is a snapshot of a tree at a fixed moment, and its whole value is that it is fixed: "
        "editing it to match a later belief destroys the record rather than correcting it. If it "
        "is wrong, that is a finding to report, not a file to rewrite.",
    ),
    (
        (REPO / "_external-src").resolve(),
        "That path resolves through a symlink into a checkout this repository does not own. It "
        "may be read; it is never written. That checkout is not under version control, so the "
        "change would leave no trace in any diff.",
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
