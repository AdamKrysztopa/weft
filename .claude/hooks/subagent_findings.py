"""SubagentStop — harvest what only the subagent saw, before its context is gone.

`.claude/agents/weft-implementer.md` has always ended by asking for "anything you noticed
and did not act on... the channel by which the caller finds out what only you saw". That
was a **producing side with no consuming side** — `phase-step` never said to route it
anywhere, so a lesson paid for inside a dispatched agent reached the orchestrator's
context and died there. `docs/lessons.md` L5.15 is the rule that shape breaks, and the
skill that cites L5.15 was the one breaking it.

This hook is the consuming side. It reads the agent's final message, takes everything
under its `## Noticed` heading, and appends it to `.claude/lessons-spool.md`. The
dispatching session drains that spool into `docs/lessons.md` — or records that it
declined to — and `.claude/hooks/lessons_gate.py` refuses to let the turn end while the
spool still holds unread entries.

**An exact heading, not a heuristic.** `.claude/hooks/lessons_context.py` tells every
subagent to use `## Noticed` verbatim, so the harvest is a string match rather than a
guess about which paragraph was the interesting one. Two shapes travelling in one stream
need a discriminant (`docs/lessons.md` L5.16); the heading is it.

**This hook writes nothing to stdout, and that is load-bearing rather than tidy.**
Measured 2026-08-22 with a probe, before any of this was built: emitting
`hookSpecificOutput.additionalContext` from `SubagentStop` does *not* inform the parent
session — it sends the subagent **back**, repeatedly. The probe agent was re-invoked
twelve times and its real answer ("FOUND MAGIC-INJECT-SubagentStart-7f3a", captured in
the log) was overwritten by "Standing by." The published documentation says only that
`SubagentStop` cannot inject into the parent, which reads as a harmless no-op and is not:
it is a loop that destroys the result. So the finding travels through a **file**, and the
only thing this hook may ever do on the way out is exit 0.

**Written for the system interpreter, not this project's.** Hooks are launched as bare
`python3`, which on this machine is 3.9 — so `CLAUDE.md`'s "native 3.12 type hints" rule
does not reach this directory. `from __future__ import annotations` is what lets the
signatures below stay in the project's own idiom anyway, and `timezone.utc` stands in for
3.11's `datetime.UTC`. Found by running the hook rather than by reading it, which is the
only way this class of defect surfaces: a hook that fails to import is silently a hook
that does not exist.

An unreadable spool, an unparsable payload or a missing heading all produce silence and
exit 0, on `lessons_context.py`'s own rule: a hook that cannot do its job must not break
the session that was about to fix it. The corresponding guarantee is that it never
invents — no heading means no entry, never a reassuring one.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPOOL = ROOT / ".claude" / "lessons-spool.md"

HEADING = "## Noticed"

#: The heading line. **Deliberately loose, and every relaxation here is a measured near-miss.**
#: An adversarial review fed the first version `## noticed`, `### Noticed` (nested under another
#: heading) and `## Noticed: things I saw`; all three produced no entry, no error and exit 0 —
#: total silent loss of the finding. The instruction says "the exact string" and nothing enforces
#: it, so a model drifting one character costs the whole channel. Matching loosely is the correct
#: trade: a false positive spools a paragraph somebody deletes, a false negative loses a lesson.
_HEADING = re.compile(r"^[ \t]*#{2,4}[ \t]*Noticed\b[^\n]*$", re.M | re.I)

#: Anything that could be read back as an entry boundary by `lessons_gate.pending`.
_UNSAFE = re.compile(r"[\r\n`]+")
#: A body whose only content is punctuation, "none", "nothing", "n/a" — an honest empty.
_EMPTY = re.compile(r"^[\s\-*_.·—–]*(none|nothing|n/?a|nil)?[\s\-*_.·—–]*$", re.I)


def noticed_section(message: str) -> str | None:
    """The text under `## Noticed`, or `None` when the agent reported nothing.

    An agent that wrote the heading with nothing under it said "I looked and found
    nothing", which is a different fact from never having been asked — but it is not a
    finding either, so it spools nothing. Returning `None` for both keeps the spool a
    list of things to act on rather than a log of dispatches.
    """
    found = _HEADING.search(message or "")
    if found is None:
        return None
    # **Everything to the end of the message, not up to the next `## `.** The old form stopped at
    # the first body line that merely looked like an H2, so a finding that quoted a document
    # heading was silently truncated mid-thought. The instruction is to end the report with this
    # section, so end-of-message is what it means — and where the two readings differ, capturing
    # a trailing paragraph too many is recoverable and dropping half a finding is not.
    body = message[found.end() :].strip()
    if not body or _EMPTY.match(body):
        return None
    return body


def _safe(value: str) -> str:
    """One field, flattened so it cannot forge an entry boundary in the spool.

    `append` writes a line-oriented format that `lessons_gate.pending` reads back, and
    `agent_type` is supplied by whatever dispatched the agent. A newline in it would write a
    second `## ` heading and spoof an extra entry; a backtick would break the quoting. The same
    file's docstring insists on "an exact heading, not a heuristic" for the *input* side, and
    this is that standard applied to its own output — found by an adversarial review that
    pointed out the asymmetry.
    """
    return _UNSAFE.sub(" ", value).strip() or "agent"


def append(entry: str, *, agent_type: str, agent_id: str, transcript: str) -> None:
    """Add one harvested finding to the spool, creating it with its own header.

    Append-only and plain markdown: the drain is a person or a session reading it, and a
    format that needs a parser to read is a format that stops being read.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if not SPOOL.exists():
        SPOOL.write_text(
            "# Lesson candidates harvested from dispatched agents\n\n"
            "Written by `.claude/hooks/subagent_findings.py` from each agent's own\n"
            "`## Noticed` section. **Drain this file** — promote what is a lesson into\n"
            "`docs/lessons.md` with the `lessons` skill, and delete what is not, saying why\n"
            "in the commit. `.claude/hooks/lessons_gate.py` blocks the turn from ending\n"
            "while anything is still here.\n",
            encoding="utf-8",
        )
    with SPOOL.open("a", encoding="utf-8") as fh:
        fh.write(f"\n---\n\n## {stamp} — `{_safe(agent_type)}` ({_safe(agent_id)[:12]})\n\n")
        fh.write(f"Transcript: `{_safe(transcript)}`\n\n")
        fh.write(entry.rstrip() + "\n")


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return
    if payload.get("hook_event_name") != "SubagentStop":
        return
    entry = noticed_section(payload.get("last_assistant_message") or "")
    if entry is None:
        return
    try:
        append(
            entry,
            agent_type=str(payload.get("agent_type") or "agent"),
            agent_id=str(payload.get("agent_id") or ""),
            transcript=str(payload.get("agent_transcript_path") or ""),
        )
    except OSError:
        return


if __name__ == "__main__":
    main()
    # Never anything on stdout — see the module docstring. This is the whole contract.
    sys.exit(0)
