"""`GraphWalkRetriever` — ranks nodes by graph proximity to the entities a query names,
never by vector or lexical similarity. Satisfies `weft_retrieve.contract.Retriever`
structurally; this class never imports it.

**`needs_store` is not declared**, on `weft_retrieve.iterative.NoRetrieval`'s own precedent
("this plugin never touches [the configured] store"): this retriever never resolves
`ctx.require(NodeStore)` at all. It owns its own connection to its own store — the same one
`weft_example_graph.store.GraphStore` uses, over the identical `weft.toml` DSN setting — because the
graph store is a *second*, pack-owned store sitting beside whatever `[services] store`
names, not a capability of the configured primary store; declaring `needs_store` against
the primary would assert a requirement this retriever never actually checks there.
"""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from weft_example_graph.extraction import extract_entity_names
from weft_example_graph.payload import GraphData
from weft_example_graph.store import GraphSettings, GraphStore
from weft_kernel.context import Context
from weft_kernel.payload import Node, Outcome, Produced
from weft_retrieve.payload import Candidates, Passage, QuerySet, RankedList
from weft_store.contract import Scored

NAME = "example-graph-walk"


class GraphWalkConfig(BaseModel):
    """`graph-walk`'s `with:` config — every field defaults, per this project's rule that
    every pack's settings must be constructible with none supplied.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: How many results at most, per query.
    top_k: int = 10
    #: How many relation-hops out from a query's own named entities to walk before scoring.
    hops: int = 1


class GraphWalkRetriever:
    """One graph walk per query: extract the entities a question names, widen by `hops`
    relation-steps, then rank every node mentioning any of them by hop distance (closer
    scores higher). A query naming no entity this pack's own crude extractor recognises
    gets an empty `RankedList`, not an error — the same "never asked" versus "asked and
    found nothing" distinction `weft_retrieve.vector_top_k.VectorTopK`'s own docstring
    draws, applied to a graph walk instead of a vector search.
    """

    needs_store: ClassVar[tuple[type, ...]] = ()
    config_model: ClassVar[type[GraphWalkConfig]] = GraphWalkConfig

    def __init__(self, settings: GraphSettings, config: GraphWalkConfig | None = None) -> None:
        self._store = GraphStore(settings)
        self._config = config if config is not None else GraphWalkConfig()

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[Candidates]:
        del ctx
        lists: list[RankedList] = []
        for query in payload.queries:
            seeds = extract_entity_names(query.text)
            if not seeds:
                lists.append(RankedList(query=query, retriever=NAME, hits=()))
                continue
            distances = await self._store.entity_distances(seeds, hops=self._config.hops)
            node_ids = await self._store.node_ids_for_entities(tuple(distances))
            nodes = await self._store.get(node_ids)
            scored = sorted(
                (
                    (node, min((distances[name] for name in _names_of(node, distances)), default=0))
                    for node in nodes
                ),
                key=lambda pair: pair[1],
            )[: self._config.top_k]
            hits = tuple(
                Passage(
                    scored=Scored(value=node, score=1.0 / (1 + distance)),
                    rank=rank,
                    retrieved_by=NAME,
                )
                for rank, (node, distance) in enumerate(scored)
            )
            lists.append(RankedList(query=query, retriever=NAME, hits=hits))
        return Produced(
            value=Candidates(origin=payload.origin, lists=tuple(lists), ext=payload.ext)
        )


def _names_of(node: Node, distances: dict[str, int]) -> tuple[str, ...]:
    """Which of `distances`' own entity names this node's `GraphData` actually carries —
    scoring by the *closest* of them, since a node mentioning both a seed and a two-hop
    neighbour is exactly as relevant as its nearest match, never diluted by the farther one.
    """
    data = node.ext_as(GraphData)
    if data is None:
        return ()
    names = {entity.name for entity in data.entities}
    return tuple(name for name in distances if name in names)


__all__ = ["GraphWalkConfig", "GraphWalkRetriever"]
