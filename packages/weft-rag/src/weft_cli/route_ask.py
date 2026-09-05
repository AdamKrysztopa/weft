"""Resolve a pipeline through the real router, then run it — `weft ask`'s own default path.

Task **2.8**. `.phase2-design.md` §5, read literally: "`weft ask` runs `route` through
`run_once`, gets a `Route`, looks `Route.pipeline` up in the pipeline catalogue, resolves
it, and runs it. **Selection is pipeline selection, never dispatch.**" This module is
that walk. 2.8 shipped it behind a new, *additive* command, `weft route`, rather than as a
rewrite of `weft ask` — Phase 0's own documented, tested, retrieve-only contract was left
untouched deliberately, because rewriting it was a bigger, separate risk than 2.8's own —
and named the gap explicitly rather than closing it by silence (`docs/build-ledger.md`'s
2.25 note). **Task 3.11 is that gap closed**: `weft route` is retired, and
`weft_cli.commands.AskCommand` calls `run_routed_ask` below directly, so the question a
user asks reaches the pipeline the router names with no second command to learn. `weft_cli.
ask.run_ask` — the direct embed-and-search call this module never touches — survives as
`weft ask --retrieve-only`, Phase 0's own contract kept reachable for a caller (a script, a
deterministic baseline measurement) that genuinely wants no router and no model call; see
`docs/build-ledger.md`'s 3.11 entry for the argument in full.

**Two resolutions, not one.** `route.yaml` (`packages/weft-rag/src/weft_retrieve/
pipelines/route.yaml`, contributed by `weft-retrieve`'s own `register()`) is resolved and
run first, taking a bare `Query` and returning a `Route`. Whatever pipeline it names is
then resolved and run *second*, taking a `QuerySet` — the same two-step `.phase2-design.md`
§5 states, with `weft_cli.compile.contracts_for`/`to_specs` and `weft_kernel.runner.Runner`
doing the actual resolution and execution work for both, exactly as they would for any
other pipeline document. Neither resolution is special-cased: this module names no plugin
and no pipeline of its own at all. **Which document is the router is `[services] route`'s
answer since task 8.3**, defaulting to `route` — until then the name was a constant here, and
that made it the one pipeline in the tree nobody could substitute: a pack cannot contribute a
second document under a name another pack already holds, and a project that ships its own
`route.yaml` is refused by `full_catalogue` and takes every `weft pipeline` command with it.
`weft_cli.services.DEFAULT_ROUTER` carries the argument, and the two registered routing
policies that were unreachable because of it are the evidence.

`weft_cli.run_services.check_store_capabilities` runs once per resolved pipeline,
immediately before that pipeline's own `run_once` call — see `weft_cli.run_services`'s
own module docstring for why that check is not inside `build_services` itself.

**`run_named_ask`, task 3.11 — the same walk, minus the router.** `weft ask <question>
--pipeline <name>` is what a caller who wants a *specific* pipeline uses now that `weft
route` has been folded into `ask` (`docs/build-ledger.md`'s 3.11 entry has the surface
argument in full): this function skips `route.yaml` entirely and resolves `pipeline_name`
straight against `weft_cli.pipeline_catalogue.full_catalogue` — project-local documents
*and* every installed pack's own contribution, deliberately broader than `run_routed_ask`'s
own `load_contributed`-only catalogue, because naming a pipeline by hand is exactly the case
a project-local document scaffolded by `weft pipeline derive` and never published as a pack
should be reachable from. `_prepared_runner` below is the setup the two functions share —
`build_services`, the routed `Context`, the `Runner` and the resolved store — factored out
once both existed, rather than a second copy of `run_routed_ask`'s own first half.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace

from weft_cli.compile import contracts_for, to_specs
from weft_cli.llm_roles import LLMSection
from weft_cli.pipeline_catalogue import (
    DEFAULT_PIPELINES_DIR,
    UnknownPipelineNameError,
    full_catalogue,
    load_contributed,
)
from weft_cli.run_services import build_services, check_store_capabilities
from weft_cli.services import DEFAULT_ROUTER, ServiceSelection
from weft_generate.contract import Generator
from weft_generate.payload import Answer
from weft_kernel.context import Context
from weft_kernel.discovery import PackReport
from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_kernel.payload import Produced
from weft_kernel.pipeline import Pipeline
from weft_kernel.registry import Registry
from weft_kernel.resolution import Contribution, resolve
from weft_kernel.runner import PipelineResolutionError, Runner
from weft_llm.contract import TokenSink
from weft_retrieve.contract import RoutingPolicy
from weft_retrieve.payload import Query, QuerySet, Route
from weft_store import NodeStore

#: `route.yaml`'s own `name:` field, and **the default rather than the law** since ledger task
#: **8.3**. It was a module constant until then, and `weft_cli.services.DEFAULT_ROUTER` — where
#: it now lives as `[services] route`'s default — carries the argument for the change in full:
#: a hard-coded router name is the one privileged pipeline in the tree, because no second
#: document can take the name and no project may declare it either. This alias stays so the
#: name a reader greps for still resolves; `run_routed_ask` reads `services.route`.
ROUTE_PIPELINE_NAME = DEFAULT_ROUTER


class NoRouterPipelineError(WeftError, UnresolvedNameError):
    """`[services] route` names a pipeline no installed pack contributed.

    `weft-retrieve`'s own `register()` contributes `route`, the default — so against an
    unedited configuration this fires only when `weft-retrieve` is not installed, not permitted
    by `[packs] allow`, or failed to register, all of which `weft plugins doctor` already
    reports by distribution. Since task **8.3** it also fires on a typo in `[services] route`,
    which is a different mistake and gets a different remedy: `valid_options` carries every
    contributed pipeline whose last stage is a `RoutingPolicy`, so requirement 5's third clause
    — *what the valid options are* — is answered with the routers that exist rather than with
    advice about `doctor`. `weft_cli.route_ask.pipelines_producing` computes it, the same walk
    `run_named_ask`'s own refusal already uses one contract over.
    """

    def __init__(
        self, message: str, *, valid_options: tuple[str, ...], remedy: str | None = None
    ) -> None:
        super().__init__(message)
        self.valid_options = valid_options
        self.remedy = remedy


class UnroutedPipelineNameError(PipelineResolutionError, UnresolvedNameError):
    """The router selected a pipeline `Route.pipeline` names, but the catalogue holds no
    document by that name.

    Cannot happen against `weft_retrieve.contract.RoutingPolicy`'s own published
    implementations — every one of them selects from `RouteCatalogue.candidates()`, which
    is built from the very same catalogue this module resolves against — but a third
    party's `RoutingPolicy` is under no contract obligation to stay inside the catalogue
    it was handed, so this is refused by name rather than assumed impossible.

    Fitness function 12's family: `valid_options` is every pipeline name the catalogue
    does hold.
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


class PipelineDidNotProduceError(PipelineResolutionError):
    """Either resolution ran to completion but answered `NothingToProduce` or `Failed`
    rather than `Produced` — a real outcome from a real run, never a bare exception, so
    it is translated into its own named `WeftError` rather than left for a caller to
    pattern-match on `Outcome`.
    """


async def run_routed_ask(
    question: str,
    *,
    registry: Registry,
    reports: Sequence[PackReport],
    ctx: Context,
    llm: LLMSection,
    services: ServiceSelection,
    sink: TokenSink,
    contributions: tuple[Contribution, ...] = (),
) -> tuple[str, Answer]:
    """Route `question` through the real router, run whichever pipeline it selects, and
    return `(the pipeline name selected, the Answer it produced)`.

    Raises `NoRouterPipelineError` if no installed pack contributed `route.yaml`;
    `UnroutedPipelineNameError` if a `RoutingPolicy` names a pipeline the catalogue does
    not hold; `weft_cli.run_services.StoreCapabilityMissingError` if either resolved
    pipeline needs a store capability `[services] store` does not provide; any
    `weft_kernel.runner.PipelineResolutionError` a malformed document or a name nothing
    registered raises, from either resolution. Every one of these is a `WeftError` a
    caller maps to an exit code exactly the way `weft_cli.cli.handle_ask` already does.

    `sink` — task **3.6** — is the `TokenSink` the generating stage streams into, threaded
    straight through to `build_services`; `weft_cli.commands.AskCommand.run` passes
    `Dependencies.token_sink`, the sink `weft_cli.cli.main` chose from `--json`/`--quiet`.
    This is `weft ask`'s own default, router-driven path since task **3.11** folded the
    formerly-separate `weft route` command into it — `docs/build-ledger.md`'s 3.11 entry
    has the surface argument; this function's own resolution behaviour is untouched, Phase
    2's settled work.

    `contributions` — task **5.3a** (`S8`) — reaches both of this function's own two
    `_run_pipeline` calls (the router's own resolution, and whichever pipeline it selects),
    on the identical footing `weft_cli.pipeline_commands._resolved_or_refuse` and
    `weft_cli.ingest._specs_from_document` already receive it.
    """
    catalogue = load_contributed(reports)
    router_name = services.route
    router = catalogue.get(router_name)
    if router is None:
        options = pipelines_producing(RoutingPolicy, catalogue=catalogue, registry=registry)
        raise NoRouterPipelineError(
            f"no installed pack contributed a pipeline named '{router_name}', which is what "
            f"[services] route selects. Routers contributed: "
            f"{', '.join(options) or '(none)'}.",
            valid_options=options,
            remedy=(
                f"set [services] route in weft.toml to one of: {', '.join(options)}."
                if options
                else "run `weft plugins doctor` to see whether 'weft-retrieve' is active — no "
                "installed pack contributed any pipeline ending in a RoutingPolicy."
            ),
        )

    runner, routed_ctx, store = await _prepared_runner(
        registry=registry, catalogue=catalogue, ctx=ctx, llm=llm, services=services, sink=sink
    )

    query = Query(text=question)
    route = await _run_pipeline(
        router,
        query,
        registry=registry,
        runner=runner,
        ctx=routed_ctx,
        store=store,
        catalogue=catalogue,
        contributions=contributions,
    )
    route = _require(route, Route, pipeline=router_name, produced_by="routing")

    target = catalogue.get(route.pipeline)
    if target is None:
        options = tuple(sorted(catalogue))
        raise UnroutedPipelineNameError(
            f"the router selected '{route.pipeline}', which the pipeline catalogue does "
            f"not hold. Catalogue: {options}.",
            valid_options=options,
            pipeline=route.pipeline,
            remedy=(
                "the RoutingPolicy that produced this Route selected a name outside its "
                "own RouteCatalogue — that is a defect in the policy plugin, not in this "
                "question."
            ),
        )
    query_set = QuerySet(origin=query, queries=(query,))
    answer = await _run_pipeline(
        target,
        query_set,
        registry=registry,
        runner=runner,
        ctx=routed_ctx,
        store=store,
        catalogue=catalogue,
        contributions=contributions,
    )
    answer = _require(
        answer,
        Answer,
        pipeline=route.pipeline,
        produced_by="`weft ask`",
        alternatives=pipelines_producing(Generator, catalogue=catalogue, registry=registry),
    )
    return route.pipeline, answer


class PipelineProducedTheWrongShapeError(WeftError):
    """A pipeline ran to completion and its last stage produced something else — task **6.25**.

    **This replaces three bare `assert isinstance(...)` calls, and the comment on two of them is
    why.** They read `# every shipped routable pipeline ends in a Generator` — an "every X" stated
    over what *this repository ships*, checked against pipeline documents **anyone may write**.
    `docs/lessons.md` L6.15: an invariant's scope is the inputs that actually reach it, not the
    ones its comment names. A three-line user pipeline ending in a retriever made it fail with no
    message at all, which is how it was found (`weft ask --pipeline <name>`, ledger task 6.21's
    own binary run).

    **And `assert` is worse than it looks here**: `python -O` strips it, so on an optimised
    interpreter the wrong object simply flows on to whatever reads it next. A refusal that vanishes
    under a flag is not a refusal.

    The message names the pipeline, the stage that produced the value, what was expected and what
    arrived — `02` §2's rule that a refusal says what was wanted and why it is unavailable, applied
    to a shape rather than to a name.
    """


def pipelines_producing(
    contract: type[object], *, catalogue: Mapping[str, Pipeline], registry: Registry
) -> tuple[str, ...]:
    """Every pipeline in `catalogue` whose **last stage** is registered under `contract`.

    Public because the check that keeps it honest needs it: the assertion worth making is that
    this returns something against the *real* registry, and a test reaching a private name to
    make it would be the wrong shape of coupling.

    **The argument is the *contract*, not the payload the caller wanted.** `Answer` is a payload
    type and nothing is registered under it; `Generator` is the contract that produces one. The
    first draft asked the registry for `Answer`, got an empty list, and printed a refusal with no
    alternatives at all — an empty answer read as "there are none" when it meant "I asked the
    wrong question" (`docs/lessons.md` L5.9), and it was caught by running the binary rather than
    by any test.

    Task **6.32**. Requirement 5's third clause is *"what the valid options are"*, and the
    refusal below could name two remedies without ever saying which pipelines already satisfy
    the one it recommends. The catalogue is in hand at every raise site, so the answer is one
    walk away.

    **Asked of the registry, never of the document.** A pipeline names a plugin and nothing in
    it says what contract that plugin answers for — G1 keeps the kernel from naming a
    capability, so the registry is the only thing that knows. A stage whose plugin is
    registered under no contract, or under several, is simply not offered: this list exists to
    be *useful*, and a name that might not work is worse than a shorter list. Computed on the
    failure path only, so an ambiguous registry costs nothing on the happy one.
    """
    producing: list[str] = []
    for name, pipeline in catalogue.items():
        stages = pipeline.stages
        if not stages:
            continue
        registered = {
            candidate
            for candidate in registry.contracts()
            if stages[-1].use in registry.names_for(candidate)
        }
        if registered == {contract}:
            producing.append(name)
    return tuple(sorted(producing))


def _require[T](
    value: object,
    expected: type[T],
    *,
    pipeline: str,
    produced_by: str,
    alternatives: tuple[str, ...] = (),
) -> T:
    """Refuse, by name, when a pipeline's final value is not the shape the caller needs.

    **Returns the value, narrowed**, rather than asserting and returning nothing. That is not a
    convenience: `assert isinstance(x, T)` narrows `x` for a type checker and a plain call does
    not, so a refusal seam that returned `None` would trade three bare asserts for sixteen
    `reportUnknownMemberType` errors at the call sites. Handing back the narrowed value keeps the
    static guarantee the asserts were carrying while making the runtime one survive `python -O`.

    One seam for all three call sites rather than a repair at the one that was noticed —
    `docs/lessons.md` L5.10, and L6.13's *"a repair specified from one failing instance narrows to
    that instance"*. `tests/architecture/test_ff7_colour_integrity.py`'s sibling check keeps a new
    bare `assert` from reappearing in shipped code.
    """
    if isinstance(value, expected):
        return value
    raise PipelineProducedTheWrongShapeError(
        f"pipeline '{pipeline}' finished and produced {type(value).__name__}, but "
        f"{produced_by} needs {expected.__name__}. A pipeline's last stage decides the shape of "
        f"its result: a query pipeline that ends in a retriever produces passages, and only one "
        f"ending in a Generator produces an Answer. Add a generating stage, or run this pipeline "
        f"with `--retrieve-only`, which asks for the shape it actually produces."
        + (
            f" Pipelines that already end in {expected.__name__}: "
            f"{', '.join(repr(name) for name in alternatives)}."
            if alternatives
            else ""
        )
    )


async def run_named_ask(
    question: str,
    *,
    pipeline_name: str,
    registry: Registry,
    reports: Sequence[PackReport],
    ctx: Context,
    llm: LLMSection,
    services: ServiceSelection,
    sink: TokenSink,
    contributions: tuple[Contribution, ...] = (),
) -> Answer:
    """Run `pipeline_name` directly against `question`, bypassing the router entirely.

    Task **3.11**'s own answer to "what does a caller who wants a specific pipeline use":
    `weft ask <question> --pipeline <name>`, never a second command. Resolved against
    `weft_cli.pipeline_catalogue.full_catalogue` — project-local documents *and* every
    installed pack's own contribution, the identical set `weft pipeline show/validate/diff/
    derive` already resolve names against — deliberately wider than `run_routed_ask`'s own
    `load_contributed`-only catalogue, which is the *router*'s own search set (Phase 2's
    settled behaviour, untouched here): a pipeline scaffolded by `weft pipeline derive` and
    never published as a pack is reachable the moment it validates.

    Raises `weft_cli.pipeline_catalogue.UnknownPipelineNameError` if `pipeline_name` is not
    in the catalogue — reused rather than duplicated, on `weft_cli.commands.
    _raise_for_plugin_refusal`'s own "one code path, not two" footing: that class's own
    docstring already covers "a bare name a person typed at the command line", which is
    exactly what this is, one caller further than the four `weft pipeline` commands that
    established it. `weft_cli.run_services.StoreCapabilityMissingError` and any
    `weft_kernel.runner.PipelineResolutionError` propagate unchanged, the same set
    `run_routed_ask` documents for its own second resolution.

    `contributions` — task **5.3a** (`S8`) — reaches `_run_pipeline` below on the identical
    footing `run_routed_ask` already passes it through.
    """
    catalogue = full_catalogue(reports=reports)
    target = catalogue.get(pipeline_name)
    if target is None:
        options = tuple(sorted(catalogue))
        raise UnknownPipelineNameError(
            f"'{pipeline_name}' is not a pipeline this project knows — checked the "
            f"project's own '{DEFAULT_PIPELINES_DIR}' directory and every installed pack's "
            f"own contribution. Known pipelines: {', '.join(options) or '(none)'}.",
            valid_options=options,
            pipeline=pipeline_name,
            remedy=f"use one of: {', '.join(options) or '(none — no pipeline is known yet)'}.",
        )

    runner, routed_ctx, store = await _prepared_runner(
        registry=registry, catalogue=catalogue, ctx=ctx, llm=llm, services=services, sink=sink
    )
    query = Query(text=question)
    query_set = QuerySet(origin=query, queries=(query,))
    answer = await _run_pipeline(
        target,
        query_set,
        registry=registry,
        runner=runner,
        ctx=routed_ctx,
        store=store,
        catalogue=catalogue,
        contributions=contributions,
    )
    return _require(
        answer,
        Answer,
        pipeline=pipeline_name,
        produced_by="`weft ask`",
        alternatives=pipelines_producing(Generator, catalogue=catalogue, registry=registry),
    )


async def _prepared_runner(
    *,
    registry: Registry,
    catalogue: dict[str, Pipeline],
    ctx: Context,
    llm: LLMSection,
    services: ServiceSelection,
    sink: TokenSink,
) -> tuple[Runner, Context, object]:
    """The setup `run_routed_ask` and `run_named_ask` share: the assembled service
    registry, a `Context` carrying it, a `Runner`, and the resolved `NodeStore` both
    functions' own two `_run_pipeline` calls need. Factored out once a second caller
    existed (task 3.11) rather than duplicated — the identical "one code path, not two"
    reasoning `weft_cli.commands._raise_for_plugin_refusal`'s own docstring states.
    """
    service_registry = await build_services(
        registry=registry, catalogue=catalogue, llm=llm, services=services, sink=sink
    )
    routed_ctx = replace(ctx, services=service_registry)
    runner = Runner(registry)
    store = service_registry.resolve(NodeStore)
    return runner, routed_ctx, store


async def _run_pipeline(
    pipeline: Pipeline,
    payload: object,
    *,
    registry: Registry,
    runner: Runner,
    ctx: Context,
    store: object,
    catalogue: Mapping[str, Pipeline],
    contributions: tuple[Contribution, ...] = (),
) -> object:
    """Resolve `pipeline` and run it — `catalogue`, added as a **repair**, is `resolve()`'s
    own `parents` lookup, not a one-entry `{pipeline.name: pipeline}` mapping: a derived
    pipeline's `extends:` names an ancestor, and a mapping holding only the named pipeline
    itself has no ancestor for `resolve()` to find, so every derived pipeline reached through
    `weft ask --pipeline`/the router failed `UnknownParentPipelineError` outright — found by
    running `weft eval run` over a real `weft pipeline derive`d document (task 4.6); see
    `weft_cli.ingest._specs_from_document`'s own docstring for the parallel repair and the
    full argument. Both callers already build the full catalogue for their own lookups, so
    this costs nothing beyond passing it one call further.

    `contributions` — task **5.3a** (`S8`) — is `weft_cli.registry_bootstrap.Dependencies.
    contributions`, threaded down from `run_routed_ask`/`run_named_ask`, on the identical
    footing `catalogue` already is: one caller assembles it, every `resolve()` call site
    receives it unchanged.
    """
    contracts = contracts_for(
        pipeline, registry=registry, parents=catalogue, contributions=contributions
    )
    resolved = resolve(
        pipeline,
        registry=registry,
        contracts=contracts,
        parents=catalogue,
        contributions=contributions,
    )
    specs = to_specs(resolved, registry=registry)
    check_store_capabilities(
        specs,
        registry=registry,
        store=store,
        store_contract=NodeStore,
        store_name=type(store).__name__,
        pipeline=pipeline.name,
    )
    runnable = runner.resolve(specs, tenant_id=ctx.tenant_id)
    outcome = await runner.run_once(runnable, payload, ctx)
    if not isinstance(outcome, Produced):
        raise PipelineDidNotProduceError(
            f"pipeline '{pipeline.name}' did not produce: {outcome.reason}",
            pipeline=pipeline.name,
        )
    return outcome.value
