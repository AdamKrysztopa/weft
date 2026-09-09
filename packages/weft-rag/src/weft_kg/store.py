"""`GraphStore` — `NodeStore`, `SourceDeletable` and `Reconcilable`, over Postgres. Ledger **11.5**.

**Carries forward the design of the out-of-tree graph pack's own store module, one task earlier
in this same project's own history.** That module is Weft's own code, written for the identical
shape, and this one reuses its design rather than reinventing it — `NOTICE` case 2 does not apply,
because carrying a project's own prior work forward within the same project is not a third party's
text. First-party core deliberately does not name that out-of-tree pack by its own identifiers —
fitness function 9(b) — so this docstring describes the reuse without spelling them. What is new
here: `GraphSettings.dsn` defaults empty for the reason its own docstring below states, and this
store additionally keeps `kg_entities`, `kg_entity_nodes` and `kg_relations` — the minimum table
set `weft_kg.traversal.GraphWalk` reads, via `put_entity`/`put_relation`. Task **11.8** owns that
table's real design (aliases, canonical ids, a schema version row); this ships the smallest thing
that can hold `Entity`'s two fields and the edges between them.

**Sits beside the vector store, literally** — `docs/02-extension-model.md` §4: "Graph store |
`NodeStore` | ... Sits beside the vector store." This class persists a *full* `Node` — content,
lineage, `ext`, embedding — exactly as `weft_store.pgvector_store.PgVectorStore` does, so a
document naming both `store: pgvector` and `store: graph` (`pipelines/index-with-graph.yaml`) hands
the identical batch to each.

**`ext` round-trips through `weft_store.rehydrate`, not a hand-rolled map** — the published
extension point `docs/02-extension-model.md` §1 names, reused here exactly as `PgVectorStore`
already does, so a node carrying any installed pack's ext data survives a round trip through this
store with no special-casing here.

**No row outlives the nodes that support it — the Phase 11 preamble's narrowing of G15, and it is
schema, not an optimisation.** `kg_entity_nodes.node_id` carries `ON DELETE CASCADE` against
`kg_nodes(id)`, so deleting a node's row removes its entity-attachment rows for free; an entity
left with none is dropped explicitly by `_drop_orphaned_entities` (Postgres cascades a child's
deletion from its parent, never the reverse), and `kg_relations` in turn cascades from
`kg_entities` — one entity gone takes every relation naming it with it.
"""

from collections.abc import Mapping, Sequence
from hashlib import sha256
from typing import Any, cast

import psycopg
from pgvector import Vector as PgVector
from pgvector.psycopg import register_vector_async
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, SecretStr

from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.payload import Node, NodeId, Outcome, Produced, SourceId, Vector
from weft_kg.contract import EntityId
from weft_store.contract import (
    Cursor,
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

_CREATE_EXTENSION = "CREATE EXTENSION IF NOT EXISTS vector"

# `embedding` is a bare `vector`, unconstrained — the identical choice `PgVectorStore` makes
# and for the identical reason: this store has no business hard-coding a dimension the
# configured embedder owns.
_CREATE_NODES_TABLE = """
CREATE TABLE IF NOT EXISTS kg_nodes (
    id TEXT PRIMARY KEY,
    parents TEXT[] NOT NULL,
    sources TEXT[] NOT NULL,
    content TEXT NOT NULL,
    media_type TEXT NOT NULL,
    embedding VECTOR,
    ext JSONB NOT NULL
)
"""

_CREATE_SOURCES_TABLE = """
CREATE TABLE IF NOT EXISTS kg_sources (
    id TEXT PRIMARY KEY,
    uri TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    indexed_at TIMESTAMPTZ NOT NULL,
    pipeline TEXT NOT NULL,
    status TEXT NOT NULL,
    pipeline_identity TEXT NOT NULL DEFAULT ''
)
"""

#: Task **11.8** owns the real shape of an entity row — this is the minimum the four
#: `GraphTraversal` members answer over: an id, a name, and (for `nearest_entities`) a vector.
_CREATE_ENTITIES_TABLE = """
CREATE TABLE IF NOT EXISTS kg_entities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    embedding VECTOR
)
"""

#: The join a node's deletion cascades through — see the module docstring's note on G15.
_CREATE_ENTITY_NODES_TABLE = """
CREATE TABLE IF NOT EXISTS kg_entity_nodes (
    entity_id TEXT NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    node_id TEXT NOT NULL REFERENCES kg_nodes(id) ON DELETE CASCADE,
    PRIMARY KEY (entity_id, node_id)
)
"""

#: `neighbourhood`'s own edges. Stored with a direction — `predicate` reads `source -> target`
#: — even though `GraphTraversal.neighbourhood` walks it undirected; see `traversal.py`.
_CREATE_RELATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS kg_relations (
    source_entity TEXT NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    target_entity TEXT NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    predicate TEXT NOT NULL,
    PRIMARY KEY (source_entity, target_entity, predicate)
)
"""


class GraphSettings(BaseModel):
    """This pack's one connection setting — `[packs.graph]` in `weft.toml`.

    **`dsn` defaults to empty, unlike `weft_store.pgvector_store.PgVectorSettings.dsn`, and that
    is deliberate rather than an oversight.** `register()` must succeed on a machine with no
    `weft.toml` at all — a project that never names this pack should see an ordinary `active` row
    in `weft plugins doctor`, not a `failed` one it has to read past, the way `weft-store`'s own
    mandatory `dsn` correctly produces for the store an operator *is* required to configure. This
    store's connection is opened lazily (`_connection`, never from `__init__` or `register()`), so
    an empty default costs nothing at registration time and the refusal moves to the first call
    that genuinely needs one — `require_dsn` below.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    dsn: SecretStr = SecretStr("")


class GraphDsnNotConfiguredError(WeftError):
    """`[packs.graph] dsn` was never set, and this call needs a real connection.

    Raised only where a connection is actually opened — never at `register()`, which never calls
    `_connection` — so a pack installed with no settings still registers cleanly and fails exactly
    where an operator's mistake becomes consequential.
    """


def require_dsn(settings: GraphSettings) -> str:
    dsn = settings.dsn.get_secret_value()
    if not dsn:
        raise GraphDsnNotConfiguredError(
            "weft_kg has no database to talk to: [packs.graph] dsn is unset. Add "
            '`[packs.graph]\ndsn = "${env:WEFT_DATABASE_URL}"` (or a literal DSN) to '
            "weft.toml. Exporting WEFT_DATABASE_URL alone is not enough: this pack is "
            "offered no ambient setting, so the one line above is what points it at the "
            "container [packs.store] already uses.",
            pack="weft-rag",
        )
    return dsn


async def provision_schema(conn: "psycopg.AsyncConnection[dict[str, Any]]") -> None:
    """Create every table this pack's two classes read and write, idempotently, on first use.

    Shared by `GraphStore._connection` and `GraphWalk._connection`, because either may be the
    first to dial in a given process — a run naming only `[services] graph` and no `store:
    graph` stage must not find `kg_relations` missing. Order matters: `kg_entity_nodes` and
    `kg_relations` both carry a foreign key, so their own referents are created first.
    """
    async with conn.cursor() as cur:
        await cur.execute(_CREATE_EXTENSION)
    # `pgvector`'s type adapter looks the `vector` type up by name in the database's own
    # catalog, so it must register *after* `CREATE EXTENSION` has run at least once.
    await register_vector_async(conn)
    async with conn.cursor() as cur:
        await cur.execute(_CREATE_NODES_TABLE)
        await cur.execute(_CREATE_SOURCES_TABLE)
        await cur.execute(_CREATE_ENTITIES_TABLE)
        await cur.execute(_CREATE_ENTITY_NODES_TABLE)
        await cur.execute(_CREATE_RELATIONS_TABLE)


async def _drop_orphaned_entities(cur: "psycopg.AsyncCursor[dict[str, Any]]") -> None:
    """Remove every entity with no remaining `kg_entity_nodes` row — the module docstring's G15
    note. Postgres cascades a child's row from its parent's deletion, never the reverse, so this
    is the explicit other half: called after any statement that may have removed a node.
    """
    await cur.execute(
        "DELETE FROM kg_entities e WHERE NOT EXISTS "
        "(SELECT 1 FROM kg_entity_nodes en WHERE en.entity_id = e.id)"
    )


class GraphStore:
    """`NodeStore`, `SourceDeletable` and `Reconcilable`, all three satisfied structurally — this
    class never imports one of the Protocols, the same path any third-party store pack takes.

    Plus `put_entity`/`put_relation`, this task's own addition and not on any contract:
    `weft_kg.traversal.GraphWalk` needs something to read, and ledger tasks **11.6**/**11.7** are
    the producers that will call these for real. Deliberately its own class rather than shared
    with `GraphWalk` — see `weft_kg/__init__.py`'s module docstring on `L11.23`: one class under
    both `NodeStore` and `GraphTraversal` would let the fan-out's `NodeStore` filter be skipped
    entirely.
    """

    def __init__(self, settings: GraphSettings, config: object = None) -> None:
        del config  # the kernel's `factory(None)` convention — nothing at the stage level needed
        self._settings = settings
        self._conn: psycopg.AsyncConnection[dict[str, Any]] | None = None

    async def _connection(self) -> "psycopg.AsyncConnection[dict[str, Any]]":
        """The lazily-opened, schema-provisioned connection this store reuses for its lifetime."""
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
        """Not part of any contract `NodeStore` publishes — read defensively, exactly as
        `weft_cli`'s own fan-out already does for `PgVectorStore`.
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
                INSERT INTO kg_nodes (id, parents, sources, content, media_type, embedding, ext)
                VALUES (%(id)s, %(parents)s, %(sources)s, %(content)s, %(media_type)s,
                        %(embedding)s, %(ext)s)
                ON CONFLICT (id) DO UPDATE SET
                    parents = EXCLUDED.parents,
                    sources = EXCLUDED.sources,
                    content = EXCLUDED.content,
                    media_type = EXCLUDED.media_type,
                    embedding = EXCLUDED.embedding,
                    ext = EXCLUDED.ext
                """,
                rows,
            )

    async def flush(self) -> None:
        """A true no-op: `add()` writes immediately, the same choice `PgVectorStore` makes."""
        return

    async def get(self, ids: Sequence[NodeId]) -> Sequence[Node]:
        if not ids:
            return ()
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM kg_nodes WHERE id = ANY(%s)", (list(ids),))
            rows = await cur.fetchall()
        return tuple(_row_to_node(row) for row in rows)

    async def scan(self, cursor: Cursor | None = None) -> Page[Node]:
        conn = await self._connection()
        after = cursor if cursor is not None else ""
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM kg_nodes WHERE id > %s ORDER BY id LIMIT %s",
                (after, _PAGE_SIZE + 1),
            )
            rows = await cur.fetchall()
        return _page_of(rows)

    async def count(self) -> int:
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute("SELECT count(*) AS n FROM kg_nodes")
            row = await cur.fetchone()
        return cast(int, row["n"]) if row is not None else 0

    async def put_source(self, record: SourceRecord) -> None:
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO kg_sources
                    (id, uri, content_hash, indexed_at, pipeline, status, pipeline_identity)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    uri = EXCLUDED.uri,
                    content_hash = EXCLUDED.content_hash,
                    indexed_at = EXCLUDED.indexed_at,
                    pipeline = EXCLUDED.pipeline,
                    status = EXCLUDED.status,
                    pipeline_identity = EXCLUDED.pipeline_identity
                """,
                (
                    record.id,
                    record.uri,
                    record.content_hash,
                    record.indexed_at,
                    record.pipeline,
                    record.status.value,
                    record.pipeline_identity,
                ),
            )

    async def get_source(self, source_id: SourceId) -> SourceRecord | None:
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM kg_sources WHERE id = %s", (source_id,))
            row = await cur.fetchone()
        return _row_to_source_record(row) if row is not None else None

    async def list_sources(self) -> Sequence[SourceRecord]:
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM kg_sources ORDER BY id")
            rows = await cur.fetchall()
        return tuple(_row_to_source_record(row) for row in rows)

    # -- SourceDeletable -------------------------------------------------------------------

    async def delete_source(self, source_id: SourceId) -> Removed:
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE kg_sources SET status = %s WHERE id = %s",
                (SourceStatus.DELETING.value, source_id),
            )
            await cur.execute("DELETE FROM kg_nodes WHERE %s = ANY(sources)", (source_id,))
            node_count = cur.rowcount
            await _drop_orphaned_entities(cur)
            await cur.execute("DELETE FROM kg_sources WHERE id = %s", (source_id,))
        return Removed(source_id=source_id, node_count=node_count)

    # -- Reconcilable ----------------------------------------------------------------------

    async def reconcile(self, ctx: Context, mode: ReconcileMode) -> ReconcileReport:
        """Finish every deletion that was interrupted — the identical tombstone convergence
        `PgVectorStore.reconcile` carries out, over this store's own `kg_sources`/`kg_nodes`, with
        orphaned entities dropped alongside each node deletion.
        """
        del ctx
        conn = await self._connection()
        examined = 0
        removed = 0
        for source_id in await self._tombstoned():
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM kg_nodes WHERE %s = ANY(sources)", (source_id,))
                removed += cur.rowcount
                await _drop_orphaned_entities(cur)
                await cur.execute("DELETE FROM kg_sources WHERE id = %s", (source_id,))
            examined += 1
        return ReconcileReport(
            mode=mode,
            examined=examined,
            removed=removed,
            remaining=len(await self._tombstoned()),
        )

    async def estimate(self, ctx: Context, mode: ReconcileMode) -> ReconcileEstimate:
        """The honest cost of `reconcile` — see its own docstring. `model_calls` is always `0`:
        this store backfills nothing, it only finishes deletions already in flight.
        """
        del ctx
        pending = len(await self._tombstoned())
        description = (
            f"{pending} source(s) have an unfinished deletion to finish"
            if pending
            else "no unfinished deletions; nothing to converge"
        )
        return ReconcileEstimate(mode=mode, pending=pending, description=description)

    async def _tombstoned(self) -> tuple[str, ...]:
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id FROM kg_sources WHERE status = %s ORDER BY id",
                (SourceStatus.DELETING.value,),
            )
            rows = await cur.fetchall()
        return tuple(cast(str, row["id"]) for row in rows)

    # -- This task's own addition — nothing on any contract; see the class docstring ------

    async def put_entity(
        self, *, name: str, nodes: Sequence[NodeId], embedding: Vector | None = None
    ) -> EntityId:
        """Upsert an entity by `name`, attach it to every id in `nodes`, and return its id.

        **Deterministic for a given name** — `_entity_id_for` derives the id from `name` alone,
        so calling this twice with the same name upserts the same row rather than creating a
        second one with no way back to the first.
        """
        entity_id = _entity_id_for(name)
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO kg_entities (id, name, embedding)
                VALUES (%(id)s, %(name)s, %(embedding)s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    embedding = COALESCE(EXCLUDED.embedding, kg_entities.embedding)
                """,
                {
                    "id": entity_id,
                    "name": name,
                    "embedding": PgVector(list(embedding.values))
                    if embedding is not None
                    else None,
                },
            )
            if nodes:
                await cur.executemany(
                    "INSERT INTO kg_entity_nodes (entity_id, node_id) VALUES (%s, %s) "
                    "ON CONFLICT DO NOTHING",
                    [(entity_id, node_id) for node_id in nodes],
                )
        return entity_id

    async def put_relation(self, *, source: EntityId, target: EntityId, predicate: str) -> None:
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO kg_relations (source_entity, target_entity, predicate) "
                "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (source, target, predicate),
            )


def _entity_id_for(name: str) -> EntityId:
    """A deterministic id for `name` — same name, same id, within this store.

    A digest rather than the name itself so an entity id is stable characters `psycopg` and a
    URL both handle uninspected, and so that `put_entity`'s `ON CONFLICT (id)` is exactly the
    same row a second call with the same name would touch. This is *not* the canonical-id
    resolution ledger task **11.8** owns — no alias, no merge — only the minimum determinism
    `put_entity`'s own contract promises.
    """
    return EntityId(sha256(name.encode("utf-8")).hexdigest()[:32])


def _page_of(rows: Sequence[Mapping[str, object]]) -> Page[Node]:
    page_rows = rows[:_PAGE_SIZE]
    has_more = len(rows) > _PAGE_SIZE
    next_cursor = Cursor(cast(str, page_rows[-1]["id"])) if has_more else None
    return Page(items=tuple(_row_to_node(row) for row in page_rows), next_cursor=next_cursor)


def _node_to_row(node: Node) -> dict[str, object]:
    dump = node.model_dump(mode="json")
    lineage = cast(dict[str, object], dump["lineage"])
    embedding = dump["embedding"]
    return {
        "id": dump["id"],
        "parents": lineage["parents"],
        "sources": lineage["sources"],
        "content": dump["content"],
        "media_type": dump["media_type"],
        "embedding": cast("dict[str, object]", embedding)["values"] if embedding else None,
        "ext": Jsonb(dump["ext"]),
    }


def _row_to_node(row: Mapping[str, object]) -> Node:
    embedding = row["embedding"]
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
            "embedding": {"values": cast(PgVector, embedding).to_list()}
            if embedding is not None
            else None,
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
        pipeline_identity=cast(str, row.get("pipeline_identity") or ""),
        status=SourceStatus(row["status"]),
    )


__all__ = [
    "GraphDsnNotConfiguredError",
    "GraphSettings",
    "GraphStore",
]
