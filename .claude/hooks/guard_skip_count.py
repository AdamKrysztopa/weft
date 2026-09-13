"""PreToolUse guard: refuse a commit that adds a skip CI will count and does not move the count.

`docs/internal/lessons.md` `L19.1`, and it is the **third** time this constant has been the
subject of a lesson — `L11.22` and `L12.1` are both Applied, and the number even lives in
`.github/workflows/ci.yml` under a paragraph that says *"move this number in the commit that
changed it"*. It did not bite either time, and the reason is structural rather than careless:

**the moment it governs is invisible on the machine where the commit is made.** A test that
skips only on a clean checkout *runs* locally, so nothing looks different — the local gate is
green, the push is made, and CI reports *claimed 73 and produced 77* three minutes later. That
is a rule whose trigger no human can see, which `implement-ll`'s routing order says belongs in
machinery rather than in a louder sentence.

It recurred a fourth time in the session that wrote this hook: the Phase 21a close added
`tests/docs/test_settled_gates_are_not_cited_as_open.py`, whose two log-reading tests skip on a
clean checkout, and the number had to be moved 78 -> 80. That instance was caught by hand,
which is exactly the evidence that catching it by hand is what the project has been relying on.

**What is refused.** A `git commit` whose *staged* diff adds a line calling `untracked_reason(`
— the single point every untracked-by-design skip in this tree goes through, per
`tests/conftest.py`'s `UNTRACKED_BY_DESIGN` — while `.github/workflows/ci.yml`, the file that
declares the environment the count is a fact about, is not staged in the same commit.

**Why `untracked_reason` and not `pytest.mark.skipif` generally.** Most skips in this tree are
about a service being absent, and CI provisions those, so they do not move this number. The
ones that do are exactly the ones keyed on a file that is untracked by design: they run here
and skip there. Matching the narrower thing is what keeps the guard from firing on correct
work, which `guard_history_rewrites.py` states as the reason it refuses four commands and not
six.

**The remedy the refusal prints is a command, not an instruction.**
`WEFT_PRETEND_UNTRACKED=1 uv run poe test` makes `tests.conftest.untracked_reason` answer as a
clean checkout would, so the number can be read before it is pushed rather than after. That
mechanism already exists; what was missing was anything that tells you to run it.

Runs under bare `python3` (3.9 on the development machine), per `CLAUDE.md`: no 3.12 idiom
here, and `ci-checks` does not cover this directory.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

#: A `git commit` at a command position — the same anchoring `guard_history_rewrites.py` uses,
#: so a commit named inside a heredoc or a quoted message is not matched as one.
_GIT_COMMIT = re.compile(r"(?:^|[;&|]\s*|\n\s*)git\s+commit\b")

#: Every call that can create a **new reason to skip**. Both move `WEFT_TEST_EXPECTED_SKIPS`,
#: and until 2026-09-13 this held only the first — `docs/internal/lessons.md` `L21.9`.
#:
#: **The narrowing above was argued and its premise was wrong.** It read: *"Most skips in this
#: tree are about a service being absent, and CI provisions those, so they do not move this
#: number."* CI provisions Postgres and **deliberately provisions no Qdrant**, so a
#: service-absent skip moves the number whenever the service is one CI does not run — and 44 of
#: that count already came from exactly that. Phase 21b added eight Qdrant tests behind a
#: fixture that calls `pytest.skip`, this guard saw nothing, and `main` went red claiming 86
#: against 94. `L19.2`'s shape: a narrowing outliving the premise it rested on.
#:
#: **Sized before widening**, because a guard that fires on correct work is one people learn to
#: route around: measured 2026-09-13, **13 of the last 60 commits** add a `pytest.skip(` line,
#: against **32 of the last 40** that add a `registrar.add(` — which is why the plugin-
#: registration form of this idea was declined in the same drain and this one was not. Each of
#: those thirteen is a commit creating a new skip *reason*, which is exactly when the question
#: is worth asking.
_SKIP_CALLS = ("untracked_reason(", "pytest.skip(")

#: The file that declares the environment `WEFT_TEST_EXPECTED_SKIPS` is a fact about. A count
#: measured on a developer's machine has no home, because a developer's machine declares
#: nothing — `docs/internal/lessons.md` `L12.1`.
_WORKFLOW = ".github/workflows/ci.yml"


def _git(args):
    """`git` output, or `None` when git cannot answer. A guard that crashes blocks every
    command in the session, so every failure here is a pass.
    """
    try:
        done = subprocess.run(  # noqa: S603
            ["git"] + args,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return done.stdout


def adds_a_clean_checkout_skip(diff):
    """Whether the staged diff **adds** a call that can create a new reason to skip.

    **Added lines in `tests/` only, and the second half was learned by this guard refusing the
    commit that widened it.** Matching the token anywhere matched `"pytest.skip("` written as a
    *literal* in this file's own `_SKIP_CALLS`, and it would equally match the string quoted in a
    lesson, a changelog entry or a docstring. Only a skip in a test file can move the count, and
    a guard that fires on prose about itself is one people learn to route around —
    `guard_history_rewrites.py` states the same reason for refusing four commands and not six.

    Added lines only: a diff that moves or re-indents an existing skip changes no count, and
    `-` lines are removals, which move the number the other way and are the *good news* the
    workflow's own comment says to record. Removing one without moving the count fails CI just
    as loudly, and it fails with the number going down, which is legible; adding one fails with
    it going up, which reads as a service that did not come up.
    """
    current = ""
    for line in diff.splitlines():
        if line.startswith("+++"):
            # `+++ b/path/to/file.py`, or `+++ /dev/null` for a deletion.
            current = line[6:] if line.startswith("+++ b/") else ""
            continue
        if not current.startswith("tests/"):
            continue
        if line.startswith("+") and any(call in line for call in _SKIP_CALLS):
            return True
    return False


def offends():
    """Whether this commit adds a clean-checkout skip without touching the file that counts.

    Reads the **staged** tree, not the working tree, because that is what a `git commit` about
    to run will record — the same reason `phase-step` → *Finish* item 0 says to stage before
    the gate.
    """
    diff = _git(["diff", "--cached", "--unified=0"])
    if diff is None or not adds_a_clean_checkout_skip(diff):
        return False
    staged = _git(["diff", "--cached", "--name-only"])
    if staged is None:
        return False
    return _WORKFLOW not in staged.split()


REASON = """Refused: this commit adds a test that skips on a clean checkout, and does not move
the number CI checks that against.

A `untracked_reason(...)` skip RUNS on this machine and SKIPS in CI, so nothing looks wrong
locally — the gate is green, and CI reports `claimed N and produced N+k` after the push.
`docs/internal/lessons.md` L19.1; L11.22 and L12.1 are the same constant, twice before.

Measure it before you push, then move it:

  WEFT_PRETEND_UNTRACKED=1 uv run poe test      # answers as a clean checkout would
  # then set WEFT_TEST_EXPECTED_SKIPS in .github/workflows/ci.yml to that number + 45
  # (45 is what CI's own services add; the workflow comment carries the history)

Stage .github/workflows/ci.yml in the same commit and this guard passes. If you have checked
and the count genuinely does not move, staging the workflow with no change is not the answer —
say so in the commit message and re-run with the file touched only if it should be."""


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
    if _GIT_COMMIT.search(command) is None:
        return 0
    if offends():
        sys.stderr.write(REASON + "\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
