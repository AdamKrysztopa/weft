"""`graph-walk` — a question naming an entity, answered from a bounded walk. Ledger **11.10**.

No container: the walk is doubled at `weft_kg.contract.GraphTraversal` and the corpus at
`weft_store.contract.NodeStore`, which are exactly the two services this plugin reaches and the
two declarations it makes.

**The name, settled before the code through `paper-to-plugin` and `10` §2.1.** `10` §4 reserves
`grag`, `g-retriever`, `archrag` and `hipporag` for techniques Weft does not implement, and taking
one for a bounded neighbourhood walk would be rule 4's overclaim — none of them is this. `graph-
walk` states the mechanism (rule 2) and is qualified against the siblings a graph family will grow
(rule 6): `graph-ppr` and `graph-community` stay free, where a bare `graph` would have let the
first implementation seize a namespace meant to be shared. There is no paper: walking a
neighbourhood from a matched entity is ordinary practice, and `10` §5 records the absence rather
than inventing a provenance.

**Two declarations, and the split is the point of this task.** `needs_store = (NodeStore,)` says
what the *configured store* must be — this plugin reads node bodies back with `store.get`, exactly
as `weft_retrieve.collapse` does. `needs_services = (GraphTraversal,)` is new at `11.10` and says
what the *run* must have: a capability no store provides and no `[services] store` can supply,
reached through `ctx.require` and named by a `[services] graph` role. Declaring the traversal
under `needs_store` would compare it against `pgvector` and refuse every run with a remedy pointing
at the wrong setting — which is the defect `weft_cli.run_services.SelectedCapabilityMissingError`
was written to describe.

**Seeding is capitalisation, not a model — settled with the owner 2026-09-09.** A question's
Title-Case runs are the entity-name candidates, the identical rule `weft_kg.cooccurrence` already
applies to a chunk, now published once in `weft_kg.names` so the pack holds one notion of what a
name looks like rather than two. It keeps `cost_bound = (0, 0)`, so a graph question costs no
credential — the property `index-with-cooccurrence` was built for, carried to the query side. It is
crude in the same way and the row in `10` says so: it cannot see a lower-cased name, and it cannot
see a language that does not capitalise.

**The score decays by hop distance**, also settled with the owner: a walk produces no ranking, and
the two honest options were to invent an interpretable one or to flatten every hit to `1.0`. Flat
scores make every hit tie, and `reciprocal-rank-fusion` turns an arbitrary tie-break into an
arbitrary weight with nothing saying so. `1/(1 + hops)` is a number a reader can interpret and is
what makes `graph-2hop-then-generate` visibly a different rung rather than merely a larger one.

**Getting a per-entity hop distance costs one round trip per hop, and that is the honest price of
the number above meaning anything.** `GraphTraversal.neighbourhood` answers "everything reachable
within `hops` edges", not "what is reachable at exactly hop `n`" — read `weft_kg/traversal.py`
before assuming otherwise. So this stage calls it once per ring, `hops=1`, then `hops=2`, and so
on up to `config.hops`, and treats whatever is newly present at ring `n` that was not already
present at a smaller ring as being exactly `n` hops from the nearest seed that reached it. The
single-call alternative — one `neighbourhood` call at the full `hops` bound, with everything it
returns flattened into one ring — was rejected: it would make `1/(1 + hops)` a claim this class
cannot back with anything it actually asked for. The cost is bounded by construction: `hops` is
small, because a *bounded* walk is the entire point of this technique over an unbounded graph
traversal.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from weft_kernel.context import Context
from weft_kernel.payload import NodeId, Outcome, Produced
from weft_kg.contract import Entity, EntityId, GraphTraversal
from weft_kg.names import DEFAULT_MAX_NAME_WORDS, candidate_names, with_subspans
from weft_retrieve.payload import Candidates, Passage, Query, QuerySet, RankedList
from weft_store.contract import NodeStore, Scored

#: The name this retriever is registered and selectable under — see `weft_kg.register`.
NAME = "graph-walk"


class GraphWalkConfig(BaseModel):
    """`graph-walk`'s `with:` config.

    `hops=0` asks for exactly the seeds' own nodes and walks nowhere — the cheapest, most
    literal reading of a question naming an entity. `arm` is `vector-top-k`'s own argument
    carried here unchanged: with the channel hardcoded, two lists in one fusion would share one
    label and an operator would have no key to weight them apart in a `weights` mapping.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    hops: int = Field(default=1, ge=0)
    top_k: int = Field(default=20, ge=1)
    max_name_words: int = Field(default=DEFAULT_MAX_NAME_WORDS, ge=1)
    arm: str = Field(default="graph", min_length=1)


class GraphWalkRetriever:
    """A bounded walk from a question's own named entities. Satisfies
    `weft_retrieve.contract.Retriever` structurally — see the module docstring for why this
    class never imports that Protocol.

    Two declarations, not one — see the module docstring's *Two declarations* section.
    `cost_bound = (0, 0)` is true because seeding is a regular expression and the walk is SQL:
    this module imports nothing from `weft_llm` and resolves no model-shaped service.
    """

    config_model: ClassVar[type[GraphWalkConfig]] = GraphWalkConfig
    needs_store: ClassVar[tuple[type, ...]] = (NodeStore,)
    needs_services: ClassVar[tuple[type, ...]] = (GraphTraversal,)
    cost_bound: ClassVar[tuple[int, int]] = (0, 0)

    def __init__(self, config: GraphWalkConfig | None = None) -> None:
        self._config = config if config is not None else GraphWalkConfig()

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[Candidates]:
        """One `RankedList` per query — see the module docstring for the six-step order.

        A query naming no entity still gets a `RankedList` with `hits=()` rather than no list
        at all — `L5.9`, and `vector_top_k.run`'s own distinction between a query that was
        searched and matched nothing and a query this retriever never asked about. `payload.ext`
        is carried onto `Candidates.ext` unchanged, for the reason `vector_top_k.run`'s own
        docstring gives: a `QueryTransform` upstream may have attached something a later stage
        needs, and dropping it here would silently orphan it at this seam.
        """
        traversal = ctx.require(GraphTraversal)
        store = ctx.require(NodeStore)

        lists: list[RankedList] = []
        for query in payload.queries:
            seeds = with_subspans(
                candidate_names(query.text, max_words=self._config.max_name_words)
            )
            seed_entities = await traversal.entities_by_name(list(seeds))
            lists.append(await self._ranked_list_for(query, seed_entities, traversal, store))

        return Produced(
            value=Candidates(origin=payload.origin, lists=tuple(lists), ext=payload.ext)
        )

    async def _ranked_list_for(
        self,
        query: Query,
        seed_entities: tuple[Entity, ...],
        traversal: GraphTraversal,
        store: NodeStore,
    ) -> RankedList:
        if not seed_entities:
            return RankedList(query=query, retriever=NAME, channel=self._config.arm, hits=())

        seed_ids = tuple(dict.fromkeys(entity.id for entity in seed_entities))
        distances: dict[EntityId, int] = {seed_id: 0 for seed_id in seed_ids}

        # One `neighbourhood` call per ring, never one flattened call for the whole bound — see
        # the module docstring for why a single call cannot support the score below.
        for hop in range(1, self._config.hops + 1):
            ring: Mapping[EntityId, tuple[Entity, ...]] = await traversal.neighbourhood(
                seed_ids, hops=hop
            )
            for reached in ring.values():
                for entity in reached:
                    if entity.id not in distances:
                        distances[entity.id] = hop

        node_ids_for_entity = await traversal.nodes_for_entities(tuple(distances))
        node_distance: dict[NodeId, int] = {}
        for entity_id, node_ids in node_ids_for_entity.items():
            hop = distances[entity_id]
            for node_id in node_ids:
                if node_id not in node_distance or hop < node_distance[node_id]:
                    node_distance[node_id] = hop

        nodes = await store.get(tuple(node_distance))
        ordered = sorted(nodes, key=lambda node: (-1.0 / (1 + node_distance[node.id]), node.id))
        top = ordered[: self._config.top_k]
        hits = tuple(
            Passage(
                scored=Scored(value=node, score=1.0 / (1 + node_distance[node.id])),
                rank=rank,
                retrieved_by=NAME,
            )
            for rank, node in enumerate(top)
        )
        return RankedList(query=query, retriever=NAME, channel=self._config.arm, hits=hits)


__all__ = ["NAME", "GraphWalkConfig", "GraphWalkRetriever"]
