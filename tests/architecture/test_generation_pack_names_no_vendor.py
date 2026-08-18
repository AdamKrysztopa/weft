"""Task 2.30's stated property: the generation pack names no vendor.

`docs/build-ledger.md` 2.30: "the generation pack names no vendor, because a provider
adapter is its own pack and the offline default is a deterministic scripted provider." No
fitness function is named for this task; the property is checked directly, against the two
places a dependency on a vendor could actually be introduced.

**Dependencies, not prose.** `weft_store`'s own docstrings freely name `weft-qdrant` by
distribution, and `weft_openai.embedder`'s own docstring names `weft-llm` by task — cross-
referencing a sibling pack in a comment explaining *why* a boundary is drawn where it is is
how this whole tree documents itself, and grepping prose for a distribution's name would
flag that convention as a violation of the very property it exists to explain. What task
2.30 actually forbids is a generation-pack **distribution depending on** the vendor adapter,
or a generation-pack **module importing** the vendor's SDK — either would make "swap the
provider by configuration alone" false regardless of what any docstring says.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
PACKAGES_ROOT: Final[Path] = REPO_ROOT / "packages"

#: The packs a generation pipeline is actually built from — the ones task 2.30's sentence is
#: a claim about. `weft-openai` is excluded on purpose: it is the vendor adapter itself, and
#: naming its own vendor is exactly its job.
_GENERATION_PACKS: Final[tuple[str, ...]] = ("weft-llm", "weft-retrieve", "weft-generate")

#: Import roots that would make a generation pack depend on one vendor rather than the
#: contract every vendor registers under.
_VENDOR_MODULES: Final[tuple[str, ...]] = ("openai", "weft_openai")


def _pyproject_dependencies(distribution: str) -> list[str]:
    path = PACKAGES_ROOT / distribution / "pyproject.toml"
    with path.open("rb") as handle:
        document = tomllib.load(handle)
    project = document.get("project", {})
    return list(project.get("dependencies", []))


def _python_files(distribution: str) -> list[Path]:
    src = PACKAGES_ROOT / distribution / "src"
    if not src.is_dir():
        return []
    return [path for path in src.rglob("*.py") if "__pycache__" not in path.parts]


def _imported_roots(path: Path) -> set[str]:
    """The top-level module every `import`/`from ... import` in `path` names."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_no_generation_pack_declares_a_dependency_on_the_vendor_adapter() -> None:
    # Act
    offenders = {
        distribution: deps
        for distribution in _GENERATION_PACKS
        if (deps := [d for d in _pyproject_dependencies(distribution) if "openai" in d])
    }

    # Assert
    assert not offenders, (
        f"a generation pack declares a dependency on the vendor adapter, which task 2.30 "
        f"forbids — a provider adapter must be swappable by configuration alone "
        f"(.phase2-findings.md finding 9): {offenders}"
    )


def test_no_generation_pack_module_imports_the_vendor() -> None:
    # Act
    hits = [
        (path.relative_to(REPO_ROOT), root)
        for distribution in _GENERATION_PACKS
        for path in _python_files(distribution)
        for root in sorted(_imported_roots(path) & set(_VENDOR_MODULES))
    ]

    # Assert
    assert not hits, (
        "a generation pack module imports the vendor SDK or its adapter pack directly, "
        "which task 2.30 forbids:\n  " + "\n  ".join(f"{path}: {name!r}" for path, name in hits)
    )


def test_at_least_one_generation_pack_directory_exists() -> None:
    # Floor — a scan over distributions that do not exist yet would pass this file's real
    # checks by being blind, the same shape every architecture check in this tree states.
    assert any((PACKAGES_ROOT / distribution).is_dir() for distribution in _GENERATION_PACKS)


def test_the_import_scan_can_actually_fail(tmp_path: Path) -> None:
    # Self-test: a file that really does import the vendor SDK must be caught.
    planted = tmp_path / "planted.py"
    planted.write_text("import openai\n", encoding="utf-8")

    assert "openai" in _imported_roots(planted)
