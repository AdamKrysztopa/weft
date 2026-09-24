"""Resolve a pipeline through the real router, then run it — `weft ask`'s own default path.

Task **2.8**. `.phase2-design.md` §5, read literally: "`weft ask` runs `route` through
`run_once`, gets a `Route`, looks `Route.pipeline` up in the pipeline catalogue, resolves
it, and runs it. **Selection is pipeline selection, never dispatch.**" This module is
that walk. 2.8 shipped it behind a new, *additive* command, `weft route`, rather than as a
rewrite of `weft ask` — Phase 0's own documented, tested, retrieve-only contract was left
untouched deliberately, because rewriting it was a bigger, separate risk than 2.8's own —
and named the gap explicitly rather than closing it by silence (`docs/internal/build-ledger.md`'s
2.25 note). **Task 3.11 is that gap closed**: `weft route` is retired, and
`weft_cli.commands.AskCommand` calls `run_routed_ask` below directly, so the question a
user asks reaches the pipeline the router names with no second command to learn. `weft_cli.
ask.run_ask` — the direct embed-and-search call this module never touches — survives as
`weft ask --retrieve-only`, Phase 0's own contract kept reachable for a caller (a script, a
deterministic baseline measurement) that genuinely wants no router and no model call; see
`docs/internal/build-ledger.md`'s 3.11 entry for the argument in full.

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
`weft_engine.services.DEFAULT_ROUTER` carries the argument, and the two registered routing
policies that were unreachable because of it are the evidence.

`weft_engine.run_services.check_store_capabilities` runs once per resolved pipeline,
immediately before that pipeline's own `run_once` call — see `weft_engine.run_services`'s
own module docstring for why that check is not inside `build_services` itself.
`check_selected_capabilities` — ledger task **11.10** — runs immediately after it, in the
same window: `needs_store` is answered against the one configured `[services] store`, but a
retriever needing a capability *no store advertises* — a traversal, say — can only be answered
against the whole selected `[services]` set, and
had no caller until this task built `weft_engine.run_services.demanded_capabilities`, the map from
the resolved `StageSpec` list this check needs. Both checks need the identical two things
`build_services` already builds and this module used to drop: the `RoleTable` and the raw
`selected_role_instances` mapping, which `_prepared_runner` now threads out to `_run_pipeline`
rather than a second call rebuilding either — building a selected role's plugin twice per run
could disagree with the one instance the `ServiceRegistry` actually holds.

**`run_named_ask`, task 3.11 — the same walk, minus the router.** `weft ask <question>
--pipeline <name>` is what a caller who wants a *specific* pipeline uses now that `weft
route` has been folded into `ask` (`docs/internal/build-ledger.md`'s 3.11 entry has the surface
argument in full): this function skips `route.yaml` entirely and resolves `pipeline_name`
straight against `weft_cli.pipeline_catalogue.full_catalogue` — project-local documents
*and* every installed pack's own contribution, **the same catalogue `run_routed_ask` now
builds since ledger task 8.12** — naming a pipeline by hand is exactly the case a
project-local document scaffolded by `weft pipeline derive` and never published as a pack
should be reachable from, and so is naming one as the router: the narrower,
contributed-only search set the router used to have was a Phase 2 implementation gap
carried forward, never a trust boundary, and 8.12 closed it. `_prepared_runner` below is
the setup the two functions share — `build_services`, the routed `Context`, the `Runner`
and the resolved store — factored out once both existed, rather than a second copy of
`run_routed_ask`'s own first half.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace

from weft_cli.closing import CloseTarget, close_each
from weft_cli.compile import RefusedStagePluginError, contracts_for, to_specs
from weft_cli.pipeline_catalogue import (
    DEFAULT_PIPELINES_DIR,
    UnknownPipelineNameError,
    full_catalogue,
)
from weft_embed import Embedder
from weft_engine.llm_roles import LLMSection
from weft_engine.run_services import (
    build_services,
    check_selected_capabilities,
    check_store_capabilities,
    demanded_capabilities,
    selected_role_instances,
)
from weft_engine.service_roles import RoleTable
from weft_engine.services import DEFAULT_ROUTER, ServiceSelection
from weft_generate.contract import Generator
from weft_generate.payload import Answer
from weft_kernel.context import Context
from weft_kernel.discovery import PackReport
from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_kernel.payload import Produced
from weft_kernel.pipeline import Pipeline
from weft_kernel.registry import Registry
from weft_kernel.resolution import Contribution, ResolvedPipeline, resolve
from weft_kernel.runner import PipelineResolutionError, Runner, StageSpec
from weft_llm.contract import LLMProvider, TokenSink
from weft_retrieve.contract import RoutingPolicy
from weft_retrieve.engine import roles_needed, route_catalogue
from weft_retrieve.payload import Passages, Query, QuerySet, Ranking, Route
from weft_store import NodeStore

#: `route.yaml`'s own `name:` field, and **the default rather than the law** since ledger task
#: **8.3**. It was a module constant until then, and `weft_engine.services.DEFAULT_ROUTER` — where
#: it now lives as `[services] route`'s default — carries the argument for the change in full:
#: a hard-coded router name is the one privileged pipeline in the tree, because no second
#: document can take the name and no project may declare it either. This alias stays so the
#: name a reader greps for still resolves; `run_routed_ask` reads `services.route`.
ROUTE_PIPELINE_NAME = DEFAULT_ROUTER

#: `run_routed_ask`/`run_named_ask`/`_prepared_runner`'s own default for their new `roles`
#: parameter (ledger task **9.0**) — a module-level singleton, never `RoleTable()` written
#: inline in a signature, because ruff's B008 refuses a function call in a default argument's
#: position regardless of the type being frozen. Empty and selects nothing, which is exactly
#: today's behaviour for a caller that names none — `weft_cli.eval_scoring`'s own
#: `run_named_ask` call, which holds no `Dependencies` to read a real one from.
_NO_ROLES: RoleTable = RoleTable()


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


class NoRungOfferedError(WeftError):
    """Every rung the router could offer needs a model role `[llm.roles]` does not map —
    carried repair **R43.30**. Raised before any model call, so the router is never paid to
    choose between nothing; the message names each missing role and the rungs it would restore.
    """


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
    roles: RoleTable = _NO_ROLES,
    target: str | None = None,
    ready_layers: frozenset[str] | None = None,
) -> tuple[str, Answer]:
    """Route `question` through the real router, run whichever pipeline it selects, and
    return `(the pipeline name selected, the Answer it produced)`.

    Raises `NoRouterPipelineError` if no installed pack contributed `route.yaml`;
    `UnroutedPipelineNameError` if a `RoutingPolicy` names a pipeline the catalogue does
    not hold; `weft_engine.run_services.StoreCapabilityMissingError` if either resolved
    pipeline needs a store capability `[services] store` does not provide; any
    `weft_kernel.runner.PipelineResolutionError` a malformed document or a name nothing
    registered raises, from either resolution. Every one of these is a `WeftError` a
    caller maps to an exit code exactly the way `weft_cli.cli.handle_ask` already does.

    `sink` — task **3.6** — is the `TokenSink` the generating stage streams into, threaded
    straight through to `build_services`; `weft_cli.commands.AskCommand.run` passes
    `Dependencies.token_sink`, the sink `weft_cli.cli.main` chose from `--json`/`--quiet`.
    This is `weft ask`'s own default, router-driven path since task **3.11** folded the
    formerly-separate `weft route` command into it — `docs/internal/build-ledger.md`'s 3.11 entry
    has the surface argument; this function's own resolution behaviour is untouched, Phase
    2's settled work.

    `contributions` — task **5.3a** (`S8`) — reaches both of this function's own two
    `_run_pipeline` calls (the router's own resolution, and whichever pipeline it selects),
    on the identical footing `weft_cli.pipeline_commands._resolved_or_refuse` and
    `weft_cli.ingest._specs_from_document` already receive it.

    `roles` — ledger task **9.0** — is `weft_engine.registry_bootstrap.Dependencies.roles`,
    threaded straight through to `_prepared_runner`'s own `build_services` call. Defaults to
    `_NO_ROLES` (empty), so `weft_cli.eval_scoring`'s own call — which holds no `Dependencies`
    to read a real one from — keeps registering exactly today's set.

    `target` — ledger task **34.6** — reaches `_prepared_runner`'s own `build_services` call
    unchanged; `None` (every caller before this task) reads the live target. `ready_layers`
    — ledger task **43.9** — reaches it the same way, so the router never offers a rung whose
    `route.requires` layer is not built everywhere.

    **Roles, before any model call — carried repair R43.30.** A role the router itself calls
    under that `[llm.roles]` does not map raises `weft_llm.roles.UnmappedLLMRoleError`; a rung
    needing one is left out of the router's candidates, and `NoRungOfferedError` is raised when
    that leaves none. Both before `_prepared_runner` builds anything.

    **Closes what it built — repair R38.6.** The store and embedder `_prepared_runner` builds
    for this call are closed before returning, success or error, through
    `weft_cli.closing.close_each`: this function is `weft ask`'s own default path, and every
    turn of the REPL calls it again, so a store built here and never closed held one Postgres
    connection per turn until the process exited.
    """
    catalogue = full_catalogue(reports=reports)
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

    rung_roles = _offerable_rung_roles(
        router,
        catalogue=catalogue,
        registry=registry,
        reports=reports,
        contributions=contributions,
        llm=llm,
        ready_layers=ready_layers,
    )
    built = await _prepared_runner(
        registry=registry,
        catalogue=catalogue,
        ctx=ctx,
        llm=llm,
        services=services,
        sink=sink,
        roles=roles,
        target=target,
        ready_layers=ready_layers,
        rung_roles=rung_roles,
    )
    in_flight: BaseException | None = None
    try:
        query = Query(text=question)
        route = await _run_pipeline(
            router,
            query,
            sink=sink,
            registry=registry,
            runner=built.runner,
            ctx=built.ctx,
            store=built.store,
            store_name=services.store,
            table=built.table,
            selected=built.selected,
            names=services.roles,
            catalogue=catalogue,
            reports=reports,
            contributions=contributions,
            entry_type=Query,
        )
        route = _require(route, Route, pipeline=router_name, produced_by="routing")

        selected_pipeline = catalogue.get(route.pipeline)
        if selected_pipeline is None:
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
            selected_pipeline,
            query_set,
            sink=sink,
            entry_type=QuerySet,
            registry=registry,
            runner=built.runner,
            ctx=built.ctx,
            store=built.store,
            store_name=services.store,
            table=built.table,
            selected=built.selected,
            names=services.roles,
            catalogue=catalogue,
            reports=reports,
            contributions=contributions,
        )
        answer = _require(
            answer,
            Answer,
            pipeline=route.pipeline,
            produced_by="`weft ask`",
            alternatives=pipelines_producing(Generator, catalogue=catalogue, registry=registry),
        )
    except BaseException as failure:
        in_flight = failure
        raise
    finally:
        await close_each(built.close_targets, in_flight=in_flight)
    return route.pipeline, answer


class PipelineProducedTheWrongShapeError(WeftError):
    """A pipeline ran to completion and its last stage produced something else — task **6.25**.

    **This replaces three bare `assert isinstance(...)` calls, and the comment on two of them is
    why.** They read `# every shipped routable pipeline ends in a Generator` — an "every X" stated
    over what *this repository ships*, checked against pipeline documents **anyone may write**.
    `docs/internal/lessons.md` L6.15: an invariant's scope is the inputs that actually reach it, not
    the ones its comment names. A three-line user pipeline ending in a retriever made it fail with
    no message at all, which is how it was found (`weft ask --pipeline <name>`, ledger task 6.21's
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
    alternatives at all — an empty answer read as "there are none" when it meant "I asked the wrong
    question" (`docs/internal/lessons.md` L5.9), and it was caught by running the binary rather than
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
    `docs/internal/lessons.md` L5.10, and L6.13's *"a repair specified from one failing instance
    narrows to that instance"*. `tests/architecture/test_ff7_colour_integrity.py`'s sibling check
    keeps a new bare `assert` from reappearing in shipped code.
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


def named_pipeline(pipeline_name: str, *, catalogue: Mapping[str, Pipeline]) -> Pipeline:
    """`pipeline_name` looked up in `catalogue`, or `UnknownPipelineNameError` naming every
    pipeline the catalogue does hold.

    Lifted out of `run_named_ask` at task **16.1** so `resolve_named_pipeline` refuses the
    identical way rather than growing a second, divergent "name not found" message — the same
    "one code path, not two" footing `weft_cli.commands._raise_for_plugin_refusal`'s own
    docstring already states.
    """
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
    return target


def resolve_named_pipeline(
    pipeline_name: str,
    *,
    registry: Registry,
    reports: Sequence[PackReport],
    contributions: tuple[Contribution, ...] = (),
) -> ResolvedPipeline:
    """What `run_named_ask` will resolve `pipeline_name` to — `full_catalogue`, the same
    lookup, the same `resolve_in_catalogue`. Pure: `resolution.py:783 "Pure and det"` is data
    manipulation over already-parsed structures, so this does no I/O and runs nothing.
    """
    catalogue = full_catalogue(reports=reports)
    target = named_pipeline(pipeline_name, catalogue=catalogue)
    return resolve_in_catalogue(
        target,
        registry=registry,
        catalogue=catalogue,
        reports=reports,
        contributions=contributions,
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
    roles: RoleTable = _NO_ROLES,
    prepared: PreparedRunner | None = None,
    target: str | None = None,
) -> Answer:
    """Run `pipeline_name` directly against `question`, bypassing the router entirely.

    Task **3.11**'s own answer to "what does a caller who wants a specific pipeline use":
    `weft ask <question> --pipeline <name>`, never a second command. Resolved against
    `weft_cli.pipeline_catalogue.full_catalogue` — project-local documents *and* every
    installed pack's own contribution, the identical set `weft pipeline show/validate/diff/
    derive` resolve names against, and, since ledger task **8.12**, the identical set
    `run_routed_ask` resolves `[services] route` against too: a pipeline scaffolded by
    `weft pipeline derive` and never published as a pack is reachable the moment it
    validates, whether it is named by hand here or named as the router.

    Raises `weft_cli.pipeline_catalogue.UnknownPipelineNameError` if `pipeline_name` is not
    in the catalogue — reused rather than duplicated, on `weft_cli.commands.
    _raise_for_plugin_refusal`'s own "one code path, not two" footing: that class's own
    docstring already covers "a bare name a person typed at the command line", which is
    exactly what this is, one caller further than the four `weft pipeline` commands that
    established it. `weft_engine.run_services.StoreCapabilityMissingError` and any
    `weft_kernel.runner.PipelineResolutionError` propagate unchanged, the same set
    `run_routed_ask` documents for its own second resolution.

    `contributions` — task **5.3a** (`S8`) — reaches `_run_pipeline` below on the identical
    footing `run_routed_ask` already passes it through.

    `roles` — ledger task **9.0** — the identical parameter `run_routed_ask` documents for
    itself, threaded through to `_prepared_runner` the same way.

    **`prepared` — repair R38.6.** `None` (the default) is `weft ask`/the REPL's own shape:
    this call builds its own `PreparedRunner` and closes it before returning, success or
    error, through `weft_cli.closing.close_each` — no store or embedder this function
    opens outlives the call that opened it. A caller scoring many questions through one rung
    (`weft_cli.eval_scoring.score_pipeline`) instead builds one with
    `weft_cli.route_ask.prepared_services` and passes it here for every question; this
    function then builds nothing of its own and closes nothing — the `async with` block that
    built it owns that, once, for the whole run.

    `target` — ledger task **34.6** — reaches `_prepared_runner`'s own `build_services` call
    when this function builds its own `PreparedRunner` (`prepared is None`); ignored when a
    caller already built one, since that one's store is already bound to whatever `target` it
    was given.
    """
    catalogue = full_catalogue(reports=reports)
    pipeline_doc = named_pipeline(pipeline_name, catalogue=catalogue)
    owns = prepared is None
    built = (
        prepared
        if prepared is not None
        else await _prepared_runner(
            registry=registry,
            catalogue=catalogue,
            ctx=ctx,
            llm=llm,
            services=services,
            sink=sink,
            roles=roles,
            target=target,
        )
    )
    in_flight: BaseException | None = None
    try:
        query = Query(text=question)
        query_set = QuerySet(origin=query, queries=(query,))
        answer = await _run_pipeline(
            pipeline_doc,
            query_set,
            sink=sink,
            entry_type=QuerySet,
            registry=registry,
            runner=built.runner,
            ctx=built.ctx,
            store=built.store,
            store_name=services.store,
            table=built.table,
            selected=built.selected,
            names=services.roles,
            catalogue=catalogue,
            reports=reports,
            contributions=contributions,
        )
    except BaseException as failure:
        in_flight = failure
        raise
    finally:
        if owns:
            await close_each(built.close_targets, in_flight=in_flight)
    return _require(
        answer,
        Answer,
        pipeline=pipeline_name,
        produced_by="`weft ask`",
        alternatives=pipelines_producing(Generator, catalogue=catalogue, registry=registry),
    )


async def run_named_retrieve(
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
    roles: RoleTable = _NO_ROLES,
    prepared: PreparedRunner | None = None,
    target: str | None = None,
) -> Passages:
    """`run_named_ask`'s retrieval-only twin — repair **R21.5**.

    Same resolution (`full_catalogue`, `named_pipeline`), the same assembled services
    (`_prepared_runner`), the same execution (`_run_pipeline`) — the only difference is
    where it stops: `run_named_ask` requires an `Answer` at the end and this requires
    `Passages`, through the identical `_require` seam, so a pipeline that ends in a
    `Generator` is refused by the same message `run_named_ask` already gives a pipeline
    that ends in a retriever, read the other way round. `weft_cli.commands.AskCommand.run`
    is expected to have already refused a pipeline ending in a `Generator` by name, before
    ever calling this — the `_require` refusal here exists for the pipeline that ends
    in neither, not as this function's primary defence.

    `--retrieve-only --pipeline <name>` is the caller: a named pipeline, run through to
    whatever it produces, with no router and no `Answer` — this is `weft ask
    --retrieve-only`'s own "no model call" contract, extended to a caller who wants a
    *specific* retrieval pipeline rather than the hardwired vector search
    `weft_cli.ask.run_ask` performs.

    **`prepared` — repair R38.6.** `run_named_ask`'s own docstring states the rule in full:
    `None` builds a `PreparedRunner` here and closes it before returning, whatever a caller
    already built through `weft_cli.route_ask.prepared_services` is used and left for that
    caller to close.

    `target` — ledger task **34.6** — `run_named_ask`'s own docstring states the rule: reaches
    `_prepared_runner`'s own `build_services` call when this function builds its own
    `PreparedRunner`, ignored when a caller already built one.
    """
    catalogue = full_catalogue(reports=reports)
    pipeline_doc = named_pipeline(pipeline_name, catalogue=catalogue)
    owns = prepared is None
    built = (
        prepared
        if prepared is not None
        else await _prepared_runner(
            registry=registry,
            catalogue=catalogue,
            ctx=ctx,
            llm=llm,
            services=services,
            sink=sink,
            roles=roles,
            target=target,
        )
    )
    in_flight: BaseException | None = None
    try:
        query = Query(text=question)
        query_set = QuerySet(origin=query, queries=(query,))
        result = await _run_pipeline(
            pipeline_doc,
            query_set,
            sink=sink,
            entry_type=QuerySet,
            registry=registry,
            runner=built.runner,
            ctx=built.ctx,
            store=built.store,
            store_name=services.store,
            table=built.table,
            selected=built.selected,
            names=services.roles,
            catalogue=catalogue,
            reports=reports,
            contributions=contributions,
        )
    except BaseException as failure:
        in_flight = failure
        raise
    finally:
        if owns:
            await close_each(built.close_targets, in_flight=in_flight)
    return _require(
        result,
        Passages,
        pipeline=pipeline_name,
        produced_by="`weft ask --retrieve-only`",
    )


@dataclass(frozen=True, slots=True)
class PreparedRunner:
    """One run's assembled services — repair **R38.6**: what `_prepared_runner` built, and
    what closes it. `runner`, `ctx`, `store`, `table` and `selected` are exactly the five
    values `_prepared_runner` returned before this repair; `close_targets` is new, and is
    the only reason this is a dataclass rather than the bare tuple it replaces.
    """

    runner: Runner
    ctx: Context
    store: object
    table: RoleTable
    selected: Mapping[str, object]
    close_targets: tuple[CloseTarget, ...] = ()


def _close_targets(
    *,
    registry: Registry,
    services: ServiceSelection,
    roles: RoleTable,
    role_instances: Mapping[str, object],
    store: object,
    embedder: object,
) -> tuple[CloseTarget, ...]:
    """Every instance `_prepared_runner` itself built from `registry`, in the reverse of the
    order it built them — repair **R38.6**.

    `weft_kernel.seam.aclose` already no-ops on an instance carrying no `aclose`, so nothing
    here is checked twice for that; this only has to say which distribution and plugin each
    one came from, the identical attribution `weft_cli.ask.run_ask`'s own `close_each` call
    already gives the one embedder it builds. `registry.entry(...)` is a lookup, not a second
    construction — the instances themselves are the ones `build_services`/
    `selected_role_instances` already built, passed in rather than rebuilt.

    Construction order was roles, then the store, then the embedder (`build_services`'s own
    body registers `NodeStore` before `Embedder`); closing undoes that, embedder first.
    """
    targets = [
        CloseTarget(
            instance=embedder,
            distribution=registry.entry(Embedder, services.embed).distribution,
            contract=Embedder.__name__,
            plugin=services.embed,
            stage="prepared:embed",
        ),
        CloseTarget(
            instance=store,
            distribution=registry.entry(NodeStore, services.store).distribution,
            contract=NodeStore.__name__,
            plugin=services.store,
            stage="prepared:store",
        ),
    ]
    for key in reversed(tuple(role_instances)):
        role = roles.roles[key]
        targets.append(
            CloseTarget(
                instance=role_instances[key],
                distribution=registry.entry(role.contract, services.roles[key]).distribution,
                contract=role.contract.__name__,
                plugin=services.roles[key],
                stage=f"prepared:{key}",
            )
        )
    return tuple(targets)


async def _prepared_runner(
    *,
    registry: Registry,
    catalogue: dict[str, Pipeline],
    ctx: Context,
    llm: LLMSection,
    services: ServiceSelection,
    sink: TokenSink,
    roles: RoleTable = _NO_ROLES,
    target: str | None = None,
    ready_layers: frozenset[str] | None = None,
    rung_roles: Mapping[str, frozenset[str]] | None = None,
) -> PreparedRunner:
    """The setup `run_routed_ask` and `run_named_ask` share: the assembled service
    registry, a `Context` carrying it, a `Runner`, and the resolved `NodeStore` both
    functions' own two `_run_pipeline` calls need. Factored out once a second caller
    existed (task 3.11) rather than duplicated — the identical "one code path, not two"
    reasoning `weft_cli.commands._raise_for_plugin_refusal`'s own docstring states.

    `roles` — ledger task **9.0** — reaches `build_services` unchanged; both callers document
    it for themselves.

    **The last two — ledger task 11.10.** `roles` itself, and the raw `selected_role_instances`
    mapping, both used to be received here and dropped: nothing downstream of this function
    needed either before `check_selected_capabilities` existed. Now both do — `_run_pipeline`
    needs the `RoleTable` to turn a demanded capability back into role keys a caller could
    select, and the selected instances to ask whether one of them actually provides it. The
    mapping is built **once**, here, before `build_services` is called, and handed into it as
    `role_instances` rather than left for `build_services` to build its own copy: constructing
    a selected role's plugin twice per run is not acceptable, and a second construction could
    disagree with the one instance the `ServiceRegistry` this function returns actually holds
    — which would make the capability check answer about a different object than the run uses.

    **`close_targets` — repair R38.6.** Every caller of this function used to keep what it
    built for the rest of its own body and never close any of it — `PgVectorStore` opens one
    Postgres connection per instance and releases it only in `aclose`, so a store built here
    and never closed held its connection until the garbage collector happened by. This
    function still builds; it is now also the one place that knows what it built and what to
    close, so a caller closes through `PreparedRunner.close_targets` rather than each
    reconstructing that list from `registry`/`services`/`roles` itself.

    `target` — ledger task **34.6** — reaches `build_services` unchanged; `None` (every
    caller before this task) reads the live target.

    `ready_layers` — ledger task **43.9** — reaches `build_services` unchanged; `None`
    (every caller before this task) offers every candidate the catalogue holds. `rung_roles`
    — carried repair **R43.30** — reaches it the same way.
    """
    role_instances = selected_role_instances(registry=registry, services=services, table=roles)
    service_registry = await build_services(
        registry=registry,
        catalogue=catalogue,
        llm=llm,
        services=services,
        sink=sink,
        roles=roles,
        role_instances=role_instances,
        target=target,
        ready_layers=ready_layers,
        rung_roles=rung_roles,
    )
    routed_ctx = replace(ctx, services=service_registry)
    runner = Runner(registry)
    store = service_registry.resolve(NodeStore)
    embedder = service_registry.resolve(Embedder)
    return PreparedRunner(
        runner=runner,
        ctx=routed_ctx,
        store=store,
        table=roles,
        selected=role_instances,
        close_targets=_close_targets(
            registry=registry,
            services=services,
            roles=roles,
            role_instances=role_instances,
            store=store,
            embedder=embedder,
        ),
    )


@asynccontextmanager
async def prepared_services(
    *,
    registry: Registry,
    reports: Sequence[PackReport],
    ctx: Context,
    llm: LLMSection,
    services: ServiceSelection,
    sink: TokenSink,
    roles: RoleTable = _NO_ROLES,
    target: str | None = None,
) -> AsyncGenerator[PreparedRunner]:
    """One run's assembled services, built once and closed once — repair **R38.6**'s public
    seam for a caller that runs many questions through the same rung.

    `weft_cli.eval_scoring.score_pipeline` is that caller: scoring a query rung over a whole
    question set used to call `run_named_retrieve` once per question, and each call built and
    never closed its own `NodeStore`/`Embedder` — a store's first search provisions its
    schema, so a per-question store also put that DDL and a connection handshake inside every
    question's recorded seconds, and `weft eval experiment`'s hybrid arm exhausted a
    100-connection server partway through its first record. `async with prepared_services(...)
    as prepared:` builds once, and closes on the way out — success or error — through
    `weft_kernel.seam.aclose`, exactly as `weft_engine.api.Weft.__aexit__` closes what a
    session held. A caller inside the block passes the yielded `PreparedRunner` as
    `run_named_ask`/`run_named_retrieve`'s own `prepared` keyword; both then build nothing and
    close nothing of their own.

    `target` — ledger task **34.6** — reaches `_prepared_runner` unchanged; `None` (every
    caller before this task) reads the live target.
    """
    catalogue = full_catalogue(reports=reports)
    built = await _prepared_runner(
        registry=registry,
        catalogue=catalogue,
        ctx=ctx,
        llm=llm,
        services=services,
        sink=sink,
        roles=roles,
        target=target,
    )
    in_flight: BaseException | None = None
    try:
        yield built
    except BaseException as failure:
        in_flight = failure
        raise
    finally:
        await close_each(built.close_targets, in_flight=in_flight)


def show_only_the_answering_stage(specs: Sequence[StageSpec], *, sink: TokenSink) -> None:
    """Tell `sink` which stage produces the answer, so nothing else interleaves with it.

    **Carried repair `R10.1`.** A sink filters on `TokenChunk.role`, and a role names a *model
    mapping* — so two stages calling a model on the answering role are one thing to it. The
    first pipeline with a concurrent query-time summariser printed five cluster summaries
    interleaving word by word above an answer that was itself correct, on a run whose
    configuration was right (`10.15`, found by running the binary). The last stage is the one
    whose output is returned, so it is the one a reader is waiting for.

    **Reached by `getattr`, deliberately.** `show_only_stage` is not on `weft_llm.contract.
    TokenSink` and must not be: adding a method to a published contract breaks every
    implementation at once, first- and third-party alike (`09` §3, G9's *Bring* list). This is a
    convenience `weft-cli`'s own two sinks offer; a pack's own sink that does not is simply not
    told, and behaves exactly as every sink did before this repair.

    An empty `specs` tells the sink nothing rather than naming a stage that does not exist —
    `Runner.resolve` already refuses to build a pipeline out of one, so this is defensive
    rather than reachable, and *saying so* is cheaper than a reader wondering.
    """
    if not specs:
        return
    narrow = getattr(sink, "show_only_stage", None)
    if narrow is not None:
        narrow(specs[-1].id)


def resolve_in_catalogue(
    pipeline: Pipeline,
    *,
    registry: Registry,
    catalogue: Mapping[str, Pipeline],
    reports: Sequence[PackReport],
    contributions: tuple[Contribution, ...] = (),
) -> ResolvedPipeline:
    """`pipeline` resolved against `catalogue` — the one composition every run of a named
    pipeline goes through, and therefore the one an identity may be computed from.

    Lifted out of `_run_pipeline` at task **16.1** rather than copied: a record that named a
    rung by an identity computed from a *second* resolution would be making a claim about a
    resolution no question ran under, and two pure functions agreeing today is not the same
    fact as one function answering both.
    """
    contracts = contracts_for(
        pipeline, registry=registry, parents=catalogue, reports=reports, contributions=contributions
    )
    return resolve(
        pipeline,
        registry=registry,
        contracts=contracts,
        parents=catalogue,
        contributions=contributions,
    )


def routable_rung_roles(
    catalogue: Mapping[str, Pipeline],
    *,
    registry: Registry,
    reports: Sequence[PackReport],
    contributions: tuple[Contribution, ...] = (),
) -> dict[str, frozenset[str]]:
    """Every document carrying `route.summary`, to the roles its resolved form calls a model
    under (`weft_retrieve.engine.roles_needed`) — carried repair **R43.30**. Resolved through
    `resolve_in_catalogue`, so a derived rung's `replace`/`set` count.

    A document that does not resolve here is left out of the mapping, so no role filter
    applies to it and it is offered exactly as before this repair: its own resolution error is
    raised, by name, if the router selects it.
    """
    rung_roles: dict[str, frozenset[str]] = {}
    for name, pipeline in sorted(catalogue.items()):
        if "route.summary" not in pipeline.vars:
            continue
        try:
            resolved = resolve_in_catalogue(
                pipeline,
                registry=registry,
                catalogue=catalogue,
                reports=reports,
                contributions=contributions,
            )
        except (PipelineResolutionError, RefusedStagePluginError):
            continue
        rung_roles[name] = roles_needed(resolved, registry)
    return rung_roles


def _offerable_rung_roles(
    router: Pipeline,
    *,
    catalogue: Mapping[str, Pipeline],
    registry: Registry,
    reports: Sequence[PackReport],
    contributions: tuple[Contribution, ...],
    llm: LLMSection,
    ready_layers: frozenset[str] | None,
) -> dict[str, frozenset[str]]:
    """`routable_rung_roles`, once the router's own roles are mapped and at least one rung
    survives the role filter — `run_routed_ask`'s two up-front refusals, carried repair
    **R43.30**.
    """
    resolved_router = resolve_in_catalogue(
        router, registry=registry, catalogue=catalogue, reports=reports, contributions=contributions
    )
    providers = tuple(sorted(registry.names_for(LLMProvider)))
    for role in sorted(roles_needed(resolved_router, registry)):
        llm.roles.resolve(role, providers=providers)
    rung_roles = routable_rung_roles(
        catalogue, registry=registry, reports=reports, contributions=contributions
    )
    mapped = frozenset(llm.roles.roles)
    offered = route_catalogue(catalogue, ready_layers, rung_roles=rung_roles, mapped_roles=mapped)
    missing = offered.missing_roles()
    if missing and not offered.candidates():
        needed = sorted({role for roles in missing.values() for role in roles})
        rungs = "; ".join(
            f"'{name}' needs {', '.join(repr(role) for role in roles)}"
            for name, roles in missing.items()
        )
        raise NoRungOfferedError(
            f"the router has no rung to offer: every routable pipeline needs a model role "
            f"[llm.roles] does not map — {rungs}. Roles mapped in weft.toml: "
            f"{', '.join(sorted(mapped)) or '(none mapped)'}. Map "
            f"{', '.join(repr(role) for role in needed)} under [llm.roles], or ask with "
            f"--pipeline <name>."
        )
    return rung_roles


async def _run_pipeline(
    pipeline: Pipeline,
    payload: object,
    *,
    sink: TokenSink,
    registry: Registry,
    runner: Runner,
    ctx: Context,
    store: object,
    store_name: str,
    table: RoleTable,
    selected: Mapping[str, object],
    names: Mapping[str, str],
    catalogue: Mapping[str, Pipeline],
    reports: Sequence[PackReport],
    contributions: tuple[Contribution, ...] = (),
    entry_type: type[object] | None = None,
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

    `contributions` — task **5.3a** (`S8`) — is `weft_engine.registry_bootstrap.Dependencies.
    contributions`, threaded down from `run_routed_ask`/`run_named_ask`, on the identical
    footing `catalogue` already is: one caller assembles it, every `resolve()` call site
    receives it unchanged.

    `entry_type` — ledger **8.18** — is what `payload` will be once execution reaches this
    pipeline's first stage, so `weft_kernel.runner.Runner.resolve` can refuse a document
    whose first stage cannot accept it before anything runs, naming the stage and the
    mismatch by type rather than surfacing as an `AttributeError` mid-run. Defaulted to
    `None` because a caller that does not know what it is handing over must not guess — but
    **every caller in this module does know, and all three now say so.** The router's own
    resolution passes `Query`; `run_named_ask` and the router's selected-pipeline call each
    construct the `QuerySet` on the line above and pass `QuerySet`.

    **This paragraph used to claim the opposite** — *"every other call keeps making none"* — and
    that was a statement about two call sites, written at the one being edited, which is `L6.13`
    exactly: a repair specified from one failing instance narrows to that instance. It was
    falsified in one command at Phase 8's close review: `weft ask "..." --pipeline route` died with
    `'QuerySet' object has no attribute 'text'` and exit `1`, while the routed path refused the
    same mistake by name at exit `4`. The default stays for a genuine stranger; it is no longer
    the answer any first-party caller gives.

    **`store_name`, `table`, `selected`, `names` — ledger task 11.10.** `store_name` is the
    configured `[services] store` plugin name, not `type(store).__name__` — this call used to
    pass the latter, which is the live defect `weft_engine.run_services.
    SelectedCapabilityMissingError`'s own docstring names as `L9.26`: a refusal read *the
    configured store 'PgVectorStore'* while `[services] store` accepts `pgvector`, a remedy
    nobody could carry out. `table` and `selected` are `_prepared_runner`'s own `RoleTable` and
    raw `selected_role_instances` mapping, threaded through rather than rebuilt — see that
    function's own docstring for why a second build is not acceptable here. `names` is
    `services.roles`, the `[services]` key → configured plugin name mapping, so
    `check_selected_capabilities`'s own refusal can say what was configured rather than what
    class it turned into, the identical `L9.26` argument one layer over.

    `reports` — carried repair **R11.3**, required rather than defaulted — is threaded
    straight through to `contracts_for`/`to_specs` so a `use:` field this pipeline names
    that fails to resolve can be attributed to the pack that would have supplied it, the
    same reason `weft plugins doctor` already gives. Both callers already hold it
    (`run_routed_ask`, `run_named_ask`), so this costs nothing beyond passing it one call
    further.
    """
    resolved = resolve_in_catalogue(
        pipeline,
        registry=registry,
        catalogue=catalogue,
        reports=reports,
        contributions=contributions,
    )
    specs = to_specs(resolved, registry=registry, reports=reports)
    show_only_the_answering_stage(specs, sink=sink)
    check_store_capabilities(
        specs,
        registry=registry,
        store=store,
        store_contract=NodeStore,
        store_name=store_name,
        pipeline=pipeline.name,
    )
    check_selected_capabilities(
        demanded=demanded_capabilities(specs, registry=registry),
        selected=selected,
        table=table,
        names=names,
    )
    runnable = runner.resolve(specs, tenant_id=ctx.tenant_id, entry_type=entry_type)
    outcome = await runner.run_once(runnable, payload, ctx)
    if not isinstance(outcome, Produced):
        raise PipelineDidNotProduceError(
            f"pipeline '{pipeline.name}' did not produce: {outcome.reason}",
            pipeline=pipeline.name,
        )
    return outcome.value


async def run_named_rerank(
    ranking: Ranking,
    *,
    pipeline_name: str,
    registry: Registry,
    reports: Sequence[PackReport],
    ctx: Context,
    llm: LLMSection,
    services: ServiceSelection,
    sink: TokenSink,
    contributions: tuple[Contribution, ...] = (),
    roles: RoleTable = _NO_ROLES,
    prepared: PreparedRunner | None = None,
) -> Passages:
    """`run_named_retrieve`'s twin for a caller that already holds a `Ranking` — ledger task
    **40.2**'s second half: `weft_cli.eval_scoring.score_pipeline`'s pool-replay path hydrates a
    captured pool's own chunks into a `Ranking` itself, rather than a `Query`, so there is no
    `Query`/`QuerySet` construction here for a rung to resolve retrieval from — the entry payload
    is `ranking` itself, and `entry_type=Ranking` is what lets `weft_kernel.runner.Runner.resolve`
    refuse a document whose first stage cannot accept one, before anything runs, exactly as
    `run_named_ask`/`run_named_retrieve` already refuse a first stage that cannot accept a
    `QuerySet`.

    Same resolution, the same assembled services, the same execution and the same `_require`
    seam as `run_named_retrieve`: a pipeline that ends in anything other than a `ContextPacker`
    is refused by the identical message, read for `Passages` instead of `Ranking`.

    `prepared` — repair R38.6's own footing, restated here for a third caller: `None` builds a
    `PreparedRunner` here and closes it before returning; a caller scoring many questions through
    one rung builds one once through `weft_cli.route_ask.prepared_services` and passes it here,
    on the identical terms `run_named_ask`/`run_named_retrieve` already document for themselves.
    """
    catalogue = full_catalogue(reports=reports)
    pipeline_doc = named_pipeline(pipeline_name, catalogue=catalogue)
    owns = prepared is None
    built = (
        prepared
        if prepared is not None
        else await _prepared_runner(
            registry=registry,
            catalogue=catalogue,
            ctx=ctx,
            llm=llm,
            services=services,
            sink=sink,
            roles=roles,
        )
    )
    in_flight: BaseException | None = None
    try:
        result = await _run_pipeline(
            pipeline_doc,
            ranking,
            sink=sink,
            entry_type=Ranking,
            registry=registry,
            runner=built.runner,
            ctx=built.ctx,
            store=built.store,
            store_name=services.store,
            table=built.table,
            selected=built.selected,
            names=services.roles,
            catalogue=catalogue,
            reports=reports,
            contributions=contributions,
        )
    except BaseException as failure:
        in_flight = failure
        raise
    finally:
        if owns:
            await close_each(built.close_targets, in_flight=in_flight)
    return _require(
        result,
        Passages,
        pipeline=pipeline_name,
        produced_by="a pool replay",
    )
