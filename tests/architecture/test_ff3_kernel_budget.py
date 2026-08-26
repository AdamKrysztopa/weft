"""Fitness function 3 — the kernel budget.

3,500 non-blank, non-comment, **non-docstring** lines in `weft-kernel`, tests
excluded. 2,800 is a review trigger, not a failure.

Settled in G1 with its reasoning, which matters more than the number: the reference's
kernel-analogous code measures roughly 2,500 lines, and the discovery, pipeline
and derivation machinery it has none of is worth another 600-900. The honest
estimate is ~3,300, so 3,500 leaves enough headroom to be legitimate and not
enough to be ignored.

Docstrings are excluded deliberately, so the budget can never become an argument
against documenting the kernel.

**The revision rule is the part that does the work:** these constants change only
by a dated entry in the decision log, never in the same pull request that grew
the kernel.
"""

import ast
from pathlib import Path
from typing import Final

from .conftest import KERNEL_ROOT

BUDGET: Final[int] = 3_500
REVIEW_TRIGGER: Final[int] = 2_800


def test_kernel_is_within_budget() -> None:
    counted = _count_kernel_lines()

    assert counted <= BUDGET, (
        f"weft-kernel is {counted} lines, over its {BUDGET}-line budget. This number is "
        f"changed only by a dated entry in docs/README.md's decision log, and never in the "
        f"same pull request that grew the kernel. If the kernel needs to be bigger, that is "
        f"a conversation about the kernel boundary, not an edit to this constant."
    )


def test_review_trigger_is_reported(capsys: object) -> None:
    counted = _count_kernel_lines()

    if counted > REVIEW_TRIGGER:
        print(  # noqa: T201 - the signal is the point
            f"\nweft-kernel is {counted} lines, past the {REVIEW_TRIGGER}-line review "
            f"trigger ({BUDGET} fails). Kernel growth belongs on the agenda before the "
            f"ceiling is a crisis."
        )

    assert counted <= BUDGET


def test_at_least_one_kernel_file_is_walked() -> None:
    # Floor — `08` §3's shape, applied to a source walk instead of a document walk: a
    # walk that finds nothing counts 0 lines, and 0 is `<= BUDGET` — the test above
    # would pass on an empty tree, exactly the shape `reference/study/08-salvage.md:777-782`'s
    # parity test takes.
    walked = sorted((KERNEL_ROOT / "src").rglob("*.py"))
    assert walked, (
        f"no `.py` file found under {KERNEL_ROOT / 'src'} — the walk itself is broken; "
        f"fix it before trusting the budget check above."
    )


def _count_kernel_lines() -> int:
    """Count real code lines in the kernel distribution, tests excluded."""
    return sum(_count_file(path) for path in sorted((KERNEL_ROOT / "src").rglob("*.py")))


def _count_file(path: Path) -> int:
    source = path.read_text(encoding="utf-8")
    docstring_lines = _docstring_lines(source)

    return sum(
        1
        for number, line in enumerate(source.splitlines(), start=1)
        if line.strip() and not line.lstrip().startswith("#") and number not in docstring_lines
    )


def _docstring_lines(source: str) -> set[int]:
    """Every line occupied by a module, class or function docstring."""
    occupied: set[int] = set()

    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue

        first = node.body[0] if node.body else None
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
            and first.end_lineno is not None
        ):
            occupied.update(range(first.lineno, first.end_lineno + 1))

    return occupied


def test_the_check_can_actually_fail(tmp_path: Path) -> None:
    """Fitness function 16 clause (b) — ledger task **6.15**.

    The budget check passes today and always has, so the only way to know the counter is
    measuring anything is to hand it source whose answer is known and watch the comparison
    go the other way. Planted through `_count_file` itself rather than against a number:
    what has to be proved is that the *counter* discriminates, not that `>` works.

    The fixture is chosen to exercise every exclusion the counter makes — a module
    docstring spanning three lines, a comment, a blank line, and a function docstring —
    because a counter that silently stopped excluding docstrings would still pass
    `test_kernel_is_within_budget` right up until it did not, and would then look like
    kernel growth rather than like a broken count.
    """
    # Arrange — four real code lines; everything else is docstring, comment or blank.
    source = '''"""A module docstring.

    Spanning three lines.
    """

# a comment

import os


def thing() -> int:
    """A function docstring."""
    value = os.getpid()
    return value
'''
    planted = tmp_path / "planted.py"
    planted.write_text(source, encoding="utf-8")

    # Act
    counted = _count_file(planted)
    docstrings = _docstring_lines(source)

    # Assert — the four are `import os`, `def thing...`, `value = ...`, `return value`.
    assert counted == 4
    assert 1 in docstrings and 3 in docstrings, "the module docstring was not excluded"
    assert counted > 3, "a budget of 3 would fail on this file — the comparison discriminates"
