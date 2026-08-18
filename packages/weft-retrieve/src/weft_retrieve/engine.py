"""The real `StageLookup` and `RouteCatalogue` — `weft_retrieve.contract`'s own two
service Protocols, built for the first time. Task **2.8**.

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

from collections.abc import Awaitable, Callable, Mapping
from typing import cast

from weft_kernel.context import Context
from weft_kernel.payload import Outcome
from weft_kernel.pipeline import Pipeline
from weft_kernel.registry import Registry
from weft_kernel.runner import Stage
from weft_kernel.seam import wrap
from weft_retrieve.payload import RouteCandidate

#: The two `vars:` keys a routable pipeline writes — `weft_retrieve.contract.
#: RouteCatalogue`'s own docstring, and `.phase2-design.md` §5's worked examples.
_ROUTE_SUMMARY_VAR = "route.summary"
_ROUTE_COST_VAR = "route.cost"


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
        """Every name registered for `contract` — read straight off the registry, so a
        newly installed pack's plugin is visible the moment discovery ran, with nothing
        cached here to go stale."""
        return self._registry.names_for(contract)

    async def build[In, Out](
        self, contract: type[Stage[In, Out]], name: str, config: object = None
    ) -> Callable[[In, Context], Awaitable[Outcome[Out]]]:
        """Resolve `name` under `contract`, construct it, and hand back a callable
        already wrapped through `weft_kernel.seam.wrap` — see the module docstring for
        why nothing here caches the instance.

        Raises `weft_kernel.registry.UnknownPluginError` — the registry's own, naming
        `contract`, `name` and every registered option — for an unresolvable name;
        nothing here invents a second message for the same fact.
        """
        entry = self._registry.entry(contract, name)
        instance = cast("Stage[In, Out]", entry.factory(config))
        return wrap(
            instance.run,
            distribution=entry.distribution,
            contract=contract.__name__,
            plugin=name,
            stage=f"sub:{name}",
        )

    async def build_capability[T](self, contract: type[T], name: str, config: object = None) -> T:
        """Resolve `name` under `contract` and construct it — the raw instance, never
        wrapped: a capability like `weft_prompts.contract.Prompt` has no `run` a `Stage`
        signature could wrap, and its own caller (`weft_prompts.cascade.execute`, for a
        `Prompt`) already runs inside the calling technique's own seam-wrapped span.
        """
        entry = self._registry.entry(contract, name)
        return cast(T, entry.factory(config))


def stage_lookup(registry: Registry) -> RegistryStageLookup:
    """Build the run's `StageLookup`. This pack's own constructor — see the module
    docstring, and `.phase2-design.md` §7: "so a library caller is not forced through
    the CLI." `weft_cli.run_services.build_services` is the one caller that is.
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
    """

    def __init__(self, catalogue: Mapping[str, Pipeline]) -> None:
        self._candidates = tuple(
            RouteCandidate(
                name=name,
                summary=str(pipeline.vars[_ROUTE_SUMMARY_VAR]),
                cost=str(pipeline.vars.get(_ROUTE_COST_VAR, "")),
            )
            for name, pipeline in sorted(catalogue.items())
            if _ROUTE_SUMMARY_VAR in pipeline.vars
        )

    def candidates(self) -> tuple[RouteCandidate, ...]:
        return self._candidates

    def names(self) -> frozenset[str]:
        return frozenset(candidate.name for candidate in self._candidates)


def route_catalogue(catalogue: Mapping[str, Pipeline]) -> PipelineRouteCatalogue:
    """Build the run's `RouteCatalogue`. This pack's own constructor — see the module
    docstring on `stage_lookup`, the identical shape.
    """
    return PipelineRouteCatalogue(catalogue)
