"""Shared location logic for the architecture checks.

These tests reason about the repository as a shipped artifact — its task
definitions, its distribution metadata, its line counts — so they need the
repository root rather than an installed package.
"""

import tomllib
from pathlib import Path
from typing import Final, cast

import pytest

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
KERNEL_ROOT: Final[Path] = REPO_ROOT / "packages" / "weft-kernel"


@pytest.fixture(scope="session")
def workspace_config() -> dict[str, object]:
    """The root `pyproject.toml`, parsed."""
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


@pytest.fixture(scope="session")
def kernel_config() -> dict[str, object]:
    """The kernel distribution's `pyproject.toml`, parsed."""
    with (KERNEL_ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def table_at(root: dict[str, object], *path: str) -> dict[str, object]:
    """Walk a nested TOML table, failing with the path that was missing.

    `tomllib` returns `dict[str, Any]`, and these checks read configuration that
    must be exactly the shape they expect — so the shape is asserted here once
    rather than re-narrowed at every call site.
    """
    current: object = root

    for key in path:
        table = _as_table(current, path)
        if key not in table:
            raise KeyError(f"missing table: {'.'.join(path)} (no '{key}')")
        current = table[key]

    return _as_table(current, path)


def str_list_at(table: dict[str, object], key: str) -> list[str]:
    """Read a list-of-strings field, treating an absent key as empty."""
    value = table.get(key, [])

    if not isinstance(value, list):
        raise TypeError(f"expected a list at '{key}', found {type(value).__name__}")

    return [item for item in cast(list[object], value) if isinstance(item, str)]


def _as_table(value: object, path: tuple[str, ...]) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(f"expected a table at {'.'.join(path)}, found {type(value).__name__}")

    return cast(dict[str, object], value)


def first_party_source_roots() -> dict[str, Path]:
    """Every first-party top-level import package, mapped to its own source directory.

    Read as `packages/*/src/*` rather than as `packages/<distribution>/src/<distribution with
    underscores>`, because that second form stopped being true on 2026-09-05: `weft-rag` ships
    fourteen top-level packages in one distribution (`packages/weft-rag/pyproject.toml`), and
    every check that had hard-coded the one-package-per-distribution shape either broke loudly
    or — worse — went on walking a directory that no longer existed and found nothing.

    The invariant that *did* survive is the one this reads: every first-party module lives at
    `packages/<something>/src/<module>`. `testing/` is deliberately excluded — `weft-canary` is
    test-only infrastructure and is not part of the shipped tree.
    """
    roots: dict[str, Path] = {}
    for src in sorted((REPO_ROOT / "packages").glob("*/src")):
        for module in sorted(path for path in src.iterdir() if (path / "__init__.py").is_file()):
            roots[module.name] = module
    return roots


def distribution_for_module(module: str) -> str:
    """Which published distribution ships the top-level import package `module`.

    Read off the `project.name` of the `pyproject.toml` beside its source tree, never derived
    from the module name — those two agreed for every package until fourteen of them moved into
    one wheel, and a check that assumes they still agree is asserting the thing it should be
    measuring.
    """
    roots = first_party_source_roots()
    if module not in roots:
        raise KeyError(
            f"'{module}' is not a first-party top-level package; found: {sorted(roots)}."
        )
    manifest = roots[module].parents[1] / "pyproject.toml"
    with manifest.open("rb") as handle:
        document = tomllib.load(handle)
    name = table_at(document, "project").get("name")
    if not isinstance(name, str):
        raise TypeError(f"{manifest} declares no project.name")
    return name
