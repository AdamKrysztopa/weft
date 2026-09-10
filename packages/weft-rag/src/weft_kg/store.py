"""`GraphStore` — `NodeStore`, `SourceDeletable` and `Reconcilable`, over Postgres. Ledger **11.5**,
schema and resolution pass at **11.8**, the curated-schema record at **11.11**.

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

import asyncio
from collections.abc import Mapping, Sequence
from datetime import datetime
from hashlib import sha256
from typing import Any, Final, NewType, cast

import psycopg
from pgvector import Vector as PgVector
from pgvector.psycopg import register_vector_async
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.payload import Node, NodeId, Outcome, Produced, SourceId, Vector
from weft_kg import resolution
from weft_kg.adjudication import DEFAULT_ADJUDICATION_FLOOR, first_verdict, threshold_adjudicator
from weft_kg.bridges import BridgeCandidate, BridgeHop
from weft_kg.contract import EntityId
from weft_kg.payload import CooccurrenceGraph, ExtractedFact, MentionedEntity
from weft_kg.prompts import (
    AdjudicateEntitiesPrompt,
    AdjudicateEntitiesRequest,
    EntityVerdict,
    SameEntity,
)
from weft_kg.schema import GraphSchema, ObservedTriple
from weft_llm.contract import LLM
from weft_prompts.cascade import execute as cascade_execute
from weft_prompts.contract import Prompt
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

#: A memory bound on `_run_resolution_pass`'s own corpus-content read, never a tuning knob
#: anyone has measured — the identical caveat `weft_index`'s own paged reads carry, restated
#: here because this is the first read in this pack that needed one. At most this many
#: `kg_nodes` rows' content is held at once while signal 2 scans for definitions; the resolution
#: pass carries no state that would make a larger or smaller page change what it decides.
_RESOLUTION_CONTENT_PAGE_SIZE: Final[int] = 500

#: `S5`, per surface: a persisted schema carries its own version in the stored bytes, because at
#: the read site the pack that wrote it may not be the one installed. `KG_SCHEMA_SURFACE` is the
#: `kg_schema.surface` this pack's own tables answer under — a second surface (e.g. a future
#: alternate storage engine for the same capability) would carry its own row and its own version,
#: never share this one.
#:
#: **Ledger `11.11` adds `kg_active_schema` and deliberately does not bump this constant — a
#: decision, not an omission.** `_check_schema_version` compares exactly, so bumping it for an
#: additive table would refuse every database this pack itself wrote yesterday, for a change that
#: removes nothing and reinterprets nothing already stored. Upgrade-or-refuse means *refuse when
#: meaning changed*; `kg_active_schema` is created `IF NOT EXISTS` on every connection, alongside
#: every other table `provision_schema` already creates the same way, and reads nothing that was
#: there before. A change that would earn a bump is one that makes an *existing* row mean
#: something different than it did — dropping a column, changing a type, re-purposing a key —
#: which this is not.
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

#: The corpus's own record of which curated schema it is under — ledger `11.11`, `S13`'s corpus
#: half (the file `GraphActivateCommand` writes is the operator's own half; see
#: `weft_kg.commands`'s module docstring). **One row, keyed on nothing but `id = 1`.** This
#: pack's tables are already one namespace per `[packs.graph] dsn`, so today one database *is*
#: one corpus and a single row delivers "which schema is this corpus under" in full — `S13` says
#: *keyed by collection*, and there is no collection in this tree (`03` defers the concept and
#: argues against building one: no command accepts one, and nothing would consult it). When a
#: collection concept ships, this row's key becomes the collection; inventing one now would be
#: state that looks consulted and is not, exactly what `03` refused.
_CREATE_ACTIVE_SCHEMA_TABLE = """
CREATE TABLE IF NOT EXISTS kg_active_schema (
    id integer PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    name text NOT NULL,
    identity text NOT NULL,
    source_path text NOT NULL,
    activated_at timestamptz NOT NULL DEFAULT now()
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

    **`adjudication_floor`, `adjudication_role` and `max_concurrent_adjudications`, ledger
    `11.9` — pack settings, not stage config.** The expensive resolution pass they configure
    runs from `Reconcilable.reconcile`, never from a pipeline's `with:` block — a reconcile pass
    is not a pipeline stage, so there is no per-stage config object for it to read, and these
    three live under `[packs.graph]` beside `dsn` for that reason rather than as an oversight.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    dsn: SecretStr = SecretStr("")
    #: The band's own lower edge, restated as an operator's field rather than left as merely
    #: `weft_kg.adjudication.threshold_adjudicator`'s default — requirement 6's rule that the
    #: one number a filter turns on is an operator's, not a constant baked into the pack. Below
    #: this score `_banded_pairs` never puts a pair to a model at all.
    adjudication_floor: float = Field(default=DEFAULT_ADJUDICATION_FLOOR, ge=0.0, le=1.0)
    #: The `[llm.roles]` key the expensive pass resolves a provider through. Defaults to
    #: `"index"`, exactly as `weft_kg.extraction.LlmFactsConfig.role` does, because a reconcile
    #: pass over this store's own aliases is index-side work, not query-time work.
    adjudication_role: str = Field(default="index", min_length=1)
    #: The fan-out bound for the expensive pass's model calls — the identical argument
    #: `weft_kg.extraction.LlmFactsConfig.max_concurrent_nodes` makes one call-site over: what a
    #: configured provider tolerates is an operator's fact, not this pack's, and this pass
    #: should not disagree with the extraction stage's own bound by accident.
    max_concurrent_adjudications: int = Field(default=8, ge=1)
    #: The project-local curated schema a `weft graph activate` run wrote — ledger `11.11`.
    #: Empty (the default) means *no schema is active*: `LlmFactExtractor` constrains and stamps
    #: nothing, exactly today's behaviour. A pack setting rather than stage `with:` config for
    #: the identical reason `dsn` is: `weft graph activate` writes this path once, per project,
    #: and every stage that reads a curated schema should read the one the corpus is actually
    #: under rather than a value some pipeline document happened to repeat.
    schema_file: str = ""


class GraphDsnNotConfiguredError(WeftError):
    """`[packs.graph] dsn` was never set, and this call needs a real connection.

    Raised only where a connection is actually opened — never at `register()`, which never calls
    `_connection` — so a pack installed with no settings still registers cleanly and fails exactly
    where an operator's mistake becomes consequential.
    """


class UnhandledSameEntityVerdictError(WeftError):
    """A `SameEntity` member the expensive pass's `match`/`case` has not been taught to map to
    a `Verdict` — `weft_store.contract.UnhandledFilterOpError`'s own closed-vocabulary rule, one
    contract over. `SameEntity` is a closed, three-member enum today, but a fourth member added
    to it later must be a refusal here rather than a silent "different": this pass's whole
    argument for a three-valued vote is that guessing is worse than abstaining, and falling
    through an `if`/`elif` to a default `False` would be exactly the guess it exists to forbid.
    """

    def __init__(self, message: str, *, valid_options: tuple[str, ...], pack: str) -> None:
        super().__init__(message, pack=pack)
        self.valid_options = valid_options


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
        # `kg_active_schema` carries no foreign key onto anything created above and nothing
        # references it in turn — its own single row stands apart from the corpus it describes,
        # so it needs no particular position in this list beyond "created before anything reads
        # it", which every statement in this cursor block already satisfies for its own table.
        await cur.execute(_CREATE_ACTIVE_SCHEMA_TABLE)
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
    as `O(corpus)` in *time* and interruptible, and this is within that. Three `O(corpus)`
    **memory** costs used to belong to this task and ledger `11.9` removed all three rather than
    merely paging them. The `kg_entities` upsert used to hold one full vector per alias in an
    `embeddings` dict for a value it now reads straight out of `kg_aliases` in the `INSERT`
    itself, via a correlated subquery — `COALESCE` already meant "keep what is there when the new
    one is null", so nothing about what gets written changed. The cosine fetch used to build one
    map entry per alias *pair* with no threshold at all; it now asks pgvector for cosines only on
    the pairs `weft_kg.resolution.initialism_candidates` says signal 3 could possibly act on,
    which is a function of the alias *names* alone and needs no database to compute first. And the
    corpus-content read that feeds signal 2 used to fetch every non-derived node's content in one
    round trip; it is now paged by `id`, `_RESOLUTION_CONTENT_PAGE_SIZE` rows at a time, so at most
    one page of node content is held at once rather than the whole non-derived corpus.

    What genuinely remains `O(corpus)` in memory: the alias name list itself (`names`), the
    similar-pairs list SQL narrows to whatever clears the blended threshold, the acronym
    definitions the corpus actually states, and `resolution.resolve_clusters`'s own union-find —
    each is bounded by the number of aliases, pairs or definitions the corpus produces, never by
    its content, and none of them is a cost this task introduced.

    Returns the number of `kg_aliases` rows whose `entity_id` this pass actually changed, via
    `IS DISTINCT FROM` in the closing `UPDATE` — the count `ReconcileReport.backfilled` reports,
    and the reason a second pass over an already-resolved graph reports zero rather than
    re-writing every row it touches nothing new about.
    """
    await cur.execute("SELECT name, entity_id FROM kg_aliases ORDER BY name")
    alias_rows = await cur.fetchall()
    names = [cast(str, row["name"]) for row in alias_rows]
    if not names:
        return 0

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

    # `11.9`'s own addition, not a fourth signal: two aliases a *model* already put under one
    # entity — `_bridge_merge`, in an earlier `full` pass — are fed in here as extra similar
    # pairs, on the identical footing the SQL-scored ones above sit on. Without this, this
    # unconditional pass would see two names its own three signals never merge, reset each back
    # to its own solo cluster the moment it next ran, and the very next `full` pass would find
    # the pair back in the band and put it to the model again — the question `_banded_pairs`'s
    # own `entity_id IS DISTINCT FROM` clause is supposed to have already answered. That would
    # be this pass re-guessing at a decision a later, better-informed one already made, exactly
    # what `put_entity`'s own docstring refuses for the identical reason ("a resolution pass may
    # have moved it, and re-pointing it back ... would undo that pass on every index run"). A
    # star of edges within each current entity group is enough to union the whole group — the
    # transitive closure below does the rest — and a fresh alias, still pointing at itself, sits
    # in a group of one and contributes no edge at all.
    current_groups: dict[str, list[str]] = {}
    for row in alias_rows:
        current_groups.setdefault(cast(str, row["entity_id"]), []).append(cast(str, row["name"]))
    for members in current_groups.values():
        similar_pairs.extend((members[0], other) for other in members[1:])

    definitions: list[tuple[str, str]] = []
    after = ""
    while True:
        await cur.execute(
            """
            SELECT id, content FROM kg_nodes
            WHERE NOT (ext ? %(fact)s) AND NOT (ext ? %(mention)s) AND id > %(after)s
            ORDER BY id
            LIMIT %(page)s
            """,
            {
                "fact": ExtractedFact.__namespace__,
                "mention": MentionedEntity.__namespace__,
                "after": after,
                "page": _RESOLUTION_CONTENT_PAGE_SIZE,
            },
        )
        node_rows = await cur.fetchall()
        if not node_rows:
            break
        for node_row in node_rows:
            definitions.extend(resolution.acronym_definitions(cast(str, node_row["content"])))
        after = cast(str, node_rows[-1]["id"])
        if len(node_rows) < _RESOLUTION_CONTENT_PAGE_SIZE:
            break

    # Signal 3's own gate, fetched only for the pairs the shape test could possibly act on —
    # see `weft_kg.resolution.initialism_candidates`'s own docstring for why this is a function
    # of the names alone and safe to compute before touching the database at all.
    candidates = resolution.initialism_candidates(names)
    cosines: dict[tuple[str, str], float] = {}
    if candidates:
        await cur.execute(
            """
            SELECT s.short AS left_name, s.long AS long_name,
                   1 - (a.embedding <=> b.embedding) AS cosine
            FROM unnest(%(shorts)s::text[], %(longs)s::text[]) AS s(short, long)
            JOIN kg_aliases a ON a.name = s.short
            JOIN kg_aliases b ON b.name = s.long
            WHERE a.embedding IS NOT NULL AND b.embedding IS NOT NULL
            """,
            {
                "shorts": [short for short, _ in candidates],
                "longs": [long_form for _, long_form in candidates],
            },
        )
        cosine_rows = await cur.fetchall()
        cosines = {
            (cast(str, row["left_name"]), cast(str, row["long_name"])): cast(float, row["cosine"])
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
            VALUES (%(id)s, %(name)s, (SELECT embedding FROM kg_aliases WHERE name = %(name)s))
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                embedding = COALESCE(EXCLUDED.embedding, kg_entities.embedding)
            """,
            {"id": canonical_id, "name": representative},
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


async def _banded_pairs(
    cur: "psycopg.AsyncCursor[dict[str, Any]]", *, floor: float, ceiling: float
) -> tuple[tuple[str, str, float], ...]:
    """The pairs the expensive pass has to put to a model — ledger `11.9`.

    Scores the identical blend `_run_resolution_pass`'s own signal 1 scores — the same
    `resolution.DEFAULT_VECTOR_WEIGHT`, the same `1 - (a.embedding <=> b.embedding)`, the same
    `similarity(a.name, b.name)` — over the identical join, `kg_aliases a JOIN kg_aliases b ON
    a.name < b.name`, both embeddings `NOT NULL`. Two clauses signal 1 alone does not need:

    `a.entity_id IS DISTINCT FROM b.entity_id` — a pair whose two aliases already point at one
    entity needs no judgement, whether a cheap merge or an earlier model call put them there.
    This is exactly what makes a second `full` pass over an already-decided pair ask nothing:
    the pair simply leaves the band the moment it stops being two entities
    (`test_a_second_full_pass_asks_nothing_and_changes_nothing`).

    The blend in `[floor, ceiling)` — closed at the bottom, open at the top, the identical
    half-open band `weft_kg.adjudication.threshold_adjudicator` uses, so this query and that
    adjudicator can never disagree about where the band's own edges are.

    `ORDER BY a.name, b.name`, so the pairs one run asks about are a function of the corpus
    alone, never of a plan's own row order.
    """
    await cur.execute(
        """
        SELECT a.name AS left_name, b.name AS right_name,
               (%(w)s * (1 - (a.embedding <=> b.embedding))
                + (1 - %(w)s) * similarity(a.name, b.name)) AS score
        FROM kg_aliases a JOIN kg_aliases b ON a.name < b.name
        WHERE a.embedding IS NOT NULL AND b.embedding IS NOT NULL
        AND a.entity_id IS DISTINCT FROM b.entity_id
        AND (%(w)s * (1 - (a.embedding <=> b.embedding))
             + (1 - %(w)s) * similarity(a.name, b.name)) >= %(floor)s
        AND (%(w)s * (1 - (a.embedding <=> b.embedding))
             + (1 - %(w)s) * similarity(a.name, b.name)) < %(ceiling)s
        ORDER BY a.name, b.name
        """,
        {"w": resolution.DEFAULT_VECTOR_WEIGHT, "floor": floor, "ceiling": ceiling},
    )
    rows = await cur.fetchall()
    return tuple(
        (cast(str, row["left_name"]), cast(str, row["right_name"]), cast(float, row["score"]))
        for row in rows
    )


async def _adjudicate_pairs(
    pairs: tuple[tuple[str, str, float], ...],
    *,
    llm: LLM,
    prompt: Prompt,
    settings: GraphSettings,
    ctx: Context,
) -> tuple[tuple[tuple[str, str], ...], int]:
    """Put every pair in `pairs` to the adjudication chain, and report what the model decided.

    Fanned out with `asyncio.gather` under a single `asyncio.Semaphore(
    settings.max_concurrent_adjudications)` held across the whole call — copied in shape from
    `weft_kg.extraction.LlmFactExtractor.run`, which is where the argument for a semaphore
    rather than chunked waves already lives: chunking would run the whole batch in lockstep and
    let one slow completion idle every other permit until its own wave finished.

    **The threshold adjudicator goes first in the chain, deliberately, even though it is
    guaranteed to abstain on every pair here.** `_banded_pairs` only ever selects scores inside
    `[floor, ceiling)`, so `weft_kg.adjudication.threshold_adjudicator` can never return
    anything but `None` for one of them — it is in the chain anyway because it is the seam a
    cheaper future adjudicator slots into ahead of the model, and keeping the band's own
    definition inside `first_verdict`'s own chain is what keeps the chain and the query that
    feeds it from ever being able to disagree about where the band actually is. Read this as
    that seam, not as dead code.

    Returns the pairs the model said `YES` to (the merge list) and the number it could not
    decide (the abstention count); a `NO` is a decision and is neither.
    """
    limit = asyncio.Semaphore(settings.max_concurrent_adjudications)

    async def _model_adjudicator(left: str, right: str, score: float) -> bool | None:
        del score  # the model is shown the two names, never the score that put them here —
        # `AdjudicateEntitiesRequest`'s own docstring: showing it invites deferring to a signal
        # the model cannot see the reasoning behind, rather than looking at the two names.
        answered = await cascade_execute(
            llm=llm,
            prompt=prompt,
            values=AdjudicateEntitiesRequest(left=left, right=right),
            output=EntityVerdict,
            role=settings.adjudication_role,
            ctx=ctx,
        )
        if not isinstance(answered, Produced):
            # A model in a bad mood is not a judgement — `weft_kg.extraction._facts_for` takes
            # the identical view of a cascade that could not produce a typed answer.
            return None
        match answered.value.value.verdict:
            case SameEntity.YES:
                return True
            case SameEntity.NO:
                return False
            case SameEntity.UNSURE:
                return None
            case _:  # pragma: no cover — exhaustive by construction; see the error's own note
                raise UnhandledSameEntityVerdictError(
                    f"weft_kg's adjudication pass received a SameEntity verdict of "
                    f"{answered.value.value.verdict!r}, which its match/case has not been "
                    f"taught to map to a Verdict. Known members: "
                    f"{[member.value for member in SameEntity]}.",
                    valid_options=tuple(member.value for member in SameEntity),
                    pack="weft-rag",
                )

    async def _bounded(left: str, right: str, score: float) -> bool | None:
        async with limit:
            return await first_verdict(
                left,
                right,
                score,
                adjudicators=(
                    threshold_adjudicator(
                        floor=settings.adjudication_floor,
                        ceiling=resolution.DEFAULT_SIMILARITY_THRESHOLD,
                    ),
                    _model_adjudicator,
                ),
            )

    verdicts = await asyncio.gather(*(_bounded(left, right, score) for left, right, score in pairs))

    merges: list[tuple[str, str]] = []
    abstained = 0
    for (left, right, _), verdict in zip(pairs, verdicts, strict=True):
        if verdict is True:
            merges.append((left, right))
        elif verdict is None:
            abstained += 1
    return tuple(merges), abstained


async def _bridge_merge(
    cur: "psycopg.AsyncCursor[dict[str, Any]]", pairs: Sequence[tuple[str, str]]
) -> int:
    """Re-point every alias in the losing entity of each pair onto the winning entity's id.

    **A bridge-merge re-points aliases so the evidence for the judgement survives the
    judgement.** `kg_entity_nodes` and `kg_relations` key on the *alias* — `11.8`'s decision —
    so re-pointing one alias's `entity_id` carries every node it anchors and every edge naming
    it along with it, in this one `UPDATE`, and nothing is deleted. The surface form the model
    was actually shown stays in the table as an alias row, so a person can later see what was
    merged and on what evidence.

    **The winner is the entity whose *name* is lexicographically smaller — `11.8`'s own rule,
    extended to a merge a model licenses.** The canonical id is a function of the set, not of
    arrival order, and `min` is associative: a batch of pairs merged in any order ends at the
    same winner, so this is order-independent under transitive closure even though it is
    applied pair-by-pair rather than as one closure computation.

    **Divergence from the donor this pattern is carried from:** that implementation deletes the
    losing entity outright and re-points three relationship types by hand. Here the alias layer
    already carries the join, so a merge is one `UPDATE` and the losing entity row simply
    becomes an orphan the existing sweep at the end of `_run_resolution_pass` already collects —
    reused directly below rather than through `_drop_orphaned_entities`, because that helper's
    first step (dropping aliases with no `kg_entity_nodes` row) has nothing to do here: a
    bridge-merge never removes a node-to-alias attachment, only which entity an alias points at.

    Returns the total number of `kg_aliases` rows this call re-pointed.
    """
    total = 0
    for left_name, right_name in pairs:
        await cur.execute(
            """
            SELECT a.entity_id AS left_entity, ea.name AS left_entity_name,
                   b.entity_id AS right_entity, eb.name AS right_entity_name
            FROM kg_aliases a
            JOIN kg_entities ea ON ea.id = a.entity_id
            JOIN kg_aliases b ON b.name = %(right)s
            JOIN kg_entities eb ON eb.id = b.entity_id
            WHERE a.name = %(left)s
            """,
            {"left": left_name, "right": right_name},
        )
        row = await cur.fetchone()
        if row is None:  # pragma: no cover — both names come from `_banded_pairs`'s own query
            continue
        left_entity = cast(str, row["left_entity"])
        right_entity = cast(str, row["right_entity"])
        if left_entity == right_entity:
            # An earlier pair in this same batch may already have merged them transitively —
            # re-merging is a no-op that would otherwise be double-counted.
            continue
        if cast(str, row["left_entity_name"]) <= cast(str, row["right_entity_name"]):
            winner, loser = left_entity, right_entity
        else:
            winner, loser = right_entity, left_entity
        await cur.execute(
            "UPDATE kg_aliases SET entity_id = %(winner)s WHERE entity_id = %(loser)s",
            {"winner": winner, "loser": loser},
        )
        total += cur.rowcount

    await cur.execute(
        "DELETE FROM kg_entities e WHERE NOT EXISTS "
        "(SELECT 1 FROM kg_aliases a WHERE a.entity_id = e.id)"
    )
    return total


class ActiveSchema(BaseModel):
    """The one row `kg_active_schema` holds — ledger `11.11`. `GraphStore`'s own return shape
    rather than a `weft_kg.schema` data model, on `weft_store.contract.Removed`/`Page`'s own
    footing: this is what the store's `active_schema` call answers with, never a value
    `GraphSchema` itself constructs or a curated file parses into — see `weft_kg.commands`'s
    module docstring for the file/row split this shape is one half of.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    identity: str
    source_path: str
    activated_at: datetime


class SchemaPresence(BaseModel):
    """One schema identity a corpus's own `ExtractedFact` nodes carry, and how many facts carry
    it — ledger `11.11`, `weft graph show`'s evidence that a corpus indexed under two schemas
    holds facts from both. `identity` empty is the untagged group: facts extracted with no schema
    active, reported on the identical footing as any named schema rather than folded into
    whichever one happens to be active now.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    identity: str
    facts: int = Field(ge=1)


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
        resolution pass over `kg_aliases`, in **every** mode — then, only under `full`, the
        expensive pass ledger `11.9` adds.

        **Why the resolution pass runs under `repair` as well as `full`, against
        `ReconcileMode`'s own "backfills state that was never built" line for `full` alone.**
        That split is drawn on consent, because backfill ordinarily spends model calls an
        operator has not agreed to. This pass spends none — `estimate` below always reports
        `model_calls=0` for it — so the consent boundary the split exists to enforce has nothing
        to gate here, and running it only under `full` would mean the automatic post-index pass
        (hardcoded `repair`) never resolves an alias at all.

        **What `full` now buys, and why the model is reached only when there is something to ask
        it.** `_banded_pairs` runs after the cheap resolution pass above, over whatever it left
        behind, and asks a strictly narrower question than that pass does: pairs the blend could
        neither merge nor refuse outright. When that query comes back empty this method reaches
        for no service at all — a `full` run on a project that never configured a provider must
        converge, not fail (`test_a_full_pass_with_nothing_in_the_band_needs_no_model_at_all`).
        Only when there is at least one such pair does it call `ctx.require(LLM)`;
        `weft_cli.commands._register_model_services` is what puts an `LLM` on the `Context` in a
        real run, and only under `full`, so a `repair` pass could not reach one even if this
        method tried — the mode is the gate, not a rule this method has to remember.
        """
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

        abstained = 0
        if mode is ReconcileMode.FULL:
            async with conn.cursor() as cur:
                pairs = await _banded_pairs(
                    cur,
                    floor=self._settings.adjudication_floor,
                    ceiling=resolution.DEFAULT_SIMILARITY_THRESHOLD,
                )
            if pairs:
                llm = ctx.require(LLM)
                # Constructed directly rather than resolved through `StageLookup`, for the
                # identical reason `weft_kg.extraction.LlmFactExtractor.run` casts
                # `ExtractFactsPrompt` the same way — see that call site's own long comment for
                # why the cast stands in for a runtime check that does pass, rather than for a
                # gap in this class.
                prompt = cast(Prompt, AdjudicateEntitiesPrompt())
                merges, abstained = await _adjudicate_pairs(
                    pairs, llm=llm, prompt=prompt, settings=self._settings, ctx=ctx
                )
                async with conn.cursor() as cur:
                    backfilled += await _bridge_merge(cur, merges)

        return ReconcileReport(
            mode=mode,
            examined=examined,
            removed=removed,
            backfilled=backfilled,
            remaining=len(await self._tombstoned()),
            abstained=abstained,
        )

    async def estimate(self, ctx: Context, mode: ReconcileMode) -> ReconcileEstimate:
        """The honest cost of `reconcile` — see its own docstring.

        `pending` and the tombstone half of `description` are as they were: nothing about the
        expensive pass changes what convergence itself costs. `model_calls` does change — this
        is the first participant in this tree whose `full` states a real number rather than an
        honest `0`. The count comes from `_banded_pairs`, the identical query `reconcile` then
        runs under `full`, so the cost stated here and the cost `reconcile` actually spends
        cannot disagree; this method makes no model call itself
        (`test_full_states_its_model_calls_before_it_spends_any`). Under any other mode no band
        query runs at all and `model_calls` stays `0` — `repair` never backfills, so its own
        honest `model_calls` is always `0`, and that is still true of `repair` here: it is
        `reconcile`'s own resolution pass, run under every mode, that spends nothing; it is
        `repair` never reaching the band at all that keeps this estimate honest for it.
        """
        del ctx  # `estimate` makes no model call itself — see the docstring above
        pending = len(await self._tombstoned())
        description = (
            f"{pending} source(s) have an unfinished deletion to finish"
            if pending
            else "no unfinished deletions; nothing to converge"
        )
        model_calls = 0
        if mode is ReconcileMode.FULL:
            conn = await self._connection()
            async with conn.cursor() as cur:
                pairs = await _banded_pairs(
                    cur,
                    floor=self._settings.adjudication_floor,
                    ceiling=resolution.DEFAULT_SIMILARITY_THRESHOLD,
                )
            model_calls = len(pairs)
            description += f"; {model_calls} ambiguous name pair(s) to put to a model"
        return ReconcileEstimate(
            mode=mode, pending=pending, description=description, model_calls=model_calls
        )

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

    # -- Ledger `11.11` — the corpus's own record of which curated schema it is under ------

    async def active_schema(self) -> ActiveSchema | None:
        """The one row `kg_active_schema` holds, or `None` when `activate_schema` has never run
        against this database — see `ActiveSchema`'s own docstring.
        """
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT name, identity, source_path, activated_at FROM kg_active_schema "
                "WHERE id = 1"
            )
            row = await cur.fetchone()
        if row is None:
            return None
        return ActiveSchema(
            name=cast(str, row["name"]),
            identity=cast(str, row["identity"]),
            source_path=cast(str, row["source_path"]),
            activated_at=cast(datetime, row["activated_at"]),
        )

    async def activate_schema(self, schema: GraphSchema, *, source_path: str) -> None:
        """Upsert the one `kg_active_schema` row — `S13`'s corpus half; see the module docstring
        on `_CREATE_ACTIVE_SCHEMA_TABLE` for why a single row, keyed on nothing, delivers that
        property in full today. `source_path` is recorded as given (a curated schema file's own
        path), never resolved or validated here — that already happened at `weft_kg.schema.
        load_schema`, which `weft_kg.commands.GraphActivateCommand` calls before this.
        """
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO kg_active_schema (id, name, identity, source_path, activated_at)
                VALUES (1, %(name)s, %(identity)s, %(source_path)s, now())
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    identity = EXCLUDED.identity,
                    source_path = EXCLUDED.source_path,
                    activated_at = EXCLUDED.activated_at
                """,
                {"name": schema.name, "identity": schema.identity, "source_path": source_path},
            )

    async def observed_triples(self) -> tuple[ObservedTriple, ...]:
        """Every distinct `(source_type, predicate, target_type)` this corpus's own
        `ExtractedFact` nodes already produced, with counts — `weft_kg.schema.propose_schema`'s
        only input. Grouped and ordered in SQL, count descending, over the same `ext ? %s` /
        `->>` jsonb access `_run_resolution_pass` already established for this pack.
        """
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT ext->%(fact)s->>'source_type' AS source_type,
                       ext->%(fact)s->>'predicate' AS predicate,
                       ext->%(fact)s->>'target_type' AS target_type,
                       count(*) AS n
                FROM kg_nodes
                WHERE ext ? %(fact)s
                GROUP BY 1, 2, 3
                ORDER BY n DESC, 1, 2, 3
                """,
                {"fact": ExtractedFact.__namespace__},
            )
            rows = await cur.fetchall()
        return tuple(
            ObservedTriple(
                source_type=cast(str, row["source_type"]),
                predicate=cast(str, row["predicate"]),
                target_type=cast(str, row["target_type"]),
                count=cast(int, row["n"]),
            )
            for row in rows
        )

    async def schemas_in_corpus(self) -> tuple[SchemaPresence, ...]:
        """Every distinct `schema_id` this corpus's own `ExtractedFact` nodes carry, with counts
        — `weft graph show`'s evidence that a corpus indexed under two schemas holds facts from
        both. The empty identity is included on the same footing as any other: `COALESCE` turns
        a pre-`11.11` fact with no `schema_id` key at all into the identical empty group a fresh
        no-schema extraction produces, rather than a third, unlabelled bucket.
        """
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT COALESCE(ext->%(fact)s->>'schema_id', '') AS identity, count(*) AS n
                FROM kg_nodes
                WHERE ext ? %(fact)s
                GROUP BY 1
                ORDER BY n DESC, 1
                """,
                {"fact": ExtractedFact.__namespace__},
            )
            rows = await cur.fetchall()
        return tuple(
            SchemaPresence(identity=cast(str, row["identity"]), facts=cast(int, row["n"]))
            for row in rows
        )

    # -- Ledger `11.13` — `weft graph bridges`'s own two reads --------------------------------

    async def relation_count(self) -> int:
        """How many `kg_relations` rows this corpus holds — `GraphBridgesCommand`'s own way of
        telling "no relations at all" (index the corpus) from "relations, but no bridge among
        them" (the corpus's own finding) apart, before it ever calls `two_hop_bridges`.
        """
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute("SELECT count(*) AS n FROM kg_relations")
            row = await cur.fetchone()
        return cast(int, row["n"]) if row is not None else 0

    async def two_hop_bridges(self, *, limit: int) -> tuple[BridgeCandidate, ...]:
        """Every two-hop path `A --p1--> B --p2--> C` this corpus's own `kg_relations` rows
        support, where no single `kg_nodes` row names both `A` and `C` — see `weft_kg.bridges`'s
        module docstring for why that is the property a bridge exists to guarantee.

        **Routed through `kg_aliases`, never through `kg_entities` directly** — `kg_relations`
        and `kg_entity_nodes` both key on the alias, per the module docstring's ledger `11.8`
        note, and `_refuse_pre_118_layout` is what rejects a database still keyed the old way.

        **Walked undirected, and the stored direction survives the walk.** `edges` doubles every
        `kg_relations` row into both directions, the identical shape `GraphWalk.neighbourhood`
        walks — reach does not care which way a relation points. A *predicate* does, and that
        walk states none while this one prints one, so each doubled row carries
        `walked_backwards` and `_bridge_candidate_of` orients the hop by it. Without that column
        a hop reached against its own direction prints the corpus's claim inverted, beside a
        citation that is perfectly real.

        **Each hop's citation is entirely its own**: `cited` joins `kg_entity_nodes` twice per
        hop, once per that hop's own two endpoint aliases (the exact alias ids the underlying
        `kg_relations` row names, not just any alias of the resolved entity) — a node that
        anchors both is the fact (or co-occurrence edge) that stated that hop.

        **The two-hop endpoints sharing no node is this walk's own filter** (`named`'s
        `NOT EXISTS`), read over every alias of the two endpoint *entities* — this is what makes
        a candidate a bridge in the first place, and it is checked against every alias, not only
        the ones this particular path happened to use. `chunks_by_entity` is a second,
        independent query over the identical fact and must never reuse this clause — see
        `weft_kg.bridges.bridges_from`.

        **Deduplicated in two stages.** `named` keeps only the mirror where
        `source_name < target_name`, so `A-B-C` and `C-B-A` are the same bridge once; `deduped`'s
        `DISTINCT ON (source_entity, via_entity, target_entity)` keeps exactly one citing node
        pair per triple when several predicates or several fact nodes could evidence it, chosen
        by an `ORDER BY` over the predicates and node ids so two runs over one corpus agree.

        Final order is `source_name, via_name, target_name` — a function of the corpus alone,
        never of a plan's own row order — and `limit` bounds it, the identical shape
        `weft_kg.schema.propose_schema`'s own caller-supplied bound takes one level up.
        """
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute(
                """
                WITH edges AS (
                    SELECT r.source_alias AS from_alias, r.target_alias AS to_alias,
                           r.predicate AS predicate, FALSE AS walked_backwards,
                           sa.entity_id AS from_entity, ta.entity_id AS to_entity
                    FROM kg_relations r
                    JOIN kg_aliases sa ON sa.id = r.source_alias
                    JOIN kg_aliases ta ON ta.id = r.target_alias
                    UNION ALL
                    SELECT r.target_alias AS from_alias, r.source_alias AS to_alias,
                           r.predicate AS predicate, TRUE AS walked_backwards,
                           ta.entity_id AS from_entity, sa.entity_id AS to_entity
                    FROM kg_relations r
                    JOIN kg_aliases sa ON sa.id = r.source_alias
                    JOIN kg_aliases ta ON ta.id = r.target_alias
                ),
                paths AS (
                    SELECT
                        e1.from_entity AS source_entity,
                        e1.to_entity AS via_entity,
                        e2.to_entity AS target_entity,
                        e1.from_alias AS source_alias,
                        e1.to_alias AS first_via_alias,
                        e1.predicate AS first_predicate,
                        e1.walked_backwards AS first_walked_backwards,
                        e2.from_alias AS second_via_alias,
                        e2.to_alias AS target_alias,
                        e2.predicate AS second_predicate,
                        e2.walked_backwards AS second_walked_backwards
                    FROM edges e1
                    JOIN edges e2 ON e2.from_entity = e1.to_entity
                    WHERE e1.from_entity <> e1.to_entity
                      AND e2.from_entity <> e2.to_entity
                      AND e1.from_entity <> e2.to_entity
                ),
                named AS (
                    SELECT p.*, se.name AS source_name, ve.name AS via_name,
                           te.name AS target_name
                    FROM paths p
                    JOIN kg_entities se ON se.id = p.source_entity
                    JOIN kg_entities ve ON ve.id = p.via_entity
                    JOIN kg_entities te ON te.id = p.target_entity
                    WHERE se.name < te.name
                      AND NOT EXISTS (
                          SELECT 1
                          FROM kg_entity_nodes en_a
                          JOIN kg_aliases aa ON aa.id = en_a.alias_id
                          JOIN kg_entity_nodes en_c ON en_c.node_id = en_a.node_id
                          JOIN kg_aliases ac ON ac.id = en_c.alias_id
                          WHERE aa.entity_id = p.source_entity
                            AND ac.entity_id = p.target_entity
                      )
                ),
                cited AS (
                    SELECT n.source_entity, n.source_name, n.via_entity, n.via_name,
                           n.target_entity, n.target_name,
                           n.first_predicate, n.first_walked_backwards,
                           hop1.node_id AS first_node_id,
                           n.second_predicate, n.second_walked_backwards,
                           hop2.node_id AS second_node_id
                    FROM named n
                    JOIN kg_entity_nodes hop1a ON hop1a.alias_id = n.source_alias
                    JOIN kg_entity_nodes hop1
                        ON hop1.alias_id = n.first_via_alias
                       AND hop1.node_id = hop1a.node_id
                    JOIN kg_entity_nodes hop2 ON hop2.alias_id = n.second_via_alias
                    JOIN kg_entity_nodes hop2b
                        ON hop2b.alias_id = n.target_alias
                       AND hop2b.node_id = hop2.node_id
                ),
                deduped AS (
                    SELECT DISTINCT ON (source_entity, via_entity, target_entity)
                        source_entity, source_name, via_name, target_entity, target_name,
                        first_predicate, first_walked_backwards, first_node_id,
                        second_predicate, second_walked_backwards, second_node_id
                    FROM cited
                    ORDER BY source_entity, via_entity, target_entity,
                             first_predicate, second_predicate, first_node_id, second_node_id
                )
                SELECT d.source_entity, d.source_name, d.via_name,
                       d.target_entity, d.target_name,
                       d.first_predicate, d.first_walked_backwards,
                       d.first_node_id, n1.sources AS first_sources,
                       d.second_predicate, d.second_walked_backwards,
                       d.second_node_id, n2.sources AS second_sources
                FROM deduped d
                JOIN kg_nodes n1 ON n1.id = d.first_node_id
                JOIN kg_nodes n2 ON n2.id = d.second_node_id
                ORDER BY d.source_name, d.via_name, d.target_name
                LIMIT %(limit)s
                """,
                {"limit": limit},
            )
            rows = await cur.fetchall()
        return tuple(_bridge_candidate_of(row) for row in rows)

    async def chunks_by_entity(self, entity_ids: Sequence[str]) -> Mapping[str, frozenset[str]]:
        """The frozenset of `kg_entity_nodes.node_id` reachable through each id in `entity_ids`'s
        own aliases — `GraphBridgesCommand`'s independent second measurement of the vector
        ceiling, see `weft_kg.bridges`'s module docstring for why it must never reuse
        `two_hop_bridges`'s own `NOT EXISTS` clause.

        Keys are exactly the requested ids this store holds an entity row for: an id with no
        nodes maps to an empty frozenset, an id not in `kg_entities` at all is **absent** —
        `GraphWalk.nodes_for_entities`'s own documented rule, restated here rather than
        reinvented, because presence and "found nothing" must mean the same two different things
        in both readers of this schema.
        """
        if not entity_ids:
            return {}
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT e.id AS entity_id, en.node_id AS node_id "
                "FROM kg_entities e "
                "LEFT JOIN kg_aliases a ON a.entity_id = e.id "
                "LEFT JOIN kg_entity_nodes en ON en.alias_id = a.id "
                "WHERE e.id = ANY(%s)",
                (list(entity_ids),),
            )
            rows = await cur.fetchall()
        result: dict[str, set[str]] = {}
        for row in rows:
            entity_id = cast(str, row["entity_id"])
            result.setdefault(entity_id, set())
            node_id = row["node_id"]
            if node_id is not None:
                result[entity_id].add(cast(str, node_id))
        return {entity_id: frozenset(nodes) for entity_id, nodes in result.items()}

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


def _bridge_candidate_of(row: Mapping[str, object]) -> BridgeCandidate:
    """One row of `two_hop_bridges`'s own final `SELECT` into a `BridgeCandidate`.

    Hop endpoints are the **canonical entity names** either side of that hop, never the raw alias
    names `kg_relations` stores, so a hop reads consistently with `source_name`/`via_name`/
    `target_name` whichever surface form the underlying fact used — and they are ordered by
    `walked_backwards`, so `source --predicate--> target` is the sentence the corpus actually
    wrote rather than the direction this walk happened to arrive from. `BridgeHop`'s own
    docstring carries why those are two different facts.
    """
    source_name = cast(str, row["source_name"])
    via_name = cast(str, row["via_name"])
    target_name = cast(str, row["target_name"])
    first_backwards = cast(bool, row["first_walked_backwards"])
    second_backwards = cast(bool, row["second_walked_backwards"])
    return BridgeCandidate(
        source_entity=cast(str, row["source_entity"]),
        source_name=source_name,
        via_name=via_name,
        target_entity=cast(str, row["target_entity"]),
        target_name=target_name,
        first=BridgeHop(
            source=via_name if first_backwards else source_name,
            predicate=cast(str, row["first_predicate"]),
            target=source_name if first_backwards else via_name,
            node_id=cast(str, row["first_node_id"]),
            documents=tuple(sorted(cast("list[str]", row["first_sources"]))),
        ),
        second=BridgeHop(
            source=target_name if second_backwards else via_name,
            predicate=cast(str, row["second_predicate"]),
            target=via_name if second_backwards else target_name,
            node_id=cast(str, row["second_node_id"]),
            documents=tuple(sorted(cast("list[str]", row["second_sources"]))),
        ),
    )


__all__ = [
    "KG_SCHEMA_SURFACE",
    "KG_SCHEMA_VERSION",
    "ActiveSchema",
    "AliasId",
    "GraphDsnNotConfiguredError",
    "GraphSchemaVersionRefusedError",
    "GraphSettings",
    "GraphStore",
    "SchemaPresence",
    "UnhandledSameEntityVerdictError",
]
