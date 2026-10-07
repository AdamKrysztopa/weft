"""The README's release sentence is the tree's versions — carried repair **R20.7**.

An outside review read `weft-rag 2.7.0` / `weft-kernel 0.2.1` in the README at `3.1.0` / `0.3.0`.
The sentence is rendered from both `pyproject.toml`s by `scripts/generate_readme_release.py`, and
these checks fail a version bump that did not regenerate it, or a README naming a version of either
distribution anywhere but there.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]


def _generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "generate_readme_release", REPO_ROOT / "scripts" / "generate_readme_release.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_release_sentence_names_both_pyproject_versions() -> None:
    # Arrange
    generator = _generator()
    checked_in = generator.README.read_text(encoding="utf-8")

    # Act
    expected = generator.spliced(checked_in, generator.render(generator.workspace_versions()))

    # Assert
    assert checked_in == expected, (
        "README.md's release sentence is not the tree's versions. Regenerate it with "
        "`uv run python scripts/generate_readme_release.py` and commit the result."
    )


def test_no_readme_names_a_version_outside_the_generated_sentence() -> None:
    # Arrange
    generator = _generator()
    readmes = {path: path.read_text(encoding="utf-8") for path in generator.READMES}

    # Act
    stray = {
        str(path.relative_to(REPO_ROOT)): generator.versions_named_outside(text)
        for path, text in readmes.items()
    }

    # Assert
    assert all(not found for found in stray.values()), stray


def test_the_check_can_actually_fail() -> None:
    # Arrange
    generator = _generator()
    checked_in = generator.README.read_text(encoding="utf-8")
    bumped = {**generator.workspace_versions(), "weft-rag": "99.0.0"}
    planted = checked_in + "\nCurrent at `weft-rag 3.0.9` / `weft-kernel 0.1.0`.\n"

    # Act
    regenerated = generator.spliced(checked_in, generator.render(bumped))
    found = generator.versions_named_outside(planted)

    # Assert
    assert regenerated != checked_in
    assert len(found) == 2
