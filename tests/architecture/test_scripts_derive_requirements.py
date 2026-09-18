"""No script carries a copy of a requirement the distributions' manifests declare.

`docs/internal/lessons.md` `L26.6`. `scripts/check_sdists.py` installed a hand list of
`weft-rag[all]`'s libraries; it drifted twice (`tiktoken` never added, `qdrant-client` lost its
bound) and CI's sdist suite died on an import the local gate never exercised. A list that mirrors a
manifest is read from the manifest. Sized at the Phase 32 drain: 2,860 string literals in 27 tracked
scripts, one failing (`ruff>=0.16.0`, the `reference` extra), repaired in the same change.

A literal is a copy when it equals a declared requirement, or names a declared distribution with a
version bound or extras. A bare name is not refused: `openai` is also a provider's name.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path
from typing import Final

from packaging.requirements import InvalidRequirement, Requirement

from .conftest import REPO_ROOT, tracked_files

MANIFESTS: Final[tuple[Path, ...]] = (
    REPO_ROOT / "packages/weft-kernel/pyproject.toml",
    REPO_ROOT / "packages/weft-rag/pyproject.toml",
)

#: `path:line "literal"` a script may keep. Pinned empty.
COPIED_REQUIREMENTS_WAIVED: Final[frozenset[str]] = frozenset()


def declared_requirements() -> tuple[frozenset[str], frozenset[str]]:
    requirements: set[str] = set()
    for manifest in MANIFESTS:
        project = tomllib.loads(manifest.read_text())["project"]
        requirements.update(project.get("dependencies", []))
        for extra in project.get("optional-dependencies", {}).values():
            requirements.update(extra)
    names = frozenset(Requirement(r).name.lower() for r in requirements)
    return frozenset(requirements), names


def copies_in(source: str, requirements: frozenset[str], names: frozenset[str]) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        literal = node.value
        if literal in requirements:
            found.append(f'{node.lineno} "{literal}"')
            continue
        try:
            parsed = Requirement(literal)
        except InvalidRequirement:
            continue
        if parsed.name.lower() in names and (parsed.specifier or parsed.extras):
            found.append(f'{node.lineno} "{literal}"')
    return found


def test_no_script_copies_a_declared_requirement() -> None:
    # Arrange
    requirements, names = declared_requirements()
    scripts = sorted(
        path for path in tracked_files() if path.startswith("scripts/") and path.endswith(".py")
    )

    # Act
    copies = {
        f"{path}:{site}"
        for path in scripts
        for site in copies_in((REPO_ROOT / path).read_text(), requirements, names)
    }

    # Assert
    assert scripts, "no tracked script under scripts/"
    assert copies - COPIED_REQUIREMENTS_WAIVED == set(), (
        f"a script repeats a requirement its manifest declares — read it from the manifest "
        f"(L26.6): {sorted(copies - COPIED_REQUIREMENTS_WAIVED)}"
    )


def test_the_check_can_actually_fail() -> None:
    requirements = frozenset({"tiktoken>=0.8", "qdrant-client>=1.12,<1.14"})
    names = frozenset({"tiktoken", "qdrant-client"})
    source = 'A = ["tiktoken>=0.8", "qdrant-client>=1.12", "qdrant-client", "openai>=1"]\n'

    found = copies_in(source, requirements, names)

    assert found == ['1 "tiktoken>=0.8"', '1 "qdrant-client>=1.12"']
