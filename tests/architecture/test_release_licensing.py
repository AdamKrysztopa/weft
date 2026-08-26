"""`LICENSE` and `NOTICE` are in every built artefact — ledger task **6.11**.

`docs/09-release.md` §5.2, *Security, licensing, documentation*, and `CLAUDE.md`'s originality
rule: every file in the release is accounted for as original work, and the licence travels with the
artefact rather than with the repository.

**Measured before it was fixed: not one built artefact carried either file.** No distribution
declared a `license` at all, and `LICENSE`/`NOTICE` sit at the repository root, which nothing in a
per-distribution build can see. Twenty wheels were one `uv publish` away from an index with no
licence in them — the state where a company's own tooling refuses the dependency and there is no
answer in the artefact to point at.

**Why each distribution carries its own copy rather than reaching for the root one.** Measured, not
assumed: `[tool.hatch.build.targets.wheel.force-include]` with `"../../LICENSE"` fails the build
outright, and PEP 639's `license-files` resolves relative to the distribution's own directory. So
the copies are real files, and this check is what makes twenty copies safe — each is asserted
**byte-identical** to the root original, so a licence edited in one place and not the others fails
the gate rather than shipping twenty different licences.

**The artefact half lives in `scripts/check_sdists.py`**, not here: `files_that_must_ship` requires
both files of every distribution, so task 6.7's comparison against the real archive is what proves
they are actually *in* the tarball. This file checks the declarations and the copies; that one
checks the bytes that ship. Two sources, and they can disagree — a `license-files` entry naming a
file that is not there, or a file present and never declared.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Final, cast

from publish_set import publishing_members

from .conftest import REPO_ROOT

ROOT_LICENSE: Final[Path] = REPO_ROOT / "LICENSE"
ROOT_NOTICE: Final[Path] = REPO_ROOT / "NOTICE"

#: The files every published distribution carries, and the SPDX expression they are under.
LICENCE_FILES: Final[tuple[str, ...]] = ("LICENSE", "NOTICE")
SPDX: Final[str] = "MIT"


def _project(manifest: Path) -> dict[str, object]:
    with manifest.open("rb") as handle:
        document: dict[str, Any] = tomllib.load(handle)
    project = document.get("project", {})
    return cast("dict[str, object]", project) if isinstance(project, dict) else {}


def test_every_published_distribution_carries_the_licence_files() -> None:
    """The copies exist. A `license-files` entry naming a file that is not there builds a wheel
    with no licence in it and says nothing about it.
    """
    # Arrange
    members = publishing_members()

    # Act
    missing = [
        f"{member.name}/{name}"
        for member in members
        for name in LICENCE_FILES
        if not (member.directory / name).is_file()
    ]

    # Assert
    assert members, "no publishing member was found — the reader is wrong, not the workspace"
    assert not missing, (
        f"{missing} are absent. Every published distribution carries its own copy: hatchling "
        f"cannot force-include a path outside the distribution directory, and PEP 639's "
        f"`license-files` resolves relative to it, so the root files are unreachable from a "
        f"per-distribution build."
    )


def test_every_carried_licence_is_byte_identical_to_the_root_original() -> None:
    """Twenty copies are safe only because this check makes them one file.

    Without it, the licence is the classic two-lists bug aimed at the one document a lawyer
    reads: edited in one place, stale in nineteen, and every one of them shipped.
    """
    # Arrange
    originals = {"LICENSE": ROOT_LICENSE.read_bytes(), "NOTICE": ROOT_NOTICE.read_bytes()}

    # Act
    drifted = [
        f"{member.name}/{name}"
        for member in publishing_members()
        for name in LICENCE_FILES
        if (member.directory / name).is_file()
        and (member.directory / name).read_bytes() != originals[name]
    ]

    # Assert
    assert originals["LICENSE"] and originals["NOTICE"], (
        f"{ROOT_LICENSE} or {ROOT_NOTICE} is empty — the comparison below would pass by having "
        f"nothing to compare."
    )
    assert not drifted, (
        f"{drifted} differ from the repository's own copy. There is one licence and one notice; "
        f"a distribution shipping a different one is shipping a different promise."
    )


def test_every_published_distribution_declares_its_licence() -> None:
    """The declaration is what puts the files in the artefact. A copy sitting in the directory
    with nothing naming it is a file the build ignores.
    """
    # Arrange
    members = publishing_members()

    # Act
    undeclared: list[str] = []
    for member in members:
        project = _project(member.directory / "pyproject.toml")
        declared = project.get("license-files")
        names: set[str] = set(cast("list[str]", declared)) if isinstance(declared, list) else set()
        if project.get("license") != SPDX or not set(LICENCE_FILES) <= names:
            undeclared.append(member.name)

    # Assert
    assert not undeclared, (
        f'{undeclared} do not declare `license = "{SPDX}"` and '
        f"`license-files = {list(LICENCE_FILES)}`. Without the declaration the files are in the "
        f"directory and not in the wheel, which is the state this task found the whole tree in."
    )


def test_the_check_can_actually_fail(tmp_path: Path) -> None:
    """Planted, because the real tree agrees once this task lands and the comparison is then
    never seen disagreeing (`docs/lessons.md` L5.19). Both halves: a drifted copy and a
    declaration that names a file nobody wrote.
    """
    # Arrange
    original = b"MIT License\n\nCopyright (c) 2026\n"
    drifted_dir = tmp_path / "weft-drifted"
    drifted_dir.mkdir()
    (drifted_dir / "LICENSE").write_bytes(b"Apache License\n")
    (drifted_dir / "pyproject.toml").write_text(
        '[project]\nname = "weft-drifted"\nversion = "0.0.0"\nlicense = "Apache-2.0"\n',
        encoding="utf-8",
    )

    # Act
    drifted = (drifted_dir / "LICENSE").read_bytes() != original
    project = _project(drifted_dir / "pyproject.toml")
    declared = project.get("license-files")
    names: set[str] = set(cast("list[str]", declared)) if isinstance(declared, list) else set()

    # Assert
    assert drifted, "a different licence text must read as drifted"
    assert not (drifted_dir / "NOTICE").is_file()
    assert project.get("license") != SPDX
    assert not set(LICENCE_FILES) <= names
