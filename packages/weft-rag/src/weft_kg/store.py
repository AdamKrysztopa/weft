"""`GraphStore` — `NodeStore`, `SourceDeletable` and `Reconcilable`, over Postgres. Ledger **11.5**,
schema and resolution pass at **11.8**.

**Carries forward the design of the out-of-tree graph pack's own store module, one task earlier
in this same project's own history.** That module is Weft's own code, written for the identical
shape, and this one reuses its design rather than reinventing it — `NOTICE` case 2 does not apply,
because carrying a project's own prior work forward within the same project is not a third party's
text. First-party core deliberately does not name that out-of-tree pack by its own identifiers —
fitness function 9(b) — so this docstring describes the reuse without spelling them.

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
`kg_nodes(id)`, so deleting a node's row removes its entity-attachment rows for free; an alias
left with none is dropped explicitly by `_drop_orphaned_entities`, and an entity left with no
alias follows it, one statement later (Postgres cascades a child's deletion from its parent, never
the reverse). `kg_relations` cascades from `kg_aliases` in turn — one alias gone takes every
relation naming it with it.

**Ledger `11.8` — a surface form is an alias, an entity is what aliases point at.** `kg_entities`
and `kg_relations` used to key on the entity id directly; now `kg_entity_nodes` and `kg_relations`
key on the **alias**, so a resolution pass that re-points one alias's `entity_id` moves every row
of evidence that named it in a single `UPDATE`, and deletes nothing. `put_entity` returns the
alias id it upserted, not the entity id — `weft_kg.traversal.GraphWalk` is what resolves an alias
to the canonical entity a caller asks about.
"""

from collections.abc import Mapping, Sequence
from hashlib import sha256
from typing import Any, Final, NewType, cast

import psycopg
from pgvector import Vector as PgVector
from pgvector.psycopg import register_vector_async
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, SecretStr

from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.payload import Node, NodeId, Outcome, Produced, SourceId, Vector
from weft_kg import resolution
from weft_kg.contract import EntityId
from weft_kg.payload import CooccurrenceGraph, ExtractedFact, MentionedEntity
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

#: `S5`, per surface: a persisted schema carries its own version in the stored bytes, because at
#: the read site the pack that wrote it may not be the one installed. `KG_SCHEMA_SURFACE` is the
#: `kg_schema.surface` this pack's own tables answer under — a second surface (e.g. a future
#: alternate storage engine for the same capability) would carry its own row and its own version,
#: never share this one.
KG_SCHEMA_VERSION: Final[str] = "2.0.0"
KG_SCHEMA_SURFACE: Final[str] = "tables"

#: An alias's identity — a surface form the corpus actually wrote, distinct from the entity it
#: currently resolves to. See the module docstring's note on ledger `11.8`.
AliasId = NewType("AliasId", str)


class GraphSchemaVersionRefusedError(WeftError):
    """`kg_schema` disagrees with this installed pack, or predates it entirely.

    Raised rather than silently migrated in either case: the rows underneath are an operator's
    data, and guessing at their shape means misreading it. Both cases name what was found and
    what an operator can do about it — see `provision_schema`.
    """


_CREATE_EXTENSION = "CREATE EXTENSION IF NOT EXISTS vector"

#: `similarity(text, text)` — the lexical half of the resolution pass's blended score, and the
#: index that keeps `kg_aliases a JOIN kg_aliases b` from being an unindexed scan over every pair.
_CREATE_TRGM_EXTENSION = "CREATE EXTENSION IF NOT EXISTS pg_trgm"

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

#: The version row — see `KG_SCHEMA_VERSION`'s own docstring.
_CREATE_SCHEMA_TABLE = """
CREATE TABLE IF NOT EXISTS kg_schema (
    surface TEXT PRIMARY KEY,
    version TEXT NOT NULL
)
"""

#: The canonical row a resolved name points at. `id` is `_entity_id_for` of whichever alias name
#: is currently the cluster's representative — stable for as long as the cluster's membership is,
#: never a fact about how many times a resolution pass has run (see `_run_resolution_pass`).
_CREATE_ENTITIES_TABLE = """
CREATE TABLE IF NOT EXISTS kg_entities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    embedding VECTOR
)
"""

#: One surface form the corpus actually wrote. `entity_id` is what a resolution pass moves;
#: `name` is unique because `_alias_id_for` derives `id` from `name` alone, so a second write of
#: the same surface form is the same row, never a duplicate racing it for the same identity.
_CREATE_ALIASES_TABLE = """
CREATE TABLE IF NOT EXISTS kg_aliases (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    entity_id TEXT NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    embedding VECTOR
)
"""

#: The join a node's deletion cascades through — see the module docstring's note on G15. Keyed on
#: the alias, not the entity: re-pointing an alias's `entity_id` moves this row's meaning with it
#: for free, with no `UPDATE` against this table at all.
_CREATE_ENTITY_NODES_TABLE = """
CREATE TABLE IF NOT EXISTS kg_entity_nodes (
    alias_id TEXT NOT NULL REFERENCES kg_aliases(id) ON DELETE CASCADE,
    node_id TEXT NOT NULL REFERENCES kg_nodes(id) ON DELETE CASCADE,
    PRIMARY KEY (alias_id, node_id)
)
"""

#: `neighbourhood`'s own edges. Stored with a direction — `predicate` reads `source -> target`
#: — even though `GraphTraversal.neighbourhood` walks it undirected; see `traversal.py`. Keyed
#: on the alias for the identical reason `kg_entity_nodes` is: a merge re-points both endpoints
#: for free.
_CREATE_RELATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS kg_relations (
    source_alias TEXT NOT NULL REFERENCES kg_aliases(id) ON DELETE CASCADE,
    target_alias TEXT NOT NULL REFERENCES kg_aliases(id) ON DELETE CASCADE,
    predicate TEXT NOT NULL,
    PRIMARY KEY (source_alias, target_alias, predicate)
)
"""

_CREATE_ALIAS_TRGM_INDEX = (
    "CREATE INDEX IF NOT EXISTS kg_aliases_name_trgm_idx "
    "ON kg_aliases USING gin (name gin_trgm_ops)"
)


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


async def _refuse_pre_118_layout(conn: "psycopg.AsyncConnection[dict[str, Any]]") -> None:
    """Refuse a `kg_nodes` table with no `kg_schema` row — the layout these tables had before
    ledger `11.8`, where `kg_entities` and `kg_relations` keyed on entity ids directly rather
    than on an alias. Checked **before creating anything**, because the tables these rows would
    live beside are about to be created `IF NOT EXISTS`, which would otherwise silently adopt an
    operator's pre-11.8 rows into the new layout's columns.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT to_regclass('kg_nodes') IS NOT NULL AS nodes_exist, "
            "to_regclass('kg_schema') IS NOT NULL AS schema_exists"
        )
        row = await cur.fetchone()
    if row is not None and row["nodes_exist"] and not row["schema_exists"]:
        raise GraphSchemaVersionRefusedError(
            "weft_kg found an existing kg_nodes table with no kg_schema row — the layout these "
            "tables had before ledger task 11.8, where kg_entities and kg_relations keyed on "
            "entity ids directly rather than on an alias. Those rows are an operator's own "
            "data, and this pack refuses to guess at their shape rather than silently reading "
            f"or rewriting them: drop kg_nodes, kg_sources, kg_entities, kg_entity_nodes and "
            f"kg_relations (they hold only state this pack can rebuild by re-indexing) and let "
            f"it recreate them at {KG_SCHEMA_VERSION!r}, or migrate them to that layout by hand "
            f"before running weft again.",
            pack="weft-rag",
        )


async def _check_schema_version(conn: "psycopg.AsyncConnection[dict[str, Any]]") -> None:
    """Read `kg_schema` for `KG_SCHEMA_SURFACE`: absent inserts `KG_SCHEMA_VERSION`, present and
    equal does nothing, present and different refuses — naming both versions and what an
    operator can do about it, because a refusal that names only one is a crash with better
    manners than a plain exception and nothing more.
    """
    async with conn.cursor() as cur:
        await cur.execute("SELECT version FROM kg_schema WHERE surface = %s", (KG_SCHEMA_SURFACE,))
        row = await cur.fetchone()
        if row is None:
            await cur.execute(
                "INSERT INTO kg_schema (surface, version) VALUES (%s, %s)",
                (KG_SCHEMA_SURFACE, KG_SCHEMA_VERSION),
            )
            return
    stored = cast(str, row["version"])
    if stored != KG_SCHEMA_VERSION:
        raise GraphSchemaVersionRefusedError(
            f"weft_kg's kg_schema row for surface {KG_SCHEMA_SURFACE!r} is at version "
            f"{stored!r}, but this installed pack knows {KG_SCHEMA_VERSION!r}. Refusing to "
            f"read kg_* tables written by a different schema version rather than guessing at "
            f"their shape: install the version of weft-rag that wrote {stored!r}, or migrate "
            f"the tables to {KG_SCHEMA_VERSION!r} and update the kg_schema row yourself.",
            pack="weft-rag",
        )


async def provision_schema(conn: "psycopg.AsyncConnection[dict[str, Any]]") -> None:
    """Create every table this pack's two classes read and write, idempotently, on first use.

    Shared by `GraphStore._connection` and `GraphWalk._connection`, because either may be the
    first to dial in a given process — a run naming only `[services] graph` and no `store:
    graph` stage must not find `kg_relations` missing.

    **Order, and no other**: refuse the pre-11.8 layout before creating anything; create the
    extensions and register the vector adapter; create the tables, `kg_entities` and
    `kg_aliases` before the two that reference them; then check `kg_schema` against
    `KG_SCHEMA_VERSION`, which can only be answered once the table exists to answer it from.
    """
    await _refuse_pre_118_layout(conn)
    async with conn.cursor() as cur:
        await cur.execute(_CREATE_EXTENSION)
        await cur.execute(_CREATE_TRGM_EXTENSION)
    # `pgvector`'s type adapter looks the `vector` type up by name in the database's own
    # catalog, so it must register *after* `CREATE EXTENSION` has run at least once.
    await register_vector_async(conn)
    async with conn.cursor() as cur:
        await cur.execute(_CREATE_NODES_TABLE)
        await cur.execute(_CREATE_SOURCES_TABLE)
        await cur.execute(_CREATE_SCHEMA_TABLE)
        await cur.execute(_CREATE_ENTITIES_TABLE)
        await cur.execute(_CREATE_ALIASES_TABLE)
        await cur.execute(_CREATE_ENTITY_NODES_TABLE)
        await cur.execute(_CREATE_RELATIONS_TABLE)
        await cur.execute(_CREATE_ALIAS_TRGM_INDEX)
    await _check_schema_version(conn)


async def _drop_orphaned_entities(cur: "psycopg.AsyncCursor[dict[str, Any]]") -> None:
    """Remove every alias with no remaining `kg_entity_nodes` row, then every entity with no
    remaining alias — the module docstring's G15 note, in the two steps that order now takes.
    Postgres cascades a child's row from its parent's deletion, never the reverse, so this is
    the explicit other half: called after any statement that may have removed a node.
    """
    await cur.execute(
        "DELETE FROM kg_aliases a WHERE NOT EXISTS "
        "(SELECT 1 FROM kg_entity_nodes en WHERE en.alias_id = a.id)"
    )
    await cur.execute(
        "DELETE FROM kg_entities e WHERE NOT EXISTS "
        "(SELECT 1 FROM kg_aliases a WHERE a.entity_id = e.id)"
    )


async def _row_census(cur: "psycopg.AsyncCursor[dict[str, Any]]") -> dict[str, int]:
    """How many alias, entity and relation rows this store holds right now — ledger **11.3**.

    Taken immediately before and after a deletion, so the counts reported are of rows **this
    deletion removed** rather than of rows the table happens not to hold. The difference matters
    the moment two sources share an entity, which is the ordinary case in any real corpus: a
    count read off the table afterwards would call a surviving entity removed.
    """
    await cur.execute(
        "SELECT (SELECT count(*) FROM kg_aliases) AS alias, "
        "(SELECT count(*) FROM kg_entities) AS entity, "
        "(SELECT count(*) FROM kg_relations) AS relation"
    )
    row = await cur.fetchone()
    if row is None:  # pragma: no cover — a scalar aggregate always returns a row
        return {"alias": 0, "entity": 0, "relation": 0}
    return {kind: cast(int, row[kind]) for kind in ("alias", "entity", "relation")}


async def _run_resolution_pass(cur: "psycopg.AsyncCursor[dict[str, Any]]") -> int:
    """Which surface forms are one entity, decided by `weft_kg.resolution` and applied here.

    Runs on every call to `GraphStore.reconcile`, in every `ReconcileMode` — see that method's
    own docstring for why a pass with `model_calls == 0` needs no consent gate.

    **The three signals, scored where each belongs.** Signal 1 (blended similarity) and signal 3's
    gate (raw cosines) are both scored in SQL, over `kg_aliases a JOIN kg_aliases b ON a.name <
    b.name` with both embeddings `NOT NULL` — O(n²) in the number of aliases and bounded per
    corpus, the donor's own bound (see `weft_kg.resolution`'s module docstring). Signal 2
    (acronym definitions) is read from the corpus's own node content, excluding mention and fact
    nodes, whose content is a bare name or a machine-rendered triple rather than prose a
    definition could appear in. Everything past that — the transitive closure and the choice of
    representative — is `resolution.resolve_clusters`, pure and untouched here.

    **What this pass costs, stated rather than left to be discovered.** `reconcile` is documented
    as `O(corpus)` in *time* and interruptible, and this is within that. It is also `O(corpus)` in
    **memory**, in two places a reader should know about before pointing it at a large corpus: the
    cosine map is one entry per alias *pair*, and signal 2 reads every non-derived node's content
    in one fetch rather than through `scan`'s own paging. Both are the donor's shape and both are
    honest at the sizes this task was built and measured against. Neither is a bound this pack
    should keep once the pass grows a model call — `11.9` makes it expensive and cursored, and
    paging these two reads belongs with that change rather than ahead of it, where it would be a
    complication with no consumer.

    Returns the number of `kg_aliases` rows whose `entity_id` this pass actually changed, via
    `IS DISTINCT FROM` in the closing `UPDATE` — the count `ReconcileReport.backfilled` reports,
    and the reason a second pass over an already-resolved graph reports zero rather than
    re-writing every row it touches nothing new about.
    """
    await cur.execute("SELECT name, embedding FROM kg_aliases ORDER BY name")
    alias_rows = await cur.fetchall()
    names = [cast(str, row["name"]) for row in alias_rows]
    if not names:
        return 0
    embeddings = {
        cast(str, row["name"]): row["embedding"]
        for row in alias_rows
        if row["embedding"] is not None
    }

    await cur.execute(
        """
        SELECT a.name AS left_name, b.name AS right_name
        FROM kg_aliases a JOIN kg_aliases b ON a.name < b.name
        WHERE a.embedding IS NOT NULL AND b.embedding IS NOT NULL
        AND (%(w)s * (1 - (a.embedding <=> b.embedding))
             + (1 - %(w)s) * similarity(a.name, b.name)) >= %(t)s
        """,
        {"w": resolution.DEFAULT_VECTOR_WEIGHT, "t": resolution.DEFAULT_SIMILARITY_THRESHOLD},
    )
    similar_rows = await cur.fetchall()
    similar_pairs = [
        (cast(str, row["left_name"]), cast(str, row["right_name"])) for row in similar_rows
    ]

    await cur.execute(
        "SELECT content FROM kg_nodes WHERE NOT (ext ? %s) AND NOT (ext ? %s)",
        (MentionedEntity.__namespace__, ExtractedFact.__namespace__),
    )
    node_rows = await cur.fetchall()
    definitions: list[tuple[str, str]] = []
    for node_row in node_rows:
        definitions.extend(resolution.acronym_definitions(cast(str, node_row["content"])))

    await cur.execute(
        """
        SELECT a.name AS left_name, b.name AS right_name,
               1 - (a.embedding <=> b.embedding) AS cosine
        FROM kg_aliases a JOIN kg_aliases b ON a.name < b.name
        WHERE a.embedding IS NOT NULL AND b.embedding IS NOT NULL
        """
    )
    cosine_rows = await cur.fetchall()
    cosines = {
        (cast(str, row["left_name"]), cast(str, row["right_name"])): cast(float, row["cosine"])
        for row in cosine_rows
    }

    clusters = resolution.resolve_clusters(
        names,
        similar_pairs=similar_pairs,
        acronym_definitions=definitions,
        cosines=cosines,
    )

    members_by_representative: dict[str, list[str]] = {}
    for name, representative in clusters.items():
        members_by_representative.setdefault(representative, []).append(name)

    backfilled = 0
    for representative, members in members_by_representative.items():
        canonical_id = _entity_id_for(representative)
        await cur.execute(
            """
            INSERT INTO kg_entities (id, name, embedding)
            VALUES (%(id)s, %(name)s, %(embedding)s)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                embedding = COALESCE(EXCLUDED.embedding, kg_entities.embedding)
            """,
            {
                "id": canonical_id,
                "name": representative,
                "embedding": embeddings.get(representative),
            },
        )
        await cur.execute(
            """
            UPDATE kg_aliases SET entity_id = %(entity_id)s
            WHERE name = ANY(%(members)s) AND entity_id IS DISTINCT FROM %(entity_id)s
            """,
            {"entity_id": canonical_id, "members": members},
        )
        backfilled += cur.rowcount

    await cur.execute(
        "DELETE FROM kg_entities e WHERE NOT EXISTS "
        "(SELECT 1 FROM kg_aliases a WHERE a.entity_id = e.id)"
    )
    return backfilled


class GraphStore:
    """`NodeStore`, `SourceDeletable` and `Reconcilable`, all three satisfied structurally — this
    class never imports one of the Protocols, the same path any third-party store pack takes.

    Plus `put_entity`/`put_relation`, this task's own addition and not on any contract:
    `weft_kg.traversal.GraphWalk` needs something to read, and ledger tasks **11.6**/**11.7** are
    the producers that call these for real. Deliberately its own class rather than shared with
    `GraphWalk` — see `weft_kg/__init__.py`'s module docstring on `L11.23`: one class under both
    `NodeStore` and `GraphTraversal` would let the fan-out's `NodeStore` filter be skipped
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
        for node in nodes:
            await self._derive_graph_rows(node)

    async def _derive_graph_rows(self, node: Node) -> None:
        """Ledger `11.6`'s other half, extended at `11.7` to the model-extracted rung: every
        stage in this pack that produces graph data attaches ext and writes no row itself, so
        this is where the entity and relation rows this pack's traversal reads all come from.
        A node carrying none of the three ext models below derives no rows and is stored
        normally — a store that refused it would make every one of these stages mandatory.

        All three are considered on every node, never `elif`-chained, because nothing forbids
        a future node from carrying more than one: `MentionedEntity` anchors an entity to the
        node that names it, `ExtractedFact` anchors both its endpoints to the fact node *and*
        writes the relation between them, and `CooccurrenceGraph` carries its own bundle of
        both shapes for the no-model rung. Attaching a fact's own two endpoints to the fact
        node (rather than to some other node that merely mentions them) is what keeps a
        relation from outliving the evidence for it: `kg_relations` cascades from
        `kg_aliases`, which cascades from `kg_entity_nodes`, which cascades from `kg_nodes` — so
        deleting the fact node is what makes the relation it stated unreachable, per the module
        docstring's G15 note.

        **`MentionedEntity`'s embedding is the mention node's own** — a mention node's content
        *is* the entity name and it went through the pipeline's own `embed` stage, so this is a
        real embedding of that name with no embedder needed at reconcile time; `ExtractedFact`'s
        two endpoints get no embedding, because the fact node's own vector is of the triple, not
        of either endpoint.

        Reuses `put_entity`/`put_relation` rather than a third SQL path; `entity.count` is not
        persisted here — it is a fact about this node's own content, and `kg_entities` carries
        no per-node column to hold it in.
        """
        mention = node.ext_as(MentionedEntity)
        if mention is not None:
            await self.put_entity(name=mention.name, nodes=[node.id], embedding=node.embedding)

        fact = node.ext_as(ExtractedFact)
        if fact is not None:
            source_id = await self.put_entity(name=fact.source, nodes=[node.id])
            target_id = await self.put_entity(name=fact.target, nodes=[node.id])
            await self.put_relation(source=source_id, target=target_id, predicate=fact.predicate)

        graph = node.ext_as(CooccurrenceGraph)
        if graph is not None:
            for entity in graph.entities:
                await self.put_entity(name=entity.name, nodes=[node.id])
            for edge in graph.relations:
                await self.put_relation(
                    source=_alias_id_for(edge.source),
                    target=_alias_id_for(edge.target),
                    predicate=edge.predicate,
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
        """Every node this source supported, and **an account of what went with them** — `11.3`.

        `Removed.node_count` alone was this participant's whole answer until now, and `11.3`'s
        own line is why that is not good enough: a store that reaped forty of its own rows
        answering `node_count=0` has told an operator nothing about the forty. `Removed.removed`
        is task `9.3`'s open, participant-owned vocabulary and this pack names five kinds in it.

        **`fact` and `mention` sit *beside* `node_count`, never instead of it.** Both are nodes,
        so both are already inside that total; what these add is the breakdown, which is exactly
        why `"node"` is a reserved key — a second spelling of the total would be the two-lists
        shape `docs/README.md` opens with, reproduced inside one model.

        **Absent means none, never zero.** A kind this deletion did not touch is left out rather
        than reported as `0`: a column of zeroes reads identically whether the participant looked
        and found nothing or does not count that kind at all (`docs/lessons.md` L5.9).

        **Counted as a difference across the deletion, not read off the tables afterwards.** An
        entity two sources both mention survives the first of them, and a count taken from the
        table would call it removed.
        """
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE kg_sources SET status = %s WHERE id = %s",
                (SourceStatus.DELETING.value, source_id),
            )
            await cur.execute(
                "SELECT count(*) FILTER (WHERE ext ? %(fact)s) AS fact, "
                "count(*) FILTER (WHERE ext ? %(mention)s) AS mention "
                "FROM kg_nodes WHERE %(source)s = ANY(sources)",
                {
                    "fact": ExtractedFact.__namespace__,
                    "mention": MentionedEntity.__namespace__,
                    "source": source_id,
                },
            )
            derived_row = await cur.fetchone()
            derived = (
                {kind: cast(int, derived_row[kind]) for kind in ("fact", "mention")}
                if derived_row is not None
                else {}
            )
            before = await _row_census(cur)
            await cur.execute("DELETE FROM kg_nodes WHERE %s = ANY(sources)", (source_id,))
            node_count = cur.rowcount
            await _drop_orphaned_entities(cur)
            after = await _row_census(cur)
            await cur.execute("DELETE FROM kg_sources WHERE id = %s", (source_id,))
        counts = {**derived, **{kind: before[kind] - after[kind] for kind in before}}
        return Removed(
            source_id=source_id,
            node_count=node_count,
            removed={kind: count for kind, count in counts.items() if count},
        )

    # -- Reconcilable ----------------------------------------------------------------------

    async def reconcile(self, ctx: Context, mode: ReconcileMode) -> ReconcileReport:
        """Finish every deletion that was interrupted — the identical tombstone convergence
        `PgVectorStore.reconcile` carries out, over this store's own `kg_sources`/`kg_nodes`, with
        orphaned aliases and entities dropped alongside each node deletion — then run the
        resolution pass over `kg_aliases`, in **every** mode.

        **Why the resolution pass runs under `repair` as well as `full`, against
        `ReconcileMode`'s own "backfills state that was never built" line for `full` alone.**
        That split is drawn on consent, because backfill ordinarily spends model calls an
        operator has not agreed to. This pass spends none — `estimate` below always reports
        `model_calls=0` for it — so the consent boundary the split exists to enforce has nothing
        to gate here, and running it only under `full` would mean the automatic post-index pass
        (hardcoded `repair`) never resolves an alias at all.
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
        async with conn.cursor() as cur:
            backfilled = await _run_resolution_pass(cur)
        return ReconcileReport(
            mode=mode,
            examined=examined,
            removed=removed,
            backfilled=backfilled,
            remaining=len(await self._tombstoned()),
        )

    async def estimate(self, ctx: Context, mode: ReconcileMode) -> ReconcileEstimate:
        """The honest cost of `reconcile` — see its own docstring. `model_calls` is always `0`:
        this store backfills nothing that costs a model call — the resolution pass reads
        `kg_aliases` and `kg_nodes` it already holds and calls no provider, and the tombstone
        convergence only finishes deletions already in flight.
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

    # -- `S5` -------------------------------------------------------------------------------

    async def schema_version(self) -> str:
        """The version this store's own `kg_schema` row carries — `S5`, per surface."""
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT version FROM kg_schema WHERE surface = %s", (KG_SCHEMA_SURFACE,)
            )
            row = await cur.fetchone()
        return cast(str, row["version"]) if row is not None else KG_SCHEMA_VERSION

    # -- This task's own addition — nothing on any contract; see the class docstring ------

    async def put_entity(
        self, *, name: str, nodes: Sequence[NodeId], embedding: Vector | None = None
    ) -> AliasId:
        """Upsert the alias for `name`, attach it to every id in `nodes`, and return the alias id.

        **If the alias already exists, its `entity_id` is left exactly as it was** — a
        resolution pass may have moved it, and re-pointing it back to `_entity_id_for(name)` on
        the next `add` would undo that pass on every index run. **If it is new**, its canonical
        `kg_entities` row is created alongside it, at `_entity_id_for(name)`, pointing at itself.

        `embedding`, when given, is written onto the alias and `COALESCE`d onto whichever entity
        row it currently resolves to — never overwriting an entity's own name, which the
        resolution pass and only the resolution pass decides.
        """
        alias_id = _alias_id_for(name)
        pg_embedding = PgVector(list(embedding.values)) if embedding is not None else None
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute("SELECT entity_id FROM kg_aliases WHERE id = %s", (alias_id,))
            existing = await cur.fetchone()
            if existing is not None:
                # The alias already exists: its `entity_id` may have been moved by a resolution
                # pass, and is left exactly as it is — only the embedding is coalesced, onto
                # both rows.
                entity_id = cast(str, existing["entity_id"])
                if pg_embedding is not None:
                    await cur.execute(
                        "UPDATE kg_aliases SET embedding = %s WHERE id = %s",
                        (pg_embedding, alias_id),
                    )
                    await cur.execute(
                        "UPDATE kg_entities SET embedding = COALESCE(%s, embedding) WHERE id = %s",
                        (pg_embedding, entity_id),
                    )
            else:
                # New: create the canonical row first — `kg_aliases.entity_id` carries a foreign
                # key onto it — then the alias, pointing at itself.
                entity_id = _entity_id_for(name)
                await cur.execute(
                    """
                    INSERT INTO kg_entities (id, name, embedding)
                    VALUES (%(id)s, %(name)s, %(embedding)s)
                    ON CONFLICT (id) DO UPDATE SET
                        embedding = COALESCE(EXCLUDED.embedding, kg_entities.embedding)
                    """,
                    {"id": entity_id, "name": name, "embedding": pg_embedding},
                )
                await cur.execute(
                    """
                    INSERT INTO kg_aliases (id, name, entity_id, embedding)
                    VALUES (%(id)s, %(name)s, %(entity_id)s, %(embedding)s)
                    """,
                    {
                        "id": alias_id,
                        "name": name,
                        "entity_id": entity_id,
                        "embedding": pg_embedding,
                    },
                )
            if nodes:
                await cur.executemany(
                    "INSERT INTO kg_entity_nodes (alias_id, node_id) VALUES (%s, %s) "
                    "ON CONFLICT DO NOTHING",
                    [(alias_id, node_id) for node_id in nodes],
                )
        return AliasId(alias_id)

    async def put_relation(self, *, source: AliasId, target: AliasId, predicate: str) -> None:
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO kg_relations (source_alias, target_alias, predicate) "
                "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (source, target, predicate),
            )


def _alias_id_for(name: str) -> AliasId:
    """A deterministic id for the alias `name` — same name, same id, within this store.

    Namespaced (`"alias:" + name`) rather than sharing `_entity_id_for`'s digest outright, so an
    alias id and the entity id a brand-new alias's own canonical row takes are never the same
    bytes by construction — a reader who sees one knows without checking which table it names.
    """
    return AliasId(sha256(("alias:" + name).encode("utf-8")).hexdigest()[:32])


def _entity_id_for(name: str) -> EntityId:
    """A deterministic id for `name` — same name, same id, within this store.

    A digest rather than the name itself so an entity id is stable characters `psycopg` and a
    URL both handle uninspected. This is the id a brand-new alias's own canonical row takes, and
    the id a resolution pass gives a cluster's chosen representative — never a fact about arrival
    order, only about the name itself.
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
    "KG_SCHEMA_SURFACE",
    "KG_SCHEMA_VERSION",
    "AliasId",
    "GraphDsnNotConfiguredError",
    "GraphSchemaVersionRefusedError",
    "GraphSettings",
    "GraphStore",
]
