"""Stop — refuse to end a turn that harvested a lesson candidate and never read it.

The other half of `.claude/hooks/subagent_findings.py`. That hook writes what a dispatched
agent noticed into `.claude/lessons-spool.md`; this one makes reading it non-optional.
Without this, the spool is a file somebody has to remember to open — which is the exact
failure `lessons_context.py` was built to prevent, one level down, and a lesson that lands
in an unread file has not been collected, it has been filed.

**What it does not do.** It does not judge whether a finding is a lesson — that needs the
reasoning, and a hook has none. It decides one thing a hook *can* decide: the spool is
non-empty, and nobody has said what happened to it. The session then either promotes the
entry with the `lessons` skill or deletes it saying why. Both empty the spool; both are
fine; only silence is refused.

**`stop_hook_active` is why this cannot loop.** The payload carries it, and it is true on
the continuation this hook itself caused. Blocking again there would be an unbreakable
turn — the same shape as the `SubagentStop` injection loop measured on 2026-08-22, which
re-invoked a probe agent twelve times. So the block fires once. If the session ignores it,
that is a visible choice in the transcript rather than a hook fighting the model.

Exit 2 with the message on **stderr** is the documented way to hold a turn open; anything
else is silence and exit 0, on `lessons_context.py`'s rule — a hook that cannot do its job
must not break the session that was about to fix it.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPOOL = ROOT / ".claude" / "lessons-spool.md"

#: `subagent_findings.append` separates every entry with this and nothing else does — the file's
#: own header is written once, before the first one, and carries no separator.
_ENTRY_MARK = "\n---\n"


def pending(text: str) -> list[str]:
    """The `## <stamp> — <agent>` heading of every unread entry in the spool.

    **Split on the separator, then take one heading per part** — never a scan for `## ` lines
    across the whole file. Two ways that second shape was wrong, one of them found by an
    adversarial review that ran it rather than read it:

    - An entry's *body* is a model's own prose and may contain anything, including a line
      beginning `## `. Counting those inflates the total and, worse, makes the count depend on
      what an agent happened to write.
    - The first version excluded any heading containing the word `harvested`, meant to skip the
      file's own header. The header begins with a single `#`, so it was never matched anyway —
      and the exclusion instead made a real entry **invisible** whenever `agent_type` contained
      that substring. An `agent_type` of `harvested-checker` produced a spool with one finding
      in it and a gate that passed. A gate that exists to stop a finding being lost silently,
      losing a finding silently, on a data-dependent condition nobody would think to test.
    """
    parts = text.split(_ENTRY_MARK)[1:]
    headings: list[str] = []
    for part in parts:
        first = next((line for line in part.splitlines() if line.startswith("## ")), None)
        if first is not None:
            headings.append(first.strip())
    return headings


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if payload.get("hook_event_name") != "Stop":
        return 0
    # The continuation this hook already caused. See the module docstring.
    if payload.get("stop_hook_active"):
        return 0
    try:
        text = SPOOL.read_text(encoding="utf-8")
    except OSError:
        return 0

    entries = pending(text)
    if not entries:
        return 0

    listed = "\n".join(f"  - {entry.lstrip('# ')}" for entry in entries)
    print(
        f"`.claude/lessons-spool.md` holds {len(entries)} harvested finding(s) that this "
        f"turn has not accounted for:\n{listed}\n\n"
        f"These came from a dispatched agent's own `## Noticed` section — the one channel "
        f"by which what only it saw survives the context boundary. Read the spool, then "
        f"either write the entry into `docs/lessons.md` with the `lessons` skill, or "
        f"delete it and say in your reply why it is not a lesson. Empty the file either "
        f"way. A finding left in an unread file has been filed, not collected.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
