"""Every production ingest goes through `run_index_for`, which alone passes `Dependencies` on.

Carried repair `R19.17`. `weft_cli.ingest.run_index` takes each ingest concern as its own keyword,
and `L8.24` fired three times at its call sites, each time because a concern was passed by hand at
one site and forgotten at another. The fourth was live: `weft eval run` passed everything
`weft index` did except `contributions`. `run_index_for` reads every concern off `Dependencies` in
one place, and this check keeps each production caller on it, so a new concern is one edit rather
than one per caller. Tests still call `run_index` directly with doubles; only production is held.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

SOURCE_ROOT: Final[Path] = Path(__file__).resolve().parents[3] / "packages" / "weft-rag" / "src"
_ALLOWED: Final[frozenset[str]] = frozenset({"weft_cli/ingest.py::run_index_for"})


def run_index_callers(tree: ast.AST, *, module: str) -> set[str]:
    """`module::function` for every function in `tree` whose body calls `run_index` directly."""
    callers: set[str] = set()
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for node in ast.walk(function):
            if not isinstance(node, ast.Call):
                continue
            called = node.func
            name = called.id if isinstance(called, ast.Name) else getattr(called, "attr", None)
            if name == "run_index":
                callers.add(f"{module}::{function.name}")
    return callers


def _production_callers() -> set[str]:
    callers: set[str] = set()
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        module = path.relative_to(SOURCE_ROOT).as_posix()
        callers |= run_index_callers(ast.parse(path.read_text(encoding="utf-8")), module=module)
    return callers


def test_only_run_index_for_calls_run_index_in_production() -> None:
    # Arrange / Act
    callers = _production_callers()

    # Assert
    assert callers, "no production caller of run_index was found, so this check compares nothing"
    assert callers == _ALLOWED, (
        f"production code calls run_index directly from {sorted(callers - _ALLOWED)}; call "
        "weft_cli.ingest.run_index_for(deps, ...) so every Dependencies concern arrives together"
    )


def test_the_check_can_actually_fail() -> None:
    # Arrange
    source = "async def index(deps):\n    await run_index(path, registry=deps.registry)\n"

    # Act
    callers = run_index_callers(ast.parse(source), module="weft_cli/commands.py")

    # Assert
    assert callers == {"weft_cli/commands.py::index"}
