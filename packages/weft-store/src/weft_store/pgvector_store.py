"""`PgVectorStore` — the built-in `NodeStore` + `VectorSearch`, over Postgres and pgvector.

Specified in `docs/06-phase-0-build.md` step 8: "a pgvector `NodeStore` with
`VectorSearch`... this is where the one container arrives — a `compose.yaml`
with Postgres and pgvector, because G4 retired the zero-container target and
made pgvector the floor." `compose.yaml`, at the repository root, brings up
that one container; `WEFT_DATABASE_URL` in `.env.example` is what a
`PgVectorSettings` block resolves against once discovery interpolates
`${env:...}`.

**Capability is derived, never declared.** This class implements every
method `weft_store.contract.NodeStore` and `VectorSearch` name; nothing here
sets a flag saying so — `isinstance(store, VectorSearch)` at registration is
what makes that true, per `docs/02-extension-model.md` → *The store contract
family*.

**Connection settings are pack settings, not stage `with:` config** — the
same distinction `docs/02-extension-model.md` §2 draws for the graph pack's
`endpoint`/`api_key`: a database connection is one resource shared by
whatever this pack registers, not a per-pipeline-stage tuning knob. `register()`
wires `PgVectorSettings` in through `functools.partial`, exactly the shape
that section's own example shows, so `weft_kernel.runner.Runner.resolve`'s
`entry.factory(spec.config)` call becomes `PgVectorStore(settings, spec.config)`
— `spec.config` is accepted and ignored today; Phase 0 has no stage-level
tuning this store needs.

**The connection is opened lazily**, on first use, never inside `__init__`:
`psycopg.AsyncConnection.connect` is a coroutine, and `__init__` cannot be
one. `autocommit=True` is deliberate — Phase 0's contract already states
"durability is a guarantee, not a call" and "deletion is idempotent and
resumable rather than atomic", so per-statement autocommit is sufficient and
avoids a manual transaction lifecycle this contract does not ask for. The
`vector` extension and this store's two tables are created, idempotently, on
first connect — a store that requires a human to have already run a
migration before `weft index` works once is exactly the friction a walking
skeleton exists to remove.

**`add()` writes immediately; `flush()` is a true no-op.** The contract
permits buffering ("`add()` may buffer") but does not require it, and
writing immediately — one upsert per `add()` call — is the simpler
implementation that still satisfies "`flush` is documented as idempotent":
calling it on a store with nothing buffered is a legitimate no-op, not a
hazard.

**`ext` round-trips through `weft_store.rehydrate`**, not a hand-rolled map
— see that module's docstring for why `Node.model_validate` alone cannot
reconstruct a node's typed extension data from a JSONB column.

**Filters are not yet translated to SQL.** `docs/02-extension-model.md` →
*Filters are data*: "validated at pipeline load against the registered ext
models... nothing in Phase 0 resolves a pipeline against a store's filter
capability yet." `search_vector` therefore accepts `filter` because the
`VectorSearch` Protocol requires it, and raises loudly — never silently
ignores it — if a caller actually supplies one; only `filter=None` is
implemented today.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from functools import partial
from typing import Any, cast

import psycopg
from pgvector import Vector as PgVector
from pgvector.psycopg import register_vector_async
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, SecretStr

from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.errors import WeftError
from weft_kernel.payload import Node, NodeId, Outcome, Produced, SourceId, Vector
from weft_store.contract import (
    Cursor,
    Filter,
    NodeStore,
    Page,
    Removed,
    Scored,
    SourceRecord,
    SourceStatus,
)
from weft_store.rehydrate import rehydrate_ext

_PAGE_SIZE = 100

_CREATE_EXTENSION = "CREATE EXTENSION IF NOT EXISTS vector"

_CREATE_SOURCES_TABLE = """
CREATE TABLE IF NOT EXISTS weft_sources (
    id TEXT PRIMARY KEY,
    uri TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    indexed_at TIMESTAMPTZ NOT NULL,
    pipeline TEXT NOT NULL,
    status TEXT NOT NULL
)
"""

# `embedding` is declared as a bare `vector`, with no fixed dimension: pgvector has allowed an
# unconstrained column since 0.5.0, and this store has no reason to hard-code a dimension the
# configured embedder (`weft-embed`, or any future one) already owns.
_CREATE_NODES_TABLE = """
CREATE TABLE IF NOT EXISTS weft_nodes (
    id TEXT PRIMARY KEY,
    parents TEXT[] NOT NULL,
    sources TEXT[] NOT NULL,
    content TEXT NOT NULL,
    media_type TEXT NOT NULL,
    embedding VECTOR,
    ext JSONB NOT NULL
)
"""


class PgVectorSettings(BaseModel):
    """`weft-store`'s pack settings: one connection string, shared by everything it registers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dsn: SecretStr


class UnsupportedFilterError(WeftError):
    """`search_vector` was given a `Filter` this store cannot yet translate to SQL.

    Phase 0 has no pipeline-resolution step that validates a `Filter` against
    a store's capability, so this store refuses loudly at query time instead
    — the same "no silent fallback" standard every other unimplemented-but-
    requested capability in this project is held to.
    """


class PgVectorStore:
    """A `NodeStore` and `VectorSearch` over Postgres, with pgvector for the vector column.

    Satisfies both contracts structurally — this class never imports either
    Protocol, the same path any third-party store pack takes.
    """

    def __init__(self, settings: PgVectorSettings, config: object = None) -> None:
        del config  # nothing at the stage level this store needs — see the module docstring
        self._dsn = settings.dsn.get_secret_value()
        self._conn: psycopg.AsyncConnection[dict[str, Any]] | None = None

    async def _connection(self) -> psycopg.AsyncConnection[dict[str, Any]]:
        """The lazily-opened, schema-provisioned connection this store reuses for its lifetime."""
        if self._conn is not None:
            return self._conn
        # Parameterising the class explicitly, rather than relying on inference from
        # `row_factory=dict_row`, is what makes `Self` bind to `AsyncConnection[dict[str, Any]]`
        # under strict checking — inference alone resolves `Row` to the class's `TupleRow`
        # default before it ever looks at `dict_row`'s own return type.
        conn = await psycopg.AsyncConnection[dict[str, Any]].connect(
            self._dsn, autocommit=True, row_factory=dict_row
        )
        async with conn.cursor() as cur:
            await cur.execute(_CREATE_EXTENSION)
        # `pgvector`'s type adapter looks the `vector` type up by name in the database's own
        # catalog, so it must register *after* `CREATE EXTENSION` has run at least once, never
        # before — a fresh database has no `vector` type until this statement creates it.
        await register_vector_async(conn)
        async with conn.cursor() as cur:
            await cur.execute(_CREATE_SOURCES_TABLE)
            await cur.execute(_CREATE_NODES_TABLE)
        self._conn = conn
        return conn

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        """Store `payload` and pass it through — the module docstring's narrowing note."""
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
                INSERT INTO weft_nodes (id, parents, sources, content, media_type, embedding, ext)
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
        """A true no-op: `add()` writes immediately — see the module docstring."""
        return

    async def get(self, ids: Sequence[NodeId]) -> Sequence[Node]:
        if not ids:
            return ()
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM weft_nodes WHERE id = ANY(%s)", (list(ids),))
            rows = await cur.fetchall()
        return tuple(_row_to_node(row) for row in rows)

    async def delete_source(self, source_id: SourceId) -> Removed:
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE weft_sources SET status = %s WHERE id = %s",
                (SourceStatus.DELETING.value, source_id),
            )
            await cur.execute("DELETE FROM weft_nodes WHERE %s = ANY(sources)", (source_id,))
            node_count = cur.rowcount
            await cur.execute("DELETE FROM weft_sources WHERE id = %s", (source_id,))
        return Removed(source_id=source_id, node_count=node_count)

    async def scan(self, cursor: Cursor | None = None) -> Page[Node]:
        conn = await self._connection()
        after = cursor if cursor is not None else ""
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM weft_nodes WHERE id > %s ORDER BY id LIMIT %s",
                (after, _PAGE_SIZE + 1),
            )
            rows = await cur.fetchall()
        has_more = len(rows) > _PAGE_SIZE
        page_rows = rows[:_PAGE_SIZE]
        next_cursor = Cursor(cast(str, page_rows[-1]["id"])) if has_more else None
        return Page(items=tuple(_row_to_node(row) for row in page_rows), next_cursor=next_cursor)

    async def count(self) -> int:
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) AS n FROM weft_nodes")
            row = await cur.fetchone()
        return cast(int, row["n"]) if row is not None else 0

    async def put_source(self, record: SourceRecord) -> None:
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO weft_sources (id, uri, content_hash, indexed_at, pipeline, status)
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
            await cur.execute("SELECT * FROM weft_sources WHERE id = %s", (source_id,))
            row = await cur.fetchone()
        return _row_to_source_record(row) if row is not None else None

    async def list_sources(self) -> Sequence[SourceRecord]:
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM weft_sources ORDER BY id")
            rows = await cur.fetchall()
        return tuple(_row_to_source_record(row) for row in rows)

    async def search_vector(
        self, vector: Vector, top_k: int, filter: Filter | None = None
    ) -> Sequence[Scored[Node]]:
        if filter is not None:
            raise UnsupportedFilterError(
                "PgVectorStore.search_vector does not yet translate Filter to SQL — "
                "Phase 0 resolves no pipeline against a store's filter capability. "
                "Pass filter=None."
            )
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT *, embedding <=> %(vector)s AS distance
                FROM weft_nodes
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> %(vector)s
                LIMIT %(top_k)s
                """,
                # Wrapped in `pgvector.Vector`, not passed as a bare list: a plain Python list
                # adapts to a Postgres array, and `<=>` has no overload comparing `vector` to
                # `double precision[]`. `register_vector_async` is what makes `PgVector` dump as
                # the `vector` type instead.
                {"vector": PgVector(list(vector.values)), "top_k": top_k},
            )
            rows = await cur.fetchall()
        return [
            Scored(value=_row_to_node(row), score=1.0 - cast(float, row["distance"]))
            for row in rows
        ]

    async def aclose(self) -> None:
        """Close the underlying connection, if one was ever opened. Not part of any contract."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None


def register(registrar: PackRegistrar, settings: PgVectorSettings) -> None:
    """Register `PgVectorStore` as `"pgvector"` for `NodeStore`. The only plugin this pack ships."""
    registrar.add(NodeStore, "pgvector", partial(PgVectorStore, settings))


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
            # `pgvector`'s registered adapter (`register_vector_async`) decodes the `vector`
            # column into its own `pgvector.Vector` wrapper, not a plain sequence — `.to_list()`
            # is what turns it back into the floats `weft_kernel.payload.Vector` wants.
            "embedding": {"values": cast(PgVector, embedding).to_list()}
            if embedding is not None
            else None,
            "ext": rehydrate_ext(raw_ext),
        },
        context={"derived": True},
    )


def _row_to_source_record(row: Mapping[str, object]) -> SourceRecord:
    return SourceRecord(
        id=SourceId(cast(str, row["id"])),
        uri=cast(str, row["uri"]),
        content_hash=cast(str, row["content_hash"]),
        indexed_at=cast(datetime, row["indexed_at"]),
        pipeline=cast(str, row["pipeline"]),
        status=SourceStatus(cast(str, row["status"])),
    )
