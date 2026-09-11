"""`ExampleGraphWalk` — this pack's `GraphTraversal`, over the tables it already keeps.

**Why a stranger implements this at all.** `weft_kg` publishes `GraphTraversal` and is the only
first-party implementer of it, which is the "second paradigm" `S12` refused — a capability bound to
one class. Fitness function 9(c) is what keeps that from being true: every published contract needs
an implementation living outside the repository that published it. This is that implementation for
the graph traversal contract, and it is written the way a third party's would be — against the
published Protocol, importing only its payload types, with no `weft_kg` class inherited or wrapped.

**A different data model, which is the point rather than an accident.** `weft_kg`'s entities are
rows with ids of their own; this pack's are `(node_id, name, count)` triples derived from each
node's `GraphData` ext, so an entity's *identity here is its name*. `EntityId` is a `NewType` over
`str` precisely so a backend may decide that for itself, and a second implementation that agreed
with the first about storage would prove nothing about whether the contract is satisfiable by
somebody who did not write it.

**It has no `nearest_entities`, and that is what the contract's own narrowing is for.** This pack
stores no vectors at all — `exgraph_nodes` has no embedding column and there is no embedder
anywhere in it — so while `nearest_entities` was a member of `GraphTraversal`, a graph backend that
walks entities and relations perfectly well was a three-quarters implementer of a capability it
fully had. That member moved to an `EntityVectorSearch` Protocol of its own at ledger `11.5`
(`weft_kg.contract` records it, unwritten, with its trigger), on the same footing
`weft_store.contract` publishes `VectorSearch` beside `NodeStore` rather than inside it. This class
is the backend that made the case; `docs/internal/lessons.md` `L11.29`.

**Holds its own `GraphStore` rather than being one.** The queries it needs — `entity_distances`,
`node_ids_for_entities` — are already on that class, and reimplementing them here would be two
answers to one question inside one pack. It is deliberately **not** a `NodeStore`: it has no `add`
and no `get`, so nothing that fans out over stores will ever build it thinking it is one.
"""

from collections.abc import Mapping, Sequence

from weft_example_graph.store import GraphSettings, GraphStore
from weft_kernel.payload import NodeId
from weft_kg.contract import Entity, EntityId


class ExampleGraphWalk:
    """A bounded, undirected walk over this pack's entity and relation tables."""

    def __init__(self, settings: GraphSettings, config: object = None) -> None:
        del config  # the kernel's `factory(None)` convention — nothing at the stage level needed
        self._store = GraphStore(settings)

    async def aclose(self) -> None:
        """Closes the connection this class opened. Not a contract method — read defensively by
        `weft_cli.fanout.built` and by `weft_cli.ingest`, exactly as `GraphStore.aclose` is.
        """
        await self._store.aclose()

    async def entities_by_name(self, names: Sequence[str]) -> tuple[Entity, ...]:
        """The entities this graph holds under any of `names`, in the order asked.

        A name with no row is simply absent — the honest answer to "do you know this name",
        and never a placeholder `Entity` that would read to a caller as a hit.
        """
        found: list[Entity] = []
        for name in names:
            if await self._store.node_ids_for_entities((name,)):
                found.append(Entity(id=EntityId(name), name=name))
        return tuple(found)

    async def nodes_for_entities(
        self, entity_ids: Sequence[EntityId]
    ) -> Mapping[EntityId, tuple[NodeId, ...]]:
        """The nodes each requested entity was mentioned in.

        **An id this graph does not hold is absent from the mapping**, never a key with an empty
        tuple: a caller has to be able to tell "no such entity" from "that entity, and nothing
        mentions it any more". `docs/internal/lessons.md` L5.9.
        """
        answer: dict[EntityId, tuple[NodeId, ...]] = {}
        for entity_id in entity_ids:
            nodes = await self._store.node_ids_for_entities((str(entity_id),))
            if nodes:
                answer[entity_id] = nodes
        return answer

    async def neighbourhood(
        self, entity_ids: Sequence[EntityId], *, hops: int
    ) -> Mapping[EntityId, tuple[Entity, ...]]:
        """Every entity within `hops` relation edges of each seed, the seed itself excluded.

        `GraphStore.entity_distances` already walks this pack's relations in both directions and
        returns each reachable name with the hop it was reached at, so the bound is applied there
        and this only shapes the answer. The seed is dropped because "the neighbourhood of x" is
        the question a caller asked, and x is not its own neighbour.
        """
        answer: dict[EntityId, tuple[Entity, ...]] = {}
        for entity_id in entity_ids:
            seed = str(entity_id)
            distances = await self._store.entity_distances((seed,), hops=hops)
            answer[entity_id] = tuple(
                Entity(id=EntityId(name), name=name)
                for name in sorted(distances)
                if name != seed and distances[name] <= hops
            )
        return answer


__all__ = ["ExampleGraphWalk"]
