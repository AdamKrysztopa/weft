"""`GraphStore` — the whole store family this pack needs, over Postgres: `NodeStore`,
`SourceDeletable` and `Reconcilable`, all three structurally, the identical path
`examples/weft-example-ingest/src/weft_example_ingest/store.py` takes for its own six.

**Why Postgres, not a plain dict.** `docs/build-ledger.md` task 5.4/5.5 explicitly permits
either — "it needs no real graph database... a graph store over a plain dict... is fine" —
but a plain dict is *process-lifetime* state (`weft_example_ingest.store.InMemoryNodeStore`'s
own docstring: "`Lifetime.PROCESS`... an in-memory store has no database behind it"), and
every `weft` invocation is a fresh OS process. `weft index --pipeline kg` and a later
`weft graph show` are two separate processes; a dict would forget everything between them.
This pack reuses the one container the project already runs (`compose.yaml`) rather than
inventing a second storage technology, per this task's own instruction.

**Sits beside the vector store, literally.** `docs/02-extension-model.md` section 4's own
table: "Graph store | `NodeStore`... Sits beside the vector store." This class persists a
*full* `Node` — content, lineage, `ext` — exactly as `weft_store.pgvector_store.PgVectorStore`
does, so a document naming both `store: pgvector` and `store: graph` as two ordinary stages
(this pack's own `pipelines/kg.yaml`) hands the identical batch to each; the derived
entities/relations tables are additional bookkeeping this store keeps on the side, read off
each node's own `GraphData` ext.

**`ext` round-trips through `weft_store.rehydrate`, not a hand-rolled map.** Published API
this pack depends on `weft-store` for exactly this (`docs/02-extension-model.md` section 1,
Phase 0 step 8's own narrowing note) — reusing it, rather than inventing a second namespace
registry, is what lets a node carrying *any* installed pack's ext data (not only this pack's
own `GraphData`) survive a round trip through this store with no special-casing here.
"""

from collections.abc import Mapping, Sequence
from typing import Any, cast

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, SecretStr

from weft_example_graph.extraction import extract_graph_data
from weft_example_graph.payload import GraphData
from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.payload import SCHEMA_VERSION_KEY, Node, NodeId, Outcome, Produced, SourceId
from weft_store.contract import (
    Cursor,
    NodeStore,
    Page,
    ReconcileEstimate,
    ReconcileMode,
    ReconcileReport,
    Removed,
    SourceRecord,
    SourceStatus,
)
from weft_store.rehydrate import rehydrate_ext

_PAGE_SIZE = 100

_CREATE_NODES_TABLE = """
CREATE TABLE IF NOT EXISTS exgraph_nodes (
    id TEXT PRIMARY KEY,
    parents TEXT[] NOT NULL,
    sources TEXT[] NOT NULL,
    content TEXT NOT NULL,
    media_type TEXT NOT NULL,
    ext JSONB NOT NULL
)
"""

_CREATE_SOURCES_TABLE = """
CREATE TABLE IF NOT EXISTS exgraph_sources (
    id TEXT PRIMARY KEY,
    uri TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    indexed_at TIMESTAMPTZ NOT NULL,
    pipeline TEXT NOT NULL,
    status TEXT NOT NULL
)
"""

#: `ON DELETE CASCADE` is what makes `exgraph_nodes`'s own row the one place a node's
#: entities/relations live or die — deleting the node row (`delete_source`, or a rebuild's
#: own delete-then-reinsert) never leaves either table an orphan to clean up separately.
_CREATE_ENTITIES_TABLE = """
CREATE TABLE IF NOT EXISTS exgraph_entities (
    node_id TEXT NOT NULL REFERENCES exgraph_nodes(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    count INT NOT NULL,
    PRIMARY KEY (node_id, name)
)
"""

_CREATE_RELATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS exgraph_relations (
    node_id TEXT NOT NULL REFERENCES exgraph_nodes(id) ON DELETE CASCADE,
    source_entity TEXT NOT NULL,
    target_entity TEXT NOT NULL,
    predicate TEXT NOT NULL,
    count INT NOT NULL,
    PRIMARY KEY (node_id, source_entity, target_entity, predicate)
)
"""


class GraphSettings(BaseModel):
    """This pack's one connection setting — `[packs.graph]` in `weft.toml`.

    **`dsn` defaults to empty, unlike `weft_store.pgvector_store.PgVectorSettings.dsn`, and
    that is a finding rather than a stylistic choice.** `tests/architecture/
    test_ff9_extension_from_outside.py::test_no_first_party_file_names_the_example_pack`
    constructs every example pack's own `Settings()` with zero arguments and runs `register()`
    against a bare stand-in registrar — no `weft.toml`, no environment, nothing supplied. A
    mandatory `dsn` would make `register()` raise `ValidationError` there, for every pack
    this file is examined alongside, not only this one. `register()` itself never opens a
    connection (see `GraphStore._connection`, opened lazily on first real use), so an empty
    default costs nothing at registration time and fails loudly, naming the setting, at the
    first call that actually needs it — `_require_dsn` below.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    dsn: SecretStr = SecretStr("")


class GraphDsnNotConfiguredError(WeftError):
    """`[packs.graph] dsn` was never set, and this call needs a real connection.

    Raised only where a connection is actually opened — never at `register()`, which never
    calls `_connection` — so a pack installed with no settings still registers cleanly and
    fails exactly where an operator's mistake becomes consequential.
    """


def _require_dsn(settings: GraphSettings) -> str:
    dsn = settings.dsn.get_secret_value()
    if not dsn:
        raise GraphDsnNotConfiguredError(
            "weft-example-graph has no database to talk to: "
            "[packs.graph] dsn is unset. Add "
            '`[packs.graph]\\ndsn = "${env:WEFT_DATABASE_URL}"` (or a literal DSN) to '
            "weft.toml.",
            pack="weft-example-graph",
        )
    return dsn


class GraphStore:
    """`NodeStore`, `SourceDeletable` and `Reconcilable`, all three satisfied structurally —
    this class never imports one of the Protocols, the same path any third-party store
    pack takes (`docs/02-extension-model.md` section 4's own "Graph store | `NodeStore`" row,
    plus the two G7 rows: "The graph store, again | `SourceDeletable`" / "`Reconcilable`").
    `delete_source` needs no second method for `SourceDeletable`, on the identical footing
    `weft_example_ingest.store.InMemoryNodeStore`'s own docstring states.
    """

    def __init__(self, settings: GraphSettings, config: object = None) -> None:
        del config  # nothing at the stage level this store needs
        self._settings = settings
        self._conn: psycopg.AsyncConnection[dict[str, Any]] | None = None

    async def _connection(self) -> psycopg.AsyncConnection[dict[str, Any]]:
        """The lazily-opened, schema-provisioned connection this store reuses for its lifetime."""
        if self._conn is not None:
            return self._conn
        dsn = _require_dsn(self._settings)
        conn = await psycopg.AsyncConnection[dict[str, Any]].connect(
            dsn, autocommit=True, row_factory=dict_row
        )
        async with conn.cursor() as cur:
            await cur.execute(_CREATE_NODES_TABLE)
            await cur.execute(_CREATE_SOURCES_TABLE)
            await cur.execute(_CREATE_ENTITIES_TABLE)
            await cur.execute(_CREATE_RELATIONS_TABLE)
        self._conn = conn
        return conn

    async def aclose(self) -> None:
        """Not part of any contract `NodeStore` publishes — `weft_cli.ingest`'s own
        docstring reads this defensively, exactly as it already does for `PgVectorStore`.
        """
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # -- NodeStore -----------------------------------------------------------------------

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        await self.add(payload)
        return Produced(value=payload)

    async def add(self, nodes: Sequence[Node]) -> None:
        if not nodes:
            return
        conn = await self._connection()
        rows = [_node_to_row(node) for node in nodes]
        async with conn.cursor() as cur:
            await cur.executemany(
                """
                INSERT INTO exgraph_nodes (id, parents, sources, content, media_type, ext)
                VALUES (%(id)s, %(parents)s, %(sources)s, %(content)s, %(media_type)s, %(ext)s)
                ON CONFLICT (id) DO UPDATE SET
                    parents = EXCLUDED.parents,
                    sources = EXCLUDED.sources,
                    content = EXCLUDED.content,
                    media_type = EXCLUDED.media_type,
                    ext = EXCLUDED.ext
                """,
                rows,
            )
            for node in nodes:
                await _replace_graph_rows(cur, node.id, node.ext_as(GraphData))

    async def flush(self) -> None:
        """A true no-op: `add()` writes immediately, the same choice `PgVectorStore` makes."""
        return

    async def get(self, ids: Sequence[NodeId]) -> Sequence[Node]:
        if not ids:
            return ()
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM exgraph_nodes WHERE id = ANY(%s)", (list(ids),))
            rows = await cur.fetchall()
        return tuple(_row_to_node(row) for row in rows)

    async def scan(self, cursor: Cursor | None = None) -> Page[Node]:
        conn = await self._connection()
        async with conn.cursor() as cur:
            if cursor is None:
                await cur.execute(
                    "SELECT * FROM exgraph_nodes ORDER BY id LIMIT %s", (_PAGE_SIZE + 1,)
                )
            else:
                await cur.execute(
                    "SELECT * FROM exgraph_nodes WHERE id > %s ORDER BY id LIMIT %s",
                    (str(cursor), _PAGE_SIZE + 1),
                )
            rows = await cur.fetchall()
        page_rows = rows[:_PAGE_SIZE]
        next_cursor = Cursor(cast(str, page_rows[-1]["id"])) if len(rows) > _PAGE_SIZE else None
        return Page(items=tuple(_row_to_node(row) for row in page_rows), next_cursor=next_cursor)

    async def count(self) -> int:
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute("SELECT count(*) AS n FROM exgraph_nodes")
            row = await cur.fetchone()
        return cast(int, row["n"]) if row is not None else 0

    async def put_source(self, record: SourceRecord) -> None:
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO exgraph_sources (id, uri, content_hash, indexed_at, pipeline, status)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    uri = EXCLUDED.uri,
                    content_hash = EXCLUDED.content_hash,
                    indexed_at = EXCLUDED.indexed_at,
                    pipeline = EXCLUDED.pipeline,
                    status = EXCLUDED.status
                """,
                (
                    record.id,
                    record.uri,
                    record.content_hash,
                    record.indexed_at,
                    record.pipeline,
                    record.status.value,
                ),
            )

    async def get_source(self, source_id: SourceId) -> SourceRecord | None:
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM exgraph_sources WHERE id = %s", (source_id,))
            row = await cur.fetchone()
        return _row_to_source_record(row) if row is not None else None

    async def list_sources(self) -> Sequence[SourceRecord]:
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM exgraph_sources ORDER BY id")
            rows = await cur.fetchall()
        return tuple(_row_to_source_record(row) for row in rows)

    # -- SourceDeletable -------------------------------------------------------------------

    async def delete_source(self, source_id: SourceId) -> Removed:
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM exgraph_nodes WHERE %s = ANY(sources)", (source_id,))
            node_count = cur.rowcount
            await cur.execute("DELETE FROM exgraph_sources WHERE id = %s", (source_id,))
        return Removed(source_id=source_id, node_count=node_count)

    # -- Reconcilable ----------------------------------------------------------------------

    async def estimate(self, ctx: Context, mode: ReconcileMode) -> ReconcileEstimate:
        if mode is ReconcileMode.FULL:
            corpus = ctx.require(NodeStore)
            pending = 0
            cursor: Cursor | None = None
            while True:
                page = await corpus.scan(cursor)
                pending += len(await self._missing_from(page.items))
                cursor = page.next_cursor
                if cursor is None:
                    break
            return ReconcileEstimate(
                mode=mode,
                pending=pending,
                description=(
                    f"{pending} node(s) in the corpus have no graph data yet and would be "
                    f"backfilled from their own stored content"
                ),
                model_calls=0,
            )
        del ctx
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute("SELECT count(*) AS n FROM exgraph_nodes")
            row = await cur.fetchone()
        pending = cast(int, row["n"]) if row is not None else 0
        return ReconcileEstimate(
            mode=mode,
            pending=pending,
            description=(
                f"{pending} node(s) in weft-example-graph's own store will have their entities and "
                f"relations recomputed from stored content and reconciled against it"
            ),
            model_calls=0,
        )

    async def reconcile(self, ctx: Context, mode: ReconcileMode) -> ReconcileReport:
        """Repairs this pack's *own* bookkeeping against its *own* stored node content, and,
        for `full`, also backfills from the corpus.

        **`repair` does two things, and task 6.21 built the second.** It recomputes every
        node's entities/relations from that node's own stored content and re-derives them, so
        a partial write (a crash between the node upsert and the entities/relations upsert in
        `add`, since each statement autocommits independently) cannot leave the two out of
        step. And it **drops orphans** — `docs/02-extension-model.md` section 4's own table:
        "`repair` drops orphans left by anything the [deletion] fan-out missed". An orphan is
        a node here whose source the *primary corpus* no longer lists, which this store cannot
        answer from its own tables and could not ask about at all until task 6.19 put the
        corpus on the passport. The deletion fan-out reaching this store in-command (task
        6.18) makes an orphan rarer, never impossible: a participant that raised part-way
        through leaves exactly this. Idempotent — running it twice does the same work and
        reaches the same state.

        **So `repair` requires the corpus too, and refuses without it.** Doing the half it can
        and silently skipping orphan detection is `01` rule 5's silent degradation with extra
        steps: the operator would read "converged" and still be holding orphans. A run with no
        `NodeStore` on the passport raises `UnresolvedServiceError`, naming what was wanted and
        what is available, and the fan-out records that as this participant's own named failure
        rather than swallowing it.

        **`full` additionally backfills, task 6.19 (G13's second repair).** `docs/02` section
        1 → *Extended by G13*: a participant that is not the primary store reaches it through
        the passport, `ctx.require(NodeStore)` — G1's one resolution seam, never a wider
        `reconcile` signature. Every node the corpus holds and this store does not is given
        `GraphData` derived from its own content and stored, exactly what `02` section 4's own
        table row promises: "`full` backfills entities for nodes indexed by a pipeline that
        had no graph stage". `remaining` is honestly `0` because nothing here is left
        unexamined.
        """
        corpus = ctx.require(NodeStore)
        live = await _live_sources(corpus)
        conn = await self._connection()
        examined = 0
        removed = 0
        async with conn.cursor() as cur:
            await cur.execute("SELECT id, ext, sources FROM exgraph_nodes ORDER BY id")
            rows = await cur.fetchall()
            for row in rows:
                examined += 1
                node_id = cast(NodeId, row["id"])
                sources = {str(source) for source in cast("list[object]", row["sources"])}
                if sources and not (sources & live):
                    removed += await _drop_node(cur, node_id)
                    continue
                raw_ext = cast(dict[str, object], row["ext"])
                data = _graph_data_of(raw_ext)
                removed += await _replace_graph_rows(cur, node_id, data)

        backfilled = 0
        if mode is ReconcileMode.FULL:
            cursor: Cursor | None = None
            while True:
                page = await corpus.scan(cursor)
                examined += len(page.items)
                for node in await self._missing_from(page.items):
                    entities, relations = extract_graph_data(node.content)
                    await self.add(
                        [node.with_ext(GraphData(entities=entities, relations=relations))]
                    )
                    backfilled += 1
                cursor = page.next_cursor
                if cursor is None:
                    break

        return ReconcileReport(
            mode=mode, examined=examined, removed=removed, backfilled=backfilled, remaining=0
        )

    async def _missing_from(self, nodes: Sequence[Node]) -> list[Node]:
        """Which of `nodes` this store does not already hold — one batched `get` over their
        own ids, never assumed.
        """
        if not nodes:
            return []
        held_ids = {held.id for held in await self.get([node.id for node in nodes])}
        return [node for node in nodes if node.id not in held_ids]

    # -- This pack's own additional surface, for its retriever and commands ----------------

    async def rebuild(self) -> tuple[int, int, int]:
        """Recompute every stored node's `GraphData` from its own stored `content`, using
        the *current* `weft_example_graph.extraction.extract_graph_data` — `weft graph build`'s own
        implementation. Unlike `reconcile`, this re-derives from `content`, not merely from
        the previously-computed `ext`, so it is what actually picks up a change to the
        extraction heuristic itself. Needs nothing this store does not already hold.
        """
        conn = await self._connection()
        examined = 0
        total_entities = 0
        total_relations = 0
        async with conn.cursor() as cur:
            await cur.execute("SELECT id, content FROM exgraph_nodes ORDER BY id")
            rows = await cur.fetchall()
            for row in rows:
                examined += 1
                node_id = cast(NodeId, row["id"])
                entities, relations = extract_graph_data(cast(str, row["content"]))
                data = GraphData(entities=entities, relations=relations)
                await cur.execute(
                    "UPDATE exgraph_nodes "
                    "SET ext = jsonb_set(ext, '{weft-example-graph}', %s::jsonb) "
                    "WHERE id = %s",
                    (Jsonb(_dump_graph_data(data)), node_id),
                )
                await _replace_graph_rows(cur, node_id, data)
                total_entities += len(entities)
                total_relations += len(relations)
        return examined, total_entities, total_relations

    async def summary(self) -> tuple[int, int, int]:
        """`(nodes with graph data, distinct entity names, distinct relation pairs)`."""
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute("SELECT count(DISTINCT node_id) AS n FROM exgraph_entities")
            nodes_with_data = _count_of(await cur.fetchone())
            await cur.execute("SELECT count(DISTINCT name) AS n FROM exgraph_entities")
            entities = _count_of(await cur.fetchone())
            await cur.execute(
                "SELECT count(DISTINCT (source_entity, target_entity, predicate)) AS n "
                "FROM exgraph_relations"
            )
            relations = _count_of(await cur.fetchone())
        return nodes_with_data, entities, relations

    async def top_entities(self, limit: int) -> tuple[tuple[str, int], ...]:
        """The `limit` entity names with the highest corpus-wide mention count."""
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT name, sum(count) AS total FROM exgraph_entities "
                "GROUP BY name ORDER BY total DESC, name ASC LIMIT %s",
                (limit,),
            )
            rows = await cur.fetchall()
        return tuple((cast(str, row["name"]), cast(int, row["total"])) for row in rows)

    async def neighbors_of(self, name: str) -> tuple[tuple[str, str, int], ...]:
        """Every `(neighbor name, predicate, count)` this entity co-occurs with, corpus-wide."""
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT target_entity AS other, predicate, sum(count) AS total "
                "FROM exgraph_relations WHERE source_entity = %s "
                "GROUP BY target_entity, predicate "
                "UNION ALL "
                "SELECT source_entity AS other, predicate, sum(count) AS total "
                "FROM exgraph_relations WHERE target_entity = %s "
                "GROUP BY source_entity, predicate "
                "ORDER BY total DESC, other ASC",
                (name, name),
            )
            rows = await cur.fetchall()
        return tuple(
            (cast(str, row["other"]), cast(str, row["predicate"]), cast(int, row["total"]))
            for row in rows
        )

    async def entity_distances(self, seeds: tuple[str, ...], *, hops: int) -> dict[str, int]:
        """`{entity name: hop distance}` for every seed and everything within `hops` of one,
        walking `exgraph_relations` breadth-first — `weft_example_graph.retriever`'s own graph walk.
        """
        distances: dict[str, int] = dict.fromkeys(seeds, 0)
        frontier = list(seeds)
        if not frontier:
            return distances
        conn = await self._connection()
        async with conn.cursor() as cur:
            for hop in range(1, hops + 1):
                if not frontier:
                    break
                await cur.execute(
                    "SELECT DISTINCT source_entity, target_entity "
                    "FROM exgraph_relations "
                    "WHERE source_entity = ANY(%s) OR target_entity = ANY(%s)",
                    (frontier, frontier),
                )
                rows = await cur.fetchall()
                next_frontier: list[str] = []
                for row in rows:
                    for candidate in (row["source_entity"], row["target_entity"]):
                        name = cast(str, candidate)
                        if name not in distances:
                            distances[name] = hop
                            next_frontier.append(name)
                frontier = next_frontier
        return distances

    async def node_ids_for_entities(self, names: tuple[str, ...]) -> tuple[NodeId, ...]:
        if not names:
            return ()
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT DISTINCT node_id FROM exgraph_entities WHERE name = ANY(%s)",
                (list(names),),
            )
            rows = await cur.fetchall()
        return tuple(cast(NodeId, row["node_id"]) for row in rows)


def _count_of(row: Mapping[str, object] | None) -> int:
    """A `count(...)` query's own `n` column — `0` for a row `fetchone()` never returns,
    which a bare aggregate query never actually does, but pyright has no way to know that.
    """
    return cast(int, row["n"]) if row is not None else 0


async def _live_sources(corpus: NodeStore) -> set[str]:
    """Every source id the primary corpus still holds something for — task **6.21**.

    **Read off `scan()`, not off `list_sources()`, and that is a measurement rather than a
    preference.** `docs/02-extension-model.md` section 1 says `list_sources`/`scan`/`count`
    "already answer what should exist", which is true of the *contract* and was false of the
    running system when this was written: nothing on the ingest path calls `put_source`, so
    `weft_sources` is empty after a real `weft index` and `list_sources()` returns `()`. An
    orphan rule resting on it deleted every graph node the `kg` pipeline had just written —
    found by running the binary, not by this pack's tests, which had populated the double by
    hand (`docs/lessons.md` L6.14, ledger task **6.24**).

    So both are read and unioned: a node's own lineage names the sources it came from and is
    populated by every writer, and `list_sources()` contributes whatever a store that *does*
    keep a source registry knows. Neither can invent a source the other would have missed, and
    the union degrades correctly in both directions.
    """
    live = {str(record.id) for record in await corpus.list_sources()}
    cursor: Cursor | None = None
    while True:
        page = await corpus.scan(cursor)
        for node in page.items:
            live.update(str(source) for source in node.lineage.sources)
        cursor = page.next_cursor
        if cursor is None:
            return live


async def _drop_node(cur: "psycopg.AsyncCursor[dict[str, Any]]", node_id: NodeId) -> int:
    """Remove one orphaned node and everything derived from it. Returns how many rows went.

    Task **6.21**. Reached only from `reconcile(REPAIR)`, for a node none of whose sources the
    primary corpus still lists — see that method's own docstring for what an orphan is and why
    only the corpus can say.
    """
    removed = await _replace_graph_rows(cur, node_id, None)
    await cur.execute("DELETE FROM exgraph_nodes WHERE id = %s", (node_id,))
    return removed + cur.rowcount


async def _replace_graph_rows(
    cur: "psycopg.AsyncCursor[dict[str, Any]]", node_id: NodeId, data: GraphData | None
) -> int:
    """Drop and rewrite one node's own entity/relation rows. Returns how many were dropped."""
    await cur.execute("DELETE FROM exgraph_entities WHERE node_id = %s", (node_id,))
    removed = cur.rowcount
    await cur.execute("DELETE FROM exgraph_relations WHERE node_id = %s", (node_id,))
    removed += cur.rowcount
    if data is None:
        return removed
    if data.entities:
        await cur.executemany(
            "INSERT INTO exgraph_entities (node_id, name, count) VALUES (%s, %s, %s)",
            [(node_id, entity.name, entity.count) for entity in data.entities],
        )
    if data.relations:
        await cur.executemany(
            "INSERT INTO exgraph_relations "
            "(node_id, source_entity, target_entity, predicate, count) VALUES (%s, %s, %s, %s, %s)",
            [
                (node_id, relation.source, relation.target, relation.predicate, relation.count)
                for relation in data.relations
            ],
        )
    return removed


def _graph_data_of(raw_ext: Mapping[str, object]) -> GraphData | None:
    rehydrated = rehydrate_ext(raw_ext)
    found = rehydrated.get(GraphData.__namespace__)
    return found if isinstance(found, GraphData) else None


def _dump_graph_data(data: GraphData) -> dict[str, object]:
    return {**data.model_dump(mode="json"), SCHEMA_VERSION_KEY: GraphData.__schema_version__}


def _node_to_row(node: Node) -> dict[str, object]:
    dump = node.model_dump(mode="json")
    lineage = cast(dict[str, object], dump["lineage"])
    return {
        "id": dump["id"],
        "parents": lineage["parents"],
        "sources": lineage["sources"],
        "content": dump["content"],
        "media_type": dump["media_type"],
        "ext": Jsonb(dump["ext"]),
    }


def _row_to_node(row: Mapping[str, object]) -> Node:
    raw_ext = cast(dict[str, object], row["ext"])
    return Node.model_validate(
        {
            "id": row["id"],
            "lineage": {
                "parents": tuple(cast(list[str], row["parents"])),
                "sources": row["sources"],
            },
            "content": row["content"],
            "media_type": row["media_type"],
            "ext": rehydrate_ext(raw_ext),
        },
        context={"derived": True},
    )


def _row_to_source_record(row: Mapping[str, object]) -> SourceRecord:
    return SourceRecord(
        id=cast(SourceId, row["id"]),
        uri=cast(str, row["uri"]),
        content_hash=cast(str, row["content_hash"]),
        indexed_at=cast(Any, row["indexed_at"]),
        pipeline=cast(str, row["pipeline"]),
        status=SourceStatus(row["status"]),
    )


__all__ = [
    "GraphDsnNotConfiguredError",
    "GraphSettings",
    "GraphStore",
]
