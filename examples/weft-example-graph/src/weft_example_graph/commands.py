"""`weft graph build` and `weft graph show` — this pack's two contributed `Command`s.

Multi-word plugin names (`"example-graph build"`, `"example-graph show"`) group under a
shared `graph`
subparser (`weft_cli.cli.build_parser`'s own docstring: "grouping multi-word names... into
nested subparsers by their shared first word"), the same mechanism `docs/03-cli.md` → *Plugin-
contributed commands* shows for this exact pack: "`weft graph build` / `weft graph show
--entity \"Acme\"`".
"""

from typing import ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field

from weft_command import ExitCode, Rendered
from weft_command.contract import CommandResult
from weft_command.permission import PermissionClass
from weft_example_graph.store import GraphSettings, GraphStore
from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced


class GraphBuildArgs(BaseModel):
    """`weft graph build` takes no arguments — it recomputes every stored node's own graph
    data from that node's own stored content, using the pack's current extraction logic.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


class GraphBuildResult(CommandResult):
    """What one rebuild pass did — `weft_example_graph.store.GraphStore.rebuild`'s own totals."""

    examined: int
    entities: int
    relations: int


class GraphBuildCommand:
    """Rebuilds this pack's own entities and relations from its own stored node content.

    `permission_class = OVERWRITE` — `docs/03-cli.md` → *Permissions*: "`weft graph build`
    rebuilding a graph belongs in `overwrite` exactly as a core command would." Needs no
    access to the primary corpus: it recomputes only from content this pack's own store
    already holds, unlike `weft reconcile --mode full` (`weft_example_graph.store.GraphStore.
    reconcile`), which reaches the corpus through `ctx.require(NodeStore)` to backfill nodes
    this store has never seen.
    """

    args_model: ClassVar[type[BaseModel]] = GraphBuildArgs
    result_model: ClassVar[type[CommandResult]] = GraphBuildResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.OVERWRITE
    help: ClassVar[str] = (
        "recompute weft-example-graph's entities and relations from stored content"
    )

    def __init__(self, settings: GraphSettings, config: object = None) -> None:
        del config
        self._store = GraphStore(settings)

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del ctx
        assert isinstance(args, GraphBuildArgs)
        examined, entities, relations = await self._store.rebuild()
        return Produced(
            value=GraphBuildResult(examined=examined, entities=entities, relations=relations)
        )


class GraphShowArgs(BaseModel):
    """`weft graph show [--entity NAME]` — a corpus-wide summary, or one entity's neighbours."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity: str | None = Field(default=None, description="show this entity's own neighbours")


class EntityCount(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    count: int


class EntityNeighbor(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    predicate: str
    count: int


class GraphShowResult(CommandResult):
    """A corpus-wide summary, always; `neighbors` populated only when `--entity` was given."""

    nodes_with_graph_data: int
    distinct_entities: int
    distinct_relations: int
    top_entities: tuple[EntityCount, ...] = ()
    entity: str | None = None
    neighbors: tuple[EntityNeighbor, ...] = ()


class GraphShowCommand:
    """Read-only introspection over this pack's own graph — `permission_class = READ`."""

    args_model: ClassVar[type[BaseModel]] = GraphShowArgs
    result_model: ClassVar[type[CommandResult]] = GraphShowResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.READ
    help: ClassVar[str] = (
        "show weft-example-graph's corpus-wide summary, or one entity's neighbours"
    )

    def __init__(self, settings: GraphSettings, config: object = None) -> None:
        del config
        self._store = GraphStore(settings)

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        del ctx
        assert isinstance(args, GraphShowArgs)
        nodes_with_data, entities, relations = await self._store.summary()
        if args.entity is None:
            top = await self._store.top_entities(10)
            return Produced(
                value=GraphShowResult(
                    nodes_with_graph_data=nodes_with_data,
                    distinct_entities=entities,
                    distinct_relations=relations,
                    top_entities=tuple(EntityCount(name=name, count=count) for name, count in top),
                )
            )
        neighbors = await self._store.neighbors_of(args.entity)
        return Produced(
            value=GraphShowResult(
                nodes_with_graph_data=nodes_with_data,
                distinct_entities=entities,
                distinct_relations=relations,
                entity=args.entity,
                neighbors=tuple(
                    EntityNeighbor(name=name, predicate=predicate, count=count)
                    for name, predicate, count in neighbors
                ),
            )
        )


def render_graph_show(result: object) -> Rendered:
    """`weft example-graph show`, for a person — task **6.20**, G13's third repair.

    Before this function existed, `weft example-graph show` printed the raw structured dump
    every unregistered result falls through to — `{"nodes_with_graph_data":11,...}` — while
    every built-in command's own result printed prose. Registered through the identical
    `PackRegistrar.add_renderer` seam `weft_cli.commands.register` uses for its own eighteen
    (`weft_example_graph.register`, beside this pack's other five extension points), so this
    pack's own result reaches the same seam a stranger's does — there is no second, private
    path for a built-in to have kept.

    Takes `object`, not `GraphShowResult`, and `cast`s internally — the same defensive-cast
    idiom `weft_cli.render`'s own registered dispatch wrappers use for the identical reason:
    `PackRegistrar.add_renderer`'s own `renderer` parameter is `Callable[[object], object]`,
    since the kernel names no capability and cannot narrow it to this pack's own result type.
    Public (no leading underscore), because `weft_example_graph.register` — a different
    module in this pack — calls it directly.
    """
    typed = cast(GraphShowResult, result)
    lines = [
        f"{typed.nodes_with_graph_data} node(s) carry graph data: "
        f"{typed.distinct_entities} distinct entities, {typed.distinct_relations} "
        f"distinct relations."
    ]
    if typed.top_entities:
        lines.append("top entities:")
        lines.extend(f"  {entity.name} ({entity.count})" for entity in typed.top_entities)
    if typed.entity is not None:
        lines.append(f"neighbours of '{typed.entity}':")
        if typed.neighbors:
            lines.extend(
                f"  {neighbor.predicate} {neighbor.name} ({neighbor.count})"
                for neighbor in typed.neighbors
            )
        else:
            lines.append("  (none)")
    return Rendered(stdout="\n".join(lines), stderr=None, exit_code=ExitCode.SUCCESS)


__all__ = [
    "GraphBuildArgs",
    "GraphBuildCommand",
    "GraphBuildResult",
    "GraphShowArgs",
    "GraphShowCommand",
    "GraphShowResult",
    "render_graph_show",
]
