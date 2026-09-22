"""Every check the store conformance kit publishes is bound by the suite that runs it.

`docs/internal/lessons.md` `L26.4`. `weft_store.conformance` offers every `check_*` it defines
without a registration step, but `tests/integration/test_store_conformance.py` runs each through a
hand-written wrapper — so `32.2`'s two new checks ran in no green gate while a commit message said
they passed on both backends. Sized at the Phase 32 drain: 31 checks walked, 3 unbound.

Read by `ast`, not by import: the question is which names the suite's source references.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

from .conftest import REPO_ROOT

KIT: Final[Path] = REPO_ROOT / "packages/weft-rag/src/weft_store/conformance.py"
SUITE: Final[Path] = REPO_ROOT / "tests/integration/test_store_conformance.py"

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
