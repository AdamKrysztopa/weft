"""Every published distribution installs alone and imports — ledger task **6.6**.

`docs/09-release.md` §5.2, *Install path*, first item: "Fitness function 1 holds for **every**
published distribution, not only the kernel — each installs alone into a clean environment and
imports. *Fails if any distribution needs the workspace, a path dependency, or an environment
variable to import.*"

**Why a script and not a pytest.** The check needs an environment this repository's own virtualenv
cannot provide: a distribution installed on its own, with nothing of the workspace reachable. That
is what `scripts/check_kernel_isolated.py` has done for `weft-kernel` since Phase 0 and why it runs
as `poe kernel-isolated` in its own CI job rather than inside `ci-checks`. Task 6.6 generalises it,
and this file checks the parts a pytest *can* see: that the enumeration the script sweeps is right,
that a distribution shipping no code is answered rather than skipped by name, and that the script
is reachable from a task and from CI — because a check nobody runs is prose (`docs/lessons.md`
L6.12, and fitness function 0's whole reason for existing).

**One reader for "which distributions, and what does each ship".** `scripts/publish_set.py` owns
it, and `tests/architecture/test_ff10_ship_set_integrity.py` reads the workspace side of fitness
function 10(a) from the same function rather than keeping a second copy. The two sides of 10(a)
stay independent — the other one is parsed out of `.github/workflows/release.yml`, which this
reader never opens.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Final

import pytest
from publish_set import Member, PublishSetUnreadableError, publishing_members

from .conftest import REPO_ROOT

ISOLATION_SCRIPT: Final[Path] = REPO_ROOT / "scripts" / "check_isolated_installs.py"

#: The poe task that runs it, and the CI job that runs the task. Named here so a rename in either
#: place fails loudly instead of leaving a check that exists and never runs.
POE_TASK: Final[str] = "isolated-installs"


def _poe_tasks() -> dict[str, Any]:
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        document: dict[str, Any] = tomllib.load(handle)
    return dict(document["tool"]["poe"]["tasks"])


def test_the_enumeration_covers_the_workspace_and_excludes_what_opts_out() -> None:
    """The set the script sweeps is the published set — fitness function 10(a)'s workspace side."""
    # Arrange
    members = publishing_members()

    # Act
    names = {member.name for member in members}

    # Assert
    assert members, "no publishing member was found — the reader is wrong, not the workspace"
    assert "weft-canary" not in names, (
        "`testing/weft-canary` declares `[tool.weft] publish = false` and exists to be refused by "
        "discovery. It is never published, so it is never asked to install alone."
    )
    assert "weft-kernel" in names and "weft-cli" in names


def test_a_distribution_that_ships_no_code_is_answered_rather_than_skipped_by_name() -> None:
    """`docs/lessons.md` L5.27 — a sweep must answer the question for everything it sweeps.

    `packages/weft` is code-free by design (`09` §1: "the meta-distribution ships **no code**"), so
    it has no module to import. That is an *answer*, and it is reached from the structural fact
    that the distribution has no `src/` — never from its name. A distribution that has a `src/`
    whose module will not import is a real breakage and must still fail.
    """
    # Arrange
    by_name = {member.name: member for member in publishing_members()}

    # Act
    release_set = by_name["weft-rag"]
    kernel = by_name["weft-kernel"]

    # Assert
    assert release_set.module is None
    assert kernel.module == "weft_kernel"


def test_every_module_named_is_a_directory_that_exists() -> None:
    """The enumeration is checked against the tree, not trusted as a string transformation."""
    # Arrange
    members = publishing_members()

    # Act
    missing = [
        member.name
        for member in members
        if member.module is not None and not (member.directory / "src" / member.module).is_dir()
    ]

    # Assert
    assert not missing, (
        f"{missing} name a module that is not on disk at `<distribution>/src/<module>`. The "
        f"module name is derived from the distribution name, and a distribution that does not "
        f"follow that convention needs the reader to know, not the reader to guess."
    )


def test_a_workspace_that_reads_as_empty_is_refused(tmp_path: Path) -> None:
    """`docs/lessons.md` L5.9 — an empty sweep means "I did not find it", never "there is none"."""
    # Arrange
    (tmp_path / "pyproject.toml").write_text(
        '[tool.uv.workspace]\nmembers = ["packages/*"]\n', encoding="utf-8"
    )

    # Act / Assert
    with pytest.raises(PublishSetUnreadableError):
        publishing_members(tmp_path)


def test_the_check_is_reachable_from_a_task_and_from_ci() -> None:
    """Fitness function 0's property, for a check that cannot live inside `ci-checks`."""
    # Arrange
    tasks = _poe_tasks()
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    # Act
    task = tasks.get(POE_TASK)

    # Assert
    assert ISOLATION_SCRIPT.is_file(), f"{ISOLATION_SCRIPT} does not exist"
    assert task is not None, (
        f"`pyproject.toml` declares no `{POE_TASK}` task. The check needs a clean environment so "
        f"it cannot be in the `ci-checks` composite, which is exactly the shape that let the "
        f"reference ship a boundary checker nobody ran (fitness function 0)."
    )
    assert "check_isolated_installs.py" in str(task)
    assert "check_isolated_installs.py" in workflow, (
        "no job in `.github/workflows/ci.yml` runs the isolated-install check. A task nothing "
        "invokes is prose with a task runner attached."
    )


def test_the_check_can_actually_fail(tmp_path: Path) -> None:
    """The module derivation, watched separating two planted distributions.

    The real tree agrees, so this is the only place the "has a `src/`" distinction is seen doing
    work — without it, a reader that answered `module=None` for everything would sweep nothing and
    pass (`docs/lessons.md` L5.19).
    """
    # Arrange
    (tmp_path / "pyproject.toml").write_text(
        '[tool.uv.workspace]\nmembers = ["packages/*"]\n', encoding="utf-8"
    )
    for name, has_src in (("weft-planted", True), ("weft-planted-codefree", False)):
        member = tmp_path / "packages" / name
        member.mkdir(parents=True)
        (member / "pyproject.toml").write_text(
            f'[project]\nname = "{name}"\nversion = "0.0.0"\n', encoding="utf-8"
        )
        if has_src:
            (member / "src" / name.replace("-", "_")).mkdir(parents=True)

    # Act
    found = {member.name: member for member in publishing_members(tmp_path)}

    # Assert
    assert found["weft-planted"].module == "weft_planted"
    assert found["weft-planted-codefree"].module is None
    assert isinstance(found["weft-planted"], Member)
