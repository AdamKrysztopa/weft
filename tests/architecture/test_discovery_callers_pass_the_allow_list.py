"""Every first-party `discover(` call passes the allow-list, never `allow=None` (`L28.114`).

Fitness function 8(a) proves refusal precedes import through `build_dependencies`. Task 45.3 added a
second registry builder that called `discover(allow=None)`, so `weft eval claims check` imported
packs a project's `[packs] allow` refused, and nothing failed. This walks every call of
`discover` under `packages/*/src` (the kernel's own definition excepted) and fails on one that
omits `allow` or passes the literal `None`; on 2026-10-08 it walks 3 sites, waives 1, fails on 0.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

from .conftest import REPO_ROOT, tracked_files

#: Callers that are open by design. `discover_for_reference` feeds only the two generator scripts,
#: and a reference describes what a contract is, never one project's runtime policy.
OPEN_BY_DESIGN: Final[frozenset[str]] = frozenset(
    {"packages/weft-rag/src/weft_engine/contract_reference.py"}
)


def _calls_without_allow(source: str) -> list[int]:
    """Line numbers of `discover(...)` calls with no `allow=` or with `allow=None`."""
    found: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
        if name != "discover":
            continue
        allow = next((kw.value for kw in node.keywords if kw.arg == "allow"), None)
        if allow is None or (isinstance(allow, ast.Constant) and allow.value is None):
            found.append(node.lineno)
    return found


def _sources() -> list[Path]:
    return [
        REPO_ROOT / path
        for path in tracked_files()
        if path.startswith("packages/")
        and "/src/" in path
        and path.endswith(".py")
        and not path.endswith("weft_kernel/discovery.py")
    ]


def test_every_discover_call_passes_the_allow_list() -> None:
    # Act
    offending = {
        str(path.relative_to(REPO_ROOT)): lines
        for path in _sources()
        if (lines := _calls_without_allow(path.read_text(encoding="utf-8")))
    }

    # Assert
    assert set(offending) == OPEN_BY_DESIGN, "pass the project's [packs] allow to discover()"


def test_the_check_can_actually_fail() -> None:
    # Arrange
    planted = (
        "reports = discover(registry, allow=None, pack_settings={})\n"
        "kept = discover(registry, allow=allow)\n"
        "bare = discovery.discover(registry)\n"
    )

    # Act
    found = _calls_without_allow(planted)

    # Assert
    assert found == [1, 3]
