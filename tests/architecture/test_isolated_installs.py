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
    # `weft-cli` was a published name until 2026-09-05 and `weft_cli` now ships inside
    # `weft-rag`, so the two names that must be here are the two the six-name set cannot do
    # without: the kernel, which fitness function 1 installs alone, and the default install,
    # which carries the `weft` command.
    assert "weft-kernel" in names and "weft-rag" in names


def test_a_distribution_shipping_many_modules_names_all_of_them() -> None:
    """`docs/lessons.md` L5.27 — a sweep must answer the question for everything it sweeps.

    **This test used to assert the opposite fact.** `packages/weft-rag` was code-free by design
    (`09` §1: "the meta-distribution ships **no code**"), and what was checked here was that its
    `module` read as `None` — an *answer* rather than a name-based skip. Since 2026-09-05 it
    ships fourteen top-level packages, and the failure mode moved with it: the old derivation
    (`name.replace("-", "_")`) would have named `weft_rag`, a module that does not exist, and the
    isolated-install check would have imported nothing while reporting success. So what is
    asserted is the plural, against the tree.
    """
    # Arrange
    by_name = {member.name: member for member in publishing_members()}

    # Act
    default_install = by_name["weft-rag"]
    kernel = by_name["weft-kernel"]

    # Assert
    assert len(default_install.modules) > 1, (
        "weft-rag ships fourteen top-level packages; a reader that finds one (or none) is "
        "deriving the name from the distribution instead of reading the tree"
    )
    assert "weft_cli" in default_install.modules
    assert kernel.modules == ("weft_kernel",)


def test_every_module_named_is_a_directory_that_exists() -> None:
    """The enumeration is checked against the tree, not trusted as a string transformation."""
    # Arrange
    members = publishing_members()

    # Act
    missing = [
        f"{member.name}:{module}"
        for member in members
        for module in member.modules
        if not (member.directory / "src" / module).is_dir()
    ]

    # Assert
    assert any(member.modules for member in members), (
        "no member names any module — the read is broken, and the check below would pass by "
        "having nothing to check"
    )
    assert not missing, (
        f"{missing} name a module that is not on disk at `<distribution>/src/<module>`. A "
        f"distribution that does not follow that convention needs the reader to know, not the "
        f"reader to guess."
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
        f"it cannot be in the `ci-checks` composite, which is exactly the shape that lets a "
        f"boundary checker ship and never run (fitness function 0)."
    )
    assert "check_isolated_installs.py" in str(task)
    assert "check_isolated_installs.py" in workflow, (
        "no job in `.github/workflows/ci.yml` runs the isolated-install check. A task nothing "
        "invokes is prose with a task runner attached."
    )


def test_the_check_can_actually_fail(tmp_path: Path) -> None:
    """The module derivation, watched separating three planted distributions.

    The real tree agrees, so this is the only place the distinctions are seen doing work —
    without it, a reader that answered "no modules" for everything would sweep nothing and pass
    (`docs/lessons.md` L5.19). Three plants rather than two since 2026-09-05: the third is a
    distribution whose packages are **not** named after it, which is the shape the old
    `name.replace("-", "_")` derivation got silently wrong.
    """
    # Arrange
    (tmp_path / "pyproject.toml").write_text(
        '[tool.uv.workspace]\nmembers = ["packages/*"]\n', encoding="utf-8"
    )
    plants = {
        "weft-planted": ("weft_planted",),
        "weft-planted-codefree": (),
        "weft-planted-bundle": ("alpha_pack", "beta_pack"),
    }
    for name, modules in plants.items():
        member = tmp_path / "packages" / name
        member.mkdir(parents=True)
        (member / "pyproject.toml").write_text(
            f'[project]\nname = "{name}"\nversion = "0.0.0"\n', encoding="utf-8"
        )
        for module in modules:
            package = member / "src" / module
            package.mkdir(parents=True)
            (package / "__init__.py").write_text("", encoding="utf-8")

    # Act
    found = {member.name: member for member in publishing_members(tmp_path)}

    # Assert
    assert found["weft-planted"].modules == ("weft_planted",)
    assert found["weft-planted-codefree"].modules == ()
    assert found["weft-planted-bundle"].modules == ("alpha_pack", "beta_pack")
    assert isinstance(found["weft-planted"], Member)
