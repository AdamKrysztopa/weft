"""PreToolUse guard: refuse the git commands that discard work nobody can recover.

**This exists because the rule already existed and lost.** `.claude/agents/weft-implementer.md`
forbids `git stash`, `git reset`, `git checkout --` and `git clean`, with the reasons, citing
`docs/internal/lessons.md` L6.26 — and a dispatched implementer ran `git stash` anyway, because
generic harness guidance told it to stash before a destructive operation and the agent file's
sentence had no mechanism behind it. That is `docs/internal/lessons.md` L9.56: a project prohibition
that contradicts generic tool guidance needs a mechanism, not a stronger sentence, because the
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
        # **`docs/internal/lessons.md` `L11.28`** — this pattern was `git\s+checkout\s+--` and waved
        # `git checkout HEAD -- <path>` straight through: the same operation with a commit-ish in
        # the middle, and the more destructive of the two, since it overwrites from a commit
        # rather than from the index. A guard written against the *spelling* of a command guards
        # that spelling. `[^-\s]\S*\s+` matches one non-flag word — a commit-ish — so
        # `HEAD`, a sha, a branch or a tag are all covered, while `git checkout -b foo` and
        # `git checkout foo` (no `--`) stay untouched: neither discards a working tree.
        re.compile(_AT_COMMAND_POSITION + r"git\s+checkout\s+(?:[^-\s]\S*\s+)?--"),
        "`git checkout --` overwrites files from the index, silently and unrecoverably — and "
        "`git checkout <commit> -- <path>` overwrites them from that commit, which is the same "
        "loss with a longer spelling. If a file is in a state you did not intend, read it and "
        "say what is wrong with it.",
    ),
    (
        # **`docs/internal/lessons.md` `L22.47`.** Not git, and that is the point: the loss this
        # guard exists for is "work nobody can recover", and a throwaway database mid-measurement
        # is exactly that. Phase 29 swept `DROP DATABASE` over every name matching the harness's
        # own prefix, after checking the database *list* rather than the live *backends*, and
        # killed two runs belonging to a dispatched agent sharing the container. The failure it
        # produced — `FATAL: database "..." does not exist` — reads as an application defect, so
        # the cost is not only the lost run but the time spent disbelieving the tool.
        #
        # Matched on the pattern, never on the drop: `DROP DATABASE weft_bench_lat_10000_64_x`
        # names what the caller created and is untouched. It is the `LIKE`/glob *sweep* that
        # cannot know whose database it matched.
        # The flags sit once, at the very front: `(?is)` on the second alternation branch is a
        # DeprecationWarning today and an error on a later Python, and this directory runs under
        # bare `python3` outside `ci-checks`, so nothing else would have said so.
        re.compile(
            r"(?is)"
            r"(?:(?:DROP\s+DATABASE|pg_terminate_backend)\b(?:(?!;).)*?"
            r"\bdatname\b(?:(?!;).)*?\bLIKE\b"
            r"|\bdatname\s+LIKE\b(?:(?!;).)*?(?:DROP\s+DATABASE|pg_terminate_backend))"
        ),
        "dropping or terminating by a `datname LIKE` pattern takes every database the pattern "
        "matches, including ones another process is still measuring against — and the error it "
        'leaves them, `FATAL: database "..." does not exist`, looks exactly like a bug in their '
        "own code. Drop the exact names you recorded when you created them. If you must sweep, "
        "first read `pg_stat_activity` for live backends and refuse the ones that have any, "
        "rather than terminating them to take the resource.",
    ),
    (
        re.compile(_AT_COMMAND_POSITION + r"git\s+clean\b"),
        "`git clean` deletes untracked files, which in this tree includes reading material kept "
        "deliberately out of version control. Delete named paths instead, having looked at them.",
    ),
)

REASON = (
    "Refused: `{command}` is one of the commands this repository does not run, because each "
    "destroys work that exists nowhere else — four git commands, and a database sweep matched "
    "by name pattern.\n\n"
    "{advice}\n\n"
    "This is `.claude/agents/weft-implementer.md`'s standing prohibition, enforced rather than "
    "stated: it was read and overridden once by generic tool guidance (`docs/internal/lessons.md` "
    "L9.56,"
    "L6.26). If you genuinely need one of these, ask the person you are working with — that is "
    "the whole remedy, and it is cheap."
)


#: A heredoc body: everything between `<<` (or `<<-`) with its delimiter and that delimiter alone
#: on a line. Prose, never a command.
_HEREDOC = re.compile(r"<<-?\s*[\"\']?(\w+)[\"\']?\n.*?^\1\s*$", re.DOTALL | re.MULTILINE)

#: A quoted segment. A shell argument is not a command position, however many `|` it holds.
_QUOTED = re.compile(r"\"[^\"]*\"|\'[^\']*\'")


def without_prose(command):
    """`command` with heredoc bodies and quoted arguments blanked out.

    **Stripped before the split, not after, and that ordering is the whole fix.**
    `_AT_COMMAND_POSITION` treats `|` as a separator and searched the raw string, so a `|`
    *inside* a quoted argument or a heredoc body made whatever followed it look like a fresh
    command. Measured 2026-09-12: a quoted mention of one of the four names was allowed, and the
    same mention inside a `\\|` alternation was refused — so a `grep` whose pattern is an
    alternation of the four, which is the ordinary way anyone audits or documents this guard,
    could not be run at all. It refused three separate edits *documenting itself*, the third
    being the one that added this function (`docs/internal/lessons.md` `L17.15`).

    Blanked to spaces rather than removed, so the surrounding structure — and therefore every
    real command position — is preserved.
    """
    blanked = _HEREDOC.sub(lambda match: " " * len(match.group(0)), command)
    return _QUOTED.sub(lambda match: " " * len(match.group(0)), blanked)


def offending(command):
    """The first blocked pattern this command matches, or None."""
    searchable = without_prose(command)
    for pattern, advice in BLOCKED:
        match = pattern.search(searchable)
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


def _self_test():
    """The probes `L17.15` was measured with. Run as `python3 <this file> --self-test`.

    `.claude/hooks/` is outside `ci-checks` by design, so this is hand-run — `CLAUDE.md`'s
    *"run a hook to know it works"* paragraph. **The false-positive half is the half that was
    missing**: a fixture of unquoted commands alone cannot tell a correct matcher from one that
    ignores quoting entirely, which is why this guard shipped for a phase refusing prose.

    The forbidden names are assembled rather than written out, so this file does not become a
    member of the population it checks — `L12.8`'s rule, and here it is load-bearing: written
    literally, these cases would make every `grep` over this directory refuse.
    """
    name = "git " + "stash"
    reset = "git " + "reset --hard"
    cases = (
        (name, True, "a bare command is refused"),
        ('echo "plain quoted mention: ' + name + '"', False, "a quoted mention is prose"),
        ('echo "a\\|' + name + '\\|b"', False, "a quoted alternation is still prose"),
        ("cat > /dev/null <<'EOF'\nprose a\\|" + name + "\\|b\nEOF\n", False, "a heredoc is prose"),
        ("ls && " + reset, True, "a real second command is still refused"),
        # `L22.47`. Assembled, like the names above, so this file does not become a member of
        # the population it checks — written literally, every grep over this directory would
        # refuse.
        (
            # noqa is scoped to this line, not the directory: `S608` is right to fire on a
            # concatenated SQL string, and it cannot tell a *probe* from a query. This one is
            # handed to `offending()` to prove the guard refuses it and is never executed. It is
            # assembled rather than written out for the same reason as the names above — written
            # literally, this file would join the population it checks (`L12.8`). Widening
            # `pyproject.toml`'s `.claude/hooks/*` entry to cover `S608` would suppress a real
            # rule across every hook for a reason about Python versions, which is `L8.37`'s
            # defect: an ignore wider than the sentence justifying it.
            "SELECT "  # noqa: S608
            + "pg_terminate_backend(pid) FROM pg_stat_activity WHERE "
            + "datname "
            + "LIKE 'weft_bench%'",
            True,
            "terminating backends by a name pattern is refused",
        ),
        (
            "DROP " + "DATABASE weft_bench_lat_10000_64_20260916012637",
            False,
            "dropping one database by its exact name is what the caller created, and is allowed",
        ),
        (
            'echo "do not sweep with ' + "DROP " + "DATABASE ... datname " + 'LIKE"',
            False,
            "a quoted mention of the sweep is prose",
        ),
    )
    failures = []
    for command, should_refuse, why in cases:
        refused = offending(command) is not None
        if refused != should_refuse:
            failures.append(
                "{0!r}: expected {1}, got {2} — {3}".format(
                    command,
                    "refused" if should_refuse else "allowed",
                    "refused" if refused else "allowed",
                    why,
                )
            )
    for failure in failures:
        sys.stderr.write(failure + "\n")
    print("{0} of {1} probes hold".format(len(cases) - len(failures), len(cases)))
    return 1 if failures else 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(_self_test())
    sys.exit(main())
