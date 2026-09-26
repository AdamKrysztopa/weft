"""SessionStart and SubagentStart — put what this repository has learned into whoever starts.

Put what this repository has already learned into whoever is about to work.

`docs/internal/lessons.md` records how the work goes wrong. A ledger nobody opens is
worse than no ledger, because it looks like a control that is working. So
nothing here depends on anyone remembering the file exists: this hook runs on
every session start and prints the open backlog, as titles, and a pointer to the
archive into the session's context.

**The archive's rules are not inlined.** Drained, each already lives in the hook,
check, skill or document it was routed to; inlined, they reached ~72 KB, past
what a hook's output may carry into context, so a session received a truncated
preview and nothing after it.

**`SubagentStart` too, because `SessionStart` does not fire for an agent dispatched
through the Agent tool** (`docs/internal/lessons.md` L5.1). A subagent is told something
different from the main session. The open queue is not injected: a subagent cannot
drain it, cannot triage it, and must never write to `docs/internal/lessons.md`, because
that needs reasoning it was not given. What it gets instead is the one instruction
that makes its findings recoverable: put them under a `## Noticed` heading, which
`.claude/hooks/subagent_findings.py` harvests. A heading a
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

DOCS = Path(__file__).resolve().parents[2] / "docs" / "internal"
QUEUE = DOCS / "lessons.md"
ARCHIVE = DOCS / "lessons-archive.md"

_SECTION = re.compile(r"^## (Queue|Applied|Declined)\s*$", re.MULTILINE)
_QUEUED = re.compile(r"^### (L[\d.]+) — (.+)$", re.MULTILINE)
_ARCHIVED = re.compile(r"^- (\*\*L[\d.]+\*\* .+)$", re.MULTILINE)
_FENCE = re.compile(r"^```", re.MULTILINE)


def _unfenced(text: str) -> str:
    """Drop fenced blocks.

    The archive documents its own entry format with a worked example, and an example that is
    indistinguishable from data is how a check ends up reporting its own documentation as a finding.
    """
    parts = _FENCE.split(text)
    return "".join(parts[::2])


def _sections(text: str) -> dict[str, str]:
    """Split on the three `## ` headings, ignoring anything before the first."""
    marks = [(m.group(1), m.end(), m.start()) for m in _SECTION.finditer(text)]
    out: dict[str, str] = {}
    for i, (name, end, _) in enumerate(marks):
        stop = marks[i + 1][2] if i + 1 < len(marks) else len(text)
        out[name] = text[end:stop]
    return out


NOTICED_HEADING = "## Noticed"


def _applied_rules(archive_text: str) -> list[str]:
    """Every drained lesson that became a rule.

    A `declined` line is a decision, not a rule, so it is not injected.
    """
    return [
        line.strip()
        for line in _ARCHIVED.findall(_unfenced(archive_text))
        if "*declined*" not in line
    ]


def _queued_entries(queue_text: str) -> list[tuple[str, str]]:
    return [
        (m.group(1), m.group(2)) for m in _QUEUED.finditer(_sections(queue_text).get("Queue", ""))
    ]


def _archive_pointer(applied: list[str]) -> str:
    """One line in place of the archive, which is past what a hook may inline (~70 KB)."""
    return (
        f"{len(applied)} drained lessons live in `docs/internal/lessons-archive.md` in the main "
        "checkout (a worktree carries no `docs/internal/`); each was routed into the hook, "
        "fitness function, skill or document that now enforces it, or declined with a reason. "
        "When a message cites an `L` id, grep the archive for it."
    )


def _session_body(applied: list[str], queued: list[tuple[str, str]]) -> list[str]:
    """What the driving session reads: where the rules live, and the backlog as titles."""
    lines = ["# What this repository has already learned", ""]
    lines.append(_archive_pointer(applied))
    lines.append("")
    if queued:
        lines.append(
            f"**{len(queued)} in the queue**, to be drained at the next phase close by "
            f"the `implement-ll` skill (`docs/internal/lessons.md`):"
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
    """What a dispatched agent reads: where the rules live, and one instruction about reporting.

    No queue. A subagent cannot triage a backlog and must not write `docs/internal/lessons.md`;
    handing it six open entries would be context it can only ignore. The `## Noticed`
    heading is the whole consuming side of this boundary — see the module docstring.
    """
    lines = ["# What this repository has already learned", ""]
    lines += [
        "**This working tree is shared, and `git status` is not evidence about your scope.** "
        "You may be one of several agents running in it at once, and the session that "
        "dispatched you has its own uncommitted edits. Paths you did not touch will be dirty; "
        "that is the arrangement, not a defect, and it is not worth a line in your report. "
        "Your scope is the files your brief names.",
        "",
        "**You do not write to `docs/internal/lessons.md`.** Writing a lesson needs reasoning you "
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
        "",
        _archive_pointer(applied),
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
