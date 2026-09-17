#!/usr/bin/env python3
"""The two facts a green-phase brief has twice asserted from a reading instead of a measurement.

    python3 .claude/skills/phase-step/scripts/brief_facts.py \
        --red tests/unit/x/test_new.py --owners packages/weft-rag/src/weft_x/module.py

Prints a `## Brief facts` block to paste into the brief; `guard_implementer_brief.py` refuses a
`weft-implementer` dispatch whose prompt does not carry one.

1. **The red file's type errors, grouped by the symbol they name** (`L24.1`, recurring `L22.13`).
   A cascade is an error naming a symbol the tree does not define yet; every other group is a
   defect in the red test itself and must be fixed or named in the brief before dispatch. Grouping
   by message wording was the Applied rule, and it hid a `getattr` error whose message said
   "unknown" for a reason of its own.
2. **Every `path:line` citation into each owner module** (`L24.6`, recurring `L23.15`), so the
   brief says who re-points the ones the change will move.

Runs under bare `python3` (3.9), like the hooks: no 3.10+ syntax.
"""

import argparse
import builtins
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

_QUOTED = re.compile(r'"([A-Za-z_][A-Za-z0-9_]*)"')


def _run(args: list[str]) -> str:
    # A fixed argv of `git`/`uv` with paths the dispatcher typed, the shape `format_python.py` runs.
    return subprocess.run(args, capture_output=True, text=True, check=False).stdout  # noqa: S603


def _defined(symbol: str) -> bool:
    pattern = r"^\s*(async def|def|class) {0}\b|^{0}\b\s*[:=]".format(re.escape(symbol))
    out = _run(["git", "grep", "-lE", pattern, "--", "packages", "testing", "scripts", "eval"])
    return bool(out.strip())


def red_groups(red: list[str]) -> tuple[dict[tuple[str, str], int], int]:
    raw = _run(["uv", "run", "pyright", "--outputjson", *red])
    try:
        report = json.loads(raw)
    except json.JSONDecodeError:
        print(
            "pyright produced no JSON; run `uv run pyright` on the red files by hand",
            file=sys.stderr,
        )
        return {}, 0
    groups: dict[tuple[str, str], int] = defaultdict(int)
    total = 0
    for diagnostic in report.get("generalDiagnostics", []):
        if diagnostic.get("severity") != "error":
            continue
        total += 1
        message = diagnostic.get("message", "").splitlines()[0]
        names = [
            name for name in _QUOTED.findall(message) if not name.startswith("_") or len(name) > 1
        ]
        missing = [name for name in names if not hasattr(builtins, name) and not _defined(name)]
        if missing:
            groups[("cascade", ", ".join(sorted(set(missing))))] += 1
        else:
            groups[("OTHER", re.sub(r'"[^"]*"', '"…"', message))] += 1
    return groups, total


def citations(owners: list[str]) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for owner in owners:
        name = Path(owner).name
        out = _run(
            ["git", "grep", "-nE", r"(^|[^A-Za-z0-9_])" + re.escape(name) + r":[0-9]+", "--", "."]
        )
        found[owner] = [line for line in out.splitlines() if line.strip()]
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--red", nargs="+", required=True, help="the test files written red for this task"
    )
    parser.add_argument(
        "--owners", nargs="*", default=[], help="modules the implementation will edit"
    )
    options = parser.parse_args()

    head = _run(["git", "rev-parse", "--short", "HEAD"]).strip()
    groups, total = red_groups(options.red)
    print("## Brief facts")
    print(f"brief_facts_head: {head}")
    print()
    print(f"Red files: {', '.join(options.red)} — {total} pyright error(s).")
    other = 0
    for (kind, subject), count in sorted(groups.items()):
        print(f"- {count:>3} × {kind}: {subject}")
        if kind == "OTHER":
            other += count
    if other:
        print()
        print(
            f"{other} error(s) name no missing symbol: "
            "fix the red test, or state each in the brief."
        )
    for owner, lines in citations(options.owners).items():
        print()
        print(f"Citations into {owner}: {len(lines)}")
        for line in lines:
            print("- " + line[:160])
    if options.owners and any(citations(options.owners).values()):
        print()
        print("Say in the brief who re-points each citation the change moves (L23.15).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
