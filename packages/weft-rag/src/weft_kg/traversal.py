"""`GraphWalk` — the `GraphTraversal` implementation over `weft_kg.store`'s own Postgres schema.
Ledger **11.5**.

**A second class over the same schema `GraphStore` provisions, and that is a finding rather than a
style — `docs/lessons.md` `L11.23`.** `weft_cli.fanout.participants_for` narrows `NodeStore` to
`store_names` with `if contract is NodeStore` and then deduplicates the participants it finds **by
class**, walking contracts in `__qualname__` order. `GraphTraversal` sorts before `NodeStore`
alphabetically, so a single class registered under both would be reached as a `GraphTraversal`
first, join the fan-out there, and have its `NodeStore` registration silently dropped as a
duplicate — the store filter would never run and this pack would participate in every project on
earth, named or not. `GraphWalk` therefore satisfies `GraphTraversal` alone and **must not** carry
`add`/`get`/`run`: giving it those would make it satisfy `NodeStore` again structurally, which is
exactly the shape this split exists to keep out of the tree.

**Every member answers in batch, at the granularity the contract's own module docstring states:
one round trip for the whole sequence handed in, never one per element.** `entities_by_name` and
`nodes_for_entities` are single queries. Only
`neighbourhood` needs more than one round trip — one *per hop*, not one per `(entity_id, hop)` pair
— because a bounded walk genuinely cannot know hop `n`'s frontier before hop `n-1` has answered;
what stays batched is every requested seed answered together, in that one query per hop.
"""

from collections.abc import Mapping, Sequence
from typing import Any, cast

import psycopg
from psycopg.rows import dict_row

from weft_kernel.payload import NodeId
from weft_kg.contract import Entity, EntityId
from weft_kg.store import GraphSettings, provision_schema, require_dsn


class GraphWalk:
    """The bounded, undirected walk `weft_kg.contract.GraphTraversal` declares — see the module
    docstring for why this is not `GraphStore` reused under a second contract.
    """

    def __init__(self, settings: GraphSettings, config: object = None) -> None:
        del config  # the kernel's `factory(None)` convention — nothing at the stage level needed
        self._settings = settings
        self._conn: psycopg.AsyncConnection[dict[str, Any]] | None = None

    async def _connection(self) -> "psycopg.AsyncConnection[dict[str, Any]]":
        """Lazily opened and schema-provisioned, exactly like `GraphStore`'s own — either class
        may be the first to dial in a given process, so both provision identically.
        """
        if self._conn is not None:
            return self._conn
        dsn = require_dsn(self._settings)
        conn = await psycopg.AsyncConnection[dict[str, Any]].connect(
            dsn, autocommit=True, row_factory=dict_row
        )
        await provision_schema(conn)
        self._conn = conn
        return conn

    async def aclose(self) -> None:
        """Not part of `GraphTraversal` — read defensively, the same shape `GraphStore.aclose`
        and `PgVectorStore.aclose` both carry.
        """
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def entities_by_name(self, names: Sequence[str]) -> tuple[Entity, ...]:
        if not names:
            return ()
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, name FROM kg_entities WHERE name = ANY(%s) ORDER BY name",
                (list(names),),
            )
            rows = await cur.fetchall()
        return tuple(_entity_of(row) for row in rows)

    async def nodes_for_entities(
        self, entity_ids: Sequence[EntityId]
    ) -> Mapping[EntityId, tuple[NodeId, ...]]:
        """Keys are exactly the requested ids this store holds an entity row for — an id it does
        not hold is absent, never a key mapping to `()`. Read against `kg_entities` with a `LEFT
        JOIN` onto `kg_entity_nodes`, deliberately, rather than the join table alone: what decides
        presence is whether the *entity* exists, not whether it currently has a node attached —
        the two happen to coincide under this store's own G15 invariant (an entity with no nodes
        is dropped), but the query states the actual rule rather than leaning on that invariant.
        """
        if not entity_ids:
            return {}
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT e.id AS entity_id, en.node_id AS node_id "
                "FROM kg_entities e LEFT JOIN kg_entity_nodes en ON en.entity_id = e.id "
                "WHERE e.id = ANY(%s)",
                (list(entity_ids),),
            )
            rows = await cur.fetchall()
        result: dict[EntityId, list[NodeId]] = {}
        for row in rows:
            entity_id = EntityId(cast(str, row["entity_id"]))
            result.setdefault(entity_id, [])
            node_id = row["node_id"]
            if node_id is not None:
                result[entity_id].append(NodeId(cast(str, node_id)))
        return {entity_id: tuple(nodes) for entity_id, nodes in result.items()}

    async def neighbourhood(
        self, entity_ids: Sequence[EntityId], *, hops: int
    ) -> Mapping[EntityId, tuple[Entity, ...]]:
        """Every entity reachable from each requested seed within `hops` relation edges, walked
        **undirected** — a stored relation has a direction, but reach does not, and a walk that
        only followed `source -> target` would lose the half of the graph pointing at its own
        seed. The seed is excluded from its own neighbourhood.

        One query per hop, covering every seed's current frontier together — see the module
        docstring for why that is the batch granularity a bounded walk can actually offer.
        """
        if not entity_ids:
            return {}
        seeds = list(dict.fromkeys(entity_ids))
        visited: dict[EntityId, set[EntityId]] = {seed: {seed} for seed in seeds}
        frontier: dict[EntityId, set[EntityId]] = {seed: {seed} for seed in seeds}
        reached: dict[EntityId, set[EntityId]] = {seed: set() for seed in seeds}
        conn = await self._connection()
        async with conn.cursor() as cur:
            for _ in range(hops):
                combined = sorted({node for nodes in frontier.values() for node in nodes})
                if not combined:
                    break
                await cur.execute(
                    "SELECT source_entity, target_entity FROM kg_relations "
                    "WHERE source_entity = ANY(%s) OR target_entity = ANY(%s)",
                    (combined, combined),
                )
                rows = await cur.fetchall()
                edges: dict[EntityId, set[EntityId]] = {}
                for row in rows:
                    source = EntityId(cast(str, row["source_entity"]))
                    target = EntityId(cast(str, row["target_entity"]))
                    edges.setdefault(source, set()).add(target)
                    edges.setdefault(target, set()).add(source)
                next_frontier: dict[EntityId, set[EntityId]] = {}
                for seed in seeds:
                    candidates: set[EntityId] = set()
                    for node in frontier[seed]:
                        candidates |= edges.get(node, set())
                    new_nodes = candidates - visited[seed]
                    if new_nodes:
                        visited[seed] |= new_nodes
                        reached[seed] |= new_nodes
                        next_frontier[seed] = new_nodes
                frontier = next_frontier

            all_reached = sorted({entity for entities in reached.values() for entity in entities})
            names: dict[EntityId, str] = {}
            if all_reached:
                await cur.execute(
                    "SELECT id, name FROM kg_entities WHERE id = ANY(%s)", (all_reached,)
                )
                name_rows = await cur.fetchall()
                names = {
                    EntityId(cast(str, row["id"])): cast(str, row["name"]) for row in name_rows
                }

        return {
            seed: tuple(
                Entity(id=entity_id, name=names[entity_id])
                for entity_id in sorted(reached[seed])
                if entity_id in names
            )
            for seed in seeds
        }


def _entity_of(row: Mapping[str, object]) -> Entity:
    return Entity(id=EntityId(cast(str, row["id"])), name=cast(str, row["name"]))


__all__ = ["GraphWalk"]


#: **No `nearest_entities` here, and it is a decision rather than a gap.** `weft_kg.contract`
#: records the whole of it: ranking entities by an embedding belongs on an `EntityVectorSearch`
#: Protocol of its own, and that Protocol is deliberately unwritten because nothing consumes it —
#: `11.10`'s walk is *name → entities → neighbourhood → nodes* and never starts from a vector. A
#: method here with no contract declaring it and no caller reaching it would be the producing side
#: with no consuming side that `docs/lessons.md` `L5.15` is about, so the class stops where the
#: contract does. **`kg_entities.embedding` stays**, because `11.6` writes entity-name vectors
#: through the pipeline's own embedder (`01` → Phase 11) — an unused column costs nothing and has
#: its writer one task away; an unreachable method costs a reader's trust in every other one.
