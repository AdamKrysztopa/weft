"""Every check the store conformance kit publishes is bound by the suite that runs it.

`docs/internal/lessons.md` `L26.4`. `weft_store.conformance` offers every `check_*` it defines
without a registration step, but `tests/integration/test_store_conformance.py` runs each through a
hand-written wrapper — so `32.2`'s two new checks ran in no green gate while a commit message said
they passed on both backends. Sized at the Phase 32 drain: 31 checks walked, 3 unbound.

Read by `ast`, not by import: the question is which names the suite's source references.

**And a stranger's store runs the whole kit** (`R43.54`). An example pack's test file that imports
the kit calls `checks_for` at least once with no comprehension filtering what it returns: the
graph example bound three hand-picked checks, and the whole kit found seven defects in it.
Sized 2026-09-25 at 2 files; 1 failed.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

from .conftest import REPO_ROOT, tracked_files

KIT: Final[Path] = REPO_ROOT / "packages/weft-rag/src/weft_store/conformance.py"
SUITE: Final[Path] = REPO_ROOT / "tests/integration/test_store_conformance.py"
KIT_MODULE: Final[str] = "weft_store.conformance"

#: Published checks no test binds. Each entry is a check that has never run; ledger `R32.4`
#: binds them and empties this.
UNBOUND_CHECKS_WAIVED: Final[frozenset[str]] = frozenset({})


def published_checks(source: str) -> frozenset[str]:
    return frozenset(
        node.name
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name.startswith("check_")
    )


def referenced_names(source: str) -> frozenset[str]:
    tree = ast.parse(source)
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    return frozenset(names)


def imports_the_kit(tree: ast.Module) -> bool:
    return any(
        (isinstance(node, ast.ImportFrom) and node.module == KIT_MODULE)
        or (isinstance(node, ast.Import) and any(a.name == KIT_MODULE for a in node.names))
        for node in ast.walk(tree)
    )


def runs_the_whole_kit(tree: ast.Module) -> bool:
    """Whether some `checks_for(...)` call's result feeds no filtering comprehension."""
    filtered = {
        id(generator.iter)
        for node in ast.walk(tree)
        if isinstance(node, ast.ListComp | ast.SetComp | ast.GeneratorExp | ast.DictComp)
        for generator in node.generators
        if generator.ifs
    }
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name | ast.Attribute)
        and (node.func.id if isinstance(node.func, ast.Name) else node.func.attr) == "checks_for"
        and id(node) not in filtered
        for node in ast.walk(tree)
    )


def example_test_files() -> tuple[str, ...]:
    return tuple(
        sorted(
            name
            for name in tracked_files()
            if name.startswith("examples/") and "/tests/" in name and name.endswith(".py")
        )
    )


def test_every_published_conformance_check_is_bound() -> None:
    # Arrange
    published = published_checks(KIT.read_text())
    bound = referenced_names(SUITE.read_text())

    # Act
    unbound = published - bound

    # Assert
    assert published, f"no `check_*` found in {KIT.relative_to(REPO_ROOT)}"
    assert unbound - UNBOUND_CHECKS_WAIVED == frozenset(), (
        f"published by the kit and run by no test: {sorted(unbound - UNBOUND_CHECKS_WAIVED)} — "
        f"bind each in {SUITE.relative_to(REPO_ROOT)} and run it on both backends (L26.4)"
    )
    assert UNBOUND_CHECKS_WAIVED - unbound == frozenset(), (
        f"waived but now bound — remove from UNBOUND_CHECKS_WAIVED: "
        f"{sorted(UNBOUND_CHECKS_WAIVED - unbound)}"
    )


def test_the_check_can_actually_fail() -> None:
    kit = "async def check_one(store): ...\nasync def check_two(store): ...\ndef helper(): ...\n"
    suite = "from k import check_one\n\nasync def test_one(store):\n    await check_one(store)\n"

    unbound = published_checks(kit) - referenced_names(suite)

    assert unbound == frozenset({"check_two"})


def test_every_example_store_suite_runs_the_whole_kit() -> None:
    # Arrange
    suites = [
        name
        for name in example_test_files()
        if (REPO_ROOT / name).is_file()
        and imports_the_kit(ast.parse((REPO_ROOT / name).read_text()))
    ]

    # Act
    partial = [
        name for name in suites if not runs_the_whole_kit(ast.parse((REPO_ROOT / name).read_text()))
    ]

    # Assert
    assert suites, "no example test file imports weft_store.conformance"
    assert partial == [], (
        f"these import the store conformance kit and run only a subset of it: {partial} — call "
        "`checks_for(store)` and run every check it returns (R43.54)"
    )


def test_the_whole_kit_check_can_actually_fail() -> None:
    picked = ast.parse(
        "from weft_store.conformance import checks_for\n"
        "ours = [c for c in checks_for(s) if c.__name__ == 'x']\n"
    )
    whole = ast.parse("import weft_store.conformance as k\noffered = k.checks_for(s)\n")

    assert imports_the_kit(picked) and not runs_the_whole_kit(picked)
    assert imports_the_kit(whole) and runs_the_whole_kit(whole)
