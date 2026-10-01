"""`weft route explain "<q>"` shows why a question would go where it goes — task **44.16**.

It runs the configured router — its scorer and policy, never the rung it picks — and prints the
query profile, the corpus profile (from the one `list_sources()` read an ask makes) and the
`Route`. It reads only and answers nothing; under `--json` it is one object with `query_profile`,
`corpus_profile` and `route`.

The query profile is what the configured router's own scorer measured (the `Scorecard`'s features
without the `corpus.*` ones, which the corpus profile prints) — never a profile recomputed with
Weft's default cues, which would show an operator's own cue lexicon, or a third party's scorer, as
something it is not (R44.17). A scorer that emits scores and no features, such as `query-scorer`,
shows an empty profile.

**Reads only, on purpose.** The identical footing `weft_cli.eval_replay.EvalReplayCommand`
already holds: `permission_class` is `READ`, and every value this command prints comes from
`weft_cli.route_ask.explain_route`, which never runs the rung the router names.

`explain_route`/`source_records` are imported into this module's own namespace by name, not
qualified through `weft_cli.route_ask`/`weft_cli.commands`, so a test can monkeypatch either
here without reaching into a module this one merely calls through.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field

from weft_cli.commands import source_records
from weft_cli.route_ask import explain_route
from weft_command.contract import Command, CommandResult
from weft_command.permission import PermissionClass
from weft_engine.registry_bootstrap import Dependencies
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import Outcome, Produced
from weft_retrieve.payload import RouteView
from weft_retrieve.profile import CorpusProfile, corpus_profile_under
from weft_store.coverage import layer_coverage_of, ready_layers

_ROUTE_EXPLAIN_HELP = (
    "show how the configured router would route a question — its query profile, the corpus "
    "profile and the route it picks — without answering it"
)


class RouteExplainArgs(BaseModel):
    """`weft route explain "<question>" [--target NAME]` — nothing else `weft ask` also takes.

    `target` mirrors `weft_cli.commands.AskArgs.target`: which target to read instead of the
    live one (ledger task 34.6), so the corpus profile and the route both describe the same
    target an equivalent `weft ask` would have answered from.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str = Field(description="the question to route")
    target: str | None = Field(
        default=None,
        description=(
            "which target to read instead of the live one (ledger task 34.6). Refused for a "
            "target that does not exist, naming every target that does. Omit for the live one."
        ),
    )


class RouteExplainCommandResult(CommandResult):
    """`weft route explain`'s whole answer: the two profiles the router saw, and its `Route`."""

    question: str
    query_profile: Mapping[str, int | float | bool]
    corpus_profile: CorpusProfile
    route: RouteView


class RouteExplainCommand:
    """`weft route explain` — see the module docstring."""

    args_model: ClassVar[type[BaseModel]] = RouteExplainArgs
    result_model: ClassVar[type[CommandResult]] = RouteExplainCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = _ROUTE_EXPLAIN_HELP

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        """Route one question through the configured router, and answer nothing.

        Args:
            args: The parsed `RouteExplainArgs`.
            ctx: The command's context, carrying `Dependencies`.

        Returns:
            The produced `RouteExplainCommandResult`, or a read failure `source_records` hit.
        """
        explain_args = cast(RouteExplainArgs, args)
        deps = ctx.require(Dependencies)
        records_outcome = await source_records(deps, explain_args.target)
        if not isinstance(records_outcome, Produced):
            return records_outcome
        records = records_outcome.value
        ready = ready_layers(layer_coverage_of(records))
        # The same `list_sources()` read `weft_cli.commands.AskCommand`'s own routed path uses
        # to build one — ledger task **44.15** — never a second one.
        corpus = corpus_profile_under(records, deps.llm.roles.roles)
        route = await explain_route(
            explain_args.question,
            registry=deps.registry,
            reports=deps.reports,
            ctx=ctx,
            llm=deps.llm,
            services=deps.services,
            sink=deps.token_sink,
            contributions=deps.contributions,
            roles=deps.roles,
            target=explain_args.target,
            ready_layers=ready,
            corpus=corpus,
        )
        return Produced(
            value=RouteExplainCommandResult(
                question=explain_args.question,
                query_profile={
                    name: value
                    for name, value in route.scorecard.features.items()
                    if not name.startswith("corpus.")
                },
                corpus_profile=corpus,
                route=route.view(),
            )
        )


def register_route_explain_command(registrar: PackRegistrar) -> None:
    """Make `weft route explain` resolvable as an ordinary registered command.

    Register `route explain` — called from `weft_cli.commands.register`, on `weft_cli.
    eval_replay.register_eval_replay_command`'s own footing. Imported there, locally, rather
    than at that module's own top scope: this module imports `weft_cli.commands.source_records`
    at its own module scope, so a module-level import back would be the identical cycle `weft_
    cli.commands.register`'s own docstring already names for `weft_cli.render`.
    """
    registrar.add(Command, "route explain", RouteExplainCommand)


__all__ = [
    "RouteExplainArgs",
    "RouteExplainCommand",
    "RouteExplainCommandResult",
    "register_route_explain_command",
]
