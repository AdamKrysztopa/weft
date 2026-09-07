"""PreToolUse guard: refuse the git commands that discard work nobody can recover.

**This exists because the rule already existed and lost.** `.claude/agents/weft-implementer.md`
forbids `git stash`, `git reset`, `git checkout --` and `git clean`, with the reasons, citing
`docs/lessons.md` L6.26 — and a dispatched implementer ran `git stash` anyway, because generic
harness guidance told it to stash before a destructive operation and the agent file's sentence
had no mechanism behind it. That is `docs/lessons.md` L9.56: a project prohibition that
contradicts generic tool guidance needs a mechanism, not a stronger sentence, because the
sentence already lost once while being read correctly. The agent file's own neighbouring bullet
predicts this hook by name ("a PreToolUse hook will refuse most of these"); it did not exist.

**Why these four and not `git rm` or `git commit --amend`.** Each of the four throws away a
working tree or an index that exists nowhere else — no object is written, so nothing can be
recovered from the reflog. `--amend` and `rm` are recorded operations against committed history
and are recoverable; they are deliberately not refused, because a guard that fires on safe
commands is one people learn to route around.

Matching is textual and deliberately loose, per `CLAUDE.md`: where a machine parses what a model
wrote, match loosely and fail loudly. A false refusal costs one turn and prints why; a missed one
costs the work.

Blocking is a PreToolUse convention: exit 2, with the reason on stderr. Runs under bare `python3`
(3.9 on the development machine), so nothing here uses 3.10+ syntax.
"""

import json
import re
import sys

# Each entry: a compiled pattern, and what to do instead. The advice matters more than the
# refusal — an agent that is only told "no" will look for a synonym.
#: What may precede a real command: the start of the string, or a shell separator.
_AT_COMMAND_POSITION = r"(?:^|[;&|\n(]|&&|\|\|)\s*"

BLOCKED = (
    (
        re.compile(_AT_COMMAND_POSITION + r"git\s+stash\b"),
        "`git stash` moves uncommitted work somewhere no diff shows and no reviewer will look. "
        "If the tree is dirty and you did not expect it, say so and stop — that is a finding "
        "about who else is writing here, not an obstacle to clear.",
    ),
    (
        re.compile(_AT_COMMAND_POSITION + r"git\s+reset\b"),
        "`git reset` discards the index, and with `--hard` the working tree too. Nothing you "
        "have not committed survives it. If a commit is wrong, add one that corrects it.",
    ),
    (
        re.compile(_AT_COMMAND_POSITION + r"git\s+checkout\s+--"),
        "`git checkout --` overwrites files from the index, silently and unrecoverably. If a "
        "file is in a state you did not intend, read it and say what is wrong with it.",
    ),
    (
        re.compile(_AT_COMMAND_POSITION + r"git\s+clean\b"),
        "`git clean` deletes untracked files, which in this tree includes reading material kept "
        "deliberately out of version control. Delete named paths instead, having looked at them.",
    ),
)

REASON = (
    "Refused: `{command}` is one of the four git commands this repository does not run.\n\n"
    "{advice}\n\n"
    "This is `.claude/agents/weft-implementer.md`'s standing prohibition, enforced rather than "
    "stated: it was read and overridden once by generic tool guidance (`docs/lessons.md` L9.56, "
    "L6.26). If you genuinely need one of these, ask the person you are working with — that is "
    "the whole remedy, and it is cheap."
)


def offending(command):
    """The first blocked pattern this command matches, or None."""
    for pattern, advice in BLOCKED:
        match = pattern.search(command)
        if match:
            return match.group(0).strip(" ;&|\n("), advice
    return None


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    command = payload.get("tool_input", {}).get("command", "")
    if not isinstance(command, str):
        return 0
    hit = offending(command)
    if hit is None:
        return 0
    matched, advice = hit
    sys.stderr.write(REASON.format(command=matched, advice=advice) + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
