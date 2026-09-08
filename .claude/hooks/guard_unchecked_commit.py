"""PreToolUse guard: refuse a `git commit` that rides on a check in the same command.

**Three instances in one phase, which is why this is a hook and not a sentence.**
`docs/lessons.md` `L10.24`:

1. A `python3 - <<PY` heredoc raising `AssertionError` was followed by an unconditional
   `git commit` on the next line of the same command. The assertion fired, the message went
   nowhere, and task 10.10 was committed with no ledger entry at all — found two steps later
   by grepping for a string that should have been there.
2. `pytest ... | tail -3 && git commit ...`. **A pipeline's exit status is its last
   command's**, so `tail` succeeded and satisfied the `&&` while the tests were failing.
3. `uv run poe ci-checks > log 2>&1; echo "GATE_EXIT=$?"` was auto-backgrounded before the
   `echo` ran, so the harness reported the *wrapper's* exit code — 0 — for a gate whose own
   log ended `Error: Sequence aborted after failed subtask 'test'`.

All three are one rule: **a check that gates a commit must be the last command in its own
chain, and its verdict must be read before the commit is composed.** The rule was written
down after the first instance and broken twice more by the author who wrote it, which is
`implement-ll`'s own criterion for moving a rule into machinery.

**What is refused, deliberately narrowly.** Only a command that contains *both* a verifying
command (`pytest`, `poe`, a `python3 -` heredoc, `ruff`, `pyright`) *and* a `git commit`,
joined by `&&`, `;` or a newline, with the check first. That is the exact shape all three
instances took. A bare `git commit`, a check alone, or a commit preceded only by `git add`
is untouched — a guard that fires on safe commands is one people learn to route around,
which is `guard_history_rewrites.py`'s own stated reason for refusing four commands and not
six.

**Why refusing beats warning.** The failure mode is silence: in every instance the command
*succeeded* and the wrong thing was committed. A warning printed into a successful result is
exactly what was missed the first three times.

Matching is textual and loose, per `CLAUDE.md`: where a machine parses what a model wrote,
match loosely and fail loudly. A false refusal costs one turn and prints how to split the
command; a missed one costs a commit nobody reviewed.

Blocking is a PreToolUse convention: exit 2, with the reason on stderr. Runs under bare
`python3` (3.9 on the development machine), so nothing here uses 3.10+ syntax.
"""

import json
import re
import sys

#: Commands whose whole purpose is to return a verdict. Matched at a command position — after
#: a separator or at the start — so a filename or a commit message mentioning "pytest" is not
#: a hit. `python3 -` covers the heredoc form instance 1 took.
_CHECK = re.compile(
    r"(?:^|[\n;&|]|\|\||&&)\s*"
    r"(?:uv\s+run\s+)?"
    r"(?:poe\b|pytest\b|ruff\b|pyright\b|python3?\s+-\s*<<|python3?\s+-\s)",
)

#: `git commit` at a command position. `--amend` is included: it rewrites the very commit a
#: swallowed check would have produced, so it carries the same hazard.
_COMMIT = re.compile(r"(?:^|[\n;&|]|\|\||&&)\s*git\s+commit\b")

REASON = """Refused: this command runs a check and a `git commit` together, so the commit can
happen while the check's verdict is unread.

Three instances of exactly this shape cost Phase 10 real work (`docs/lessons.md` L10.24):
an assertion whose message went nowhere and a task committed with no ledger entry; a
`pytest ... | tail -3 && git commit`, where a pipeline's exit status is its LAST command's,
so `tail` satisfied the `&&` while tests failed; and a gate whose exit code was reported by
a wrapper rather than by itself.

Split it into two turns:
  1. Run the check alone. Make it the last command in its own chain — never piped into
     `tail`/`head`, and if it may be backgrounded, write the verdict into the log itself
     (`... > gate.log 2>&1; echo "EXIT=$?" >> gate.log`) rather than trusting a status.
  2. Read the verdict, then commit.

`git add` followed by `git commit` is not refused; only a *check* joined to a commit is."""


#: A heredoc opener and the delimiter it will be terminated by, quoted or not.
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def strip_heredocs(command):
    """`command` with every heredoc *body* removed, terminators kept.

    **This guard's own first false positive, and it fired on the commit that documented it.**
    Writing this rule into `CLAUDE.md` meant a `python3 - <<PY ... PY` whose body contained the
    prose "a `git commit` chained onto a check" — data being written to a file, not a command —
    and the guard refused it. Heredoc bodies are the one place in a shell command where an
    arbitrary sentence may sit, so they are exactly where a textual match must not look.

    Removing the body does **not** weaken the check against `L10.24`'s first instance: there the
    `git commit` came *after* the heredoc terminator, on its own line, which is precisely the
    shape that survives this stripping. What is discarded is only text the shell never executes.
    """
    lines = command.split("\n")
    kept = []
    pending = []
    for line in lines:
        if pending:
            if line.strip() == pending[0]:
                pending.pop(0)
            continue
        kept.append(line)
        pending.extend(match.group(2) for match in _HEREDOC.finditer(line))
    return "\n".join(kept)


def offends(command):
    """True when `command` runs a check and then commits, in one command.

    Order matters: a `git commit` *before* a check is a different (and rarer) shape, and this
    guard is about a verdict that arrives too late to stop the commit, not about any
    co-occurrence. Compared by match position rather than by parsing the shell, which is the
    loose matching this file's docstring argues for.
    """
    executable = strip_heredocs(command)
    check = _CHECK.search(executable)
    if check is None:
        return False
    commit = _COMMIT.search(executable)
    if commit is None:
        return False
    return check.start() < commit.start()


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
    if not offends(command):
        return 0
    sys.stderr.write(REASON + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
