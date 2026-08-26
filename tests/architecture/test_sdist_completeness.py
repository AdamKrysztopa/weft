"""Nothing load-bearing is in the checkout and absent from the artefact — ledger task **6.7**.

`docs/09-release.md` §5.2, *Install path*: "The sdist builds and its tests pass from the sdist.
*Fails if a data file, locale catalogue or entry-point declaration is present in the checkout and
absent from the artefact.*"

**The failure condition is the specification, and it names data files first.** This is not
hypothetical here: `weft-retrieve` ships three pipeline documents inside
`src/weft_retrieve/pipelines/`, and `02` §3 makes a pipeline *data* rather than code — a build
backend that packaged `.py` files and nothing else would produce a distribution that installs,
imports, registers, and then cannot resolve a single one of the pipelines it declares. That is
the two-lists bug wearing a packaging costume, and it is invisible to every check in this
repository that reads the checkout.

**Why the comparison is a pure function and the building is not.** `files_that_must_ship` reads
the checkout, `sdist_contents` reads an archive, and the check is one set difference between
them. Keeping them apart is what lets this file check the part that actually holds the rule while
`scripts/check_sdists.py` does the subprocess work — the same division `scripts/publish_set.py`
and `scripts/check_isolated_installs.py` already have, for the same reason.

**"Its tests pass from the sdist" is the second half and it is the script's**, not this file's: it
needs a clean environment and the one container, so it runs as `poe sdists` and in its own CI job
beside `isolated-installs`, never inside `ci-checks`.
"""

from __future__ import annotations

import tarfile
import tomllib
from pathlib import Path
from typing import Any, Final

from check_sdists import files_that_must_ship, sdist_contents
from publish_set import Member, publishing_members

from .conftest import REPO_ROOT

SDIST_SCRIPT: Final[Path] = REPO_ROOT / "scripts" / "check_sdists.py"
POE_TASK: Final[str] = "sdists"


def _poe_tasks() -> dict[str, Any]:
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        document: dict[str, Any] = tomllib.load(handle)
    return dict(document["tool"]["poe"]["tasks"])


def _member(name: str) -> Member:
    for member in publishing_members():
        if member.name == name:
            return member
    raise AssertionError(f"{name} is not a publishing member — the reader is wrong")


def test_a_packs_data_files_are_required_to_ship() -> None:
    """`09` §5.2's own first-named failure: a data file present in the checkout, absent from the
    artefact. `weft-retrieve`'s pipeline documents are this repository's real instance.
    """
    # Arrange
    retrieve = _member("weft-retrieve")

    # Act
    required = files_that_must_ship(retrieve)

    # Assert
    assert "pyproject.toml" in required, (
        "the entry-point declarations live in `pyproject.toml`, and `09` §5.2 names them "
        "alongside data files as a thing that must not be missing from the artefact"
    )
    assert "src/weft_retrieve/pipelines/retrieve-then-generate.yaml" in required
    assert "src/weft_retrieve/py.typed" in required, (
        "`py.typed` is a marker file, not code — a build that shipped only `.py` files would "
        "silently untype the distribution for every consumer"
    )


def test_build_droppings_are_not_required_to_ship() -> None:
    """The other side of the rule: a required set that swept in `__pycache__` would make the
    comparison fail on any developer machine that had ever run the tests, which is how a real
    check becomes a check somebody turns off.
    """
    # Arrange
    members = publishing_members()

    # Act
    required = {path for member in members for path in files_that_must_ship(member)}

    # Assert
    assert required, "nothing was required of any distribution — the reader is wrong"
    assert not [path for path in required if "__pycache__" in path or path.endswith(".pyc")]


def test_a_distribution_that_ships_no_code_still_owes_its_manifest_and_its_licence() -> None:
    """`packages/weft` is code-free by design (`09` §1), and that is an answer rather than a skip
    (`docs/lessons.md` L5.27). It has no `src/`, so what it owes is its manifest — and, since
    ledger task **6.11**, its licence, which every published distribution carries whether or not
    it carries code. A release set that shipped no licence would be the one artefact a newcomer
    installs and the one with nothing for their legal team to read.
    """
    # Arrange
    release_set = _member("weft-rag")

    # Act
    required = files_that_must_ship(release_set)

    # Assert
    assert required == frozenset({"pyproject.toml", "LICENSE", "NOTICE"})


def test_sdist_contents_strips_the_archive_root(tmp_path: Path) -> None:
    """A `.tar.gz` names everything under `<distribution>-<version>/`; the comparison is against
    paths relative to the distribution directory, so the prefix has to come off exactly once.
    """
    # Arrange
    payload = tmp_path / "pyproject.toml"
    payload.write_text("[project]\n", encoding="utf-8")
    archive = tmp_path / "weft_planted-1.2.3.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(payload, arcname="weft_planted-1.2.3/pyproject.toml")
        tar.add(payload, arcname="weft_planted-1.2.3/src/weft_planted/data.yaml")

    # Act
    shipped = sdist_contents(archive)

    # Assert
    assert shipped == frozenset({"pyproject.toml", "src/weft_planted/data.yaml"})


def test_the_check_can_actually_fail(tmp_path: Path) -> None:
    """Fitness function 16 clause (b) — the artefact that is missing exactly one data file.

    Every real sdist in this tree is complete and always has been, so this is the only place the
    difference is seen being non-empty. Planted through both real readers rather than against
    literal sets, so what is proved is that a missing data file survives the round trip from
    checkout to archive to comparison (`docs/lessons.md` L5.19).
    """
    # Arrange — an archive holding the code and the manifest, and not the pipeline beside them.
    payload = tmp_path / "content"
    payload.write_text("x\n", encoding="utf-8")
    archive = tmp_path / "weft_planted-1.0.0.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(payload, arcname="weft_planted-1.0.0/pyproject.toml")
        tar.add(payload, arcname="weft_planted-1.0.0/src/weft_planted/__init__.py")
    required = frozenset(
        {
            "pyproject.toml",
            "src/weft_planted/__init__.py",
            "src/weft_planted/pipelines/base.yaml",
        }
    )

    # Act
    shipped = sdist_contents(archive)
    missing = required - shipped

    # Assert
    assert missing == frozenset({"src/weft_planted/pipelines/base.yaml"})
    assert not (shipped - required), "the planted archive holds nothing the checkout does not"


def test_the_check_is_reachable_from_a_task_and_from_ci() -> None:
    """Fitness function 0's property for a check that cannot live inside `ci-checks`."""
    # Arrange
    tasks = _poe_tasks()
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    # Act
    task = tasks.get(POE_TASK)

    # Assert
    assert SDIST_SCRIPT.is_file(), f"{SDIST_SCRIPT} does not exist"
    assert task is not None, f"`pyproject.toml` declares no `{POE_TASK}` task"
    assert "check_sdists.py" in str(task)
    assert "check_sdists.py" in workflow, (
        "no job in `.github/workflows/ci.yml` runs the sdist check. A task nothing invokes is "
        "prose with a task runner attached."
    )
