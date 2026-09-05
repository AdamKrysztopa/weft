"""Unit tests for `weft_cli.skew`.

Mirrors `packages/weft-rag/src/weft_cli/skew.py`. Every test injects `requires`/`version`
doubles rather than reading the real environment — the same discipline
`weft_kernel.discovery`'s own test file uses for `entry_points`: this file proves the
module's own logic (parsing, marker evaluation, prefix filtering, specifier comparison)
against a hand-built double, and leaves proving it against a genuinely force-installed
distribution to the fitness function and the shipped binary, where a real disagreement
can actually exist.

Covers a real skew (installed version outside the declared range), the happy path
(installed version inside range — the ordinary `uv sync` case), a requirement on a
distribution that is not named `weft-...` (ignored — this module's own scope, not a
general `pip check`), a requirement string `packaging` cannot parse, and a required
distribution that is declared but not installed at all (the resolver's own refusal
territory, not skew).
"""

from importlib import metadata

from weft_cli.skew import detect_skew


def test_detect_skew_reports_an_installed_version_outside_the_declared_range() -> None:
    # Arrange
    def requires(name: str) -> list[str] | None:
        assert name == "weft-cli"
        return ["weft-kernel>=0.1.0,<1.0.0"]

    def version(name: str) -> str:
        assert name == "weft-kernel"
        return "9.9.9"

    # Act
    reports = detect_skew(["weft-cli"], requires=requires, version=version)

    # Assert — `specifier` is whatever `packaging.specifiers.SpecifierSet` renders, which
    # does not promise clause order; this module never re-orders or re-derives it.
    [report] = reports
    assert report.requiring_distribution == "weft-cli"
    assert report.required_distribution == "weft-kernel"
    assert report.installed_version == "9.9.9"
    assert set(report.specifier.split(",")) == {">=0.1.0", "<1.0.0"}


def test_detect_skew_reports_nothing_when_the_installed_version_satisfies_the_range() -> None:
    # Arrange — the ordinary, `uv sync`ed case: nothing is ever skewed.
    def requires(name: str) -> list[str] | None:
        return ["weft-kernel>=0.1.0,<1.0.0"]

    def version(name: str) -> str:
        return "0.1.0"

    # Act
    reports = detect_skew(["weft-cli"], requires=requires, version=version)

    # Assert
    assert reports == ()


def test_detect_skew_ignores_a_requirement_on_a_distribution_not_named_weft() -> None:
    # Arrange — this module's own scope is `weft-...` distributions, never a general
    # `pip check` over every dependency in the environment.
    def requires(name: str) -> list[str] | None:
        return ["numpy>=1.0,<2.0"]

    def version(name: str) -> str:
        raise AssertionError("must never be read — the requirement was filtered out first")

    # Act
    reports = detect_skew(["weft-cli"], requires=requires, version=version)

    # Assert
    assert reports == ()


def test_detect_skew_skips_a_requirement_string_it_cannot_parse() -> None:
    # Arrange
    def requires(name: str) -> list[str] | None:
        return ["not a valid PEP 508 requirement !!!"]

    def version(name: str) -> str:
        raise AssertionError("must never be read — an unparseable requirement names nothing")

    # Act
    reports = detect_skew(["weft-cli"], requires=requires, version=version)

    # Assert
    assert reports == ()


def test_detect_skew_skips_a_required_distribution_that_is_not_installed() -> None:
    # Arrange — the resolver's own refusal territory (`docs/09-release.md` §2.3's
    # unlabelled row), not skew: this function reports a version disagreement, not an
    # absence.
    def requires(name: str) -> list[str] | None:
        return ["weft-graph>=1.0.0,<2.0.0"]

    def version(name: str) -> str:
        raise metadata.PackageNotFoundError(name)

    # Act
    reports = detect_skew(["weft-cli"], requires=requires, version=version)

    # Assert
    assert reports == ()


def test_detect_skew_skips_a_requiring_distribution_that_is_not_installed() -> None:
    # Arrange — a caller may pass a distribution name discovery never actually found.
    def requires(name: str) -> list[str] | None:
        raise metadata.PackageNotFoundError(name)

    def version(name: str) -> str:
        raise AssertionError("must never be read — requiring never got past requires()")

    # Act
    reports = detect_skew(["weft-ghost"], requires=requires, version=version)

    # Assert
    assert reports == ()
