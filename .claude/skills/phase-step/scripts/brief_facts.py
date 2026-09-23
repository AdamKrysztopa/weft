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
   brief says who re-points the ones the change will move. A citation counts when what it wrote
   is a path suffix of the owner, and a bare basename counts only when its quoted fragment sits
   within FF17's window in the owner (`L28.33`): matching directory plus name (`L28.24`) dropped
   four basename citations across two briefs, which FF17 resolves just the same.
3. **The test files naming each `Protocol` an owner module defines** (`L28.16`). Widening one breaks
   every double of it, in tests the implementer may not edit; the red file's clean count says
   nothing about them. Type-check these against the changed signature before the brief orders it.
4. **Red files that fail at collection** (`L28.36`). An import error stands in front of every
   test's own reason to fail, and two dispatches in one phase returned blocked on fixture defects
   it hid. Stub the missing names in the scratchpad and run each test once before dispatch.

Runs under bare `python3` (3.9), like the hooks: no 3.10+ syntax.
"""

from __future__ import annotations

import argparse
import builtins
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

_QUOTED = re.compile(r'"([A-Za-z_][A-Za-z0-9_]*)"')
_PROTOCOL = re.compile(r"^class ([A-Za-z_][A-Za-z0-9_]*)\([^)]*\bProtocol\b", re.MULTILINE)
#: `tests/architecture/test_ff17_citations_resolve.py`'s `_CITATION_WITH_FRAGMENT`, and its window.
_CITATION = re.compile(
    r"([A-Za-z0-9_./-]+\.(?:py|md|toml|yaml|yml)):(\d+)(?:-\d+)?"
    r"(?: (?:\"([^\"]{8,})\"|'([^']{8,})'))?"
)
_FF17 = Path("tests/architecture/test_ff17_citations_resolve.py")
_WINDOW = re.compile(r"^_FRAGMENT_WINDOW\b[^=]*=\s*(\d+)", re.MULTILINE)


def _run(args: list[str]) -> str:
    # A fixed argv of `git`/`uv` with paths the dispatcher typed, the shape `format_python.py` runs.
    return subprocess.run(args, capture_output=True, text=True, check=False).stdout  # noqa: S603


def _defined(symbol: str) -> bool:
    pattern = (
        r"^[[:space:]]*(async def|def|class) {0}([^A-Za-z0-9_]|$)|^{0}[[:space:]]*[:=]".format(
            re.escape(symbol)
        )
    )
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


def _window() -> int | None:
    try:
        found = _WINDOW.search(_FF17.read_text(encoding="utf-8"))
    except OSError:
        return None
    return int(found.group(1)) if found else None


def _cites(owner: Path, lines: list[str], window: int | None, text: str) -> bool:
    for match in _CITATION.finditer(text):
        cited = match.group(1)
        if not ("/" + str(owner)).endswith("/" + cited.lstrip("./")):
            continue
        fragment = (match.group(3) or match.group(4) or "").replace('"', "")
        if "/" in cited or not fragment:
            return True
        at = int(match.group(2))
        if any(
            fragment in body.replace('"', "") and (window is None or abs(n - at) <= window)
            for n, body in enumerate(lines, start=1)
        ):
            return True
    return False


def citations(owners: list[str]) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    window = _window()
    for owner in owners:
        path = Path(owner)
        try:
            lines = path.read_text(encoding="utf-8").split("\n")
        except OSError:
            lines = []
        out = _run(
            [
                "git",
                "grep",
                "-nE",
                r"(^|[^A-Za-z0-9_])" + re.escape(path.name) + r":[0-9]+",
                "--",
                ".",
            ]
        )
        found[owner] = [
            line for line in out.splitlines() if line.strip() and _cites(path, lines, window, line)
        ]
    return found


def uncollectable(red: list[str]) -> list[str]:
    out = _run(
        [
            "uv",
            "run",
            "pytest",
            "--collect-only",
            "-q",
            "--color=no",
            "-p",
            "no:cacheprovider",
            *red,
        ]
    )
    plain = re.sub(r"\x1b\[[0-9;]*m", "", out)
    return [line for line in plain.splitlines() if line.startswith(("ERROR ", "E   "))]


def protocol_doubles(owners: list[str]) -> dict[str, tuple[list[str], list[str]]]:
    """Per owner defining a `Protocol`: its Protocols, and the tests importing that module.

    A double satisfies a Protocol structurally and rarely names it, so the population is the
    tests that import the module, not the ones that mention the class.
    """
    found: dict[str, tuple[list[str], list[str]]] = {}
    for owner in owners:
        try:
            source = Path(owner).read_text(encoding="utf-8")
        except OSError:
            continue
        protocols = _PROTOCOL.findall(source)
        parts = Path(owner).with_suffix("").parts
        if not protocols or "src" not in parts:
            continue
        module = ".".join(parts[parts.index("src") + 1 :])
        pattern = rf"(from|import) {re.escape(module)}( |$|,)"
        out = _run(["git", "grep", "-lE", pattern, "--", "tests", "testing"])
        found[owner] = (protocols, [line for line in out.splitlines() if line.strip()])
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
    failed = uncollectable(options.red)
    if failed:
        print()
        count = sum(line.startswith("ERROR ") for line in failed)
        print(f"{count} red file(s) fail at collection:")
        for line in failed:
            print("- " + line[:160])
        print(
            "Every test behind an import error is unread: stub the missing names in the "
            "scratchpad and run each test once, so each fails for its own reason (L28.36)."
        )
    for owner, (protocols, files) in protocol_doubles(options.owners).items():
        print()
        print(
            f"{owner} defines Protocol(s) {', '.join(protocols)}; "
            f"{len(files)} test file(s) import it:"
        )
        for line in files:
            print("- " + line)
        print(
            "If the brief changes a Protocol's signature, sketch the change and run "
            "`uv run pyright` on these first (L28.16). If it adds a Protocol, name the "
            "examples/ pack that will satisfy it: FF9(c) fails an exported Protocol with no "
            "stranger (L28.23)."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
