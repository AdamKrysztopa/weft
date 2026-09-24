"""`adjacent-chunks` — a hit's siblings, read back by ordinal. Ledger task **32.3**.

**Weft's own technique — no paper, and that is stated rather than omitted.** Returning a
chunk's neighbours alongside it is common practitioner lore (`10` §5's own survey of the
field names the shape), but the two labels a reader might expect here — "small-to-big" and
"sentence-window" — are a blog's and a framework's own coinages, not a citable source and
not this plugin's name. `10` §5 carries that context; this module claims nothing beyond
what `32.1` (`weft_chunk.payload.ChunkPosition`) and `32.2` (the store's Filter AST) already
make possible: read a hit's ordinal, ask the store for the ordinals on either side of it
from the same parent, and return what comes back.

**A neighbour scores as the hit that brought it.** `weft_store.contract.Scored.score` is a
required field — a `Node` has no score of its own, only a value paired with one search's
result (`Scored`'s own docstring: "a property of one search, not of the node"). A neighbour
was never searched for; it is in this ranking only because the hit beside it was, so its
score is that hit's, restated rather than invented.

**Each neighbour is its own `Passage`, never merged into its anchor's.** A citation resolves
per label (`weft_generate.cited_answer`'s own docstring on how `Citation.marker` is matched
against `Passage.label`), and a `weft_store.contract.NodeStore.get` fetches one node by one
id — a passage standing for two concatenated nodes would be a node nothing can `get` back,
and a citation naming it would point at content the store never stored under that id.

**This reranker runs after selection, never before it.** It sits at a `Reranker` position —
after fusion, before packing — so a neighbour never competes for a slot in `vector-top-k`'s
own `top_k`: it is added only once its anchor already won one. A document composing this
stage must widen whatever `ContextPacker` follows it accordingly — `repack`'s own `top_n`
truncates by count, with no notion of "this passage came in as a group", so a document that
expands three passages per hit and packs eight of them back down to eight would silently
discard most of what this stage just added.
"""

from collections.abc import Sequence
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from weft_chunk.payload import ChunkPosition
from weft_kernel.context import Context
from weft_kernel.payload import Failed, Node, NodeId, Outcome, Produced
from weft_retrieve.payload import Passage, Ranking
from weft_store.contract import Cursor, Filter, FilterOp, MetadataFilter, NodeStore, Scored

#: The name this reranker is registered and selectable under — see `weft_retrieve.register`.
NAME = "adjacent-chunks"


class AdjacentChunksConfig(BaseModel):
    """`AdjacentChunks`'s `with:` config. `window` neighbours are fetched on *each* side."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    window: int = Field(default=1, ge=1)


class AdjacentChunks:
    """Every hit, plus up to `window` same-parent neighbours on each side.

    Satisfies `weft_retrieve.contract.Reranker` structurally.

    `cost_bound = (0, 0)`: `run` resolves `NodeStore` alone, reads it through `MetadataFilter`,
    and calls no model — the same honest shape `weft_retrieve.collapse.CollapseToParent`
    states for the identical reason.
    """

    config_model: ClassVar[type[AdjacentChunksConfig]] = AdjacentChunksConfig
    needs_store: ClassVar[tuple[type, ...]] = (MetadataFilter,)
    score_semantics: ClassVar[str] = (
        "a retrieved hit keeps its own score; each added neighbour carries the score of the hit "
        "that brought it, so neighbours tie with their anchor and are not ranked by similarity"
    )
    cost_bound: ClassVar[tuple[int, int]] = (0, 0)

    def __init__(self, config: AdjacentChunksConfig | None = None) -> None:
        self._config = config if config is not None else AdjacentChunksConfig()

    async def run(self, payload: Ranking, ctx: Context) -> Outcome[Ranking]:
        """Widen every hit by its own siblings.

        See the module docstring for the scoring and passage-identity rules.

        An empty ranking passes through untouched, with no store read at all: there is
        nothing to widen, and asking a service for zero hits' siblings would be a call this
        stage never needed to make.
        """
        if not payload.hits:
            return Produced(value=payload)

        store = ctx.require(NodeStore)
        if not isinstance(store, MetadataFilter):
            return Failed(
                reason=(
                    f"'{NAME}' needs a store that can evaluate a metadata filter to find a "
                    f"hit's siblings by ordinal, and {type(store).__name__} does not provide "
                    f"it. Configure a store that satisfies MetadataFilter."
                )
            )

        positions = _positions(payload.hits)
        if isinstance(positions, Failed):
            return positions

        emitted: set[NodeId] = set()
        result: list[Passage] = []
        for hit in payload.hits:
            parent = _single_parent(hit)
            if isinstance(parent, Failed):
                return parent
            position = positions[hit.node.id]
            wanted = _wanted_ordinals(position.ordinal, window=self._config.window)
            neighbours = await _siblings(store, parent=parent, ordinals=wanted) if wanted else {}

            group: list[tuple[int, Node, Passage | None]] = [(position.ordinal, hit.node, hit)]
            group.extend((ordinal, node, None) for ordinal, node in neighbours.items())
            _emit_group(group, hit=hit, emitted=emitted, result=result)

        renumbered = tuple(
            passage.model_copy(update={"rank": rank}) for rank, passage in enumerate(result)
        )
        return Produced(
            value=Ranking(
                origin=payload.origin,
                hits=renumbered,
                contributors=payload.contributors,
                note=payload.note,
                ext=payload.ext,
            )
        )


def _positions(hits: Sequence[Passage]) -> dict[NodeId, ChunkPosition] | Failed:
    """Every hit's recorded `ChunkPosition`, by node id, or the refusal for one that has none."""
    positions: dict[NodeId, ChunkPosition] = {}
    for hit in hits:
        position = hit.node.ext_as(ChunkPosition)
        if position is None:
            return Failed(
                reason=(
                    f"'{NAME}' needs a recorded chunk position for node {hit.node.id}, "
                    f"and it carries none. The corpus was indexed before chunk positions "
                    f"were recorded — run `weft index --reprocess` over it."
                )
            )
        positions[hit.node.id] = position
    return positions


def _single_parent(hit: Passage) -> NodeId | Failed:
    """The one parent a hit's siblings are found through, or the refusal when it has not one."""
    parents = hit.node.lineage.parents
    if len(parents) != 1:
        named = ", ".join(str(parent) for parent in parents) if parents else "none"
        return Failed(
            reason=(
                f"'{NAME}' finds a hit's siblings through its single parent, and node "
                f"{hit.node.id} has {len(parents)} parents ({named}) rather than "
                f"exactly one."
            )
        )
    return parents[0]


def _wanted_ordinals(ordinal: int, *, window: int) -> tuple[int, ...]:
    """The non-negative ordinals within `window` of `ordinal`, excluding `ordinal` itself."""
    return tuple(
        candidate
        for candidate in range(ordinal - window, ordinal + window + 1)
        if candidate != ordinal and candidate >= 0
    )


def _emit_group(
    group: list[tuple[int, Node, Passage | None]],
    *,
    hit: Passage,
    emitted: set[NodeId],
    result: list[Passage],
) -> None:
    """Append `group` to `result` in ordinal order, skipping any node already emitted."""
    for _, node, original in sorted(group, key=lambda item: item[0]):
        if node.id in emitted:
            continue
        emitted.add(node.id)
        result.append(
            original
            if original is not None
            else Passage(scored=Scored(value=node, score=hit.score), rank=0, retrieved_by=NAME)
        )


async def _siblings(
    store: MetadataFilter, *, parent: NodeId, ordinals: tuple[int, ...]
) -> dict[int, Node]:
    """Every node under `parent` whose `ChunkPosition.ordinal` is in `ordinals`, by ordinal.

    Pages until `next_cursor` is exhausted — `weft_store.contract.MetadataFilter.matching`'s
    own contract, "order is not promised, pages are."
    """
    filter_ = Filter(
        op=FilterOp.AND,
        clauses=(
            Filter(op=FilterOp.CONTAINS, field="lineage.parents", value=str(parent)),
            Filter(op=FilterOp.IN, field="ext.weft-chunk.ordinal", value=ordinals),
        ),
    )
    found: dict[int, Node] = {}
    cursor: Cursor | None = None
    while True:
        page = await store.matching(filter_, cursor)
        for node in page.items:
            position = node.ext_as(ChunkPosition)
            if position is not None:
                found[position.ordinal] = node
        if page.next_cursor is None:
            return found
        cursor = page.next_cursor


__all__ = ["NAME", "AdjacentChunks", "AdjacentChunksConfig"]
