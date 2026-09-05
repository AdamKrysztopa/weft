"""Fitness function 2 — no privileged built-ins.

Specified in `docs/01-high-level-plan.md` -> *Fitness functions*, item 2, and
`docs/02-extension-model.md` section 2 ("Packs and discovery"): "Built-ins ship as
first-party packs through the same entry point... This is fitness function 2, and it
is the difference between a plugin API that works and one that is theoretically
supported." Two clauses, and they need two different kinds of check.

**Clause one — no built-in plugin is imported by the kernel.** Static.
`test_ff1_boundary.py`'s `test_kernel_imports_nothing_it_does_not_ship` already
proves a stronger version of this: the kernel imports nothing beyond `pydantic`,
`opentelemetry` and the standard library, so it necessarily imports none of
`weft_extract`, `weft_chunk`, `weft_embed` or `weft_store` either. This file still
asserts the literal, named property `01` states, rather than leaving a reader to
derive it from a broader check built for a different purpose — and it computes the
four module names from each pack's own `pyproject.toml` rather than retyping them,
the same reasoning `test_ff9_extension_from_outside.py` gives for reading the
example pack's identity off its own `pyproject.toml`: a hand-typed second copy is
the drift `docs/README.md` opens with.

**Clause two — no built-in is registered by a path a third party could not use.**
`01` states this half has to be a runtime check: "the registry's contents must
equal what the installed distributions declared." *Declared* is
`weft_kernel.discovery.PackReport` — one row per distribution, `contributed`
counting exactly what its own `register()` buffered through `PackRegistrar` before
`commit()` wrote it to the shared `Registry`. *Actual* is what task 0.12 gave
`Registry` an enumeration surface for: `contracts()` and `distributions_for()`,
contract-agnostic and read-only, walked here to build the flat set of
distributions the registry actually holds a registration for. The two sets are
compared for exact equality — nothing extra, nothing missing — which is the
runtime form of "the registry's contents equal what the installed distributions
declared." Deliberately no new kernel surface is added for this: the two methods
task 0.12 already shipped are enough to state the property.

A third party's own `register()` receives a `PackRegistrar`, and
`PackRegistrar.add` has no `distribution` parameter at all — attribution is filled
in by `discover()` itself, from whichever entry point it is currently importing
(`weft_kernel/discovery.py`'s own module docstring: "attribution is never a pack
author's to supply"). The only way to put an entry in the registry under a
distribution name of the caller's own choosing is to reach for the lower-level
`Registry.add` directly, bypassing `PackRegistrar` and `discover()` entirely —
which is precisely "a path a third party could not use."
`test_a_registration_outside_discovery_is_caught` plants exactly that and confirms
the equality check above is the thing that would have caught it, following the
same self-test discipline `test_ff9_extension_from_outside.py`'s
`test_the_grep_can_actually_fail` uses: a check that cannot be observed failing is
not proven to check anything.

**What this does not, and cannot, check through the surface it is given.**
`distributions_for` reports *which* distributions contributed to a contract, not
*how many* names each one registered — `Registry` exposes no per-name enumeration,
and task 0.12 added exactly these two contract-agnostic methods rather than a
third. So this check is blind to a bypass that reuses a distribution name already
legitimately `ACTIVE`: an extra registration smuggled in and attributed to
`weft-extract`, say, on top of the one entry `weft-extract`'s own `register()`
really added, would not change either flat distribution-name set and would pass
undetected — a re-wrap-after-decorate shape, one level removed. Two things limit
that gap in practice rather than close
it: `Registry.add` already refuses a duplicate `(contract, name)` outright (a
built-in's *existing* registrations cannot be silently replaced), and, read across
this repository's shipped code, `Registry.add`/`add_many` are called from exactly
one place — `weft_kernel.discovery._activate`, via `PackRegistrar.commit`, itself
reachable only from `discover()`. That is true by inspection of the current call
graph today, not by anything this test could fail on if it stopped being true — an
honest limit of the enumeration surface, not a gap this file's assertions paper
over. No waiver constant is defined here: as things stand there is no legitimate
exception to carve out, and adding one pre-emptively would be exactly the kind of
silent edit the ratchet in `test_ff0_gate_in_the_gate.py` exists to prevent.
"""

import ast
import tomllib
from collections import Counter
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Final, cast

from weft_kernel.discovery import PackReport, PackStatus, discover
from weft_kernel.registry import Registry

from .conftest import KERNEL_ROOT, REPO_ROOT

PACKAGES_ROOT: Final[Path] = REPO_ROOT / "packages"

#: Every first-party pack that registers no plugin against any contract *by design* —
#: `docs/02-extension-model.md` §4's own words for `weft-otel`, task 5.1d: "registers no
#: plugin against any contract, contributes to no pipeline." Named explicitly, the same
#: ratchet discipline `tests/architecture/test_ff9c_every_contract_has_a_stranger.py`'s own
#: waivers use, rather than derived from some structural property — there is no way to
#: compute "contributes nothing on purpose" from a pack's `pyproject.toml` alone, and
#: guessing at one would be exactly the kind of silent, undocumented carve-out CLAUDE.md's
#: ratchet discipline exists to make a visible diff instead.
PACKS_THAT_REGISTER_NOTHING_BY_DESIGN: Final[frozenset[str]] = frozenset({"weft-otel"})

#: `weft-store` requires a `dsn` pack setting with no default (`PgVectorSettings.dsn`), or its
#: `register()` never runs at all — `discover()` folds a settings-validation failure into
#: `FAILED`, contributed=0, before any factory is registered. The connection itself is lazy,
#: opened on first use (`pgvector_store.py`'s own docstring), so a placeholder is safe here for
#: the same reason `weft_cli.contract_reference` already relies on one to get `weft-store`
#: active without a real database.
_PLACEHOLDER_STORE_SETTINGS: Final[dict[str, dict[str, object]]] = {
    "store": {"dsn": "postgresql://ff2-placeholder/placeholder"}
}


class _PlantedContract:
    """A throwaway contract type, used only to plant a registration outside `discover()`."""


def _entry_points_table(document: dict[str, object]) -> dict[str, object] | None:
    """The `[project.entry-points."weft.packs"]` table of a parsed `pyproject.toml`, or `None`.

    `None` for `weft-kernel` and `weft-cli`, neither of which declares that group — this is
    how the two are excluded from the pack lists below without naming them.
    """
    project = document.get("project")
    if not isinstance(project, dict):
        return None
    entry_points = cast("dict[str, object]", project).get("entry-points")
    if not isinstance(entry_points, dict):
        return None
    packs = cast("dict[str, object]", entry_points).get("weft.packs")
    if not isinstance(packs, dict):
        return None
    return cast("dict[str, object]", packs)


def _first_party_packages() -> list[dict[str, object]]:
    """Every `packages/*/pyproject.toml` that declares a `weft.packs` entry point, parsed."""
    documents: list[dict[str, object]] = []
    for package_dir in sorted(p for p in PACKAGES_ROOT.iterdir() if p.is_dir()):
        pyproject = package_dir / "pyproject.toml"
        if not pyproject.is_file():
            continue
        with pyproject.open("rb") as handle:
            document = tomllib.load(handle)
        if _entry_points_table(document) is not None:
            documents.append(document)
    return documents


def _first_party_pack_modules() -> frozenset[str]:
    """The module each first-party pack's own `weft.packs` entry point resolves to.

    Computed from `packages/*/pyproject.toml` rather than hand-typed, so this set can
    never drift from what the packs actually declare.
    """
    modules: set[str] = set()
    for document in _first_party_packages():
        packs = _entry_points_table(document)
        assert packs is not None  # guaranteed by _first_party_packages' own filter
        for target in packs.values():
            if isinstance(target, str):
                modules.add(target.split(":", 1)[0])
    return frozenset(modules)


def _first_party_pack_distributions() -> frozenset[str]:
    """The `project.name` of every first-party pack — `weft-extract`, `weft-chunk`, etc."""
    distributions: set[str] = set()
    for document in _first_party_packages():
        project = cast("dict[str, object]", document["project"])
        name = project.get("name")
        if isinstance(name, str):
            distributions.add(name)
    return frozenset(distributions)


def _imported_top_level_modules(path: Path) -> set[str]:
    modules: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module.split(".")[0])
    return modules


def test_kernel_imports_no_first_party_pack_module() -> None:
    # Arrange
    pack_modules = _first_party_pack_modules()

    # Act
    violations: list[str] = []
    for path in sorted((KERNEL_ROOT / "src").rglob("*.py")):
        imported = _imported_top_level_modules(path) & pack_modules
        violations.extend(f"{path.relative_to(KERNEL_ROOT)} imports {name}" for name in imported)

    # Assert
    assert not violations, (
        "weft-kernel imports a built-in pack module directly:\n  "
        + "\n  ".join(violations)
        + "\nThe kernel names no capability and knows nothing about any particular pack (G1); "
        "a built-in earns its place in the registry through discover() calling its public "
        "register(), exactly like a third party's pack, never through the kernel importing "
        "it by name."
    )


def test_at_least_one_kernel_file_is_walked() -> None:
    # Floor — `08` §3's shape, applied to a source walk instead of a document walk: a
    # walk that finds nothing would let clause one above pass vacuously on an empty
    # tree, exactly the shape a comparison computed once and checked against itself takes.
    walked = sorted((KERNEL_ROOT / "src").rglob("*.py"))
    assert walked, (
        f"no `.py` file found under {KERNEL_ROOT / 'src'} — the walk itself is broken; "
        f"fix it before trusting clause one above."
    )


class _RecordingRegistry(Registry):
    """A `Registry` that remembers every write, so the check can compare *registrations*
    rather than the set of distribution names that made them.

    **Comparing name sets is not enough, and this is the whole point of the function.**
    `01` item 2 names the defect it exists to catch: a built-in path that re-wraps and
    re-assigns its own factories *after* the decorator already registered them, so a third
    party using the same public decorator silently does not get the span wrapping the
    built-ins get. A name-set comparison cannot see that —
    the distribution is in both sets before and after. Neither can it see a second
    registration attributed to a distribution that legitimately registered something else.

    Nothing is added to `weft-kernel` for this. `discover()` takes a `Registry` *instance*
    and `add`/`add_many`/`entry` are already public, so the recording lives here, in the
    test, where a check's own machinery belongs.
    """

    def __init__(self) -> None:
        super().__init__()
        self.written: list[tuple[type[object], str, Callable[..., object], str]] = []

    def add(
        self,
        contract: type[object],
        name: str,
        factory: Callable[..., object],
        *,
        distribution: str,
    ) -> None:
        super().add(contract, name, factory, distribution=distribution)
        self.written.append((contract, name, factory, distribution))

    def add_many(
        self,
        entries: Iterable[tuple[type[object], str, Callable[..., object]]],
        *,
        distribution: str,
    ) -> None:
        batch = list(entries)
        super().add_many(batch, distribution=distribution)
        for contract, name, factory in batch:
            self.written.append((contract, name, factory, distribution))


def _declared_and_present(
    registry: Registry, reports: tuple[PackReport, ...]
) -> tuple[frozenset[str], frozenset[str]]:
    """The same computation fitness function 2 and `weft plugins doctor` both need.

    *Declared*: every distribution `discover()` reported as having contributed at least
    one registration. *Present*: every distribution the registry actually holds a
    registration for, read through `contracts()`/`distributions_for()` alone.

    This is the coarse half — it catches a distribution appearing from nowhere. The two
    assertions in `test_registry_contents_equal_what_discovery_declared` are what make the
    clause non-vacuous; see `_RecordingRegistry`.
    """
    declared = frozenset(report.distribution for report in reports if report.contributed > 0)
    present = frozenset(
        distribution
        for contract in registry.contracts()
        for distribution in registry.distributions_for(contract)
    )
    return declared, present


def test_registry_contents_equal_what_discovery_declared() -> None:
    # Arrange / Act — the real, installed first-party packs: weft-extract, weft-chunk,
    # weft-embed and weft-store. `allow` is pinned to exactly this set, computed the same
    # way `_first_party_pack_modules` is, rather than left open — an open `discover()` would
    # also import `weft-canary`, which `test_ff8_trust_model.py` needs to observe staying
    # unimported in *this* pytest session, and importing it here first would make that
    # check pass for the wrong reason regardless of what discovery actually does.
    expected_builtins = _first_party_pack_distributions()
    registry = _RecordingRegistry()
    reports = discover(registry, allow=expected_builtins, pack_settings=_PLACEHOLDER_STORE_SETTINGS)

    # Assert
    declared, present = _declared_and_present(registry, reports)
    assert declared == present, (
        f"declared (from discovery's own reports) = {sorted(declared)}; present (actually in "
        f"the registry) = {sorted(present)}. Fitness function 2 requires these to be exactly "
        f"equal — nothing reached the registry that discovery did not report contributing, and "
        f"nothing discovery reported contributing is missing from the registry."
    )

    expected_contributing = expected_builtins - PACKS_THAT_REGISTER_NOTHING_BY_DESIGN
    assert expected_contributing <= declared, (
        f"expected every first-party pack {sorted(expected_contributing)} to be active and "
        f"contributing; discovery reported contributions only from {sorted(declared)}. Run "
        f"`uv sync` so every built-in pack in this workspace is actually installed — this "
        f"test proves nothing about built-ins specifically unless they are."
    )

    # `weft-otel` (task 5.1d) is the first first-party pack that registers no plugin against
    # any contract *by design* (`docs/02-extension-model.md` §4: "registers no plugin against
    # any contract, contributes to no pipeline") — it can never satisfy the "contributing"
    # floor above, because `declared` only ever counts `contributed > 0`. That does not
    # narrow what fitness function 2 actually polices: the equality and per-distribution
    # count assertions above and below are unchanged and still cover it (it reports
    # `contributed=0` and holds zero registrations, in exact agreement). What the assertion
    # above protects — "did this pack actually load in this environment, rather than the
    # check passing vacuously because `uv sync` was never run" — is a fact about `status`,
    # not about a contribution count, so that is what is asked of it here instead.
    statuses = {report.distribution: report.status for report in reports}
    for distribution in PACKS_THAT_REGISTER_NOTHING_BY_DESIGN & expected_builtins:
        assert statuses.get(distribution) is PackStatus.ACTIVE, (
            f"expected {distribution!r} to be ACTIVE (it registers nothing by design, not "
            f"because it failed to load); status was {statuses.get(distribution)!r}. Run "
            f"`uv sync` so it is actually installed."
        )

    # Every registration is accounted for, one for one. A distribution that registered twice
    # while reporting one contribution has taken a path a pack author cannot take.
    #
    # **Summed per distribution rather than read per report, and that is a real loss of
    # precision worth naming.** `Registry.add` attributes a registration to the distribution
    # the registrar was bound to, not to the pack — so with twelve packs in `weft-rag`, the
    # registry side of this comparison cannot tell them apart, and the report side is
    # aggregated to match. Before 2026-09-05 the two were the same thing and this caught an
    # extra registration attributed to *one specific pack*; today it catches an extra
    # registration attributed to the wheel. Carrying `pack` down through `Registry.add` is
    # what would restore the finer half. The dict comprehension this replaced was not merely
    # coarser — it silently kept whichever of the twelve reports came last, and compared 102
    # written registrations against 1.
    written_per_distribution = Counter(distribution for _, _, _, distribution in registry.written)
    reported_per_distribution: Counter[str] = Counter()
    for report in reports:
        if report.contributed > 0:
            reported_per_distribution[report.distribution] += report.contributed
    assert written_per_distribution == reported_per_distribution, (
        f"registrations actually written = {dict(sorted(written_per_distribution.items()))}; "
        f"contributions discovery reported = {dict(sorted(reported_per_distribution.items()))}. "
        f"Fitness function 2 requires these to agree per distribution, not merely to name the "
        f"same distributions — an extra registration attributed to a pack that legitimately "
        f"registered something else is exactly the privileged path this catches."
    )

    # And what a pack handed in is what the registry still holds. This is the clause that
    # catches `01` item 2's own example: a built-in re-wraps its own factories *after*
    # registration to give them span wrapping a third party would not get. The name is
    # unchanged, the distribution is unchanged, and only the identity of the factory moves.
    for contract, name, factory, distribution in registry.written:
        assert registry.entry(contract, name).factory is factory, (
            f"{distribution}:{name} factory was replaced after registration. The object the "
            f"pack handed to `register()` is not the object the registry holds, so a built-in "
            f"is running through machinery a third party's plugin would not — `01` -> "
            f"*Fitness functions* item 2, and the defect it exists to catch."
        )


def test_the_registry_check_can_actually_fail() -> None:
    """The equality check above can fail — proven by planting a violation it must catch.

    Named to fitness function 16 clause (b)'s convention at ledger task **6.15**; it was
    written as `test_a_registration_outside_discovery_is_caught` and the body is unchanged.

    A pack's own `register()` cannot choose its own `distribution`: `PackRegistrar.add` has
    no such parameter, and `discover()` fills attribution in from the entry point it is
    currently importing. The only way to put an entry in the registry under a
    self-chosen distribution name is the lower-level `Registry.add`, called directly — which
    is exactly the shape of "registered by a path a third party could not use."
    """
    # Arrange — a real, legitimate discovery run, exactly like the test above.
    registry = Registry()
    reports = discover(
        registry,
        allow=_first_party_pack_distributions(),
        pack_settings=_PLACEHOLDER_STORE_SETTINGS,
    )
    declared, present = _declared_and_present(registry, reports)
    assert declared == present, "the legitimate baseline must hold before planting a violation"

    # Act — plant a registration through the path no third party's register() can take.
    planted_distribution = "not-a-real-installed-distribution"
    registry.add(_PlantedContract, "sneaky", lambda: None, distribution=planted_distribution)

    # Assert — discovery's own reports are unchanged (planting happens after discover()
    # returns), but the registry now disagrees with them, naming exactly the planted
    # distribution as the extra.
    declared_after, present_after = _declared_and_present(registry, reports)
    assert declared_after == declared, (
        "planting must not retroactively change what discovery reported"
    )
    assert present_after - present == {planted_distribution}, (
        f"planting a registration outside discover() should add exactly one distribution to "
        f"'present' that 'declared' does not have; got {sorted(present_after - present)}"
    )
    assert declared_after != present_after, (
        "a registration that reached the registry through a path no third party can take must "
        "be visible as a mismatch between what discovery declared and what the registry "
        "actually holds. If this assertion fails, the equality check above has stopped being "
        "able to fail, which means it is not proven to check anything."
    )


def test_the_import_check_can_actually_fail(tmp_path: Path) -> None:
    """Fitness function 16 clause (b) for this file's *other* comparison — task **6.15**.

    `test_the_registry_check_can_actually_fail` proves the registry equality can fail and says
    nothing about `test_kernel_imports_no_first_party_pack_module`, which is a different
    comparison over a different input and had never been observed saying yes to anything. Both
    halves of it are planted here: a real pack module import, which must be caught, and the
    two shapes that must not be mistaken for one — the kernel importing itself, and a
    third-party module that merely starts with the same letters.
    """
    # Arrange — a real first-party pack module name, taken from the tree rather than typed,
    # so this cannot pass by planting a module nothing considers a pack.
    pack_modules = _first_party_pack_modules()
    assert "weft_store" in pack_modules, (
        "`weft_store` is not among the modules read off `packages/*/pyproject.toml` — the "
        "reader is wrong, and every assertion below would be about nothing"
    )
    planted = tmp_path / "planted.py"
    planted.write_text(
        "import weft_store\n"
        "from weft_kernel.payload import Node\n"
        "import weft_storeish_thirdparty\n",
        encoding="utf-8",
    )

    # Act — the same expression the check above computes.
    imported = _imported_top_level_modules(planted)
    violations = imported & pack_modules

    # Assert
    assert violations == {"weft_store"}
    assert "weft_kernel" in imported, "the walker must see the import; the set is what filters"
    assert "weft_storeish_thirdparty" in imported and "weft_storeish_thirdparty" not in violations
