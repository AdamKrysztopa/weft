"""What a run needs from the store, checked against the store it was configured with.

Task **2.5**, and the placement was settled one task earlier:
`docs/02-extension-model.md` §1 → *The store contract family* says `needs_store` is
checked **at run assembly, not at resolution**, because neither resolver can do it —
`weft_kernel.runner.Runner.resolve` and `weft_kernel.resolution.resolve` are kernel code,
the kernel names no capability, and neither of them knows what a store *is*. The first
thing that holds both the resolved stage list and the configured store is whatever
assembles the run, which in this tree is `weft-cli`. Only the location moves: this runs
**before any stage runs**, so the promise that section makes is unchanged — no
adaptation, no degradation, and a refusal that names the store, the missing capability
and where to get it.

**This module names no capability either, and that is not an accident.** It never
mentions `VectorSearch` or `TextSearch`: a *plugin* names what it needs, in its own
`needs_store` declaration, and `isinstance` answers whether the store has it. What the
store *does* advertise is derived the same way `weft_cli.contract_reference` derives it —
every versioned capability Protocol the store contract's own pack exports — so a store
pack shipping a capability nobody here has heard of is reported correctly by a module
that has never heard of it either. That is the same property `01` requirement 1 asks of
the kernel, held one layer out.

**`needs_store` is a *requirement*, never a capability declaration.** G4 settled that a
store's capability is derived at registration and never declared, and nothing here opens
a path around that: the store side of every comparison below is `isinstance`. What a
retriever declares is what it will *call*, which only its author can know.

**Read off the factory, not off an instance.** A pack binding its own settings has one
shape available — `functools.partial(PluginClass, settings)` — and `functools.partial`
does not proxy attribute access, so a declaration read from the factory directly is
invisible for exactly the packs most likely to make one.
`weft_kernel.registry.unwrap_factory` is the documented way through, and it is the same
call `weft_kernel.resolution` makes for `requires`/`provides`.

**`build_services` — task 2.8's own addition.** `.phase2-design.md` §7: this module's
second job, populating the run's `ServiceRegistry` with the LLM client, the token sink,
the prompt registry, the store, the embedder, and this phase's two routing services —
`StageLookup` and `RouteCatalogue`. Every one of the six is built by the pack that
publishes its contract (`weft_llm.client.llm_service`, `weft_prompts.registry.
prompts_service`, `weft_retrieve.engine.stage_lookup`/`route_catalogue`) — this function
only calls each constructor and adds the result, which is what `.phase2-design.md` §7's
own sentence means by "so a library caller is not forced through the CLI": the six
constructors are the real API, and this is `weft-cli`'s own use of it, not a second copy.
`check_store_capabilities` above is deliberately **not** called from inside this
function: it needs a resolved `StageSpec` list, and `build_services` is called once per
run while a run may resolve more than one pipeline (the router, then whichever pipeline
it selects) — the caller runs the check itself, once per resolved pipeline, immediately
before handing it to `Runner.run_once`, which keeps "before any stage runs" true for
each one individually rather than once for whichever pipeline happened to be resolved
first.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from typing import Final, cast

from weft_cli.contract_reference import capability_siblings
from weft_cli.llm_roles import LLMSection
from weft_cli.registry_bootstrap import Dependencies
from weft_cli.service_roles import RoleTable
from weft_cli.services import ServiceSelection
from weft_embed import Embedder
from weft_kernel.context import ServiceRegistry, UnresolvedServiceError
from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_kernel.pipeline import Pipeline
from weft_kernel.registry import Registry, RegistryEntry, UnknownPluginError, unwrap_factory
from weft_kernel.runner import PipelineResolutionError, StageSpec
from weft_llm.client import llm_service
from weft_llm.contract import LLM, TokenSink
from weft_prompts.contract import Prompts
from weft_prompts.registry import prompts_service
from weft_retrieve.contract import RouteCatalogue, StageLookup
from weft_retrieve.engine import route_catalogue, stage_lookup
from weft_store import NodeStore

#: Ledger task **9.0**'s own defaults for `build_services`/`build_index_services`'s new
#: `roles`/`services` parameters — module-level singletons, never `RoleTable()`/
#: `ServiceSelection()` written inline in a signature, because ruff's B008 refuses a function
#: call in a default argument's position regardless of the type being frozen. Both are empty
#: and register nothing (`RoleTable.roles`/`ServiceSelection.roles` default to `{}`), which is
#: exactly today's behaviour for a caller that names neither — see each function's own
#: docstring for which caller that is.
_NO_ROLES: Final[RoleTable] = RoleTable()
_NO_SELECTION: Final[ServiceSelection] = ServiceSelection()


class StoreCapabilityMissingError(PipelineResolutionError, UnresolvedNameError):
    """A stage needs a store capability the configured store does not advertise.

    Under the `PipelineResolutionError` family because that is what it is to an operator:
    this pipeline cannot run against this store, decided before anything ran, and
    `docs/03-cli.md`'s exit-code split puts "fix the pipeline" at 4. The alternative — a
    plain `WeftError`, exit 1 — would report a configuration that cannot work as a run
    that happened to fail.

    **There is no adaptation and no degradation**, per `docs/02-extension-model.md` §1: a
    pipeline that wanted hybrid search does not quietly become vector-only. Quality
    silently dropping is the failure `01` requirement 5 exists to forbid, and it is
    strictly worse here than a refusal, because the run still produces answers.

    Fitness function 12's family: `[services] store` names a store, and the store
    named turned out not to be a valid choice for this pipeline — `valid_options` is
    every registered store name that *does* provide the missing capability.
    """

    def __init__(
        self,
        message: str,
        *,
        valid_options: tuple[str, ...],
        pipeline: str | None = None,
        stages: tuple[str, ...] = (),
        distributions: tuple[str, ...] = (),
        remedy: str = "",
    ) -> None:
        PipelineResolutionError.__init__(
            self,
            message,
            pipeline=pipeline,
            stages=stages,
            distributions=distributions,
            remedy=remedy,
        )
        self.valid_options = valid_options


class MalformedNeedsStoreError(PipelineResolutionError):
    """A plugin's `needs_store` is not a tuple of `@runtime_checkable` capability Protocols.

    A declaration nobody can check is not skipped: skipping it would run the pipeline the
    declaration existed to stop, and the operator would learn about it from the answers
    being wrong. The two ways to get it wrong are naming a capability (`needs_store =
    "VectorSearch"`) and using a Protocol without `@runtime_checkable`, which `isinstance`
    refuses to answer for; both land here, named, with the plugin that declared it.
    """


def check_store_capabilities(
    specs: Sequence[StageSpec],
    *,
    registry: Registry,
    store: object,
    store_contract: type[object],
    store_name: str,
    pipeline: str | None = None,
) -> None:
    """Refuse the run if any stage needs a store capability `store` does not have.

    Returns nothing: this check speaks only to refuse. A stage whose plugin declares no
    `needs_store` is passed over in silence — most stages never touch the store, and
    requiring every plugin author to declare an empty tuple would be a registration tax
    with no failure behind it (the same argument `weft_enhance.contract` makes for
    declining a mandatory `destroys`).

    `store_contract` is the contract the store was resolved under, and it is a parameter
    rather than an import so this module keeps naming no capability — see the module
    docstring.

    **The whole chain is checked, not the primary alone.** A `fallback:` name is a candidate
    that `weft_kernel.fallback.try_in_order` will actually construct and run when the primary
    refuses a batch, which is why `weft_kernel.runner.Runner._chain` already checks every one
    of them for existence and substitutability. `needs_store` was the one declaration in that
    set left out, and the failure it let through was the worst available shape: the chain
    reaching a fallback that calls a method the store has not got, mid-batch, after the run had
    already done work, as a bare `AttributeError` rather than a `WeftError`.
    """
    advertised = _advertised(store, store_contract)
    for spec in specs:
        for position, (candidate, where) in enumerate(_chain_of(spec)):
            entry = _entry_or_none(registry, spec, candidate, primary=position == 0)
            if entry is None:
                continue
            required = _needs_store_of(
                entry.factory, plugin=candidate, stage=spec.id, pipeline=pipeline
            )
            missing = tuple(
                capability
                for capability in required
                if not _satisfies(
                    store, capability, plugin=candidate, stage=spec.id, pipeline=pipeline
                )
            )
            if not missing:
                continue
            wanted = ", ".join(capability.__name__ for capability in missing)
            providers = _providers_of(missing, registry=registry, store_contract=store_contract)
            offered = ", ".join(advertised) or "nothing beyond the base store contract"
            named = ", ".join(f"'{name}' ({distribution})" for name, distribution in providers)
            instead = (
                f" Otherwise choose a plugin for stage '{spec.id}' that does not need it."
                if position == 0
                else f" Otherwise drop '{candidate}' from stage '{spec.id}'s fallback list."
            )
            raise StoreCapabilityMissingError(
                f"{where}, which needs {wanted} from the store, "
                f"and the configured store '{store_name}' does not provide it. '{store_name}' "
                f"advertises: {offered}. Registered stores that do provide {wanted}: "
                f"{named or '(none installed)'}. Nothing here adapts or degrades — a run that "
                f"asked for a capability does not quietly proceed without it.",
                valid_options=tuple(name for name, _ in providers),
                pipeline=pipeline,
                stages=(spec.id,),
                distributions=tuple(sorted({distribution for _, distribution in providers})),
                remedy=(
                    # `[services] store` is the key, and it only became one at 2.6's repair —
                    # before that this sentence could not name a remedy an operator could
                    # carry out, because nothing selected a store. Naming the key here is the
                    # difference between "run against a different store" and a step.
                    f"name a store that provides {wanted} in [services] store"
                    + (f" — installed and registered: {named}." if named else ", or install one.")
                    + instead
                ),
            )


def _chain_of(spec: StageSpec) -> tuple[tuple[str, str], ...]:
    """Every plugin `spec` can run — primary first — each with how to say where it came from.

    The second element is the subject of the refusal's first clause, so a fallback is named as
    one: an operator reading "stage 'retrieve' names 'hybrid'" for a stage whose `use:` says
    `vector-top-k` would go looking for a typo that is not there.
    """
    chain = [(spec.name, f"stage '{spec.id}' names '{spec.name}'")]
    total = len(spec.fallback)
    chain.extend(
        (name, f"stage '{spec.id}' names '{name}' as fallback {position} of {total}")
        for position, name in enumerate(spec.fallback, start=1)
    )
    return tuple(chain)


def _entry_or_none(
    registry: Registry, spec: StageSpec, candidate: str, *, primary: bool
) -> RegistryEntry | None:
    """`candidate`'s registration, or `None` for a *fallback* name nothing registered.

    A primary that no distribution registered still raises `UnknownPluginError` here, unchanged.
    A missing fallback does not, and that is not a silent pass: `Runner._chain` refuses the
    whole pipeline with `UnknownFallbackError`, naming the position in the chain and every name
    registered for the contract, so the run is refused either way and nothing runs unchecked.
    A name with no registration has no `needs_store` to read, and inventing a second, worse
    answer to a question another module already answers well is how two errors for one mistake
    start.
    """
    try:
        return registry.entry(spec.contract, candidate)
    except UnknownPluginError:
        if primary:
            raise
        return None


def _needs_store_of(
    factory: Callable[..., object], *, plugin: str, stage: str, pipeline: str | None
) -> tuple[type[object], ...]:
    """The capabilities `plugin` declared it needs from the store — `()` if it declared none."""
    declared: object = getattr(unwrap_factory(factory), "needs_store", ())
    items: tuple[object, ...] = (
        cast("tuple[object, ...]", declared) if isinstance(declared, tuple) else ()
    )
    if not isinstance(declared, tuple) or not all(isinstance(item, type) for item in items):
        raise MalformedNeedsStoreError(
            f"plugin '{plugin}' declares needs_store={declared!r}, which is not a tuple of "
            f"capability Protocols. Declare the Protocols themselves — "
            f"`needs_store: ClassVar[tuple[type, ...]] = (VectorSearch,)` — importing them "
            f"from the pack that publishes them.",
            pipeline=pipeline,
            stages=(stage,),
            remedy=(
                f"fix the needs_store declaration on plugin '{plugin}', in the pack that ships it."
            ),
        )
    return tuple(item for item in items if isinstance(item, type))


def _satisfies(
    store: object, capability: type[object], *, plugin: str, stage: str, pipeline: str | None
) -> bool:
    """Whether `store` has `capability`, derived — the one question this module asks of a store."""
    try:
        return isinstance(store, capability)
    except TypeError as exc:
        raise MalformedNeedsStoreError(
            f"plugin '{plugin}' declares it needs {capability.__name__}, which cannot be "
            f"checked against a store instance: {exc}. A capability Protocol must carry "
            f"@runtime_checkable, because deriving capability *is* the isinstance call.",
            pipeline=pipeline,
            stages=(stage,),
            remedy=(
                f"have the pack publishing {capability.__name__} decorate it with "
                f"@runtime_checkable."
            ),
        ) from exc


def _advertised(store: object, store_contract: type[object]) -> tuple[str, ...]:
    """Which of the store family's capabilities this store actually has, in name order.

    Derived from the publishing pack's own `__all__`, exactly as the contract reference
    derives it, so the list an operator reads here and the list the reference prints
    cannot disagree.
    """
    return tuple(
        sorted(
            sibling.__name__
            for sibling in capability_siblings(store_contract)
            if isinstance(store, sibling)
        )
    )


def _providers_of(
    missing: tuple[type[object], ...], *, registry: Registry, store_contract: type[object]
) -> tuple[tuple[str, str], ...]:
    """Every registered store that provides all of `missing`, as `(plugin name, distribution)`.

    Answered from the registered *class*, never from an instance: building every installed
    store to write an error message would open connections on the failure path. A factory
    that is not a class — a function returning a store, which the contract permits — is
    left out rather than called, and so is a capability whose Protocol cannot answer
    `issubclass` (one with a non-method member); a remedy list is a courtesy, and the
    refusal above does not depend on it being complete.
    """
    found: list[tuple[str, str]] = []
    for name in sorted(registry.names_for(store_contract)):
        entry = registry.entry(store_contract, name)
        target = unwrap_factory(entry.factory)
        if isinstance(target, type) and all(class_provides(target, cap) for cap in missing):
            found.append((name, entry.distribution))
    return tuple(found)


def class_provides(candidate: type[object], capability: type[object]) -> bool:
    """Whether `candidate` structurally satisfies `capability`, decided from the class alone.

    `capability` is typed `type[object]` rather than a Protocol on purpose, and it is not a
    weakening: every capability Protocol in the store family declares `version` under
    `if TYPE_CHECKING:`, which a type checker reads as a non-method member and therefore
    refuses in an `issubclass` call — while at runtime `__protocol_attrs__` never contains it
    and the call is exactly the derived-capability check `docs/02-extension-model.md` §1
    specifies. A capability whose Protocol genuinely *does* carry a non-method member raises
    `TypeError` here and answers `False`, which is the honest answer for a check that could
    not be made rather than a guess about one that could.

    **Public since task 5.1a**, when `weft_cli.deletion` needed the same question asked of
    `SourceDeletable`: two implementations of "does this class have this capability" could
    disagree, and a fan-out that missed a participant the capability refusal would have named
    is exactly the divergence this project keeps refusing to ship.
    """
    try:
        return issubclass(candidate, capability)
    except TypeError:
        return False


def selected_role_instances(
    *, registry: Registry, services: ServiceSelection, table: RoleTable
) -> dict[str, object]:
    """Every declared role `services` actually names, built and keyed by its `[services]` key.

    Ledger task **9.0** — the one resolver the three assemblers share, so a pack's declared
    role reaches every path from a single implementation rather than three that could drift.
    For each key in `table.declared` that `services.roles` also names, this builds the plugin
    the same way `build_services` already builds the store and the embedder — one call to
    the registered factory, no per-role `with:` configuration to pass, since `[services]`
    selects a plugin by name only. A declared role `services` says nothing about is skipped —
    no default, no guess, per `weft_cli.service_roles`'s own module docstring. An unregistered
    plugin name raises the registry's own `UnknownPluginError`, unchanged and uncaught: an
    operator naming a plugin that does not exist for that role's contract gets the loud,
    diagnosable refusal `weft_kernel.registry` already writes, not a second, worse one
    invented here.

    **Called with no argument, not `factory(None)`.** `weft_kernel.runner._build`'s own
    comment states the kernel's convention for a plugin built on no configuration — "a
    fallback is built on its plugin's own defaults, the same call an unconfigured stage
    gets" — as `factory(None)`, and every plugin class this repository ships honours it with
    an explicit `def __init__(self, config: object = None) -> None:`. A role plugin that
    declares no `__init__` at all — no configuration to accept, ever, because a role is
    selected by name alone — takes `factory(None)`, the identical call `build_services` makes for
    would satisfy `factory(None)` if it *had* written the boilerplate parameter, so a role
    author who genuinely has nothing to configure is not taxed into writing an `__init__`
    whose only job would be discarding an argument this call never needed to send.
    """
    return {
        key: registry.entry(role.contract, services.roles[key]).factory(None)
        for key, role in table.roles.items()
        if key in services.roles
    }


def _contract_registered(registered: ServiceRegistry, contract: type[object]) -> bool:
    """Whether `registered` already holds an instance for `contract`.

    `ServiceRegistry` exposes no membership test of its own, only `resolve` (which raises)
    and `add` (which refuses a duplicate) — this is the one question both `build_services`
    and `command_path_services` need answered *before* calling `add`, so a role whose contract
    a caller already populated ambiently (`NodeStore`, `Embedder`) is skipped rather than
    raising `weft_kernel.context.DuplicateServiceError` at whichever registration happened to
    come second.
    """
    try:
        registered.resolve(contract)
    except UnresolvedServiceError:
        return False
    return True


async def build_services(
    *,
    registry: Registry,
    catalogue: Mapping[str, Pipeline],
    llm: LLMSection,
    services: ServiceSelection,
    sink: TokenSink,
    roles: RoleTable = _NO_ROLES,
) -> ServiceRegistry:
    """Assemble one run's `ServiceRegistry` — every service a query-path stage may reach
    through `ctx.require(...)`. See the module docstring's *"`build_services` — task 2.8's
    own addition."*

    **`sink` — task 3.6's own repair.** Every other service this function registers is built
    by the pack that publishes its contract; `TokenSink` used to be the one exception,
    hardcoded to `weft_llm.client.NullSink()` regardless of what a caller wanted — the gap
    `docs/03-cli.md` -> *Output* (G6) names: "the CLI registers a `TokenSink`
    implementation." Now the caller decides, exactly as it already decides `services.store`/
    `services.embed`; `weft_cli.route_ask.run_routed_ask` is this function's one caller today
    and reads `Dependencies.token_sink` to supply it — see that module's own docstring. No
    default here: a caller with nothing to say about tokens still has to say so explicitly,
    with `weft_llm.client.NullSink()`, rather than this function silently choosing it —
    "never absent" is the sink's own promise, not license for this assembler to guess.

    `async def`, per `.phase2-design.md` §7, even though nothing below awaits today: every
    constructor called here is synchronous, and the coroutine shape is what lets a future
    service that genuinely needs to (a provider warming a connection pool, say) join this
    function without changing every caller's own shape from sync to async at the same time.

    `catalogue` is the run's whole pipeline catalogue — `weft_cli.pipeline_catalogue.
    load_contributed`'s own return shape — handed straight to `RouteCatalogue`, which reads
    only the `route.summary`-carrying subset of it (`weft_retrieve.engine.
    PipelineRouteCatalogue`'s own docstring). `services.store`/`services.embed` are resolved
    the same way `weft_cli.ingest.run_index` and `weft_cli.ask.run_ask` already resolve
    them: `registry.entry(...).factory(None)`, an unregistered name raising the registry's
    own `UnknownPluginError` naming every option — `weft_cli.registry_bootstrap.
    require_plugin` is what turns that into a diagnosable exit code before this point is
    ever reached; this function does not repeat that translation.

    **`roles` — ledger task 9.0's own addition, the query-path half of the sentence "a pack
    that publishes a run-wide service is reachable by `ctx.require` on every path."**
    Defaults to `_NO_ROLES` (empty — see that constant's own docstring), so an existing
    caller naming neither keeps registering exactly the six services above and nothing more.
    Every role `services.roles` names is built through `selected_role_instances`, the one
    resolver all three assemblers share, then registered under its own contract through
    `register_selected_roles` — `demanded=()` for now: threading the resolved pipeline's own
    demanded capabilities in is a later step, not this task's. A role whose contract this
    function already added ambiently (`NodeStore`, `Embedder`) is filtered out first, through
    `_contract_registered`, rather than left to `register_selected_roles`' own `add` raise
    `weft_kernel.context.DuplicateServiceError` at whichever registration happens to run
    second — the same store/embedder contracts, never a second capability name.
    """
    registered = ServiceRegistry()
    registered.add(
        LLM,
        llm_service(registry=registry, roles=llm.roles, retry=llm.retry, loop_guard=llm.loop_guard),
    )
    registered.add(TokenSink, sink)
    registered.add(Prompts, prompts_service(registry))
    registered.add(
        NodeStore, cast(NodeStore, registry.entry(NodeStore, services.store).factory(None))
    )
    registered.add(Embedder, cast(Embedder, registry.entry(Embedder, services.embed).factory(None)))
    registered.add(StageLookup, stage_lookup(registry))
    registered.add(RouteCatalogue, route_catalogue(catalogue))

    selected = {
        key: instance
        for key, instance in selected_role_instances(
            registry=registry, services=services, table=roles
        ).items()
        if not _contract_registered(registered, roles.roles[key].contract)
    }
    register_selected_roles(registered, selected=selected, table=roles, demanded=())
    return registered


async def build_index_services(
    *,
    registry: Registry,
    llm: LLMSection,
    sink: TokenSink,
    embedder: Embedder | None,
    roles: RoleTable = _NO_ROLES,
    services: ServiceSelection = _NO_SELECTION,
    filled_by_stages: Sequence[type[object]] = (),
) -> ServiceRegistry:
    """Assemble one **ingest** run's `ServiceRegistry` — task **8.10**.

    `build_services` above is the query path's, and this is deliberately not it. Until this
    function existed `weft_cli.ingest.run_index` assembled no services at all, so a stage that
    reached one through `ctx.require` failed at run time with *"no service is registered for
    ... on this run"*. That was not a hypothetical: `raptor` and `hypothetical-questions` are
    registered under `weft_index.contract.Expander`, an ingest-path contract, and **neither had
    ever run through the CLI** — two phases, every gate green, because their exit
    demonstrations were unit tests that constructed a `Context` themselves. Found by running
    the binary (`docs/lessons.md` L8.4), not by any of the 1,929 tests that were green while it
    was true.

    **Four services, and the three that are missing are the argument.** The set is what the
    live population of `ctx.require` calls under `weft_index` actually asks for — `LLM`,
    `Prompts`, `Embedder`, plus `TokenSink` because `weft_llm.client` requires it to serve the
    first — read off the tree rather than off a contract's documentation, per
    `docs/lessons.md` L6.4. What is **not** here:

    - **`StageLookup` and `RouteCatalogue`** are `weft-retrieve`'s, published for the query
      path. An ingest stage able to reach them would be an ingest plugin depending on the
      query path, which nothing else in this tree's layering permits and which no ingest
      plugin has ever asked for. Handing `build_services`' whole set over would have granted
      it silently, which is the cheap mistake this function exists instead of. Neither is a
      declared role of any ingest-side pack, so no `roles`/`services` combination below can
      register one either.
    - **`NodeStore`**, for a different reason: an ingest document already names a store
      *stage*, so an ambient one would give a single run two paths to the same store with no
      ordering between them. On the query path a store is a service because there is no store
      stage; here there is one, and it is the pipeline's business.

    A stage reaching for any of the three gets `weft_kernel.context.UnresolvedServiceError`
    naming what *is* available, which is requirement 5 and is also the seam where a third
    party who genuinely needs one would come and ask.

    **`roles`, `services` and `filled_by_stages` — ledger task 9.0's own addition, generalising
    `NodeStore`'s exclusion above into data rather than repeating it as a second hardcoded
    absence.** The argument for excluding an ambient `NodeStore` was never about the *name*
    `NodeStore` — it was that an ingest document's own resolved pipeline already has a stage
    filling that contract, and an ambient second path to it has no ordering against the first.
    That argument is about the resolved pipeline, not about which capabilities `weft-cli` has
    heard of, so `filled_by_stages` — every contract the caller's own resolved `StageSpec`
    list already fills, `weft_cli.ingest.run_index`'s `tuple(spec.contract for spec in
    specs)` — is what a role is checked against, never a capability name written here. Every
    role `services.roles` names is built through `selected_role_instances`, the same resolver
    `build_services` shares, and a role whose contract is in `filled_by_stages` is filtered out
    before `register_selected_roles` ever sees it — which is how `NodeStore` stays excluded
    without this function naming it a second time. Both default to `_NO_ROLES`/`_NO_SELECTION`
    (empty — see those constants' own docstring), so an existing caller naming neither keeps
    registering exactly the four services above and nothing more.

    **`embedder` is an instance, not a name, and that is the decision this function encodes.**
    On a `--pipeline` run `[services] embed` is deliberately not read (`weft_cli.ingest.
    run_index`'s own *"Q3, settled"*), so resolving an ambient embedder from the configured
    name would let `raptor` cluster its leaves with one embedder while the document's own
    `embed` stage wrote vectors from another — a run that succeeds, an index that is built,
    and summaries sitting in a different vector space from the chunks they summarise, with
    nothing anywhere reporting it. The caller therefore passes the *resolved pipeline's own*
    embed-stage instance, so there is exactly one embedder per run by construction rather than
    two that happen to agree. The default path derives it the same way and needs no branch:
    its specs name `[services] embed` at the embed stage, so the instance is that one. `None`
    means the resolved pipeline has no embed stage at all, and then no `Embedder` is registered
    rather than one being conjured from configuration — a stage reaching for it gets the
    ordinary `UnresolvedServiceError` naming what this run does offer.

    `async def` for the reason `build_services` states for itself: nothing below awaits today,
    and the coroutine shape is what lets a service that genuinely needs to join without
    changing every caller from sync to async at once.
    """
    registered = ServiceRegistry()
    registered.add(
        LLM,
        llm_service(registry=registry, roles=llm.roles, retry=llm.retry, loop_guard=llm.loop_guard),
    )
    registered.add(TokenSink, sink)
    registered.add(Prompts, prompts_service(registry))
    if embedder is not None:
        registered.add(Embedder, embedder)

    selected = {
        key: instance
        for key, instance in selected_role_instances(
            registry=registry, services=services, table=roles
        ).items()
        if roles.roles[key].contract not in filled_by_stages
    }
    register_selected_roles(registered, selected=selected, table=roles, demanded=())
    return registered


class AmbiguousCapabilityError(WeftError):
    """Two selected roles both satisfy one capability a stage demanded.

    Ledger task **9.0**, property (ii). Aliasing answers a demanded capability with *the* one
    instance that provides it, and there is no such instance when two do — resolving to either
    would hand a stage one arbitrary service and report nothing.

    Refused at assembly, before any stage runs, naming the capability and **both role keys**,
    because the role key is the thing an operator edits. `ServiceRegistry.add`'s own
    `DuplicateServiceError` would also fire here, at whichever registration happened to come
    second, but it can only name the contract — an operator would learn that something is
    ambiguous and not what to change.

    Deliberately **not** in fitness function 12's `UnresolvedNameError` family, on
    `weft_cli.service_roles.DuplicateServiceRoleError`'s footing and for the identical reason:
    nothing failed to resolve against an enumerable set. Two things resolved and disagree,
    which is a collision rather than a lookup miss, so there is no `valid_options` to offer.
    """


class SelectedCapabilityMissingError(PipelineResolutionError, UnresolvedNameError):
    """A stage needs a capability no selected role provides.

    Ledger task **9.0**, property (iii) — `StoreCapabilityMissingError` above, generalised off
    the one configured store and onto the whole selected set. That class validates every
    `needs_store` against the store alone and its remedy names only `[services] store`, so a
    stage needing a capability some *other* role provides was refused before aliasing could
    help, with a remedy pointing at the wrong key. This is the same refusal asked of the right
    instance.

    Under `PipelineResolutionError` for the reason that class states: to an operator this is a
    pipeline that cannot run against this configuration, decided before anything ran, which
    `docs/03-cli.md`'s exit-code split puts at 4.

    **The remedy names a plugin name, never a Python class.** `docs/lessons.md` `L9.26`: the
    one production caller of the older check passed `store_name=type(store).__name__`
    (`weft_cli/route_ask.py:513`), so a live refusal read *the configured store
    'PgVectorStore'* while `[services] store` accepts `pgvector` — a remedy nobody could carry
    out. Every other call site was a test supplying that name by hand, which is exactly why
    none of them could catch it.

    Fitness function 12's family: `valid_options` is every role key whose declared contract
    publishes the missing capability.
    """

    def __init__(
        self,
        message: str,
        *,
        valid_options: tuple[str, ...],
        stages: tuple[str, ...] = (),
        remedy: str = "",
    ) -> None:
        PipelineResolutionError.__init__(self, message, stages=stages, remedy=remedy)
        self.valid_options = valid_options


def _roles_publishing(capability: type[object], *, table: RoleTable) -> tuple[str, ...]:
    """Every declared role key whose own contract's pack publishes `capability`, in name order.

    Derived exactly as `_advertised` derives what a store advertises — `capability_siblings`
    walks the contract-publishing pack's public module — so a capability this file has never
    heard of is attributed to the right role by a function that has never heard of it either.
    That is what keeps this module naming no capability, one layer out from where the store
    check already holds it.
    """
    return tuple(
        sorted(
            key
            for key, role in table.roles.items()
            if capability in capability_siblings(role.contract) or capability is role.contract
        )
    )


def register_selected_roles(
    registered: ServiceRegistry,
    *,
    selected: Mapping[str, object],
    table: RoleTable,
    demanded: Sequence[type[object]] = (),
) -> None:
    """Register each selected role's instance under its contract, and alias it under every
    capability the resolved pipeline actually demands of it.

    Ledger task **9.0**, property (ii). `ServiceRegistry` keys by **exact type**
    (`weft_kernel/context.py:105`), so an instance registered under its role's contract answers
    no `ctx.require` for anything else it satisfies. Aliasing is what makes a second capability
    reachable at all.

    **By demand, never by satisfaction**, and the deletion fan-out is why. `SourceDeletable` is
    a fan-out capability — many participants satisfy it at once, discovered by walking the
    factory registry (`weft_cli/fanout.py:59`, `deletion.py:67`) and never through this
    registry. A single-valued `ctx.require(SourceDeletable)` could only answer with one
    arbitrary participant, which is a wrong answer wearing a type. Nothing demands it, so
    nothing aliases it, and a stage reaching for it gets `UnresolvedServiceError` naming what
    the run does offer.

    A demanded capability **no** selected instance provides is passed over in silence here:
    `check_selected_capabilities` owns that refusal and has the stage id needed to make it
    diagnosable. Two providers is `AmbiguousCapabilityError`.

    Builds nothing — constructing a plugin from its configured name is the caller's job, so
    this function opens no connection and can be asked about a run that will not happen.
    """
    for key, instance in selected.items():
        role = table.roles.get(key)
        if role is None:
            continue
        registered.add(role.contract, instance)

    for capability in demanded:
        providers = tuple(
            key
            for key, instance in selected.items()
            if key in table.roles and _satisfies_capability(instance, capability)
        )
        if len(providers) > 1:
            named = ", ".join(f"[services] {key}" for key in sorted(providers))
            raise AmbiguousCapabilityError(
                f"a stage needs {capability.__name__} from a run-wide service, and more than "
                f"one selected role provides it: {named}. Resolving it would hand that stage "
                f"one of the two arbitrarily and report nothing, so it is refused here. "
                f"Select a plugin for exactly one of those roles that provides "
                f"{capability.__name__}."
            )
        if len(providers) == 1:
            registered.add(capability, selected[providers[0]])


def _satisfies_capability(instance: object, capability: type[object]) -> bool:
    """Whether `instance` has `capability`, derived — the one question asked of a selection.

    `_satisfies` above asks the identical question of a store and turns a non-`runtime_checkable`
    Protocol into `MalformedNeedsStoreError`. This is that stance without a plugin or stage to
    attribute it to, which is the only reason it is a second function rather than a call.
    """
    try:
        return isinstance(instance, capability)
    except TypeError:
        return False


def check_selected_capabilities(
    *,
    demanded: Mapping[type[object], str],
    selected: Mapping[str, object],
    table: RoleTable,
    names: Mapping[str, str],
) -> None:
    """Refuse the run if a stage needs a capability no selected role provides.

    Ledger task **9.0**, property (iii). Returns nothing: like `check_store_capabilities` above,
    this speaks only to refuse, and runs before any stage does, so the promise `02` §1 makes —
    no adaptation, no degradation, a refusal naming the missing capability and where to get it
    — is unchanged by being asked of a set rather than of one store.

    `demanded` maps a capability Protocol to the **stage id** that declared it needs one; the
    stage is in the refusal because "something needs this" is not a thing an operator can act
    on. `names` maps a role key to the plugin name written in `weft.toml`, so the message can
    say what was configured rather than what class it turned into — `docs/lessons.md` `L9.26`.
    """
    for capability, stage in demanded.items():
        if any(
            _satisfies_capability(instance, capability)
            for key, instance in selected.items()
            if key in table.roles
        ):
            continue

        candidates = _roles_publishing(capability, table=table)
        if not candidates:
            raise SelectedCapabilityMissingError(
                f"stage '{stage}' needs {capability.__name__} from a run-wide service, and no "
                f"installed pack declares a [services] role whose contract publishes it. "
                f"Nothing here adapts or degrades — a run that asked for a capability does not "
                f"quietly proceed without it.",
                valid_options=(),
                stages=(stage,),
                remedy=(
                    f"install a pack that publishes {capability.__name__} and declares a "
                    f"[services] role for it; `weft plugins doctor` lists what is installed."
                ),
            )

        unfilled = tuple(key for key in candidates if key not in selected)
        filled = tuple(
            f"[services] {key} = {names.get(key, selected[key].__class__.__name__)!r}"
            for key in candidates
            if key in selected
        )
        keys = ", ".join(f"[services] {key}" for key in candidates)
        detail = (
            f"nothing is selected for {keys}"
            if unfilled == candidates
            else f"what is selected does not provide it: {', '.join(filled)}"
        )
        raise SelectedCapabilityMissingError(
            f"stage '{stage}' needs {capability.__name__} from a run-wide service, and "
            f"{detail}. Nothing here adapts or degrades — a run that asked for a capability "
            f"does not quietly proceed without it.",
            valid_options=candidates,
            stages=(stage,),
            remedy=(
                f"name a plugin that provides {capability.__name__} in {keys}. "
                f"`weft plugins doctor` lists what every installed pack registered."
            ),
        )


def command_path_services(deps: Dependencies, *, sink: TokenSink) -> ServiceRegistry:
    """Assemble the third assembler's `ServiceRegistry` — the one `weft_cli.cli.run_command`
    builds inline for **every** command, `--pipeline`-driven or not. Ledger task **9.0**.

    Moved here from `run_command`'s own body, which used to build this same set — `Dependencies`,
    `LLM`, `Prompts`, `TokenSink`, `Registry` — by calling `ctx.services.add` five times in a
    row with no counterpart this module's own `build_services`/`build_index_services` could be
    checked against for the identical gap Phase 7's close found (`docs/build-ledger.md:
    4358-4366`): "`run_command` registers four contracts and a pack needing the configured
    store or embedder... still cannot reach one." The three assemblers are one list written
    thrice, and a fix landed in only two of them is exactly that defect, unrepaired, one
    assembler over.

    **`Dependencies`, replaced rather than reused.** `deps` is the run's own, frozen and
    shared across REPL turns — `dataclasses.replace(deps, token_sink=sink)` is a new instance
    carrying the caller's chosen sink, so a `Command` reading `ctx.require(Dependencies).
    token_sink` sees it for this run only, and `deps` itself is left untouched for whatever
    else holds a reference to it (`weft_cli.repl.run_repl`, across turns).

    **`LLM`/`Prompts`/`TokenSink`, registered by their own published contract types, alongside
    `Dependencies`** — task **7.4**'s own seam repair, so a command that is not `weft-cli`'s
    own can reach one through `ctx.require(LLM)` without depending on the driving adapter at
    all. Built through the identical constructors `build_services` already calls for the query
    path (`weft_llm.client.llm_service`, `weft_prompts.registry.prompts_service`) — this is not
    a second implementation of either, only a second registration of what they built.

    **`Registry` too.** `weft_cli.commands`'s own module docstring tells a third party their
    command may "read `ctx.require(weft_kernel.registry.Registry)` directly if all it needs is
    plugin resolution" — and nothing registered one before task 8.38's own repair, so that
    sentence was false for every caller it was written for. Found by running `weft agent` from
    outside this repository: the refusal named `Dependencies, LLM, Prompts, TokenSink` and no
    `Registry`, which is requirement 5 doing its job on a gap requirement 1 had left
    (`docs/lessons.md` `L8.38`).

    **`roles` — this task's own addition, closing the sentence Phase 7's close actually
    measured as failing.** Built through `selected_role_instances`, the resolver every
    assembler shares, then registered through `register_selected_roles` with `demanded=()` —
    the identical reasoning `build_services`' own docstring gives for the same call. A role
    whose contract this function already registered ambiently (none of `Dependencies`, `LLM`,
    `Prompts`, `TokenSink`, `Registry` is ever a role's own contract, since a role is declared
    against a pack's *own* published contract, never against one of these five) is filtered
    through `_contract_registered` on the identical footing `build_services` filters `NodeStore`/
    `Embedder` — kept here rather than assumed impossible, because the check costs nothing and
    a future role whose contract happened to collide would otherwise raise `weft_kernel.context.
    DuplicateServiceError` with no clue this function is where to look.

    Not `async def`: nothing this function calls awaits, unlike `build_services`/
    `build_index_services`, whose own coroutine shape exists for a future service that might.
    `weft_cli.cli.run_command` is a synchronous call site (`ctx.services.add`, not `await`
    anything) and this keeps it one.
    """
    registered = ServiceRegistry()
    registered.add(Dependencies, dataclasses.replace(deps, token_sink=sink))
    registered.add(
        LLM,
        llm_service(
            registry=deps.registry,
            roles=deps.llm.roles,
            retry=deps.llm.retry,
            loop_guard=deps.llm.loop_guard,
        ),
    )
    registered.add(Prompts, prompts_service(deps.registry))
    registered.add(TokenSink, sink)
    registered.add(Registry, deps.registry)

    selected = {
        key: instance
        for key, instance in selected_role_instances(
            registry=deps.registry, services=deps.services, table=deps.roles
        ).items()
        if not _contract_registered(registered, deps.roles.roles[key].contract)
    }
    register_selected_roles(registered, selected=selected, table=deps.roles, demanded=())
    return registered
