"""The real `StageLookup` and `RouteCatalogue`.

`weft_retrieve.contract`'s own two service Protocols, built for the first time. Task **2.8**.

Every technique that reaches a sibling by name (`weft_retrieve.iterative`'s `leaf` and
`sufficiency`, `weft_retrieve.corrective`'s `grader` and `knowledge_action`,
`weft_retrieve.routing`'s own `query-scorer`) and every `RoutingPolicy` that needs to know
what it could select between has, until this task, only ever been driven against a
hand-built test double — `weft_retrieve.routing`'s own `_StubLookup` and
`_StubCatalogue` are the pattern every one of those test modules repeats.
`.phase2-design.md` §7: "each pack builds its own service constructor … so a library
caller is not forced through the CLI" — this is that constructor, for both services
`weft-retrieve` itself publishes.

**`RegistryStageLookup` never caches.** `weft_retrieve.contract.StageLookup`'s own
docstring states the narrowing directly: "sub-plugins get `Lifetime.RUN` semantics
regardless of what they declare." `weft_kernel.runner.Runner`'s own `_process_cache` is
what gives a top-level `Lifetime.PROCESS` stage reuse across resolves; nothing here
reads that cache or writes to it, so every `build`/`build_capability` call constructs a
fresh instance. That is a real, stated cost — a `PROCESS`-lifetime sub-plugin gets no
benefit from declaring it — and it is the simpler, honest answer next to the
alternative: a second cache here would be a second place `Lifetime.PROCESS` means
something, is `Runner`'s own reuse contract restated worse (keyed by run rather than by
process, and by whichever `StageLookup` instance happens to be alive), and is unneeded
work until a real sub-plugin is expensive enough to ask for it.

**`RouteCatalogue` is a pure read over `Pipeline.vars`, not over a resolved pipeline.**
A pipeline advertises itself by writing `route.summary` (and optionally `route.cost`)
directly into its own top-level `vars:` block — `weft_kernel.pipeline.Pipeline.vars`,
already validated, already printed. This module does not call `weft_kernel.resolution.
resolve` to walk an `extends` chain first: every routable pipeline this build ships
states its own `route.summary` at its own top level (`.phase2-design.md` §4's two worked
pipelines both do, `hyde-fanout-rrf.yaml` included, which overrides rather than
inherits it), so resolving first would buy nothing here and would cost a `contracts:`
mapping this module has no registry-inference reason to build. A pipeline that means to
be routable only by *inheriting* its parent's `route.summary`, naming none of its own,
is not offered — a narrowing worth stating rather than discovering by surprise.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping
from types import UnionType
from typing import Annotated, Union, cast, get_args, get_origin

from pydantic import BaseModel, ValidationError
from pydantic.fields import FieldInfo

from weft_kernel.context import Context
from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_kernel.payload import Outcome
from weft_kernel.pipeline import Pipeline
from weft_kernel.registry import Registry, RegistryEntry, unwrap_factory
from weft_kernel.resolution import ResolvedPipeline
from weft_kernel.runner import PipelineResolutionError, Stage
from weft_kernel.seam import wrap
from weft_llm.contract import LLMRole
from weft_retrieve.contract import SubPlugin
from weft_retrieve.payload import RouteCandidate

#: The two `vars:` keys a routable pipeline writes — `weft_retrieve.contract.
#: RouteCatalogue`'s own docstring, and `.phase2-design.md` §5's worked examples.
_ROUTE_SUMMARY_VAR = "route.summary"
_ROUTE_COST_VAR = "route.cost"
#: Ledger task **43.9** — a query pipeline that only answers honestly once a named layer is
#: built over the whole corpus writes the layer's own document name here. A candidate naming
#: one is offered only when the caller's `ready_layers` says that layer is built everywhere.
_ROUTE_REQUIRES_VAR = "route.requires"
#: Carried repair **R43.13** — every `route.` var a routable document may write, sorted:
#: `UnknownRouteVarError`'s own `valid_options`, derived rather than restated so the three
#: constants above stay the one place this set is spelled.
_ROUTE_VARS: tuple[str, ...] = tuple(
    sorted((_ROUTE_SUMMARY_VAR, _ROUTE_COST_VAR, _ROUTE_REQUIRES_VAR))
)
_NOTHING_MAPPED: frozenset[str] = frozenset()


class UnknownRouteVarError(PipelineResolutionError, UnresolvedNameError):
    """A routing-catalogue document writes a `route.` var the router does not read.

    A document in the routing catalogue writes a `route.` var the router does not read —
    carried repair **R43.13**, found by the exit review: `route.require` (a typo for
    `route.requires`) was silently ignored, so the rung it named was offered over a layer that
    was not yet built everywhere; `route.sumary` (a typo for `route.summary`) dropped the
    document out of the candidates entirely, with nothing said.

    Checked over every document in the catalogue — not only ones already carrying
    `route.summary` — because a document whose only route var is misspelt has no
    `route.summary` key at all, and filtering by its presence first would let the typo pass
    unseen.
    """

    def __init__(
        self,
        message: str,
        *,
        valid_options: tuple[str, ...],
        pipeline: str | None = None,
        remedy: str = "",
    ) -> None:
        PipelineResolutionError.__init__(self, message, pipeline=pipeline, remedy=remedy)
        self.valid_options = valid_options


class UnknownSubPluginConfigFieldError(PipelineResolutionError, UnresolvedNameError):
    """A config model declares `SubPlugin(config=...)` naming no field of that model.

    Carried repair **R43.45**. `valid_options` is the declaring model's own fields, sorted.
    """

    def __init__(
        self,
        message: str,
        *,
        valid_options: tuple[str, ...],
        pipeline: str | None = None,
        remedy: str = "",
    ) -> None:
        PipelineResolutionError.__init__(self, message, pipeline=pipeline, remedy=remedy)
        self.valid_options = valid_options


def _check_route_vars(name: str, pipeline: Pipeline) -> None:
    """Catch a misspelt `route.` key at load, naming the keys the router actually reads.

    Refuse `pipeline` when its own `vars` carry a `route.` key outside `_ROUTE_VARS` —
    carried repair **R43.13**. Keys outside the `route.` namespace are untouched.
    """
    for key in pipeline.vars:
        if key.startswith("route.") and key not in _ROUTE_VARS:
            raise UnknownRouteVarError(
                f"'{name}' sets '{key}', which the router does not read. A routable document "
                f"reads: {', '.join(_ROUTE_VARS)}.",
                valid_options=_ROUTE_VARS,
                pipeline=name,
            )


class RegistryStageLookup:
    """Satisfies `weft_retrieve.contract.StageLookup` structurally.

    Built over a plain `weft_kernel.registry.Registry` — never over a `Runner`, which
    this module has no need of: a `Runner`'s extra machinery (`requires`/`provides`,
    `intact`/`destroys`, composition checking) is what a *pipeline position* needs
    checked against its neighbours, and a sub-plugin reached by name from inside a
    technique has none — `weft_retrieve.contract.StageLookup`'s own docstring calls this
    "the one late-binding seam a looping technique gets," reached with no neighbours to
    check composition against at all.
    """

    def __init__(self, registry: Registry) -> None:
        self._registry = registry

    def names(self, contract: type[object]) -> frozenset[str]:
        """Every name registered for `contract`.

        Read straight off the registry, so a newly installed pack's plugin is visible the moment
        discovery ran, with nothing cached here to go stale.
        """
        return self._registry.names_for(contract)

    async def build[In, Out](
        self, contract: type[Stage[In, Out]], name: str, config: object = None
    ) -> Callable[[In, Context], Awaitable[Outcome[Out]]]:
        """Resolve and construct `name`, returning its seam-wrapped `run`.

        Resolve `name` under `contract`, construct it, and hand back a callable
        already wrapped through `weft_kernel.seam.wrap` — see the module docstring for
        why nothing here caches the instance.

        Raises `weft_kernel.registry.UnknownPluginError` — the registry's own, naming
        `contract`, `name` and every registered option — for an unresolvable name;
        nothing here invents a second message for the same fact.
        """
        entry = self._registry.entry(contract, name)
        instance = cast("Stage[In, Out]", entry.factory(_validated_sub_config(entry, name, config)))
        return wrap(
            instance.run,
            distribution=entry.distribution,
            contract=contract.__name__,
            plugin=name,
            stage=f"sub:{name}",
        )

    async def build_capability[T](self, contract: type[T], name: str, config: object = None) -> T:
        """Resolve and construct `name`, returning the raw instance.

        Resolve `name` under `contract` and construct it — the raw instance, never
        wrapped: a capability like `weft_prompts.contract.Prompt` has no `run` a `Stage`
        signature could wrap, and its own caller (`weft_prompts.cascade.execute`, for a
        `Prompt`) already runs inside the calling technique's own seam-wrapped span.
        """
        entry = self._registry.entry(contract, name)
        return cast(T, entry.factory(_validated_sub_config(entry, name, config)))


class SubPluginConfigError(WeftError):
    """Raised as the sibling is built, so a mis-shaped config fails by name, not inside its `run`.

    A `*_config` block a plugin passed for a sibling it resolves by name does not fit
    that sibling's own `config_model`.

    **Task 8.11, and it is a repair.** `corrective`, `iterative-retrieval` and
    `refine-on-uncertainty` each resolve a sibling through `StageLookup` and each publishes
    a `*_config` field typed `Mapping[str, object] | None` — seven such fields between them,
    every one documented as *the* way a pipeline document retunes the sibling. `build` used
    to hand that mapping straight to `entry.factory`, so the sibling was constructed with a
    raw `dict` where its own config object belonged and died later inside its own `run`
    (`'dict' object has no attribute 'channels'`, found by running
    `weft ask --pipeline corrective-retrieve`). Seven configuration surfaces, none of which
    worked, and no test caught it because every test that drove these plugins left the
    sibling's config at `None`. `tests/unit/weft_retrieve/test_engine.py`'s own
    `_echo_factory` had been guarding `isinstance(config, _EchoConfig)` since this file was
    written, which is the workaround the defect leaves behind.

    **Deliberately not in fitness function 12's family.** It reports a block that does not
    fit a model, not a name failing to resolve against an enumerable set — the identical line
    `weft_engine.services` already draws between `UnknownServiceKeyError` and its own
    malformed-value check, for the identical reason.
    """


def _validated_sub_config(entry: RegistryEntry, name: str, config: object) -> object:
    """`config`, validated into the resolved plugin's own `config_model` when it is a mapping.

    Mirrors `weft_kernel.resolution`'s own `with:` validation one seam over, and does not
    reuse it: that function's messages name a *stage id* in a *pipeline*, and there is
    neither here — a sibling resolved by name has no position in any document. What it does
    reuse is the shape of the rule, including the part that is easy to skip: a non-empty
    block for a plugin publishing no `config_model` is **refused**, never accepted and
    dropped, because a configuration that silently does nothing is exactly the failure
    `StageNotConfigurableError` exists to prevent.

    **Only a `Mapping` is validated.** A caller that has already built the sibling's config
    object passes it through untouched, which is the shape every in-tree caller used before
    this repair and which must keep working — `unwrap_factory` is how the declaration is read
    off a factory a pack may have bound its settings into, the same call
    `weft_kernel.resolution` makes for `requires`/`provides`.
    """
    if not isinstance(config, Mapping):
        return config
    block = cast("Mapping[str, object]", config)
    declared = unwrap_factory(entry.factory)
    config_model = cast("type[BaseModel] | None", getattr(declared, "config_model", None))
    if config_model is None:
        raise SubPluginConfigError(
            f"a config block {dict(block)!r} was passed for '{name}', which publishes no "
            f"config_model and therefore cannot be parameterised at all. Drop the block, or "
            f"have '{name}' declare a `config_model` so it has somewhere to land."
        )
    try:
        return config_model.model_validate(block)
    except ValidationError as exc:
        problems = "; ".join(
            f"field '{'.'.join(str(part) for part in error['loc']) or '(the block itself)'}': "
            f"{error['msg']}"
            for error in exc.errors()
        )
        accepted = ", ".join(sorted(config_model.model_fields)) or "(no fields)"
        raise SubPluginConfigError(
            f"the config block passed for '{name}' is invalid for "
            f"{config_model.__name__}: {problems}. {config_model.__name__} accepts: "
            f"{accepted}."
        ) from exc


def roles_needed(pipeline: ResolvedPipeline, registry: Registry) -> frozenset[str]:
    """Every `[llm.roles]` name `pipeline`'s stages call a model under — carried repair **R43.30**.

    **The marker decides, never the name** (repair **R43.35**). Each stage's validated config
    is read for every `str` field declared with `LLMRole`, defaults included, whatever the
    field is called; a field named `role` without the marker is not a role. A field declared
    with `weft_retrieve.contract.SubPlugin` names a sibling, which is followed into its own
    config, recursively — the reference `StageLookup` resolves at run time (repair **R43.42**).
    Both markers are read in either optional spelling, and every model nested in a config — a
    `multi-retriever` arm, a stranger's panelist — is read the same way. An unmarked
    `X`/`X_config` pair is not followed: the declaration decides here too.
    """
    roles: set[str] = set()
    for stage in pipeline.stages:
        roles |= _config_roles(stage.config, registry, pipeline.name)
    return frozenset(roles)


def _config_roles(config: object, registry: Registry, rung: str) -> frozenset[str]:
    if not isinstance(config, BaseModel):
        return frozenset()
    roles: set[str] = set()
    for field, info in type(config).model_fields.items():
        roles |= _field_roles(config, field, info, registry, rung)
    return frozenset(roles)


def _field_roles(
    config: BaseModel, field: str, info: FieldInfo, registry: Registry, rung: str
) -> set[str]:
    """The roles one field of `config` names, directly, nested, or through a sub-plugin."""
    model = type(config)
    value = getattr(config, field)
    roles = set(_nested_roles(value, registry, rung))
    markers = _markers(info)
    for marker in markers:
        if isinstance(marker, SubPlugin):
            _check_sub_plugin_config(model, field, marker, rung)
    if not isinstance(value, str):
        return roles
    if any(isinstance(item, LLMRole) for item in markers):
        roles.add(value)
    for marker in markers:
        if isinstance(marker, SubPlugin):
            block = None if marker.config is None else getattr(config, marker.config)
            roles |= _sub_plugin_roles(value, block, registry, rung)
    return roles


def _check_sub_plugin_config(
    model: type[BaseModel], field: str, marker: SubPlugin, rung: str
) -> None:
    """Refuse `marker` when its `config` names no field of `model` — carried repair **R43.45**.

    Run whatever the field's value, because the declaration is the pack's defect either way.
    """
    if marker.config is None or marker.config in model.model_fields:
        return
    fields = tuple(sorted(model.model_fields))
    name = model.__name__
    raise UnknownSubPluginConfigFieldError(
        f"'{rung}': {name}.{field} is declared SubPlugin(config='{marker.config}'), but {name} "
        f"has no field '{marker.config}'. {name}'s fields: {', '.join(fields)}.",
        valid_options=fields,
        pipeline=rung,
    )


def _markers(info: FieldInfo) -> tuple[object, ...]:
    """`info.metadata`, plus any marker held inside an optional union member.

    Pydantic drops a marker spelt `Annotated[str, M()] | None` from `metadata`.
    """
    found = list(info.metadata)
    if get_origin(info.annotation) in (Union, UnionType):
        for member in get_args(info.annotation):
            if get_origin(member) is Annotated:
                found.extend(get_args(member)[1:])
    return tuple(found)


def _nested_roles(value: object, registry: Registry, rung: str) -> frozenset[str]:
    if isinstance(value, BaseModel):
        return _config_roles(value, registry, rung)
    if isinstance(value, Mapping):
        items: Iterable[object] = cast("Mapping[object, object]", value).values()
    elif isinstance(value, tuple | list):
        items = cast("Iterable[object]", value)
    else:
        return frozenset()
    roles: set[str] = set()
    for item in items:
        roles |= _nested_roles(item, registry, rung)
    return frozenset(roles)


def _sub_plugin_roles(name: str, block: object, registry: Registry, rung: str) -> frozenset[str]:
    roles: set[str] = set()
    for contract in registry.contracts():
        if name in registry.names_for(contract):
            entry = registry.entry(contract, name)
            roles |= _config_roles(_sub_config(entry, name, block), registry, rung)
    return frozenset(roles)


def _sub_config(entry: RegistryEntry, name: str, block: object) -> object:
    """The config a sibling is built with.

    Its own defaults when its `SubPlugin.config` block is unset, validated exactly as
    `RegistryStageLookup` validates it otherwise.
    """
    if block is None:
        if getattr(unwrap_factory(entry.factory), "config_model", None) is None:
            return None
        block = {}
    return _validated_sub_config(entry, name, block)


def stage_lookup(registry: Registry) -> RegistryStageLookup:
    """Build the run's `StageLookup`.

    This pack's own constructor — see the module docstring, and `.phase2-design.md` §7: "so a
    library caller is not forced through the CLI." `weft_engine.run_services.build_services` is the
    one caller that is.
    """
    return RegistryStageLookup(registry)


class PipelineRouteCatalogue:
    """Satisfies `weft_retrieve.contract.RouteCatalogue` structurally.

    Built once, over the run's whole pipeline catalogue (contributed, project-local, or
    both merged — this module has no opinion on where the mapping came from, exactly as
    `weft_kernel.resolution.resolve` has none about where its own `parents:` mapping
    came from). `candidates()` is computed once, at construction, and returned as the
    same tuple every time — a route decision reads it more than once in one run (the
    scorer's prompt, then a policy's own selection), and nothing about which pipelines
    are routable changes mid-run.

    `rung_roles` — carried repair **R43.30** — maps each routable document to the roles
    `roles_needed` found on it; a candidate needing a role outside `mapped_roles` is left out,
    and `missing_roles()` says which roles it lacked. `None` filters on nothing.
    """

    def __init__(
        self,
        catalogue: Mapping[str, Pipeline],
        ready_layers: frozenset[str] | None = None,
        *,
        rung_roles: Mapping[str, frozenset[str]] | None = None,
        mapped_roles: frozenset[str] = _NOTHING_MAPPED,
    ) -> None:
        candidates: list[RouteCandidate] = []
        self._missing_roles = missing_roles(rung_roles or {}, mapped_roles)
        for name, pipeline in sorted(catalogue.items()):
            _check_route_vars(name, pipeline)
            if (
                _ROUTE_SUMMARY_VAR in pipeline.vars
                and _layer_ready(pipeline, ready_layers)
                and name not in self._missing_roles
            ):
                candidates.append(
                    RouteCandidate(
                        name=name,
                        summary=str(pipeline.vars[_ROUTE_SUMMARY_VAR]),
                        cost=str(pipeline.vars.get(_ROUTE_COST_VAR, "")),
                    )
                )
        self._candidates = tuple(candidates)

    def candidates(self) -> tuple[RouteCandidate, ...]:
        """Every document that may be offered, as a routing candidate."""
        return self._candidates

    def names(self) -> frozenset[str]:
        """The names of every pipeline in `candidates`."""
        return frozenset(candidate.name for candidate in self._candidates)

    def missing_roles(self) -> Mapping[str, tuple[str, ...]]:
        """Each document left out for an unmapped role, to every role it lacks, sorted."""
        return self._missing_roles


def missing_roles(
    rung_roles: Mapping[str, frozenset[str]], mapped_roles: frozenset[str]
) -> dict[str, tuple[str, ...]]:
    """Map each rung lacking a mapped role to the roles it lacks.

    Each rung in `rung_roles` needing a role `mapped_roles` lacks, to those roles sorted —
    carried repair **R43.30**, the reason `PipelineRouteCatalogue` leaves a rung out.
    """
    return {
        name: tuple(sorted(needed - mapped_roles))
        for name, needed in sorted(rung_roles.items())
        if needed - mapped_roles
    }


def _layer_ready(pipeline: Pipeline, ready_layers: frozenset[str] | None) -> bool:
    """Whether `pipeline` may be offered, given the layers that are ready.

    Whether `pipeline` may be offered — `ready_layers=None` (told nothing) offers
    everything, on every caller before ledger task **43.9**'s own footing.
    """
    if ready_layers is None:
        return True
    required = pipeline.vars.get(_ROUTE_REQUIRES_VAR)
    return required is None or str(required) in ready_layers


def route_requirements(catalogue: Mapping[str, Pipeline]) -> dict[str, str]:
    """Which layer each pipeline needs built, so naming one whose layer is pending is refused.

    Every document naming `route.requires`, its name mapped to the layer it needs — ledger
    task **43.9**. `weft_cli.commands.PendingLayerError`'s own raise site reads this to learn
    which layer a caller's own `--pipeline` choice would answer from.
    """
    for name, pipeline in catalogue.items():
        _check_route_vars(name, pipeline)
    return {
        name: str(pipeline.vars[_ROUTE_REQUIRES_VAR])
        for name, pipeline in catalogue.items()
        if _ROUTE_REQUIRES_VAR in pipeline.vars
    }


def route_catalogue(
    catalogue: Mapping[str, Pipeline],
    ready_layers: frozenset[str] | None = None,
    *,
    rung_roles: Mapping[str, frozenset[str]] | None = None,
    mapped_roles: frozenset[str] = _NOTHING_MAPPED,
) -> PipelineRouteCatalogue:
    """Build the run's `RouteCatalogue`.

    This pack's own constructor — see the module docstring on `stage_lookup`, the identical shape.
    `ready_layers` — ledger task **43.9** — is which layers `weft_cli.coverage.ready_layers` found
    built on every indexed source; `None` (every caller before this task) offers every candidate,
    unfiltered. `rung_roles`/`mapped_roles` — carried repair **R43.30** — leave out a rung needing a
    role the run's `[llm.roles]` does not map; `PipelineRouteCatalogue`'s own docstring.
    """
    return PipelineRouteCatalogue(
        catalogue, ready_layers, rung_roles=rung_roles, mapped_roles=mapped_roles
    )
