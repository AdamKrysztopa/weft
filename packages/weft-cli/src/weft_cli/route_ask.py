"""`weft route <question>` — resolve a pipeline through the real router, then run it.

Task **2.8**. `.phase2-design.md` §5, read literally: "`weft ask` runs `route` through
`run_once`, gets a `Route`, looks `Route.pipeline` up in the pipeline catalogue, resolves
it, and runs it. **Selection is pipeline selection, never dispatch.**" This module is
that walk, as a new command rather than a rewrite of `weft ask` — `weft_cli.ask.run_ask`
keeps Phase 0's own documented contract (retrieve, print passages, generate nothing) so
`manual/quickstart.md` and every test that already drives it stay true; `weft route` is
the additive surface that makes the router reachable from the command line for real,
against the real, installed registry, rather than only from an architecture test.

**Two resolutions, not one.** `route.yaml` (`packages/weft-retrieve/src/weft_retrieve/
pipelines/route.yaml`, contributed by `weft-retrieve`'s own `register()`) is resolved and
run first, taking a bare `Query` and returning a `Route`. Whatever pipeline it names is
then resolved and run *second*, taking a `QuerySet` — the same two-step `.phase2-design.md`
§5 states, with `weft_cli.compile.contracts_for`/`to_specs` and `weft_kernel.runner.Runner`
doing the actual resolution and execution work for both, exactly as they would for any
other pipeline document. Neither resolution is special-cased: this module names no plugin
and no pipeline of its own beyond `route.yaml`'s own well-known name, and `route.yaml`'s
own name is the one exception a router has to have — something has to be the router.

`weft_cli.run_services.check_store_capabilities` runs once per resolved pipeline,
immediately before that pipeline's own `run_once` call — see `weft_cli.run_services`'s
own module docstring for why that check is not inside `build_services` itself.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from weft_cli.compile import contracts_for, to_specs
from weft_cli.llm_roles import LLMSection
from weft_cli.pipeline_catalogue import load_contributed
from weft_cli.run_services import build_services, check_store_capabilities
from weft_cli.services import ServiceSelection
from weft_generate.payload import Answer
from weft_kernel.context import Context
from weft_kernel.discovery import PackReport
from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_kernel.payload import Produced
from weft_kernel.pipeline import Pipeline
from weft_kernel.registry import Registry
from weft_kernel.resolution import resolve
from weft_kernel.runner import PipelineResolutionError, Runner
from weft_retrieve.payload import Query, QuerySet, Route
from weft_store import NodeStore

#: `route.yaml`'s own `name:` field — the one pipeline name this module ever writes
#: itself, because a router has to be named *something* to be resolved at all. Every
#: pipeline it can route *to* is discovered, never written here.
ROUTE_PIPELINE_NAME = "route"


class NoRouterPipelineError(WeftError):
    """No installed pack contributed a pipeline named `route.yaml`'s own `route`.

    `weft-retrieve`'s own `register()` calls `registrar.add_pipeline_resource("weft_retrieve",
    "pipelines/route.yaml")` — this fires only when `weft-retrieve` is not installed, not
    permitted by `[packs] allow`, or failed to register, all of which `weft plugins doctor`
    already reports by distribution.
    """


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
    """
    catalogue = load_contributed(reports)
    router = catalogue.get(ROUTE_PIPELINE_NAME)
    if router is None:
        raise NoRouterPipelineError(
            f"no installed pack contributed a pipeline named '{ROUTE_PIPELINE_NAME}'. "
            f"Run `weft plugins doctor` to see whether 'weft-retrieve' is active."
        )

    service_registry = await build_services(
        registry=registry, catalogue=catalogue, llm=llm, services=services
    )
    routed_ctx = replace(ctx, services=service_registry)
    runner = Runner(registry)
    store = service_registry.resolve(NodeStore)

    query = Query(text=question)
    route = await _run_pipeline(
        router, query, registry=registry, runner=runner, ctx=routed_ctx, store=store
    )
    assert isinstance(route, Route)  # `route.yaml`'s own contract: Stage[Query, Route]

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
        target, query_set, registry=registry, runner=runner, ctx=routed_ctx, store=store
    )
    assert isinstance(answer, Answer)  # every shipped routable pipeline ends in a Generator
    return route.pipeline, answer


async def _run_pipeline(
    pipeline: Pipeline,
    payload: object,
    *,
    registry: Registry,
    runner: Runner,
    ctx: Context,
    store: object,
) -> object:
    contracts = contracts_for(pipeline, registry=registry, parents={pipeline.name: pipeline})
    resolved = resolve(
        pipeline, registry=registry, contracts=contracts, parents={pipeline.name: pipeline}
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
