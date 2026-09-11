"""PreToolUse guard: refuse a verdict read from somewhere that is not the check.

Two rules, and they are one rule seen twice — `L10.24`'s second instance is literally
`pytest ... | tail -3 && git commit`, which both of them match.

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

**The second rule: `$?` read after a pipeline.** `docs/lessons.md` `L12.16`. Verifying a
repair on a shipped wheel, the binary was run as `weft ... 2>&1 | tail -8` and its exit code
read on the next line as `echo "exit=$?"`, which printed **0** — `tail`'s status — for a
binary that had exited **1**. It was noticed within the turn only because the message printed
directly above it contradicted the number.

That is `L10.24` instance 2 exactly, one step earlier in the sequence: the same pipeline, the
same wrong status, and no `git commit` for the first rule to see. The rule this guard already
prints as remedy — *"never piped into `tail`/`head`"* — was being read by the same author who
wrote it, in the same session, while typing the thing it forbids. So it stops being advice
printed after a refusal and becomes a refusal of its own: a command that pipes into a pager or
a truncator and then reads `$?` is refused, whether or not a commit follows.

Redirect and read the file instead — `cmd > out.log 2>&1; echo "EXIT=$?"; tail -8 out.log` —
which is the shape this guard's own remedy text has recommended since `L10.24`.

**Two false positives, met within minutes of writing it, and only one of them survives.** The
rule as first written had no notion of an intervening command, so it fired on the very shape it
recommends — a truncating pipe on one line, then a *separate*, redirected run whose `$?` is its
own — twice, on commands that were already following its own remedy. `reads_status_after_a_pipe`
now requires that nothing between the pipe and the `$?` be a redirect or a command substitution,
because either means another command ran and set the status being read. Eight probe cases cover
it, including both instances and both of these.

**The one that survives: a shell command that *quotes* the forbidden shape.**
The first attempt to exercise this rule was an inline `echo '{"command": "... | tail -8 ...$?"}'`
piped into the hook, and the hook refused it — the pattern was inside a single-quoted JSON
argument, which the shell never executes as a pipeline. `strip_heredocs` cannot help, because
that is not a heredoc, and stripping quoted strings in general would weaken the match against
a real `sh -c '...'`. This is the trade this file's docstring already states — a false refusal
costs one turn and prints the remedy; a missed one costs a wrong verdict — so the fix is in how
you test it: build the payload in Python and hand it to the hook on stdin, never by typing the
offending text into a shell command. That is the shape the probe used, and all six of its cases
(both instances, the remedy, a pipe with no `$?`, a bare commit, and a `$?` *before* the pipe)
answer correctly.

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


#: A pipe into a command that discards output and replaces the exit status with its own.
#: `tail`/`head` are `L10.24`'s and `L12.16`'s own instances; the others are the same hazard by
#: the same mechanism, and listing them costs nothing. Matched anywhere, because the hazard is
#: the pipeline, not its position.
_TRUNCATING_PIPE = re.compile(r"\|\s*(?:tail|head|less|more|grep|wc|sort|uniq)\b")

#: A read of the previous command's exit status. `$?` is the only spelling.
_EXIT_STATUS = re.compile(r"\$\?")

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


def reads_status_after_a_pipe(command):
    """True when `command` pipes into a truncator and then reads `$?` — `L12.16`.

    Position matters for the same reason it does in `offends`: `$?` *before* the pipeline is
    reading some earlier command's status and is not this defect. A `$?` on the same line as
    the pipe is still after it, which is the shape the instance took.

    Heredoc bodies are stripped first, exactly as in `offends` — prose describing this rule is
    not an instance of it, which is the false positive that guard's own first version shipped
    with (`strip_heredocs` below carries the story).
    """
    executable = strip_heredocs(command)
    pipe = _TRUNCATING_PIPE.search(executable)
    if pipe is None:
        return False
    status = _EXIT_STATUS.search(executable, pipe.end())
    if status is None:
        return False
    # **A redirect between the two means another command ran and set its own status**, so the
    # `$?` is not reading the pipeline's. Without this clause the rule fires on the ordinary
    # shape it exists to *recommend* — `thing | tail -3` on one line, then a separate
    # `other > out.log 2>&1; echo "EXIT=$?"` on the next — which it did, twice, within minutes
    # of being written, on commands that were already following its own remedy. A guard that
    # fires on safe commands is one people learn to route around, which is
    # `guard_history_rewrites.py`'s own stated reason for refusing four commands and not six.
    between = executable[pipe.end() : status.start()]
    return ">" not in between and "$(" not in between


PIPE_REASON = """Refused: this command pipes into a truncator and then reads `$?`, which is the
status of the LAST command in the pipeline — `tail`/`head`/`grep` — and not of the thing you
meant to check.

`docs/lessons.md` L12.16: a shipped binary run as `weft ... 2>&1 | tail -8` followed by
`echo "exit=$?"` reported 0 for a run that exited 1. L10.24's second instance is the same
pipeline with a `git commit` on the end.

Redirect, read the status, then look at the output:
  cmd > out.log 2>&1; echo "EXIT=$?"; tail -8 out.log"""


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
    if offends(command):
        sys.stderr.write(REASON + "\n")
        return 2
    if reads_status_after_a_pipe(command):
        sys.stderr.write(PIPE_REASON + "\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
