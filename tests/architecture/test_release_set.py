"""The default install is one wheel, and what it ships is a decision — `09` §1, re-settled.

`docs/09-release.md` §1 settled at G10 (2026-08-22) on "independent semver per distribution plus a
named release set" — a code-free `weft-rag` pinning one exactly-tested combination. **That is not
what ships any more.** `v0.1.0`'s first contact with a real index found the cost of twenty names,
and G10 was reopened: `weft-rag` now *contains* the fourteen packs rather than pinning them, and
five distributions publish alongside it.

**What that does to this file.** Every assertion here used to be about pins — that they were exact,
that they matched each distribution's own declared version, that nothing beside the set was in it. A
wheel that contains its members needs none of that: they cannot disagree about a version, because
there is only one version, and there is no pin left to drift. What the change does *not* remove is
the obligation those pins existed to discharge — that **what ships is a decision rather than an
accident** — and that obligation lands one file over. `weft-rag`'s hand-written
`[tool.hatch.build.targets.wheel] packages` list is now the thing that can silently disagree with
the source tree beside it: a module added under `packages/weft-rag/src/` and not listed there is not
shipped, no import in this repository notices, and every other test goes on passing while an
installed user gets `ModuleNotFoundError`. That is precisely the shape `docs/lessons.md` L5.6
requires a check for, and that comparison is the core of this file now.

**The two sources, and why they can genuinely disagree.** The first is `packages/weft-rag/src/*`,
walked from the filesystem. The second is the `packages = [...]` list a person typed into
`packages/weft-rag/pyproject.toml`, and the `[project.entry-points."weft.packs"]` table beside it.
Neither is derived from the other. A check that computed the list from the directory it compares it
to could not fail at all, which is the whole reason the list is not a glob.

**What is deliberately not here.** `09` §1's own worked example: a third-party pack "would not be in
the release set and would install beside it, exactly as `weft-store-qdrant` does". The first-party
distributions that are the same kind of thing install beside it too — `weft-qdrant` (an alternative
backend), `weft-openai` (a credentialed provider), `weft-pdf` (an optional file format), `weft-otel`
(an observability add-on), and `weft-kernel`, which stays separate because fitness function 1
installs it alone and imports it. None of the four add-ons is needed to index a directory and query
it, which is what the default install has to be able to promise. `testing/weft-canary` exists to be
*refused* by discovery (fitness function 8) and must never reach an index at all.
"""

from __future__ import annotations

import re
import tomllib
from importlib import metadata
from pathlib import Path
from typing import Any, Final, cast

import pytest

from weft_kernel.discovery import PackStatus, discover
from weft_kernel.registry import Registry

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_INSTALL = _REPO_ROOT / "packages" / "weft-rag" / "pyproject.toml"
_PACKAGES = _REPO_ROOT / "packages"

#: Structurally valid and never dialled. `weft-store`'s `register()` only partial-binds
#: `PgVectorStore(settings)` and `PgVectorStore.__init__` opens no connection — the connection is
#: lazy, opened on first use — so discovery can run here without a container. Spelled out rather
#: than imported from `weft_cli.contract_reference`'s private constant: this file's reason for
#: needing one is its own, and reaching into another distribution's private name would make a
#: rename there a failure here.
_PLACEHOLDER_DSN = "postgresql://release-set-check/placeholder"

#: Distributions that install *beside* the default install rather than inside it — see the module
#: docstring. `weft-rag` itself is here so the set can be subtracted from `packages/*` in one step.
_INSTALLS_BESIDE: Final[frozenset[str]] = frozenset(
    {"weft-kernel", "weft-qdrant", "weft-openai", "weft-pdf", "weft-otel", "weft-rag"}
)


def _toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _project(path: Path) -> dict[str, Any]:
    return cast("dict[str, Any]", _toml(path)["project"])


def _shipped_packages() -> dict[str, str]:
    """`{module: declared path}` — the hand-written list `weft-rag`'s wheel target names."""
    tool = cast("dict[str, Any]", _toml(_DEFAULT_INSTALL).get("tool", {}))
    wheel = cast(
        "dict[str, Any]",
        cast("dict[str, Any]", cast("dict[str, Any]", tool.get("hatch", {})).get("build", {}))
        .get("targets", {})
        .get("wheel", {}),
    )
    declared = cast("list[str]", wheel.get("packages", []))
    return {entry.rsplit("/", 1)[-1]: entry for entry in declared}


def _modules_under(root: Path) -> frozenset[str]:
    """Every top-level import package with an `__init__.py` under one distribution's `src/`."""
    src = root / "src"
    if not src.is_dir():
        return frozenset()
    return frozenset(path.name for path in src.iterdir() if (path / "__init__.py").is_file())


def _entry_points() -> dict[str, str]:
    """`{pack name: module}` from `weft-rag`'s own `weft.packs` table."""
    table = cast(
        "dict[str, str]", _project(_DEFAULT_INSTALL).get("entry-points", {}).get("weft.packs", {})
    )
    return {pack: target.split(":")[0].split(".")[0] for pack, target in table.items()}


def _requirement_name(requirement: str) -> str:
    return re.split(r"[><=~!\[;\s]", requirement)[0].strip()


def test_the_default_install_exists_and_is_named_weft_rag() -> None:
    # Assert
    assert _DEFAULT_INSTALL.is_file(), f"{_DEFAULT_INSTALL} is the default install (`09` §1)"
    assert _project(_DEFAULT_INSTALL)["name"] == "weft-rag"


def test_every_package_in_the_source_tree_is_declared_by_the_wheel_target() -> None:
    """The comparison this file exists for — a hand-written list against the tree beside it.

    A package added under `packages/weft-rag/src/` and not added to `packages = [...]` builds a
    wheel that silently omits it: nothing in this repository imports through the wheel, so every
    other test in the tree goes on passing while an installed user gets `ModuleNotFoundError`.
    """
    # Act
    on_disk = _modules_under(_DEFAULT_INSTALL.parent)
    declared = frozenset(_shipped_packages())

    # Assert — the floor first: a walk that found nothing would make the comparison vacuous.
    assert on_disk, "no package found under packages/weft-rag/src — the walk itself is broken"
    assert on_disk == declared, (
        f"packages/weft-rag/src holds {sorted(on_disk)}; its wheel target declares "
        f"{sorted(declared)}. Unlisted packages are silently absent from the built wheel, and "
        f"listed-but-absent ones fail the build. The list is not a glob on purpose — what ships "
        f"is a decision (`09` §1)."
    )


def test_every_declared_package_path_is_a_real_directory() -> None:
    # Act — `packages = ["src/weft_chunk"]` is a path relative to the manifest, so a typo in it
    # is otherwise only ever found at build time.
    root = _DEFAULT_INSTALL.parent
    declared = _shipped_packages()
    missing = sorted(path for path in declared.values() if not (root / path).is_dir())

    # Assert
    assert declared, "the wheel target declares no package — the read is wrong"
    assert missing == [], f"{missing} is declared by the wheel target and is not a directory"


def test_installing_the_default_install_brings_the_weft_command() -> None:
    """`09` §1's own consequence: the Phase 6 exit criterion installs the whole product with one
    `uvx` invocation, which is only true if the console script ships with it.

    It was `weft-cli`'s script and is now this distribution's, because `weft_cli` is inside it.
    """
    # Act
    scripts = cast("dict[str, str]", _project(_DEFAULT_INSTALL).get("scripts", {}))

    # Assert
    assert scripts.get("weft") == "weft_cli.cli:main"
    assert "weft_cli" in _shipped_packages(), "the console script points at a module it must ship"


def test_every_entry_point_names_a_module_this_distribution_ships() -> None:
    """An entry point pointing at a module the wheel does not carry is a pack that fails to
    import on an installed machine and loads fine in this workspace, where everything is on the
    path regardless — the same blind spot `test_distributions_declare_their_imports.py` names.
    """
    # Act
    shipped = frozenset(_shipped_packages())
    packs = _entry_points()
    dangling = sorted(
        f"{pack} -> {module}" for pack, module in packs.items() if module not in shipped
    )

    # Assert
    assert packs, "weft-rag declares no weft.packs entry point — the read is wrong"
    assert dangling == [], f"{dangling}: an entry point names a module this wheel does not ship"


def test_no_dependency_names_a_distribution_this_wheel_absorbed() -> None:
    """The fourteen pins are gone, and a leftover one would not resolve.

    `weft-chunk` and its thirteen siblings are no longer published from this repository — four of
    them exist on PyPI as vestigial `0.1.0` projects and would *resolve*, to code that predates
    everything here. A pin left behind is therefore worse than a broken install: it is a silent
    install of the wrong thing.
    """
    # Act
    absorbed = {module.replace("_", "-") for module in _shipped_packages()}
    declared = [
        _requirement_name(requirement)
        for requirement in cast("list[str]", _project(_DEFAULT_INSTALL)["dependencies"])
    ]
    leftovers = sorted(set(declared) & absorbed)

    # Assert
    assert declared, "weft-rag declares no dependency at all — the read is wrong"
    assert leftovers == [], f"{leftovers} is both depended on and shipped by weft-rag"


def test_the_kernel_is_depended_on_with_a_major_bound() -> None:
    """G9's enforcement rule, Phase 5: every distribution declares `>=X,<MAJOR+1` on a sibling.

    The kernel is the one first-party distribution `weft-rag` still depends on, and the bound is
    what makes a kernel major break a resolver's problem rather than an operator's.
    """
    # Act
    requirements = {
        _requirement_name(requirement): requirement
        for requirement in cast("list[str]", _project(_DEFAULT_INSTALL)["dependencies"])
    }
    kernel = requirements.get("weft-kernel", "")

    # Assert
    assert kernel, "weft-rag must depend on weft-kernel — every module it ships imports it"
    assert ">=" in kernel and "<" in kernel, (
        f"weft-kernel is declared as {kernel!r}, without both a floor and a major ceiling — "
        f"`09` §2.3's binding rule is what makes an incompatible kernel a resolution failure."
    )


def test_nothing_that_installs_beside_it_is_shipped_inside_it() -> None:
    """The add-ons exist to be declinable. One of their modules inside this wheel would install
    `openai` or `qdrant-client` for everybody, which is exactly what keeping them separate buys.
    """
    # Act
    shipped = frozenset(_shipped_packages())
    beside = {
        module
        for name in _INSTALLS_BESIDE - {"weft-rag"}
        for module in _modules_under(_PACKAGES / name)
    }
    overlap = sorted(shipped & beside)

    # Assert
    assert beside, "no module found for any install-beside distribution — the walk is wrong"
    assert overlap == [], f"{overlap} ships inside weft-rag and belongs to a distribution beside it"


def test_every_first_party_distribution_is_either_the_default_install_or_beside_it() -> None:
    """A distribution under `packages/` that is neither is one nobody decided about — the drift
    this file exists to refuse, unchanged in intent from when it was phrased about pins.
    """
    # Act
    first_party = {path.parent.name for path in _PACKAGES.glob("*/pyproject.toml")}
    undecided = first_party - _INSTALLS_BESIDE

    # Assert
    assert first_party, "no distribution found under packages/ — the glob is wrong"
    assert undecided == set(), (
        f"{sorted(undecided)} is under packages/ and is neither the default install nor listed "
        f"in _INSTALLS_BESIDE. Decide which it is, in a diff."
    )


@pytest.mark.parametrize("excluded", ["weft-canary", "weft-qdrant"])
def test_the_standing_exclusions_stay_excluded(excluded: str) -> None:
    """`weft-canary` exists to be *refused* by discovery (fitness function 8) and must never be
    shipped; `weft-qdrant` is `09` §1's own named example of a backend that installs beside.
    Named individually as well as by the set above, so deleting a name from `_INSTALLS_BESIDE`
    does not quietly delete the assertion with it.
    """
    # Act
    shipped = frozenset(_shipped_packages())
    modules = _modules_under(_PACKAGES / excluded) or _modules_under(
        _REPO_ROOT / "testing" / excluded
    )

    # Assert
    assert modules, f"no module found for {excluded} — this assertion would pass vacuously"
    assert not (shipped & modules), f"{sorted(shipped & modules)} must never ship inside weft-rag"


# ---------------------------------------------------------------------------
# Task 6.4 — every pack the default install names is `active`, at the version
# that distribution declares. `09` section 1; `09` section 2's table of what
# Phase 6 needs from G9.
# ---------------------------------------------------------------------------


#: The statuses that mean **the pack loaded**. `02` section 2's vocabulary answers "why is this not
#: contributing?" for every reason at once, and two of its five members are not that question:
#: `ACTIVE` is contributing everything it has, and `PARTIAL` is "registered, but a conditional
#: dependency it wanted was not available, so part of what it offers did not".
#:
#: **This read `is PackStatus.ACTIVE` until ledger task 6.29**, and the two were the same word
#: because nothing could produce `PARTIAL` — the mechanism was deferred in Phase 0 and no step took
#: it until then. With it, the `eval` pack reports `PARTIAL` on any install without the optional
#: `bertscore` extra, which is **every clean install**, by design. Requiring the literal `ACTIVE`
#: here would forbid a first-party pack from having an optional extra at all, contradicting
#: `weft-rag[bertscore]` and `weft-otel[otlp]`, both settled. Task 6.4's line was written when the
#: distinction did not exist; what it means is *loaded*.
_LOADED: Final[frozenset[PackStatus]] = frozenset({PackStatus.ACTIVE, PackStatus.PARTIAL})


def test_every_pack_the_default_install_declares_is_loaded_at_the_version_it_declares() -> None:
    """Task 6.4's property, from three sources that can genuinely disagree.

    Which packs exist comes from `weft-rag`'s own entry-point table; `loaded` comes from running
    real discovery against the installed environment; the installed version comes from
    `importlib.metadata`. Nothing here is derived from anything else here, which is what
    `docs/lessons.md` L5.6 requires of a check that is expected to pass.

    **Keyed on `PackReport.pack`, not on the distribution.** Twelve reports now carry the same
    distribution name, so a `{report.distribution: report}` index would keep whichever came last
    and answer about one pack twelve times — which is exactly the defect `require_active` had.

    **What this is not.** It is not a skew check — `weft_cli.skew` asks whether an installed
    version satisfies another distribution's declared *specifier*, at runtime. This asks whether
    every pack this wheel says it ships actually loads, in the environment that ran these tests.
    """
    # Arrange
    packs = _entry_points()
    declared_version = cast("str", _project(_DEFAULT_INSTALL)["version"])

    # Act
    registry = Registry()
    reports = discover(registry, pack_settings={"store": {"dsn": _PLACEHOLDER_DSN}})
    by_pack = {report.pack: report for report in reports}
    not_loaded = sorted(
        pack for pack in packs if pack not in by_pack or by_pack[pack].status not in _LOADED
    )
    installed_version = metadata.version("weft-rag")

    # Assert — the read is proved non-empty before anything is judged.
    assert packs, "weft-rag declares no pack — the entry-point read is wrong"
    assert not not_loaded, (
        f"{not_loaded} are declared by weft-rag and did not load. `09` section 1: the default "
        f"install is one tested combination, and a pack in it that does not load is not part of "
        f"a combination anybody tested."
    )
    assert installed_version == declared_version, (
        f"weft-rag declares {declared_version} and {installed_version} is installed — so the "
        f"environment that ran these tests is not the one this manifest describes. Run `uv sync`."
    )


def test_the_shipped_package_read_can_actually_fail() -> None:
    """`docs/lessons.md` L5.19 — the comparison this file leans on, watched separating.

    The real tree agrees, so the only place the source-tree-versus-declared-list distinction is
    seen doing work is here: a package that exists on disk and is absent from the declared list
    is what silently ships nothing, and the comparison must notice.
    """
    # Arrange — the real declared list, minus one real entry.
    declared = frozenset(_shipped_packages())
    on_disk = _modules_under(_DEFAULT_INSTALL.parent)
    dropped = declared - {"weft_store"}

    # Assert
    assert on_disk == declared, "precondition: the real tree agrees"
    assert on_disk != dropped, "dropping a real package must make the comparison disagree"
    assert "weft_store" in declared, "the entry this self-test drops must really be there"
