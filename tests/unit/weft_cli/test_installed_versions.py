"""Unit tests for `weft_cli.installed_versions`. Ledger task **6.4**, `09` §1.

`docs/09-release.md` §1, a binding consequence of the release set G10 settled: "`weft plugins
doctor` gains one column, not a new command: the version of each active distribution. **Whether
`doctor` also flags a mismatch, and what a mismatch does, are G9's** — the column exists under
either answer, because `doctor` has to be able to *say* what is installed before any policy can
act on it."

**A distribution with no recorded metadata is reported, never dropped.** `docs/lessons.md` L5.9:
an absent answer means *"I did not find it"*, and the place that fact has to survive to is the
operator's screen. So the reader omits the key and `weft_cli.plugins_report` renders the omission
as *"version not recorded"* — a `doctor` that silently printed nothing for a distribution it
could not measure would be the diagnostic command hiding the diagnosis.

**Why the assertion is against `pyproject.toml` and not against `importlib.metadata`.** Reading
the same source the code under test reads would compare a function to itself (`docs/lessons.md`
L5.6). The installed version of `weft-kernel` is checked against the number its own distribution
declares, which is a second source and can genuinely disagree — a stale editable install is
exactly the case `weft_cli.skew` exists for.
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
