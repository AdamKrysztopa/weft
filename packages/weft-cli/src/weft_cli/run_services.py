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

from collections.abc import Callable, Mapping, Sequence
from typing import cast

from weft_cli.contract_reference import capability_siblings
from weft_cli.llm_roles import LLMSection
from weft_cli.services import ServiceSelection
from weft_embed import Embedder
from weft_kernel.context import ServiceRegistry
from weft_kernel.errors import UnresolvedNameError
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
        if isinstance(target, type) and all(_class_provides(target, cap) for cap in missing):
            found.append((name, entry.distribution))
    return tuple(found)


def _class_provides(candidate: type[object], capability: type[object]) -> bool:
    try:
        return issubclass(candidate, capability)
    except TypeError:
        return False


async def build_services(
    *,
    registry: Registry,
    catalogue: Mapping[str, Pipeline],
    llm: LLMSection,
    services: ServiceSelection,
    sink: TokenSink,
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
    return registered
