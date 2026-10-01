"""Fitness function 40 — a test never writes to `os.environ`. `01` -> *Fitness functions* item 40.

`poe ci-checks` exports `WEFT_DATABASE_URL` for every test. A fixture that sets it to a throwaway
value and later calls `os.environ.pop` deletes the variable the gate exported, not the one the
fixture set, and every later container test fails in the full gate and in nothing narrower
(`L28.93`). `mock.patch.dict(os.environ, ...)` and `monkeypatch.setenv` both restore what was
there, so neither is flagged.

**Scope: every tracked `.py` under a `tests` directory, plus any `test_*.py` or `conftest.py`
elsewhere.** A subscript assignment, a `del`, or a call to `pop`, `popitem`, `setdefault`, `update`
or `clear` on `os.environ` fails. A copy (`env = dict(os.environ)`) is a different object and is
not walked. At filing: 708 test files, 0 sites. The waiver is pinned empty.
"""

from __future__ import annotations

import ast
from pathlib import PurePosixPath
from typing import Final

from .conftest import REPO_ROOT, tracked_files

WAIVED: Final[frozenset[str]] = frozenset()

_MUTATING_CALLS: Final[frozenset[str]] = frozenset(
    {"pop", "popitem", "setdefault", "update", "clear"}
)


def _is_test_code(path: str) -> bool:
    pure = PurePosixPath(path)
    return path.endswith(".py") and (
        "tests" in pure.parts or pure.name.startswith("test_") or pure.name == "conftest.py"
    )


def _is_os_environ(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "environ"
        and isinstance(node.value, ast.Name)
        and node.value.id == "os"
    )


def _is_environ_item(node: ast.expr) -> bool:
    return isinstance(node, ast.Subscript) and _is_os_environ(node.value)


def _targets(node: ast.AST) -> list[ast.expr]:
    if isinstance(node, ast.Assign | ast.Delete):
        return node.targets if isinstance(node, ast.Assign) else list(node.targets)
    if isinstance(node, ast.AugAssign | ast.AnnAssign):
        return [node.target]
    return []


def _is_mutating_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _MUTATING_CALLS
        and _is_os_environ(node.func.value)
    )


def environment_writes(source: str, label: str) -> list[str]:
    """Every direct write to `os.environ` in `source`.

    Args:
        source: Python source text.
        label: The path each violation is reported under.

    Returns:
        One `label:line` entry per write.
    """
    lines: set[int] = {
        node.lineno
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.stmt | ast.expr)
        and (_is_mutating_call(node) or any(_is_environ_item(t) for t in _targets(node)))
    }
    return [f"{label}:{line}" for line in sorted(lines)]


def test_no_test_writes_to_os_environ() -> None:
    tests = sorted(path for path in tracked_files() if _is_test_code(path))
    assert tests, "no test files found — the filter is wrong, not the tree"

    violations = [
        violation
        for path in tests
        if path not in WAIVED
        for violation in environment_writes((REPO_ROOT / path).read_text(encoding="utf-8"), path)
    ]

    assert not violations, (
        "A test that writes to `os.environ` and later undoes it with `pop` deletes the value "
        "`poe ci-checks` exported. Use `mock.patch.dict(os.environ, ...)` or "
        "`monkeypatch.setenv`, which restore what was there:\n  " + "\n  ".join(violations)
    )


def test_the_waiver_is_empty() -> None:
    assert frozenset() == WAIVED


def test_the_check_can_actually_fail() -> None:
    planted = (
        "import os\n"
        "os.environ['A'] = '1'\n"
        "os.environ.pop('A')\n"
        "del os.environ['A']\n"
        "os.environ.update({'A': '1'})\n"
        "os.environ.setdefault('A', '1')\n"
    )
    safe = (
        "import os\n"
        "from unittest import mock\n"
        "env = dict(os.environ)\n"
        "env['A'] = '1'\n"
        "with mock.patch.dict(os.environ, {'A': '1'}):\n"
        "    value = os.environ['A']\n"
        "    os.environ.get('A')\n"
    )

    assert environment_writes(planted, "planted") == [
        "planted:2",
        "planted:3",
        "planted:4",
        "planted:5",
        "planted:6",
    ]
    assert environment_writes(safe, "safe") == []
