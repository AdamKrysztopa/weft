#!/usr/bin/env python3
"""A test that calls something the tree does not have says so now, not at dispatch.

`docs/internal/lessons.md` L8.35, and it is here rather than in a skill because it recurred **three
times in one phase** after being written down as prose. Each time the shape was identical: a test
written against an API nobody had read, dispatched to an implementer with a brief promising a green
tree, and returned `blocked` with the agent correctly refusing to edit a test.

    Context(tenant_id="t", registry=Registry())   # Context has no `registry`
    registrar.flush()                             # PackRegistrar has `commit`
    _Passage(node_id="n1")                        # Passage has `retrieved_by`

**The discriminator that makes this checkable, and it is the whole idea.** A test-first task
*should* be red: the module it is written against does not exist yet. That is `reportMissingImports`
and it is expected, so it is ignored here. What is never expected is a module that **does** exist
being asked for an attribute or a keyword it does not have — that is not the red phase, it is a
mistake, and no implementer can fix it because it lives in a file they may not touch.

So this reports the second kind and stays silent about the first. It is advisory: it prints and
exits 0, because the moment is *while a test is being written*, when the right response is to look,
not to be stopped.

**Named `guard_` rather than `test_`, and that is not cosmetic.** Fitness function 0 sweeps the
tree for suites the gate never runs, and a hook called `test_calls_resolve.py` is indistinguishable
from a test file to it — the first version of this hook failed FF0 the moment it was written. The
`guard_`/`format_`/`lessons_` naming every other hook uses is what keeps a hook out of a sweep
looking for tests.

**Hooks are not project Python** (`CLAUDE.md`): this runs under bare `python3`, 3.9 on the
development machine, so nothing here uses the 3.12 idiom the packages are held to.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

# The rules that mean "this name exists and does not have that". Deliberately not
# `reportMissingImports` or `reportMissingModuleSource`: an absent module is the red phase working.
_MISTAKE_RULES = (
    "reportAttributeAccessIssue",
    "reportCallIssue",
    "reportOptionalMemberAccess",
    "reportRedeclaration",
)

#: Phrases pyright uses for the exact shape this hook exists for, when it reports no rule name.
_MISTAKE_PHRASES = (
    "no attribute",
    "unexpected keyword argument",
    "is not a known attribute",
    "No overloads for",
)

_ERROR_LINE = re.compile(r"^\s*(?P<path>\S+\.py):(?P<line>\d+):\d+ - error: (?P<message>.+)$")


def _edited_path(payload):
    """The file this tool call wrote, or `None` if the payload has no single one."""
    tool_input = payload.get("tool_input") or {}
    for key in ("file_path", "path", "notebook_path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _is_test_file(path):
    """Whether `path` is under a `tests/` directory, relative or absolute.

    The first version asked for `"/tests/" in path` and the payload hands over a **relative**
    path — `tests/unit/...`, with no leading slash — so the hook was silent on every file it
    exists for. Found by triggering it on the exact mistake it was written for, which is
    `CLAUDE.md`'s own rule that a hook is code and a green gate is not a working binary.
    """
    normalised = path.replace(os.sep, "/")
    return normalised.endswith(".py") and (
        normalised.startswith("tests/") or "/tests/" in normalised
    )


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    path = _edited_path(payload)
    if not path or not _is_test_file(path) or not Path(path).exists():
        return 0

    project = os.environ.get("CLAUDE_PROJECT_DIR") or str(Path.cwd())
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell, no user input
            ["uv", "run", "pyright", path],  # noqa: S607 - `uv` is how this repo runs everything
            cwd=project,
            capture_output=True,
            text=True,
            timeout=90,
        )
    except (OSError, subprocess.TimeoutExpired):
        # A hook that cannot run its checker says nothing rather than blocking the edit.
        return 0

    mistakes = []
    for raw in completed.stdout.splitlines():
        match = _ERROR_LINE.match(raw)
        if match is None:
            continue
        message = match.group("message")
        named_rule = any(rule in message for rule in _MISTAKE_RULES)
        named_phrase = any(phrase in message for phrase in _MISTAKE_PHRASES)
        if named_rule or named_phrase:
            mistakes.append("  {}:{} — {}".format(path, match.group("line"), message))

    if mistakes:
        print(
            "\n".join(
                [
                    "",
                    "This test calls something that exists and lacks what it was asked for:",
                    "",
                    *mistakes[:6],
                    "",
                    "An absent module is the red phase and is not reported here. This is the other "
                    "kind: a call written from memory rather than copied from an existing use. "
                    "Grep for one real call and copy its shape — docs/internal/lessons.md L8.35, "
                    "which"
                    "recurred three times in Phase 7 before this hook existed.",
                ]
            ),
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
