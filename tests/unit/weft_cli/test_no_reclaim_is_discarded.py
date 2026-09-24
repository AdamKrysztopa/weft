"""No `reclaim_withdrawn(...)` call stands as a bare statement — carried repair **R43.43**.

`reclaim_withdrawn` returns the `Removed` saying how many nodes it reclaimed, and twice a caller
dropped it, so an operator was told nothing: `weft reconcile` until R43.38, and every corpus build's
bind until R43.43. A call whose value is an expression statement's is a count nobody can report.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

PACKAGES: Final[Path] = Path(__file__).resolve().parents[3] / "packages"


def discarded_reclaims(tree: ast.AST, *, module: str) -> list[str]:
    """`module:line` for every expression statement whose value is a `reclaim_withdrawn` call,
    awaited or not.
    """
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Expr):
            continue
        value = node.value.value if isinstance(node.value, ast.Await) else node.value
        if not isinstance(value, ast.Call):
            continue
        called = value.func
        name = called.id if isinstance(called, ast.Name) else getattr(called, "attr", None)
        if name == "reclaim_withdrawn":
            found.append(f"{module}:{node.lineno}")
    return found


def _every_module() -> list[tuple[str, ast.AST]]:
    return [
        (path.relative_to(PACKAGES).as_posix(), ast.parse(path.read_text(encoding="utf-8")))
        for path in sorted(PACKAGES.rglob("*.py"))
    ]


def test_no_package_discards_what_reclaim_withdrawn_returned() -> None:
    # Arrange
    modules = _every_module()

    # Act
    discarded = [
        site for module, tree in modules for site in discarded_reclaims(tree, module=module)
    ]

    # Assert
    assert modules, "no module was found under packages/, so this check compares nothing"
    assert discarded == [], (
        f"reclaim_withdrawn's Removed is discarded at {discarded}; carry its node_count to the "
        "result the operator reads"
    )


def test_the_check_can_actually_fail() -> None:
    # Arrange
    source = (
        "async def bind(holder, other, layer):\n"
        "    await holder.reclaim_withdrawn(layer)\n"
        "    other.reclaim_withdrawn(layer)\n"
        "    removed = await holder.reclaim_withdrawn(layer)\n"
        "    return (await holder.reclaim_withdrawn(layer)).node_count + removed.node_count\n"
    )

    # Act
    discarded = discarded_reclaims(ast.parse(source), module="planted")

    # Assert
    assert discarded == ["planted:2", "planted:3"]
