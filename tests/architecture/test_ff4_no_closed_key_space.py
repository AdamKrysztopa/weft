"""Fitness function 4 — no closed enumeration of registry keys, anywhere a name is decided.

Task **2.8**, `docs/build-ledger.md`: "the router picks a strategy it was never told
about — discovered from the registry, with no enum, no if-chain and no closed key space
anywhere a name is decided." `01` → *Fitness functions* item 4: "(a) No enum shadows a
registry. (b) No literal enumeration of registry keys may appear in a dispatch, a
validator or a routing decision, expressed as a runtime property... rather than as a
grep."

**Why this is a runtime check and not a grep**, per `01`'s own correction: a grep-level
"no enum shadows a registry" check catches `StrategyName` vs `STRATEGY_REGISTRY` and
misses the two walls that actually made the reference's strategy seam unusable — a closed
enum used as a dict's *key type* (structural, no shadowing to grep for) and a hard-coded
`if`/`elif` chain assigning literal enum members (no enum anywhere near a registry to
grep). Both are catchable only by asking, at runtime, whether the set of names a real
mechanism can produce equals the set the registry actually holds.

**(a)** is `test_no_strenum_value_set_shadows_a_registered_contracts_names` — every
`StrEnum` reachable from `packages/`, checked against every registered contract's own
names, plus `test_no_module_level_dict_is_keyed_by_a_shadowing_enum` for the reference's
sharper defect, a dict whose *key type* is the closed enum. Both share
`_shadowing_enum_classes`, proven able to fail by
`test_the_shadow_detector_can_actually_fail`.

**(b)** is `test_the_router_selects_and_executes_a_freshly_generated_pipeline_name` — the
categorical proof, grafted from the winning proposal `.phase2-design.md` §5 names: no
hardcoded set, stale literal, mapping table or enum can survive a name generated at test
time. This is proof, where a set-equality assertion is only correlated with proof — the
reference's own `AdaptiveRouter._select_strategy_from_scores` (a ten-branch `if`/`elif`
assigning literal enum members) would fail this test by construction, because no branch
in it could ever produce a UUID nobody wrote down.

**Ratchet.** `SELECTION_SURFACES_WAIVED_FROM_FF4`, pinned empty, in the style of every
other ratchet in this suite (`test_ff0_gate_in_the_gate.py`'s own pattern) — see
`test_waiver_list_is_empty`.
"""

from __future__ import annotations

import importlib
import tomllib
import uuid
from enum import Enum, StrEnum
from typing import Final, cast

from weft_cli.compile import contracts_for, to_specs
from weft_embed import Embedder
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.discovery import discover
from weft_kernel.payload import Outcome, Produced
from weft_kernel.pipeline import Pipeline, StageDeclaration
from weft_kernel.registry import Registry
from weft_kernel.resolution import resolve
from weft_kernel.runner import Runner
from weft_retrieve.contract import RouteCatalogue, RoutingPolicy
from weft_retrieve.engine import route_catalogue
from weft_retrieve.payload import Candidates, Query, QuerySet, RuleOutcome, Scorecard

from .conftest import REPO_ROOT

#: `weft-store` requires a `dsn` with no default — the identical placeholder every other
#: architecture check in this suite hands it, so `register()` runs without opening a
#: real connection. See `test_ff11_pipeline_integrity.py`'s own module-level constant.
_PLACEHOLDER_STORE_SETTINGS: Final[dict[str, dict[str, object]]] = {
    "weft-store": {"dsn": "postgresql://ff4-placeholder/placeholder"}
}

#: Every selection surface this function has been asked to waive, pinned empty. Adding a
#: name here is a deliberate, dated act — see `docs/README.md`'s decision log — never a
#: place to quiet a real closed key space.
SELECTION_SURFACES_WAIVED_FROM_FF4: Final[frozenset[str]] = frozenset()


def test_waiver_list_is_empty() -> None:
    assert not SELECTION_SURFACES_WAIVED_FROM_FF4, (
        "A selection surface has been waived out of fitness function 4. If a surface "
        "genuinely cannot be expressed as an open key space, that is a design finding, "
        "not a place to quiet the check — record it with a dated entry in "
        "docs/README.md's decision log first."
    )


# --- shared machinery ------------------------------------------------------------------


def _entry_points_table(document: dict[str, object]) -> dict[str, object] | None:
    """`[project.entry-points."weft.packs"]`, or `None` if `document` declares none — the
    identical helper `test_ff11_pipeline_integrity.py` defines, restated here rather than
    imported across test files (that file's own "one self-contained scenario" reasoning).
    """
    project = document.get("project")
    if not isinstance(project, dict):
        return None
    entry_points = cast("dict[str, object]", project).get("entry-points")
    if not isinstance(entry_points, dict):
        return None
    packs = cast("dict[str, object]", entry_points).get("weft.packs")
    return cast("dict[str, object]", packs) if isinstance(packs, dict) else None


def _first_party_distributions() -> frozenset[str]:
    """Every `packages/*/pyproject.toml` declaring a `weft.packs` entry point."""
    distributions: set[str] = set()
    for package_dir in sorted(p for p in (REPO_ROOT / "packages").iterdir() if p.is_dir()):
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


def _installed_registry() -> Registry:
    """The registry `ci-checks` actually has — every first-party pack, discovered for
    real. See `test_ff11_pipeline_integrity.py::_installed_registry`, the identical call.
    """
    registry = Registry()
    discover(
        registry,
        allow=_first_party_distributions(),
        pack_settings=_PLACEHOLDER_STORE_SETTINGS,
    )
    return registry


def _import_every_first_party_module() -> None:
    """Import every `.py` file under `packages/*/src/` — "reachable from `packages/`",
    `01`'s own wording for clause (a), taken literally rather than left to whatever a
    pack's own `__init__` happens to import. `_installed_registry` above only imports
    each pack's *entry-point* module — enough to populate the registry, not enough to
    guarantee every `StrEnum` in the tree has ever been imported into `sys.modules`.
    """
    for src_root in sorted((REPO_ROOT / "packages").glob("*/src")):
        for path in sorted(src_root.rglob("*.py")):
            relative = path.relative_to(src_root).with_suffix("")
            parts = relative.parts
            if parts[-1] == "__init__":
                parts = parts[:-1]
            if not parts:
                continue
            importlib.import_module(".".join(parts))


def _all_subclasses(base: type) -> set[type]:
    found: set[type] = set()
    frontier = list(base.__subclasses__())
    while frontier:
        cls = frontier.pop()
        if cls in found:
            continue
        found.add(cls)
        frontier.extend(cls.__subclasses__())
    return found


def _shadowing_enum_classes(
    candidates: set[type[Enum]], *, registry: Registry
) -> list[tuple[type[Enum], type[object]]]:
    """Every `(enum class, contract)` pair where the enum's own value set is a non-empty
    subset of that contract's registered plugin names — `01`'s own clause (a), read
    literally: "assert its member-value set is not a subset of that contract's registered
    names." Shared by both real checks below and by the self-test, so the same logic that
    is asserted against the real tree is what is proven able to fail.
    """
    offenders: list[tuple[type[Enum], type[object]]] = []
    for enum_cls in candidates:
        try:
            values = frozenset(str(member.value) for member in enum_cls)
        except TypeError:
            continue
        if not values:
            continue
        for contract in registry.contracts():
            names = registry.names_for(contract)
            if names and values <= names:
                offenders.append((enum_cls, contract))
    return offenders


def _module_level_enum_keyed_dicts() -> list[tuple[str, type[Enum]]]:
    """Every module-level `dict` under a first-party package whose keys are all members
    of one `Enum` class — the reference's sharper defect (`01`'s own correction): "the enum
    was the registry's key **type**," which no amount of walking free-standing `StrEnum`
    classes on their own would ever see, because the closed key space lives in the dict's
    *shape*, not in a second name next to it.
    """
    import sys

    found: list[tuple[str, type[Enum]]] = []
    for module_name, module in list(sys.modules.items()):
        if not module_name.startswith("weft_"):
            continue
        for attr_name, value in list(vars(module).items()):
            if type(value) is not dict or not value:
                continue
            keys = list(cast("dict[object, object]", value).keys())
            if not all(isinstance(key, Enum) for key in keys):
                continue
            enum_classes = {type(key) for key in cast("list[Enum]", keys)}
            if len(enum_classes) != 1:
                continue
            found.append((f"{module_name}.{attr_name}", next(iter(enum_classes))))
    return found


# --- (a) no enum shadows a registry ------------------------------------------------------


def test_no_strenum_value_set_shadows_a_registered_contracts_names() -> None:
    _import_every_first_party_module()
    registry = _installed_registry()
    strenums = cast(
        "set[type[Enum]]",
        {cls for cls in _all_subclasses(StrEnum) if cls.__module__.startswith("weft_")},
    )

    offenders = _shadowing_enum_classes(strenums, registry=registry)
    described = [
        (f"{cls.__module__}.{cls.__qualname__}", contract.__name__) for cls, contract in offenders
    ]

    assert not offenders, (
        "the following StrEnum classes carry the exact set of names a real contract's "
        "registry holds, which is the reference's `RetrievalStrategyType`-shaped defect: "
        f"{described}. A plugin registers into the registry, not into a closed enum a "
        f"fourth member cannot join — if this overlap is coincidental, rename one side; "
        f"if it is a real shadow, the enum must not exist."
    )


def test_no_module_level_dict_is_keyed_by_a_shadowing_enum() -> None:
    """The reference's actual failure, `01`'s own correction states directly: no enum shadowed
    a registry by name — the enum *was* the registry's key type
    (`RETRIEVAL_BUILDERS: dict[RetrievalStrategyType, Builder]`), structurally preventing
    a fourth member from ever being a key, with nothing to grep for. Checked here as a
    dict *shape*, never a text pattern.
    """
    _import_every_first_party_module()
    registry = _installed_registry()
    keyed = _module_level_enum_keyed_dicts()

    offenders = [
        (qualified, enum_cls)
        for qualified, enum_cls in keyed
        for pair in _shadowing_enum_classes({enum_cls}, registry=registry)
        if pair[0] is enum_cls
    ]

    assert not offenders, (
        f"the following module-level dicts are keyed by an Enum whose value set is a "
        f"registered contract's exact name set — a closed key space structurally "
        f"preventing a fifth plugin from ever being a key, with no shadowing name to "
        f"grep for: {offenders}. Key the dict by `str`, resolved against the registry, "
        f"never by the enum itself."
    )


def test_the_shadow_detector_can_actually_fail() -> None:
    """Prove `_shadowing_enum_classes` is not vacuously true — every ratchet in this
    suite carries this. A throwaway `Registry` with one contract registering exactly
    `{"alpha", "beta"}`, and a throwaway `StrEnum` naming precisely those two values,
    must be flagged; a `Registry` and enum that share nothing must not.
    """

    class _Contract:
        pass

    class _MatchingNames(StrEnum):
        ALPHA = "alpha"
        BETA = "beta"

    class _UnrelatedNames(StrEnum):
        GAMMA = "gamma"

    def _factory(config: object) -> object:
        del config
        return object()

    registry = Registry()
    registry.add(_Contract, "alpha", _factory, distribution="weft-test")
    registry.add(_Contract, "beta", _factory, distribution="weft-test")

    shadowing = _shadowing_enum_classes({_MatchingNames}, registry=registry)
    clean = _shadowing_enum_classes({_UnrelatedNames}, registry=registry)

    assert shadowing == [(_MatchingNames, _Contract)]
    assert clean == []


# --- (b) the categorical proof: a name generated at test time ---------------------------


async def test_the_router_selects_and_executes_a_freshly_generated_pipeline_name() -> None:
    """`.phase2-design.md` §5's own words: "a hardcoded set, a stale literal, a mapping
    table or an enum cannot survive a name generated at test time." Every piece below is
    real production code against the real installed registry — `nearest-description`
    (`weft_retrieve.routing.NearestDescription`), `RegistryStageLookup`/
    `PipelineRouteCatalogue` (`weft_retrieve.engine`), `weft_cli.compile`, and
    `weft_kernel.runner.Runner` — nothing here is a fake standing in for the mechanism
    under test, only for the two ordinary services (`Embedder`) a `RoutingPolicy` and a
    real `Retriever` both need to run at all.
    """
    registry = _installed_registry()
    uuid_name = str(uuid.uuid4())
    stranger = Pipeline(
        name=uuid_name,
        vars={"route.summary": "a pipeline this test invented, named at run time"},
        stages=(StageDeclaration(id="retrieve", use="no-retrieval"),),
    )
    catalogue = route_catalogue({uuid_name: stranger})

    services = ServiceRegistry()
    embedder_entry = registry.entry(Embedder, "hash")
    services.add(Embedder, embedder_entry.factory(None))
    services.add(RouteCatalogue, catalogue)
    ctx = Context(tenant_id="ff4", run_id="run", trace_id="trace", locale="en", services=services)

    # Select — no name written anywhere in `nearest-description`'s own source, no enum,
    # no if-chain: it embeds `catalogue.candidates()` and picks the argmax.
    policy_entry = registry.entry(RoutingPolicy, "nearest-description")
    policy = cast(RoutingPolicy, policy_entry.factory(None))
    scorecard = Scorecard(query=Query(text="what should I do?"), scores={}, observed=True)
    route_outcome = await policy.run(scorecard, ctx)

    assert isinstance(route_outcome, Produced)
    assert route_outcome.value.pipeline == uuid_name
    assert route_outcome.value.outcome is RuleOutcome.NEAREST

    # Execute — resolve the selected pipeline against the real registry and run it.
    contracts = contracts_for(stranger, registry=registry, parents={uuid_name: stranger})
    resolved = resolve(
        stranger, registry=registry, contracts=contracts, parents={uuid_name: stranger}
    )
    specs = to_specs(resolved, registry=registry)
    runner = Runner(registry)
    runnable = runner.resolve(specs, tenant_id="ff4")
    query = Query(text="what should I do?")
    outcome: Outcome[object] = await runner.run_once(
        runnable, QuerySet(origin=query, queries=(query,)), ctx
    )

    assert isinstance(outcome, Produced)
    assert isinstance(outcome.value, Candidates)
