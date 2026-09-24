"""Fitness function 36 — a `try` body holds one statement. `01` -> *Fitness functions* item 36.

A handler is a claim about which call can raise what. With one statement under `try` that claim
names its call; with several, an `except` written for the first also catches the same class from
the second, and the reader cannot tell which one the handler was written for. When a guarded
operation takes several steps, they move into a function and the `try` guards that one call.

**Scope: every tracked `.py` outside a test tree.** A path with a `tests` segment is test code,
where a `try` usually probes behaviour rather than guarding it. `except`, `else` and `finally`
bodies are unrestricted: only `Try.body` is the guarded region.
"""

from __future__ import annotations

import ast
from pathlib import PurePosixPath
from typing import Final

from .conftest import REPO_ROOT, tracked_files

MAX_TRY_STATEMENTS: Final[int] = 1


def _is_production(path: str) -> bool:
    parts = PurePosixPath(path).parts
    return path.endswith(".py") and "tests" not in parts


def oversized_try_bodies(source: str, label: str) -> list[str]:
    """Every `try` in `source` whose body holds more than one statement.

    Args:
        source: Python source text.
        label: The path each violation is reported under.

    Returns:
        One `label:line` entry per oversized `try`, with its statement count.
    """
    return [
        f"{label}:{node.lineno} holds {len(node.body)} statements"
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Try | ast.TryStar) and len(node.body) > MAX_TRY_STATEMENTS
    ]


def test_every_try_body_holds_one_statement() -> None:
    production = sorted(path for path in tracked_files() if _is_production(path))
    assert production, "no production files found — the filter is wrong, not the tree"

    violations = [
        violation
        for path in production
        for violation in oversized_try_bodies((REPO_ROOT / path).read_text(encoding="utf-8"), path)
    ]

    assert not violations, (
        "A `try` body may hold one statement. Move the steps into a function and guard that "
        "one call:\n  " + "\n  ".join(violations)
    )


def test_the_check_can_actually_fail() -> None:
    planted = (
        "try:\n"
        "    connect()\n"
        "    execute()\n"
        "except OSError:\n"
        "    pass\n"
        "try:\n"
        "    run()\n"
        "except* ValueError:\n"
        "    pass\n"
        "try:\n"
        "    first()\n"
        "    second()\n"
        "except* ValueError:\n"
        "    pass\n"
    )

    assert oversized_try_bodies(planted, "planted.py") == [
        "planted.py:1 holds 2 statements",
        "planted.py:10 holds 2 statements",
    ]


def test_handler_else_and_finally_bodies_are_unrestricted() -> None:
    allowed = (
        "try:\n"
        "    run()\n"
        "except OSError:\n"
        "    log()\n"
        "    raise\n"
        "else:\n"
        "    one()\n"
        "    two()\n"
        "finally:\n"
        "    three()\n"
        "    four()\n"
    )

    assert oversized_try_bodies(allowed, "allowed.py") == []


def test_test_trees_are_out_of_scope() -> None:
    assert _is_production("packages/weft-kernel/src/weft_kernel/runner.py")
    assert _is_production(".claude/hooks/format_python.py")
    assert not _is_production("tests/unit/weft_kernel/test_runner.py")
    assert not _is_production("examples/weft-example-graph/tests/conftest.py")
    assert not _is_production("docs/01-high-level-plan.md")
