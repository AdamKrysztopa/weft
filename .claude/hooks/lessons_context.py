"""SessionStart and SubagentStart — put what this repository has already learned into
whoever is about to work.

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

**Subagents get the rules too, and that is why this hook is not `SessionStart`-only.**
Measured 2026-08-22, not assumed: `SessionStart` does **not** fire for an agent
dispatched through the Agent tool, so before this change every `weft-implementer`
worked without a single applied rule in its context. `.claude/agents/weft-implementer.md`
compensated by hand-copying seven constraints into its own body — and nothing kept that
copy in step with what `implement-ll` applied, so it aged silently from the moment it was
written. `SubagentStart` fires and *can* inject (proven with a probe before this was
built, per `docs/lessons.md` L5.1), so the rules now reach a subagent from the same
source the main session reads. One file to update, two audiences, no copy to go stale.

**What a subagent is told is deliberately not what the main session is told.** The open
queue is not injected: a subagent cannot drain it, cannot triage it, and must never write
to `docs/lessons.md` — that needs reasoning it was not given. What it gets instead is the
one instruction that makes its findings recoverable: put them under a `## Noticed`
heading, which `.claude/hooks/subagent_findings.py` harvests by exact match. A heading a
machine can find is the difference between a finding that survives the context boundary
and one that dies in a paragraph nobody re-read.

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


NOTICED_HEADING = "## Noticed"


def _applied_rules(archive_text: str) -> list[str]:
    """Every drained lesson that became a rule. A `declined` line is a decision, not a
    rule, so it is not injected."""
    return [
        line.strip()
        for line in _ARCHIVED.findall(_unfenced(archive_text))
        if "*declined*" not in line
    ]


def _queued_entries(queue_text: str) -> list[tuple[str, str]]:
    return [
        (m.group(1), m.group(2)) for m in _QUEUED.finditer(_sections(queue_text).get("Queue", ""))
    ]


def _session_body(applied: list[str], queued: list[tuple[str, str]]) -> list[str]:
    """What the driving session reads: the rules in full, the backlog as titles."""
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
    return lines


def _subagent_body(applied: list[str]) -> list[str]:
    """What a dispatched agent reads: the same rules, and one instruction about reporting.

    No queue. A subagent cannot triage a backlog and must not write `docs/lessons.md`;
    handing it six open entries would be context it can only ignore. The `## Noticed`
    heading is the whole consuming side of this boundary — see the module docstring.
    """
    lines = ["# What this repository has already learned", ""]
    if applied:
        lines.append(
            "Each of these cost this project something once. They bind the code you are "
            "about to write, and the brief will not re-derive them."
        )
        lines.append("")
        lines += [f"- {rule}" for rule in applied]
    else:
        lines.append("Nothing has been drained into a rule yet.")

    lines += [
        "",
        "**You do not write to `docs/lessons.md`.** Writing a lesson needs reasoning you "
        "were not given, and the session that dispatched you holds it.",
        "",
        f"**What you do instead: end your report with a `{NOTICED_HEADING}` heading** and, "
        "under it, one line per thing that cost you time or looked wrong and was not "
        "yours to fix — a check that turned out to be prose, a docstring that contradicts "
        "its code, a neighbouring assertion that looks wrong, a constraint above you had "
        "to work around, a name that collides. Write nothing under it if there was "
        "nothing; an empty heading is a fact and a missing one is not. That section is "
        "harvested automatically and routed into the lessons queue by the session that "
        "dispatched you, so it is the one channel by which what only you saw survives.",
    ]
    return lines


def main() -> None:
    """Read the hook payload, and answer for whichever of the two audiences asked.

    The event name is echoed back verbatim in `hookEventName` rather than hardcoded:
    this one script answers `SessionStart` and `SubagentStart`, and a reply naming the
    wrong event is a reply the harness discards silently — the failure that looks
    exactly like a hook that did not run.
    """
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}
    event = payload.get("hook_event_name") or "SessionStart"
    if event not in ("SessionStart", "SubagentStart"):
        return

    try:
        queue_text = QUEUE.read_text(encoding="utf-8")
    except OSError:
        return
    try:
        archive_text = ARCHIVE.read_text(encoding="utf-8")
    except OSError:
        archive_text = ""

    applied = _applied_rules(archive_text)
    if event == "SubagentStart":
        lines = _subagent_body(applied)
    else:
        lines = _session_body(applied, _queued_entries(queue_text))

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": event,
                "additionalContext": "\n".join(lines),
            }
        },
        sys.stdout,
    )


if __name__ == "__main__":
    main()
