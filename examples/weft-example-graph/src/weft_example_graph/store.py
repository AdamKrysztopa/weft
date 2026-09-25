"""Persist indexed nodes and their graph so a later `weft` process can walk it.

`GraphStore` — the whole store family this pack needs, over Postgres: `NodeStore`,
`SourceDeletable` and `Reconcilable`, all three structurally, the identical path
`examples/weft-example-ingest/src/weft_example_ingest/store.py` takes for its own six.

**Why Postgres, not a plain dict.** `docs/internal/build-ledger.md` task 5.4/5.5 explicitly permits
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
from hashlib import sha256
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
    source_failure,
    source_layers,
    source_status,
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

#: `DOUBLE PRECISION[]`, not pgvector's `vector`: nothing here searches it, so the extension is
#: not a dependency this pack carries.
_ADD_NODES_COLUMNS = """
ALTER TABLE exgraph_nodes
    ADD COLUMN IF NOT EXISTS embedding DOUBLE PRECISION[]
"""

#: One row per `(node, production, source)`, pgvector's `weft_node_productions` (ledger 27.1):
#: `production_key` groups what one `add()` wrote, so `_delete_and_narrow` can tell one production
#: naming two sources from two productions sharing a node.
_CREATE_PRODUCTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS exgraph_node_productions (
    node_id TEXT NOT NULL REFERENCES exgraph_nodes(id) ON DELETE CASCADE,
    production_key TEXT NOT NULL,
    source_id TEXT NOT NULL,
    PRIMARY KEY (node_id, production_key, source_id)
)
"""

#: A node an older version of this pack stored has no production recorded, and the honest reading
#: is one production of its whole `sources` — `weft_store.pgvector_store`'s own backfill. A no-op
#: once every node has one, so it runs on every connect.
_BACKFILL_NODE_PRODUCTIONS = """
INSERT INTO exgraph_node_productions (node_id, production_key, source_id)
SELECT n.id,
       encode(sha256(convert_to(
           array_to_string(ARRAY(SELECT unnest(n.sources) ORDER BY 1), '|'), 'UTF8')), 'hex'),
       s
FROM exgraph_nodes n, unnest(n.sources) AS s
WHERE NOT EXISTS (SELECT 1 FROM exgraph_node_productions p WHERE p.node_id = n.id)
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

#: Added in place, so a table an older version of this pack created is read and written as-is.
_ADD_SOURCES_COLUMNS = """
ALTER TABLE exgraph_sources
    ADD COLUMN IF NOT EXISTS pipeline_identity TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS failure JSONB,
    ADD COLUMN IF NOT EXISTS layers JSONB NOT NULL DEFAULT '[]'::jsonb
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


def _production_key(sources: frozenset[SourceId]) -> str:
    """The digest that groups one `add()` call's rows in `exgraph_node_productions`.

    A digest of the production's own sorted source ids, so writing the same node from the same
    document set twice contributes one production and idempotent re-indexing does not
    accumulate a duplicate — `PgVectorStore._production_key`'s own reasoning, a fresh digest
    rather than an import: that function is a private name of another distribution's module.
    """
    return sha256("|".join(sorted(sources)).encode("utf-8")).hexdigest()


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
    """A second node store beside the primary, holding each batch plus its entity graph.

    `NodeStore`, `SourceDeletable` and `Reconcilable`, all three satisfied structurally —
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
            await cur.execute(_ADD_NODES_COLUMNS)
            await cur.execute(_CREATE_PRODUCTIONS_TABLE)
            await cur.execute(_BACKFILL_NODE_PRODUCTIONS)
            await cur.execute(_CREATE_SOURCES_TABLE)
            await cur.execute(_ADD_SOURCES_COLUMNS)
            await cur.execute(_CREATE_ENTITIES_TABLE)
            await cur.execute(_CREATE_RELATIONS_TABLE)
        self._conn = conn
        return conn

    async def aclose(self) -> None:
        """Close this store's connection, if it opened one.

        Not part of any contract `NodeStore` publishes — `weft_cli.ingest`'s own
        docstring reads this defensively, exactly as it already does for `PgVectorStore`.
        """
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # -- NodeStore -----------------------------------------------------------------------

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        """Store `payload` and pass it on unchanged.

        Args:
            payload: The nodes to store.
            ctx: Unused.

        Returns:
            `Produced` carrying `payload`.
        """
        del ctx
        await self.add(payload)
        return Produced(value=payload)

    async def add(self, nodes: Sequence[Node]) -> None:
        """Upsert `nodes`, merging each one's sources with what is already stored.

        A node already held under the same id has its `lineage.sources` merged with the new
        write's — `check_add_merges_a_nodes_sources_rather_than_replacing_them` — and gets one
        more row per source in `exgraph_node_productions`, so a later `delete_source` can tell
        this write apart from any other production that also named this node (ledger **27.1**).

        Args:
            nodes: The nodes to write.
        """
        if not nodes:
            return
        conn = await self._connection()
        rows = [_node_to_row(node) for node in nodes]
        production_rows = [
            {
                "node_id": node.id,
                "production_key": _production_key(node.lineage.sources),
                "source_id": source,
            }
            for node in nodes
            for source in node.lineage.sources
        ]
        async with conn.cursor() as cur:
            await cur.executemany(
                """
                INSERT INTO exgraph_nodes
                    (id, parents, sources, content, media_type, ext, embedding)
                VALUES (%(id)s, %(parents)s, %(sources)s, %(content)s, %(media_type)s, %(ext)s,
                        %(embedding)s)
                ON CONFLICT (id) DO UPDATE SET
                    parents = EXCLUDED.parents,
                    sources = ARRAY(
                        SELECT DISTINCT unnest(exgraph_nodes.sources || EXCLUDED.sources)
                    ),
                    content = EXCLUDED.content,
                    media_type = EXCLUDED.media_type,
                    ext = EXCLUDED.ext,
                    embedding = EXCLUDED.embedding
                """,
                rows,
            )
            if production_rows:
                await cur.executemany(
                    """
                    INSERT INTO exgraph_node_productions (node_id, production_key, source_id)
                    VALUES (%(node_id)s, %(production_key)s, %(source_id)s)
                    ON CONFLICT (node_id, production_key, source_id) DO NOTHING
                    """,
                    production_rows,
                )
            for node in nodes:
                await _replace_graph_rows(cur, node.id, node.ext_as(GraphData))

    async def flush(self) -> None:
        """A true no-op: `add()` writes immediately, the same choice `PgVectorStore` makes."""
        return

    async def get(self, ids: Sequence[NodeId]) -> Sequence[Node]:
        """Read back the stored nodes among `ids`.

        Args:
            ids: The node ids to look up.

        Returns:
            The nodes found; an id this store does not hold is absent.
        """
        if not ids:
            return ()
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM exgraph_nodes WHERE id = ANY(%s)", (list(ids),))
            rows = await cur.fetchall()
        return tuple(_row_to_node(row) for row in rows)

    async def scan(self, cursor: Cursor | None = None) -> Page[Node]:
        """Read one page of stored nodes in id order.

        Args:
            cursor: Where the previous page ended, or `None` for the first page.

        Returns:
            The page, with the cursor for the next one when more remain.
        """
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
        """Count the stored nodes.

        Returns:
            How many nodes this store holds.
        """
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute("SELECT count(*) AS n FROM exgraph_nodes")
            row = await cur.fetchone()
        return cast(int, row["n"]) if row is not None else 0

    async def put_source(self, record: SourceRecord) -> None:
        """Record one source's indexing outcome, replacing any earlier record for it.

        Args:
            record: The record to write.
        """
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO exgraph_sources
                    (id, uri, content_hash, indexed_at, pipeline, status,
                     pipeline_identity, failure, layers)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    uri = EXCLUDED.uri,
                    content_hash = EXCLUDED.content_hash,
                    indexed_at = EXCLUDED.indexed_at,
                    pipeline = EXCLUDED.pipeline,
                    status = EXCLUDED.status,
                    pipeline_identity = EXCLUDED.pipeline_identity,
                    failure = EXCLUDED.failure,
                    layers = EXCLUDED.layers
                """,
                (
                    record.id,
                    record.uri,
                    record.content_hash,
                    record.indexed_at,
                    record.pipeline,
                    record.status.value,
                    record.pipeline_identity,
                    Jsonb(record.failure.model_dump(mode="json")) if record.failure else None,
                    Jsonb([layer.model_dump(mode="json") for layer in record.layers]),
                ),
            )

    async def get_source(self, source_id: SourceId) -> SourceRecord | None:
        """Look up what this store recorded about one source's last indexing run.

        Args:
            source_id: The source to look up.

        Returns:
            The record, or `None` when this store holds none for `source_id`.
        """
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM exgraph_sources WHERE id = %s", (source_id,))
            row = await cur.fetchone()
        return _row_to_source_record(row) if row is not None else None

    async def list_sources(self) -> Sequence[SourceRecord]:
        """List every source record in id order.

        Returns:
            Every stored source record.
        """
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM exgraph_sources ORDER BY id")
            rows = await cur.fetchall()
        return tuple(_row_to_source_record(row) for row in rows)

    # -- SourceDeletable -------------------------------------------------------------------

    async def delete_source(self, source_id: SourceId) -> Removed:
        """Delete the nodes `source_id` alone produced, and narrow the ones it shares.

        A node another document also produced survives, narrowed rather than deleted — ledger
        **27.1**, `_delete_and_narrow`'s own doctring has the property. Writes a `DELETING`
        tombstone first, so an interruption between the two statements is exactly what
        `reconcile`'s own tombstone-finishing pass (below) resumes rather than restarts.

        Args:
            source_id: The source to remove.

        Returns:
            The source removed, how many nodes were deleted, and how many were narrowed.
        """
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE exgraph_sources SET status = %s WHERE id = %s",
                (SourceStatus.DELETING.value, source_id),
            )
            node_count, narrowed_count = await _delete_and_narrow(cur, source_id)
            await cur.execute("DELETE FROM exgraph_sources WHERE id = %s", (source_id,))
        return Removed(source_id=source_id, node_count=node_count, narrowed_count=narrowed_count)

    # -- Reconcilable ----------------------------------------------------------------------

    async def estimate(self, ctx: Context, mode: ReconcileMode) -> ReconcileEstimate:
        """State what `reconcile` would do in `mode` before it does it.

        `repair`'s `pending` is the outstanding `DELETING` tombstones, the count `reconcile`
        examines (`ReconcileEstimate`); the node recompute it also does is only described.

        Args:
            ctx: The run's context; `full` requires the corpus `NodeStore` on it.
            mode: The reconcile mode to estimate.

        Returns:
            How many nodes the pass would touch, and a description; it calls no model.
        """
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
        pending = len(await self._tombstoned())
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute("SELECT count(*) AS n FROM exgraph_nodes")
            row = await cur.fetchone()
        nodes = cast(int, row["n"]) if row is not None else 0
        return ReconcileEstimate(
            mode=mode,
            pending=pending,
            description=(
                f"{pending} unfinished deletion(s) in weft-example-graph's own store to finish, "
                f"then {nodes} node(s) will have their entities and relations recomputed from "
                f"stored content and reconciled against it"
            ),
            model_calls=0,
        )

    async def reconcile(self, ctx: Context, mode: ReconcileMode) -> ReconcileReport:
        """Converge the graph tables with the corpus after a crash or a missed deletion.

        Finishes this store's own interrupted deletions, repairs its bookkeeping against its
        own stored node content, and, for `full`, also backfills from the corpus.

        **Finishing a tombstone comes first, ledger 27.1, repair R43.54.** `delete_source`
        above writes `status=DELETING` before it deletes, exactly as `PgVectorStore.delete_source`
        does; a crash between the two leaves a source tombstoned and its nodes still standing.
        `examined` counts these tombstones, one per source finished — the identical count
        `estimate`'s own `repair` reading answers — and `removed` carries the node count
        `_delete_and_narrow` reports for each, never the entity/relation row churn the recompute
        pass below also adds to the same field.

        **`repair` then does two more things, and task 6.21 built the second.** It recomputes
        every remaining node's entities/relations from that node's own stored content and
        re-derives them, so a partial write (a crash between the node upsert and the
        entities/relations upsert in `add`, since each statement autocommits independently)
        cannot leave the two out of step. And it **drops orphans** — `docs/02-extension-model.md`
        section 4's own table: "`repair` drops orphans left by anything the [deletion] fan-out
        missed". An orphan is a node here whose source the *primary corpus* no longer lists,
        which this store cannot answer from its own tables and could not ask about at all until
        task 6.19 put the corpus on the passport. The deletion fan-out reaching this store
        in-command (task 6.18) makes an orphan rarer, never impossible: a participant that
        raised part-way through leaves exactly this. Idempotent — running it twice does the
        same work and reaches the same state.

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
            tombstones_examined, tombstones_removed = await self._finish_tombstones(cur)
            examined += tombstones_examined
            removed += tombstones_removed
            removed += await self._repair_against_corpus(cur, live)

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
        """Find the corpus nodes a `full` reconcile still owes this store, to count or backfill.

        Which of `nodes` this store does not already hold — one batched `get` over their
        own ids, never assumed.
        """
        if not nodes:
            return []
        held_ids = {held.id for held in await self.get([node.id for node in nodes])}
        return [node for node in nodes if node.id not in held_ids]

    async def _tombstoned(self) -> tuple[str, ...]:
        """Every source id whose deletion started and did not finish, in id order."""
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id FROM exgraph_sources WHERE status = %s ORDER BY id",
                (SourceStatus.DELETING.value,),
            )
            rows = await cur.fetchall()
        return tuple(cast(str, row["id"]) for row in rows)

    async def _finish_tombstones(
        self, cur: "psycopg.AsyncCursor[dict[str, Any]]"
    ) -> tuple[int, int]:
        """Finish every `DELETING` source this store started and did not end — ledger **27.1**.

        `reconcile`'s own `examined`/`removed` for this half: one tombstone finished is one
        examined, and `removed` carries the node count `_delete_and_narrow` reports for it —
        never the entity/relation row churn `_repair_against_corpus` below also adds to the
        same field.
        """
        examined = 0
        removed = 0
        for source_id in await self._tombstoned():
            node_count, _narrowed_count = await _delete_and_narrow(cur, SourceId(source_id))
            await cur.execute("DELETE FROM exgraph_sources WHERE id = %s", (source_id,))
            examined += 1
            removed += node_count
        return examined, removed

    async def _repair_against_corpus(
        self, cur: "psycopg.AsyncCursor[dict[str, Any]]", live: set[str]
    ) -> int:
        """Drop orphans against `live` and recompute every survivor's graph rows from `ext`.

        Task **6.21** — see `reconcile`'s own docstring for what an orphan is and why only the
        corpus can say. Returns how many entity/relation/node rows this touched.
        """
        await cur.execute("SELECT id, ext, sources FROM exgraph_nodes ORDER BY id")
        rows = await cur.fetchall()
        removed = 0
        for row in rows:
            node_id = cast(NodeId, row["id"])
            sources = {str(source) for source in cast("list[object]", row["sources"])}
            if sources and not (sources & live):
                removed += await _drop_node(cur, node_id)
                continue
            raw_ext = cast(dict[str, object], row["ext"])
            data = _graph_data_of(raw_ext)
            removed += await _replace_graph_rows(cur, node_id, data)
        return removed

    # -- This pack's own additional surface, for its retriever and commands ----------------

    async def rebuild(self) -> tuple[int, int, int]:
        """Pick up a changed extraction heuristic across everything already indexed.

        Recompute every stored node's `GraphData` from its own stored `content`, using
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
        """Every entity within `hops` of a seed, mapped to its hop distance.

        `{entity name: hop distance}` for every seed and everything within `hops` of one,
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
        """Find the nodes that mention any of `names`.

        Args:
            names: The entity names to look up.

        Returns:
            The distinct ids of the nodes mentioning at least one of them.
        """
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
    """A `count(...)` query's own `n` column, or `0` for a missing row.

    A `count(...)` query's own `n` column — `0` for a row `fetchone()` never returns,
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
    hand (`docs/internal/lessons.md` L6.14, ledger task **6.24**).

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


async def _delete_and_narrow(
    cur: "psycopg.AsyncCursor[dict[str, Any]]", source_id: SourceId
) -> tuple[int, int]:
    """Delete the nodes `source_id` alone produced, narrow the ones it shares.

    Ledger **27.1**, repair **R43.54** — shared by `delete_source` and `reconcile`'s own
    tombstone-finishing pass, so an interrupted deletion finishes identically to one that ran
    straight through: `weft_store.pgvector_store.PgVectorStore._delete_and_narrow`'s own shape.

    A node is *doomed* when every production naming it also names `source_id` — no production
    would survive its removal, and deleting its `exgraph_nodes` row cascades its entities,
    relations and productions with it, the foreign keys those tables carry doing what
    `PgVectorStore` does by hand. A node is *narrowed* when at least one production does not
    name `source_id` — that production is untouched evidence the node still exists — and its
    `sources` is recomputed as the union of what remains, never merely `source_id` removed from
    it, because two productions can still overlap in a source neither alone would justify
    keeping.

    Returns:
        How many nodes were deleted, and how many were narrowed.
    """
    await cur.execute(
        """
        WITH tainted AS (
            SELECT node_id, production_key FROM exgraph_node_productions
            WHERE source_id = %(source_id)s
        ), survivors AS (
            SELECT DISTINCT p.node_id FROM exgraph_node_productions p
            LEFT JOIN tainted t ON t.node_id = p.node_id AND t.production_key = p.production_key
            WHERE t.production_key IS NULL
        )
        SELECT DISTINCT t.node_id, (s.node_id IS NOT NULL) AS has_survivor
        FROM tainted t
        LEFT JOIN survivors s ON s.node_id = t.node_id
        """,
        {"source_id": source_id},
    )
    rows = await cur.fetchall()
    doomed = [cast(str, row["node_id"]) for row in rows if not row["has_survivor"]]
    narrowed = [cast(str, row["node_id"]) for row in rows if row["has_survivor"]]
    node_count = 0
    if doomed:
        await cur.execute("DELETE FROM exgraph_nodes WHERE id = ANY(%s)", (doomed,))
        node_count = cur.rowcount
    if narrowed:
        await cur.execute(
            "DELETE FROM exgraph_node_productions WHERE source_id = %s AND node_id = ANY(%s)",
            (source_id, narrowed),
        )
        await cur.execute(
            """
            UPDATE exgraph_nodes n SET sources = sub.arr
            FROM (
                SELECT node_id, ARRAY_AGG(DISTINCT source_id ORDER BY source_id) AS arr
                FROM exgraph_node_productions
                WHERE node_id = ANY(%(narrowed)s)
                GROUP BY node_id
            ) sub
            WHERE n.id = sub.node_id
            """,
            {"narrowed": narrowed},
        )
    return node_count, len(narrowed)


def _graph_data_of(raw_ext: Mapping[str, object]) -> GraphData | None:
    rehydrated = rehydrate_ext(raw_ext)
    found = rehydrated.get(GraphData.__namespace__)
    return found if isinstance(found, GraphData) else None


def _dump_graph_data(data: GraphData) -> dict[str, object]:
    return {**data.model_dump(mode="json"), SCHEMA_VERSION_KEY: GraphData.__schema_version__}


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
        "ext": Jsonb(dump["ext"]),
        "embedding": cast("dict[str, object]", embedding)["values"] if embedding else None,
    }


def _row_to_node(row: Mapping[str, object]) -> Node:
    raw_ext = cast(dict[str, object], row["ext"])
    embedding = row.get("embedding")
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
            "embedding": {"values": cast("list[float]", embedding)}
            if embedding is not None
            else None,
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
        status=source_status(cast(str, row["status"])),
        failure=source_failure(cast("Mapping[str, object]", raw))
        if (raw := row.get("failure")) is not None
        else None,
        layers=source_layers(cast("Sequence[Mapping[str, object]]", row.get("layers") or [])),
    )


__all__ = [
    "GraphDsnNotConfiguredError",
    "GraphSettings",
    "GraphStore",
]
