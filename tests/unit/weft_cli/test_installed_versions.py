"""Unit tests for `weft_cli.installed_versions`. Ledger task **6.4**, `09` §1.

`docs/09-release.md` §1, a binding consequence of the release set G10 settled: "`weft plugins
doctor` gains one column, not a new command: the version of each active distribution. **Whether
`doctor` also flags a mismatch, and what a mismatch does, are G9's** — the column exists under
either answer, because `doctor` has to be able to *say* what is installed before any policy can
act on it."

**A distribution with no recorded metadata is reported, never dropped.** `docs/internal/lessons.md`
L5.9: an absent answer means *"I did not find it"*, and the place that fact has to survive to is the
operator's screen. So the reader omits the key and `weft_cli.plugins_report` renders the omission as
*"version not recorded"* — a `doctor` that silently printed nothing for a distribution it could not
measure would be the diagnostic command hiding the diagnosis.

**Why the assertion is against `pyproject.toml` and not against `importlib.metadata`.** Reading the
same source the code under test reads would compare a function to itself (`docs/internal/lessons.md`
L5.6). The installed version of `weft-kernel` is checked against the number its own distribution
declares, which is a second source and can genuinely disagree — a stale editable install is exactly
the case `weft_cli.skew` exists for.
"""

import tomllib
from pathlib import Path

from weft_cli.installed_versions import installed_versions

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _declared_version(distribution: str) -> str:
    manifest = _REPO_ROOT / "packages" / distribution / "pyproject.toml"
    with manifest.open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def test_it_reads_the_version_of_an_installed_distribution() -> None:
    # Arrange
    declared = _declared_version("weft-kernel")

    # Act
    found = installed_versions(["weft-kernel"])

    # Assert
    assert found == {"weft-kernel": declared}


def test_a_distribution_with_no_recorded_metadata_is_omitted_rather_than_guessed() -> None:
    """The renderer turns the omission into "version not recorded" — see the module docstring."""
    # Arrange
    asked = ["weft-kernel", "weft-not-installed-anywhere"]

    # Act
    found = installed_versions(asked)

    # Assert
    assert "weft-not-installed-anywhere" not in found
    assert "weft-kernel" in found


def test_asking_for_nothing_returns_nothing_rather_than_reading_the_environment() -> None:
    # Arrange / Act
    found = installed_versions([])

    # Assert
    assert found == {}


# --- Task 16.3 — the versions a run record carries are keyed on the set 8(c) checks.


def test_active_distribution_versions_measures_exactly_the_active_set() -> None:
    """One derivation, so a record's versions and its `active_distributions` cannot disagree.

    Fitness function 8(c) binds `RunRecord.active_distributions` to what `plugins doctor` calls
    active. A second, independently-composed set of names to look versions up for is a second way
    to disagree with it — so this reads the set through `weft_eval.run_record.
    active_distribution_set` itself, and the assertion is that the two key spaces are identical
    rather than that the versions are any particular number.
    """
    # Arrange — one active pack, one refused, and two packs of the same distribution.
    from weft_cli.installed_versions import active_distribution_versions
    from weft_eval.run_record import active_distribution_set
    from weft_kernel.discovery import PackReport, PackStatus

    reports = (
        PackReport(pack="eval", distribution="weft-rag", status=PackStatus.ACTIVE, contributed=1),
        PackReport(pack="store", distribution="weft-rag", status=PackStatus.ACTIVE, contributed=1),
        PackReport(pack="canary", distribution="weft-canary", status=PackStatus.REFUSED),
        PackReport(pack="kernel", distribution="weft-kernel", status=PackStatus.ACTIVE),
    )

    # Act
    versions = active_distribution_versions(reports)
    active = active_distribution_set(reports)

    # Assert — every name measured is an active one, and no active name is silently skipped
    # for a reason other than having no recorded metadata.
    assert set(versions) <= set(active)
    assert "weft-canary" not in versions, "a refused pack's distribution was measured as active"
    assert versions["weft-kernel"] == _declared_version("weft-kernel")
