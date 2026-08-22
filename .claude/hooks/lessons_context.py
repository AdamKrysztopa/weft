"""SessionStart — put what this repository has already learned into the session.

`docs/lessons.md` records how the work goes wrong. A ledger nobody opens is
worse than no ledger, because it looks like a control that is working. So
nothing here depends on anyone remembering the file exists: this hook runs on
every session start and prints the applied rules plus the open backlog into the
session's context.

Two halves, deliberately asymmetric:

- **Applied rules are printed in full.** They are the output of the loop — a
  lesson that cost something, was triaged, and produced an edit. A session that
  starts without them repeats the mistake that produced them.
- **Open entries are printed as titles only**, with a count. They are backlog,
  not doctrine; the detail belongs at the phase close where they are triaged,
  and pasting six full entries into every session start is how a context block
  stops being read.

Failure is silent by design, and this is the one place in this repository where
that is correct: a hook that cannot parse the ledger must not break the session
that was about to fix it. It writes nothing and exits 0. The corresponding
guarantee is that it never *invents* — an unreadable ledger produces no output
rather than a reassuring one.
"""

import json
import re
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parents[2] / "docs"
QUEUE = DOCS / "lessons.md"
ARCHIVE = DOCS / "lessons-archive.md"

_SECTION = re.compile(r"^## (Queue|Applied|Declined)\s*$", re.MULTILINE)
_QUEUED = re.compile(r"^### (L[\d.]+) — (.+)$", re.MULTILINE)
_ARCHIVED = re.compile(r"^- (\*\*L[\d.]+\*\* .+)$", re.MULTILINE)
_FENCE = re.compile(r"^```", re.MULTILINE)


def _unfenced(text: str) -> str:
    """Drop fenced blocks. The archive documents its own entry format with a worked
    example, and an example that is indistinguishable from data is how a check ends up
    reporting its own documentation as a finding."""
    parts = _FENCE.split(text)
    return "".join(parts[::2])


def _sections(text: str) -> dict[str, str]:
    """Split on the three `## ` headings, ignoring anything before the first."""
    marks = [(m.group(1), m.end(), m.start()) for m in _SECTION.finditer(text)]
    out: dict[str, str] = {}
    for i, (name, end, _start) in enumerate(marks):
        stop = marks[i + 1][2] if i + 1 < len(marks) else len(text)
        out[name] = text[end:stop]
    return out


def main() -> None:
    try:
        queue_text = QUEUE.read_text(encoding="utf-8")
    except OSError:
        return
    try:
        archive_text = ARCHIVE.read_text(encoding="utf-8")
    except OSError:
        archive_text = ""

    queued = [
        (m.group(1), m.group(2)) for m in _QUEUED.finditer(_sections(queue_text).get("Queue", ""))
    ]
    # Archive entries are one line each and already written to be read cold — a
    # `declined` line is a decision, not a rule, so it is not injected.
    applied = [
        line.strip()
        for line in _ARCHIVED.findall(_unfenced(archive_text))
        if "*declined*" not in line
    ]

    lines = ["# What this repository has already learned", ""]

    if applied:
        lines.append("Each of these cost something once. They are rules, not suggestions.")
        lines.append("")
        lines += [f"- {rule}" for rule in applied]
    else:
        lines.append(
            "Nothing has been drained into a rule yet. The queue has collected and "
            "not yet been spent."
        )

    lines.append("")
    if queued:
        lines.append(
            f"**{len(queued)} in the queue**, to be drained at the next phase close by "
            f"the `implement-ll` skill (`docs/lessons.md`):"
        )
        lines.append("")
        lines += [f"- {lid} — {title}" for lid, title in queued]
    else:
        lines.append("**The queue is empty**, which is the healthy state.")

    lines += [
        "",
        "**Collection is not yours to remember.** When a mistake is caught, a documented "
        "check turns out to be prose, a claim from intuition is falsified by measurement, "
        "or a defect is found by running the binary rather than by its tests — invoke the "
        "`lessons` skill and write it down while the reasoning is still here. `phase-step` "
        "\u2192 *Finish* and `README.md` \u2192 *Protocol* both require the queue to be "
        "current before a task or a gate may close.",
    ]

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "\n".join(lines),
            }
        },
        sys.stdout,
    )


if __name__ == "__main__":
    main()
