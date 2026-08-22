"""Fitness function 14 — every declared `ExtModel` reaches the rehydration registry.

Task **5.2g**. Specified in `docs/01-high-level-plan.md` -> *Fitness functions*, item 14, and
`docs/02-extension-model.md` section 1's own "Built in Phase 5 task 5.2g" block: a pack's own
`ExtModel` — its namespaced extension data attached to `Node.ext` — must be reconstructable by
whatever store reads a node back, or `weft_store.rehydrate.rehydrate_ext` raises
`UnknownPluginError` the moment a node carrying that namespace is read. Measured at this task's
own start: eleven `ExtModel`s existed in the tree and `weft_store.rehydrate.ext_models` held
exactly one registered namespace, `weft-kernel` — `weft_chunk.payload.ChunkOffset` alone survived,
and only because `weft_cli.registry_bootstrap._ensure_chunk_offset_rehydrates` hand-registered it.

**Why a new number rather than a clause of item 5**, whose wording — "every declared capability
resolves... or the plugin must declare it unavailable and say why" — reads as though it already
covers this: item 5 already has a real, distinct, unclaimed subject of its own, the extractor
accept set named in `docs/11-multimodal.md` and assigned to that document's own task 1.13, and
folding a second property into one numbered item would make it answer two different questions
depending on which surface is under test — the identical ambiguity item 13's own note in `01`
refuses for item 4. See `01` item 14's own note for the argument in full.

**Two independently-computed sets, the identical shape `test_ff2_no_privileged_builtins.py`
already uses for "declared" versus "present" in the plugin registry, applied to the ext-model
registry instead.** *Declared*: every namespace any `ACTIVE` `PackReport.ext_models` names, read
straight off `discover()`'s own return value — nothing here calls `register_from_reports` yet.
*Present*: every namespace `weft_store.rehydrate.ext_models.names_for(ExtModel)` actually holds,
after `register_from_reports` has run against those same reports. A namespace `declared` names
that `present` does not is exactly this task's own defect: a pack whose `register()` calls
`add_ext_model` but whose report never reached `register_from_reports`, or a pack that never
called it at all.

**Against a fresh, throwaway ext-model registry, not the real process-wide singleton.**
`weft_store.rehydrate.ext_models` is a module-level object every other test in this tree may
already have written to (`test_store_conformance.py`'s own module-level `register_ext_model
(PdfPages)`, among others) — reusing it here would make `present` depend on pytest's collection
order rather than on what this test itself computed. `monkeypatch.setattr(rehydrate, "ext_models",
Registry())` is the identical substitution `tests/unit/weft_cli/test_registry_bootstrap.py::
test_build_dependencies_lets_a_genuine_ext_model_namespace_collision_raise` already relies on:
`register_ext_model`'s own body reads the module global at call time, so redirecting the module
attribute redirects every call made through it, including the ones `register_from_reports`
makes indirectly.

**Not every `ExtModel` a pack owns belongs behind `add_ext_model`, and this suite does not expect
it to be.** `weft_retrieve`'s `BooleanPlan`/`CorrectiveTrace`/`IterativeRetrievalTrace` and
`weft_generate`'s `Agreement`/`RefinementTrace` attach to `QuerySet.ext`/`Candidates.ext`/
`Answer.ext`, never to `Node.ext`, and only a `Node` is ever handed to a `NodeStore` — see
`weft_retrieve.__init__`'s and `weft_generate.__init__`'s own module docstrings, and
`docs/lessons.md` L5.20, for the measurement that found registering them would collide
(`weft-retrieve`'s three share one namespace; `weft-generate`'s two share another) rather than
merely being unnecessary. Neither pack's `register()` calls `add_ext_model` as a result, so
*declared* below is never derived from those five classes at all, on purpose: this file's own
two-source comparison would otherwise have to explain away a collision that is correct
behaviour, not a defect.
"""

import tomllib
from typing import Final, cast

import pytest

from weft_kernel.discovery import PackReport, discover
from weft_kernel.payload import ExtModel
from weft_kernel.registry import Registry
from weft_store import rehydrate
from weft_store.rehydrate import register_from_reports

from .conftest import REPO_ROOT

#: `packages/` — same location `test_ff2_no_privileged_builtins.py` derives its own from.
_PACKAGES_ROOT: Final = REPO_ROOT / "packages"

#: `weft-store` requires a `dsn` pack setting with no default, or `discover()` folds it into
#: `FAILED` before `register()` ever runs — identical constant to
#: `test_ff2_no_privileged_builtins.py`'s own, restated here rather than imported, because a
#: private module constant crossing a file boundary is exactly the coupling this repository's
#: own architecture tests otherwise avoid between each other.
_PLACEHOLDER_STORE_SETTINGS: Final[dict[str, dict[str, object]]] = {
    "weft-store": {"dsn": "postgresql://ff14-placeholder/placeholder"}
}


def _entry_points_table(document: dict[str, object]) -> dict[str, object] | None:
    """The `[project.entry-points."weft.packs"]` table of a parsed `pyproject.toml`, or `None`.

    Restated from `test_ff2_no_privileged_builtins.py`'s own identically-named helper for the
    same reason `_PLACEHOLDER_STORE_SETTINGS` above is: this file computes its own first-party
    distribution set rather than importing another test module's private function.
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


def _first_party_pack_distributions() -> frozenset[str]:
    """The `project.name` of every `packages/*/pyproject.toml` that declares a `weft.packs`
    entry point — `weft-extract`, `weft-chunk`, `weft-store`, and so on.

    Computed rather than hand-typed, so this set can never drift from what the packs
    actually declare — the identical reasoning `test_ff2_no_privileged_builtins.py`'s own
    helper of the same name gives.
    """
    distributions: set[str] = set()
    for package_dir in sorted(p for p in _PACKAGES_ROOT.iterdir() if p.is_dir()):
        pyproject = package_dir / "pyproject.toml"
        if not pyproject.is_file():
            continue
        with pyproject.open("rb") as handle:
            document = tomllib.load(handle)
        if _entry_points_table(document) is None:
            continue
        project = cast("dict[str, object]", document["project"])
        name = project.get("name")
        if isinstance(name, str):
            distributions.add(name)
    return frozenset(distributions)


def _declared_namespaces(reports: tuple[PackReport, ...]) -> frozenset[str]:
    """Every namespace any report's own `ext_models` names — the *declared* half."""
    return frozenset(model.__namespace__ for report in reports for model in report.ext_models)


def _discover_real_packs() -> tuple[PackReport, ...]:
    """A real, restricted discovery run — every first-party pack, `weft-canary` excluded.

    `allow=` pinned to exactly the real first-party set, the same reason
    `test_ff2_no_privileged_builtins.py` pins it: an open `discover()` would also import
    `weft-canary`, which `test_ff8_trust_model.py` needs to observe staying unimported in
    *this* pytest session.
    """
    registry = Registry()
    return discover(
        registry,
        allow=_first_party_pack_distributions(),
        pack_settings=_PLACEHOLDER_STORE_SETTINGS,
    )


def test_every_declared_ext_model_reaches_rehydration(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    reports = _discover_real_packs()
    declared = _declared_namespaces(reports)
    assert declared, (
        "fixture floor: no real, installed first-party pack declared an ExtModel — this "
        "comparison would pass vacuously without at least one. Run `uv sync`."
    )

    fresh = Registry()
    monkeypatch.setattr(rehydrate, "ext_models", fresh)

    # Act
    register_from_reports(reports)

    # Assert
    present = fresh.names_for(ExtModel)
    assert declared == present, (
        f"declared (from PackReport.ext_models) = {sorted(declared)}; present (actually in "
        f"weft_store.rehydrate.ext_models) = {sorted(present)}. Fitness function 14 requires "
        f"these to be exactly equal — every namespace a pack declared through "
        f"PackRegistrar.add_ext_model must be reconstructable, and nothing may appear in the "
        f"rehydration registry that no pack's own report named."
    )


def test_the_check_can_actually_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    """Withholding one contributing pack's own report from `register_from_reports` must make
    the comparison above disagree — the realistic shape of this task's own defect: a pack
    whose `register()` calls `add_ext_model`, but whose report never reaches the call that
    reads `PackReport.ext_models` back off it (a wiring call dropped, or run too early).
    """
    # Arrange — the real, legitimate baseline first, exactly like the test above.
    reports = _discover_real_packs()
    declared = _declared_namespaces(reports)
    contributing = tuple(report for report in reports if report.ext_models)
    assert len(contributing) >= 2, (
        "fixture floor: fewer than two real, installed packs declared an ExtModel — "
        "withholding one would leave nothing to prove a mismatch against. Run `uv sync`."
    )

    withheld = contributing[0]
    withheld_namespaces = frozenset(model.__namespace__ for model in withheld.ext_models)
    incomplete_reports = tuple(report for report in reports if report is not withheld)

    fresh = Registry()
    monkeypatch.setattr(rehydrate, "ext_models", fresh)

    # Act — register everything except the withheld pack's own contribution.
    register_from_reports(incomplete_reports)

    # Assert
    present = fresh.names_for(ExtModel)
    assert withheld_namespaces, "fixture floor: the withheld pack declared no namespace at all"
    assert withheld_namespaces <= (declared - present), (
        f"withholding {withheld.distribution!r}'s own report should leave "
        f"{sorted(withheld_namespaces)} declared but not present; present = {sorted(present)}"
    )
    assert declared != present, (
        "withholding one contributing pack's report must make declared and present disagree. "
        "If this assertion fails, the equality check above has stopped being able to fail, "
        "which means it is not proven to check anything."
    )
