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
undetected — the reference's `retrieval/registry.py:649-668` re-wrap-after-decorate
shape, one level removed. Two things limit that gap in practice rather than close
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
from pathlib import Path
from typing import Final, cast

from weft_kernel.discovery import PackReport, discover
from weft_kernel.registry import Registry

from .conftest import KERNEL_ROOT, REPO_ROOT

PACKAGES_ROOT: Final[Path] = REPO_ROOT / "packages"

#: `weft-store` requires a `dsn` pack setting with no default (`PgVectorSettings.dsn`), or its
#: `register()` never runs at all — `discover()` folds a settings-validation failure into
#: `FAILED`, contributed=0, before any factory is registered. The connection itself is lazy,
#: opened on first use (`pgvector_store.py`'s own docstring), so a placeholder is safe here for
#: the same reason `weft_cli.contract_reference` already relies on one to get `weft-store`
#: active without a real database.
_PLACEHOLDER_STORE_SETTINGS: Final[dict[str, dict[str, object]]] = {
    "weft-store": {"dsn": "postgresql://ff2-placeholder/placeholder"}
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


def _declared_and_present(
    registry: Registry, reports: tuple[PackReport, ...]
) -> tuple[frozenset[str], frozenset[str]]:
    """The same computation fitness function 2 and `weft plugins doctor` both need.

    *Declared*: every distribution `discover()` reported as having contributed at least
    one registration. *Present*: every distribution the registry actually holds a
    registration for, read through `contracts()`/`distributions_for()` alone.
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
    registry = Registry()
    reports = discover(registry, allow=expected_builtins, pack_settings=_PLACEHOLDER_STORE_SETTINGS)

    # Assert
    declared, present = _declared_and_present(registry, reports)
    assert declared == present, (
        f"declared (from discovery's own reports) = {sorted(declared)}; present (actually in "
        f"the registry) = {sorted(present)}. Fitness function 2 requires these to be exactly "
        f"equal — nothing reached the registry that discovery did not report contributing, and "
        f"nothing discovery reported contributing is missing from the registry."
    )

    assert expected_builtins <= declared, (
        f"expected every first-party pack {sorted(expected_builtins)} to be active and "
        f"contributing; discovery reported contributions only from {sorted(declared)}. Run "
        f"`uv sync` so every built-in pack in this workspace is actually installed — this "
        f"test proves nothing about built-ins specifically unless they are."
    )


def test_a_registration_outside_discovery_is_caught() -> None:
    """The equality check above can fail — proven by planting a violation it must catch.

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
