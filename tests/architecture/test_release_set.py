"""The release unit is a named set, not a wheel — ledger task **6.1**, `09` §1 (settled by G10).

`docs/09-release.md` §1: the unit of release is **independent semver per distribution plus a named
release set** — "a code-free distribution `weft` pinning one exactly-tested combination". This file
is that obligation made checkable, and it is deliberately not one of fitness function 10's two
clauses: 10(a) compares the *publish job's* arguments against the workspace, which is a different
question from whether the release set says what was tested together.

**Why an exact pin and not a range.** §1's own argument: bounds say what is *compatible*, and only a
pinned set says what was *tested together*. Every distribution in this tree already declares
`>=X,<MAJOR+1` on each sibling — G9's enforcement rule landed in Phase 5 — so a release set
declaring ranges would restate what is already there and answer nobody's question.

**Why the pins are read against each distribution's own `pyproject.toml`.** Two sources that can
genuinely disagree, which is what `docs/lessons.md` L5.6 requires of any check: the set is
hand-written and the versions are not, so a pack bumped without the set following it fails here.
A check that derived the pins from the same files it compares them to could not fail at all.
"""

from __future__ import annotations

import tomllib
from importlib import metadata
from pathlib import Path
from typing import Any, Final, cast

import pytest

from weft_kernel.discovery import PackStatus, discover
from weft_kernel.registry import Registry

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RELEASE_SET = _REPO_ROOT / "packages" / "weft-rag" / "pyproject.toml"
_PACKAGES = _REPO_ROOT / "packages"

#: Structurally valid and never dialled. `weft-store`'s `register()` only partial-binds
#: `PgVectorStore(settings)` and `PgVectorStore.__init__` opens no connection — the connection is
#: lazy, opened on first use — so discovery can run here without a container. Spelled out rather
#: than imported from `weft_cli.contract_reference`'s private constant: this file's reason for
#: needing one is its own, and reaching into another distribution's private name would make a
#: rename there a failure here.
_PLACEHOLDER_DSN = "postgresql://release-set-check/placeholder"

#: Distributions that install *beside* the release set rather than in it — `09` §1's own worked
#: example says a third-party pack "would not be in the release set and would install beside it,
#: exactly as `weft-store-qdrant` does", and these are the first-party members that are the same
#: kind of thing: an alternative backend, a credentialed provider, an optional file format, and an
#: observability add-on. None of them is needed to index a directory and query it, which is what
#: the release set has to be able to promise.
_INSTALLS_BESIDE = frozenset(
    {"weft-qdrant", "weft-openai", "weft-pdf", "weft-otel", "weft-canary", "weft-rag"}
)


def _toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _project(path: Path) -> dict[str, Any]:
    return cast("dict[str, Any]", _toml(path)["project"])


def _pins() -> dict[str, str]:
    """`{distribution: pinned version}` read off the release set's own dependency list."""
    pins: dict[str, str] = {}
    for requirement in cast("list[str]", _project(_RELEASE_SET)["dependencies"]):
        name, _, version = requirement.partition("==")
        pins[name.strip()] = version.strip()
    return pins


def test_the_release_set_exists_and_is_named_weft_rag() -> None:
    # Assert
    assert _RELEASE_SET.is_file(), f"{_RELEASE_SET} is the release set G10 settled on (`09` §1)"
    assert _project(_RELEASE_SET)["name"] == "weft-rag"


def test_the_release_set_ships_no_code() -> None:
    """`09` §1: "The meta-distribution ships **no code**. If it ships code it is a pack, and it
    will accumulate the convenience shims that a kernel budget exists to prevent."
    """
    # Act
    package_dir = _RELEASE_SET.parent
    python_files = sorted(path.name for path in package_dir.rglob("*.py"))

    # Assert
    assert python_files == []
    assert not (package_dir / "src").exists()


def test_the_release_set_declares_no_module_and_no_entry_point() -> None:
    """`09` §1: "`weft` declares no module and no entry point of its own; the `weft` command a
    user runs comes from `weft-cli`, which the release set depends on."
    """
    # Act
    project = _project(_RELEASE_SET)
    tool = cast("dict[str, Any]", _toml(_RELEASE_SET).get("tool", {}))

    # Assert
    assert "scripts" not in project
    assert "entry-points" not in project
    assert "gui-scripts" not in project
    # `hatchling` refuses to build a distribution it cannot find files for, so shipping nothing
    # has to be said out loud rather than left implicit — `bypass-selection` is that statement,
    # and asserting on it keeps "ships no code" a declared fact rather than an accident of
    # there being no `src/` directory yet.
    wheel = cast(
        "dict[str, Any]",
        cast("dict[str, Any]", cast("dict[str, Any]", tool.get("hatch", {})).get("build", {}))
        .get("targets", {})
        .get("wheel", {}),
    )
    assert wheel.get("bypass-selection") is True


def test_installing_the_release_set_brings_the_weft_command() -> None:
    """The bullet above is only true because `weft-cli` is in the set — that is what lets the
    Phase 6 exit criterion install the whole product with one `uvx` invocation.
    """
    # Assert
    assert "weft-cli" in _pins()


def test_every_dependency_is_pinned_exactly() -> None:
    """A range says what is compatible; only a pin says what was tested together — `09` §1."""
    # Act
    loose = [
        requirement
        for requirement in cast("list[str]", _project(_RELEASE_SET)["dependencies"])
        if "==" not in requirement
    ]

    # Assert
    assert loose == []


def test_every_pin_matches_the_version_that_distribution_declares() -> None:
    """The two sides come from different files, so they can genuinely disagree — a pack bumped
    without the release set following it is exactly what this catches (`docs/lessons.md` L5.6).
    """
    # Act
    disagreed = {
        name: (pinned, _project(_PACKAGES / name / "pyproject.toml")["version"])
        for name, pinned in _pins().items()
        if _project(_PACKAGES / name / "pyproject.toml")["version"] != pinned
    }

    # Assert
    assert disagreed == {}, (
        f"the release set pins a version its distribution does not declare: {disagreed}. "
        f"Bump the pin in packages/weft/pyproject.toml in the same commit as the release."
    )


def test_the_release_set_names_every_first_party_pack_that_is_not_installed_beside_it() -> None:
    """The set is *exactly* tested, so a first-party pack that is neither in it nor deliberately
    beside it is a pack nobody decided about — the drift this file exists to refuse.
    """
    # Act
    first_party = {
        path.parent.name for path in _PACKAGES.glob("*/pyproject.toml")
    } - _INSTALLS_BESIDE
    undecided = first_party - set(_pins())

    # Assert
    assert undecided == set(), (
        f"{sorted(undecided)} is under packages/ and neither pinned by the release set nor "
        f"listed in _INSTALLS_BESIDE. Decide which it is, in a diff."
    )


def test_nothing_that_installs_beside_the_set_is_pinned_by_it() -> None:
    # Act
    wrongly_pinned = _INSTALLS_BESIDE & set(_pins())

    # Assert
    assert wrongly_pinned == set()


@pytest.mark.parametrize("excluded", ["weft-canary", "weft-qdrant"])
def test_the_standing_exclusions_stay_excluded(excluded: str) -> None:
    """`weft-canary` exists to be *refused* by discovery (fitness function 8) and must never be
    shipped; `weft-qdrant` is `09` §1's own named example of a backend that installs beside.
    Named individually as well as by the set above, so deleting a name from `_INSTALLS_BESIDE`
    does not quietly delete the assertion with it.
    """
    # Assert
    assert excluded not in _pins()


# ---------------------------------------------------------------------------
# Task 6.4 — every pack the release set names is `active`, at the version the
# release names. `09` section 1; `09` section 2's table of what Phase 6 needs
# from G9.
# ---------------------------------------------------------------------------


#: The statuses that mean **the pack loaded**. `02` section 2's vocabulary answers "why is this not
#: contributing?" for every reason at once, and two of its five members are not that question:
#: `ACTIVE` is contributing everything it has, and `PARTIAL` is "registered, but a conditional
#: dependency it wanted was not available, so part of what it offers did not".
#:
#: **This read `is PackStatus.ACTIVE` until ledger task 6.29**, and the two were the same word
#: because nothing could produce `PARTIAL` — the mechanism was deferred in Phase 0 and no step took
#: it until then. With it, `weft-eval` reports `PARTIAL` on any install without the optional
#: `bertscore` extra, which is **every clean install of the release set**, by design. Requiring the
#: literal `ACTIVE` here would forbid a first-party pack from having an optional extra at all,
#: contradicting `weft-eval[bertscore]` and `weft-otel[otlp]`, both settled. Task 6.4's line was
#: written when the distinction did not exist; what it means is *loaded*.
_LOADED: Final[frozenset[PackStatus]] = frozenset({PackStatus.ACTIVE, PackStatus.PARTIAL})


def _declares_a_pack(distribution: str) -> bool:
    """Whether a pinned distribution is a *pack* — declares the one `weft.packs` entry point.

    `02` section 2: a pack is a distribution declaring that entry point, and nothing else is.
    Two of the release set's pins are not packs and must not be asked to be active:
    `weft-kernel`, which registers nothing by construction (G1), and `weft` itself, which
    ships no code at all.
    """
    manifest = _PACKAGES / distribution / "pyproject.toml"
    if not manifest.is_file():
        raise AssertionError(
            f"{distribution} is pinned by the release set and is not in {_PACKAGES}"
        )
    return "weft.packs" in _toml(manifest).get("project", {}).get("entry-points", {})


def test_every_pack_the_release_set_names_is_active_at_the_version_it_names() -> None:
    """Task 6.4's property, from four sources that can genuinely disagree.

    The pins come from the release set's own `pyproject.toml`; which of them is a pack comes
    from each distribution's own entry-point declaration; `active` comes from running discovery;
    and the installed version comes from `importlib.metadata`. Nothing here is derived from
    anything else here, which is what `docs/lessons.md` L5.6 requires of a check that is
    expected to pass.

    **What this is not.** It is not a skew check — `weft_cli.skew` asks whether an installed
    version satisfies another distribution's declared *specifier*, at runtime, for whatever
    happens to be installed. This asks whether the combination the release set says was tested
    together is the combination that is actually here, and whether every pack in it loads.
    """
    # Arrange
    pins = _pins()
    packs = {name: pin for name, pin in pins.items() if _declares_a_pack(name)}

    # Act
    registry = Registry()
    reports = discover(registry, pack_settings={"weft-store": {"dsn": _PLACEHOLDER_DSN}})
    status = {report.distribution: report for report in reports}
    inactive = sorted(
        name for name in packs if name not in status or status[name].status not in _LOADED
    )
    mismatched = sorted(
        f"{name}: release set says {pin}, {metadata.version(name)} is installed"
        for name, pin in packs.items()
        if metadata.version(name) != pin
    )

    # Assert — the filter is proved to discriminate before anything is judged, so a
    # `_declares_a_pack` that answered `False` for everything cannot pass this vacuously.
    assert packs, "no pinned distribution was read as a pack — the entry-point read is wrong"
    assert "weft-kernel" in pins and "weft-kernel" not in packs, (
        "`weft-kernel` is pinned by the release set and declares no `weft.packs` entry point, "
        "so a pack filter that keeps it is not reading entry points at all"
    )
    assert not inactive, (
        f"{inactive} are pinned by the release set and did not load. `09` section 1: the set "
        f"names one exactly-tested combination, and a pack in it that does not load is not part "
        f"of a combination anybody tested."
    )
    assert not mismatched, (
        f"{mismatched}. The release set names the version, and the environment that ran these "
        f"tests is not the one it names — so 'tested together' is a claim about something else."
    )


def test_the_pack_filter_can_actually_fail() -> None:
    """`docs/lessons.md` L5.19 — the discrimination this check leans on, watched separating.

    The real tree agrees, so the only place the pack/not-a-pack distinction is seen doing
    work is here: two real distributions, one of each kind, read through the real function.
    """
    # Arrange / Act
    kernel = _declares_a_pack("weft-kernel")
    store = _declares_a_pack("weft-store")

    # Assert
    assert kernel is False
    assert store is True
