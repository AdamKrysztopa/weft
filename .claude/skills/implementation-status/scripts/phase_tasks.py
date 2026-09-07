#!/usr/bin/env python3
"""Print every task line of one phase of `docs/build-ledger.md`, with its tick state and its sha.

This exists so a status answer is *read* rather than remembered, and so it is read without the
trap that catches every hand-rolled grep: **`build-ledger.md` → *How to read a task line* contains
an unticked task line inside a fenced code block**, deliberately, so no worked example could drift
from the list below it. `grep '^- \\[ \\]'` finds that shape first, every time, and a status table
built on it opens with a row for the placeholder task `N.M`.

The fence-skipping parser already exists in `phase-step`'s `next_task.py` and is imported rather
than copied — one parser, so the two skills cannot come to disagree about what a task line is.
That script answers *which task is next*; this one answers *what does the whole phase look like*,
which is the other half of a status answer and the half `next_task.py` deliberately does not give.

    python3 .claude/skills/implementation-status/scripts/phase_tasks.py          # the live phase
    python3 .claude/skills/implementation-status/scripts/phase_tasks.py 9        # a named phase
    python3 .claude/skills/implementation-status/scripts/phase_tasks.py --json

Exit codes: 0 the phase was found and printed · 2 no phase matched · 3 the ledger, or
`docs/README.md`, could not be read.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
PHASE_STEP_SCRIPTS = HERE.parents[2] / "phase-step" / "scripts"
sys.path.insert(0, str(PHASE_STEP_SCRIPTS))

try:
    from next_task import (  # type: ignore[import-not-found]
        NEXT_ACTION_TASK,
        PHASE_IN_STATUS,
        find_ledger,
        parse,
        status_block,
    )
except ImportError as exc:  # pragma: no cover - a missing sibling skill is a broken checkout
    print(f"cannot import phase-step's parser from {PHASE_STEP_SCRIPTS}: {exc}", file=sys.stderr)
    raise SystemExit(3) from exc

BLOCKED = "⛔"
PROVISIONAL = "⚠"
PHASE_NUMBER = re.compile(r"^Phase\s+(?P<number>\d+)")

#: A line that says its own task is not scheduled. The ledger writes this in bold at the tail of
#: the line (`10.14`, `10.15`), and it is a different state from *not started*: nobody will pick
#: it up in order, and the line itself says what would schedule it.
NOT_SCHEDULED = re.compile(r"not scheduled", re.IGNORECASE)

#: The sha the line's own `sha` field carries. Pulled out by shape rather than taken as the raw
#: field, because a task line's tail continues past the field with a note and the join can leave a
#: separator inside it (`10.11` reads `sha — ·` today). A status row's sha is the thing a reader
#: will paste into `git show`, so it is either seven-plus hex characters out of this document or
#: it is `—`; there is no third option and nothing here invents one.
SHA_IN_FIELD = re.compile(r"`(?P<sha>[0-9a-f]{7,40})`")


def phase_number(title: str) -> str:
    match = PHASE_NUMBER.match(title.strip())
    return match.group("number") if match else ""


def live_phase(readme: Path) -> str:
    """The phase number `docs/README.md`'s Status block declares, or `""`."""
    status = status_block(readme)
    declared = PHASE_IN_STATUS.search(status.get("Phase", ""))
    return declared.group("number") if declared else ""


def next_action_task(readme: Path) -> str:
    """The task id the Next action row points at. It outranks ledger order."""
    pointed = NEXT_ACTION_TASK.search(status_block(readme).get("Next action", ""))
    return pointed.group("identifier") if pointed else ""


def collect(ledger: Path, wanted: str) -> dict:
    tasks, phases = parse(ledger.read_text(encoding="utf-8"))
    titles = [t for t in phases if phase_number(t) == wanted]
    if not titles:
        return {}
    title = titles[0]
    phase = phases[title]
    rows = []
    for task in tasks:
        if task.phase != title:
            continue
        found = SHA_IN_FIELD.search(task.fields.get("sha", ""))
        rows.append(
            {
                "id": task.identifier,
                "line": task.lineno,
                "ticked": task.checked,
                "provisional": task.provisional,
                # The glyph is *mentioned*, which is not the same as the task being blocked: every
                # ⛔ in Phase 10's task lines today is conditional prose ("a ⛔ this phase does not
                # take", "⛔ if the ..."). Same reason `next_task.py` prints preamble ⛔ lines
                # verbatim instead of ruling on them — text cannot tell a live block from a
                # discussed one, so this reports the mention and the reader rules.
                "mentions_blocked": BLOCKED in task.text,
                "sha": found.group("sha") if found else "—",
                "owner": task.fields.get("owner", ""),
                "turns_on": task.fields.get("turns on", "—"),
                "not_scheduled": bool(NOT_SCHEDULED.search(task.text)),
                "makes_true": task.property_sentence,
            }
        )
    return {
        "phase": title,
        "preamble_blocked_lines": [{"line": n, "text": t} for n, t in phase.blocked_lines],
        "tasks": rows,
    }


def render(report: dict, readme: Path) -> None:
    print(report["phase"])
    print(f"live phase per docs/README.md Status: {live_phase(readme) or '(not stated)'}")
    print(f"Next action row points at task: {next_action_task(readme) or '(not stated)'}")
    blocked = report["preamble_blocked_lines"]
    if blocked:
        print(f"\npreamble lines carrying {BLOCKED} — read them, a lifted block reads the same:")
        for entry in blocked:
            print(f"  {entry['line']}: {entry['text'].strip()}")
    else:
        print(f"\nno {BLOCKED} in the phase preamble")
    ticked = sum(1 for row in report["tasks"] if row["ticked"])
    print(f"\n{ticked} of {len(report['tasks'])} ticked\n")
    for row in report["tasks"]:
        box = "x" if row["ticked"] else " "
        flags = f" {PROVISIONAL}" if row["provisional"] else ""
        if row["mentions_blocked"]:
            flags += f" {BLOCKED}?(read the line)"
        tail = "  NOT SCHEDULED" if row["not_scheduled"] else ""
        print(f"[{box}] {row['id']}{flags}  sha {row['sha']}  L{row['line']}{tail}")
        print(f"      {row['makes_true']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "phase", nargs="?", help="phase number (default: the live one per docs/README.md)"
    )
    parser.add_argument("--ledger", help="path to build-ledger.md (default: found from this file)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    ledger = find_ledger(args.ledger)
    readme = ledger.parent / "README.md"
    wanted = args.phase or live_phase(readme)
    if not wanted:
        print("no phase given and docs/README.md's Status block declares none", file=sys.stderr)
        return 2

    report = collect(ledger, wanted)
    if not report:
        print(f"no phase numbered {wanted} in {ledger}", file=sys.stderr)
        return 2

    if args.json:
        report["live_phase"] = live_phase(readme)
        report["next_action_task"] = next_action_task(readme)
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        render(report, readme)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
