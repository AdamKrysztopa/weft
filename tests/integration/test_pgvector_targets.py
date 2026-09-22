"""The pgvector store holds targets as schemas — ledger tasks **34.1** and **34.2**.

A target other than `default` is the schema `weft_target_<name>`, reached through `search_path`,
so none of the store's unqualified statements is rewritten. `default` is the tables where a
database written before targets existed already keeps them, and the catalogue — which targets
exist, which is live, the identity each recorded — sits beside them.

**The hazard these tests exist for is measured, not assumed** (`34.0`, 2026-09-22): with
`search_path = weft_target_x, public`, an unqualified `weft_nodes` missing from `weft_target_x`
resolves to `public.weft_nodes`, which is `default`'s. So a candidate whose table went missing
would answer from the live corpus without an error. The store refuses instead, by name.

Every test runs in a database of its own, created and dropped by the fixture by exact name
(`L22.47`): a target test changes which target is live, and every other suite on the shared
database reads whatever target is live. `approximate_store` in `test_store_conformance.py` is the
precedent.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from pydantic import SecretStr

from weft_kernel.payload import MediaType, Node, SourceId, Vector
from weft_store.contract import (
    DEFAULT_TARGET,
    LayerRecord,
    LayerStatus,
    Promotion,
    SourceRecord,
    TargetInUseError,
    UnknownSourceLayerError,
    target_name,
)
from weft_store.pgvector_store import PgVectorSettings, PgVectorStore, TargetTableMissingError

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")


def _schema(target: str) -> sql.Identifier:
    return sql.Identifier(f"weft_target_{target}")


def _node(content: str, values: tuple[float, ...]) -> Node:
    node = Node.synthetic(
        content=content,
        media_type=MediaType.TEXT,
        reason="pgvector targets",
        sources=frozenset({SourceId("doc")}),
    )
    return node.with_embedding(Vector(values=values))


def _promotion(target: str) -> Promotion:
    return Promotion(
        target=target, at=datetime.now(UTC), by="test", evidence=(), without_evidence=True
    )


#: The database the running test owns — set by the fixture, read by every helper below.
_current: dict[str, str] = {}


async def _execute(*statements: sql.Composed | sql.SQL) -> list[tuple[object, ...]]:
    """Run each statement on a connection of this test's own; the last one's rows, if any."""
    rows: list[tuple[object, ...]] = []
    conn = await psycopg.AsyncConnection.connect(_current["dsn"], autocommit=True)
    try:
        async with conn.cursor() as cur:
            for statement in statements:
                await cur.execute(statement)
                rows = list(await cur.fetchall()) if cur.description else []
    finally:
        await conn.close()
    return rows


def _store() -> PgVectorStore:
    return PgVectorStore(PgVectorSettings(dsn=SecretStr(_current["dsn"])))


@pytest.fixture
async def store() -> AsyncIterator[PgVectorStore]:
    try:
        probe = await psycopg.AsyncConnection.connect(_DSN, connect_timeout=2)
    except psycopg.OperationalError as exc:
        pytest.skip(f"WEFT_DATABASE_URL ({_DSN}) is unreachable: {exc}. `docker compose up -d`.")
    await probe.close()
    name = f"weft_targets_{uuid4().hex[:12]}"
    admin = await psycopg.AsyncConnection.connect(_DSN, autocommit=True)
    async with admin.cursor() as cur:
        await cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    _current["dsn"] = f"{_DSN.rsplit('/', 1)[0]}/{name}"
    instance = _store()
    try:
        yield instance
    finally:
        await instance.aclose()
        async with admin.cursor() as cur:
            await cur.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )
        await admin.close()
        _current.clear()


async def test_a_database_written_before_targets_existed_reads_as_default_live(
    store: PgVectorStore,
) -> None:
    """`34.2`: the upgrade clause of `09` §5.2 stays held — no operator action, nothing moved."""
    # Arrange — a 2.8.0-shaped database: the three tables with rows, and no catalogue at all.
    await store.add([_node("written before targets", (1.0, 0.0, 0.0))])
    await store.put_source(
        SourceRecord(
            id=SourceId("doc"),
            uri="file:///doc.txt",
            content_hash="h",
            indexed_at=datetime.now(UTC),
            pipeline="index-text",
        )
    )
    await store.aclose()
    await _execute(sql.SQL("DROP TABLE IF EXISTS weft_targets, weft_live_target"))
    upgraded = _store()

    # Act
    catalogue = await upgraded.target_catalogue()
    count = await upgraded.count()
    sources = await upgraded.list_sources()
    await upgraded.aclose()

    # Assert
    assert catalogue.live == DEFAULT_TARGET
    assert catalogue.previous is None
    assert [record.name for record in catalogue.targets] == [DEFAULT_TARGET]
    assert count == 1
    assert [record.id for record in sources] == [SourceId("doc")]


async def test_a_candidate_is_written_into_its_own_schema_and_default_is_untouched(
    store: PgVectorStore,
) -> None:
    # Arrange
    await store.add([_node("live", (1.0, 0.0, 0.0))])
    candidate = await store.bind_target(target_name("w128"))

    # Act — a width of 2 beside default's 3: each target commits its own (G22).
    await candidate.add([_node("candidate one", (0.0, 1.0)), _node("candidate two", (1.0, 1.0))])
    await candidate.aclose()
    in_candidate = await _execute(
        sql.SQL("SELECT count(*) FROM {}.weft_nodes").format(_schema("w128"))
    )

    # Assert
    assert in_candidate == [(2,)]
    assert await store.count() == 1


async def test_a_catalogued_target_whose_table_is_gone_is_refused_rather_than_read_through(
    store: PgVectorStore,
) -> None:
    """The fall-through `34.0` measured, refused: never recreated empty, never read from default."""
    # Arrange
    await store.add([_node("live", (1.0, 0.0, 0.0))])
    candidate = await store.bind_target(target_name("w128"))
    await candidate.add([_node("candidate", (0.0, 1.0, 0.0))])
    await candidate.aclose()
    await _execute(sql.SQL("DROP TABLE {}.weft_nodes CASCADE").format(_schema("w128")))
    reopened = await _store().bind_target(target_name("w128"))

    # Act / Assert
    with pytest.raises(TargetTableMissingError) as caught:
        await reopened.count()
    await reopened.aclose()
    message = str(caught.value)
    assert "'w128'" in message
    assert "weft_nodes" in message
    still_missing = await _execute(
        sql.SQL("SELECT to_regclass({}) IS NULL").format(sql.Literal("weft_target_w128.weft_nodes"))
    )
    assert still_missing == [(True,)]


async def test_a_store_opened_after_a_promote_reads_the_new_live_target(
    store: PgVectorStore,
) -> None:
    """Q-C: the live pointer is read when a store opens and held for that store's lifetime."""
    # Arrange
    await store.add([_node("live", (1.0, 0.0, 0.0))])
    candidate = await store.bind_target(target_name("w128"))
    await candidate.add([_node("one", (0.0, 1.0, 0.0)), _node("two", (0.0, 0.0, 1.0))])
    await candidate.aclose()

    # Act
    await store.promote(_promotion("w128"))
    opened_after = _store()
    count_after = await opened_after.count()
    await opened_after.aclose()

    # Assert
    assert await store.count() == 1
    assert count_after == 2
    assert (await store.target_catalogue()).live == "w128"


async def test_a_target_another_open_store_is_bound_to_cannot_be_dropped(
    store: PgVectorStore,
) -> None:
    """Dropping a schema under an open handle would send its next statement to `default`'s
    tables, so the drop is refused while any connection holds the target."""
    # Arrange
    await store.add([_node("live", (1.0, 0.0, 0.0))])
    writer = await _store().bind_target(target_name("w256"))
    await writer.add([_node("candidate", (0.0, 1.0, 0.0))])

    # Act / Assert
    with pytest.raises(TargetInUseError) as caught:
        await store.drop_target(target_name("w256"))
    assert "'w256'" in str(caught.value)
    await writer.aclose()
    await store.drop_target(target_name("w256"))
    assert "w256" not in {record.name for record in (await store.target_catalogue()).targets}


async def test_four_handles_opening_one_fresh_database_at_once_all_succeed(
    store: PgVectorStore,
) -> None:
    """Carried repair **R43.4**, found running Exit A: `weft ask` in a second shell opened the
    store while the first `weft index` was still creating the schema, and the run died with
    `UniqueViolation: duplicate key ... pg_extension_name_index`. `CREATE EXTENSION IF NOT
    EXISTS` is not atomic against a concurrent creator, and neither is the rest of this store's
    open-time DDL. Reproduced minimally: four handles opening one fresh database together, three
    of them raised. That is precisely this phase's own scenario — asking while the corpus
    indexes — so the store has to survive it."""
    # Arrange: `store` owns a database nothing has opened yet, and is not itself opened first.
    others = [_store() for _ in range(3)]

    # Act
    try:
        counts = await asyncio.gather(
            store.count(), *(other.count() for other in others), return_exceptions=True
        )
    finally:
        for other in others:
            await other.aclose()

    # Assert
    assert [c for c in counts if isinstance(c, BaseException)] == []
    assert counts == [0, 0, 0, 0]


async def test_opening_a_handle_while_another_writes_never_deadlocks_the_writer(
    store: PgVectorStore,
) -> None:
    """Carried repair **R43.5**, found by Exit A's first repeat after `R43.4`: the run died in
    `store` with `DeadlockDetected` on `weft_node_productions`. Each `weft ask` opening the store
    runs the productions backfill, which inserts a production for every committed node that has
    none, and `add()` committed its nodes before their productions, so the backfill and the writer
    inserted the same keys in two transactions in opposite orders. A node and its productions are
    one write: no reader ever sees a node without them."""
    # Arrange
    sources = frozenset(SourceId(f"doc-{i}") for i in range(4))
    batches = [
        [
            Node.synthetic(
                content=f"batch {b} node {n}",
                media_type=MediaType.TEXT,
                reason="R43.5",
                sources=sources,
            ).with_embedding(Vector(values=(1.0, float(n), float(b))))
            for n in range(300)
        ]
        for b in range(20)
    ]
    await store.add(batches[0])
    writing = True

    async def write() -> None:
        nonlocal writing
        try:
            for batch in batches[1:]:
                await store.add(batch)
        finally:
            writing = False

    async def open_and_count() -> int:
        opened = 0
        while writing:
            reader = _store()
            try:
                await reader.count()
            finally:
                await reader.aclose()
            opened += 1
        return opened

    # Act
    outcomes = await asyncio.gather(
        write(), *(open_and_count() for _ in range(3)), return_exceptions=True
    )

    # Assert
    assert [o for o in outcomes if isinstance(o, BaseException)] == []
    assert await store.count() == 20 * 300
    rows = await _execute(
        sql.SQL(
            "SELECT count(*) FROM weft_nodes n WHERE NOT EXISTS "
            "(SELECT 1 FROM weft_node_productions p WHERE p.node_id = n.id)"
        )
    )
    assert rows == [(0,)]


async def test_a_source_a_2_9_0_store_wrote_reads_back_with_no_layers(
    store: PgVectorStore,
) -> None:
    """Ledger **43.6**: `layers` is a column added beside the others, so a database a `2.9.0`
    store wrote reads its records back with no layers rather than failing to parse them."""
    # Arrange — a 2.9.0-shaped database: no `layers` column, and no `R43.6` stamp.
    record = SourceRecord(
        id=SourceId("doc"),
        uri="file:///doc.txt",
        content_hash="h",
        indexed_at=datetime.now(UTC),
        pipeline="index-text",
    )
    await store.put_source(record)
    await store.aclose()
    await _execute(
        sql.SQL("ALTER TABLE weft_sources DROP COLUMN layers"),
        sql.SQL("DROP TABLE weft_schema_stamp"),
    )
    upgraded = _store()

    # Act
    try:
        found = await upgraded.get_source(SourceId("doc"))
    finally:
        await upgraded.aclose()

    # Assert
    assert found == record
    assert found is not None and found.layers == ()


async def test_a_layer_field_a_newer_release_wrote_is_refused_by_name(
    store: PgVectorStore,
) -> None:
    """Ledger **43.6**, `R36.3`'s shape: pydantic's `extra_forbidden` never reaches an operator."""
    # Arrange
    when = datetime.now(UTC)
    await store.put_source(
        SourceRecord(
            id=SourceId("doc"),
            uri="file:///doc.txt",
            content_hash="h",
            indexed_at=when,
            pipeline="index-text",
            layers=(
                LayerRecord(
                    name="enrich-with-questions",
                    pipeline_identity="q",
                    status=LayerStatus.ACTIVE,
                    attempts=1,
                    at=when,
                ),
            ),
        )
    )
    await _execute(
        sql.SQL(
            "UPDATE weft_sources SET layers = jsonb_build_array("
            "layers->0 || '{\"generation\": 3}'::jsonb) WHERE id = 'doc'"
        )
    )

    # Act
    with pytest.raises(UnknownSourceLayerError) as refused:
        await store.get_source(SourceId("doc"))

    # Assert
    assert "'generation'" in str(refused.value)


async def test_opening_a_current_database_never_waits_behind_a_writer(
    store: PgVectorStore,
) -> None:
    """Carried repair **R43.6**, found by Exit A's first complete repeat: a `weft ask` during
    ingest took 28.8 s and another 15.1 s against 3.4 s after, because every open ran
    `ALTER TABLE weft_nodes ADD COLUMN IF NOT EXISTS content_tsv ...` — an `ACCESS EXCLUSIVE` lock
    even when the column exists — and queued behind the indexer's open write transaction. A
    database whose schema this release already provisioned is opened without taking a table lock.
    """
    # Arrange — the schema is provisioned, and a writer holds `weft_nodes` mid-transaction.
    await store.add([_node("provisioned", (1.0, 0.0, 0.0))])
    await store.aclose()
    writer = await psycopg.AsyncConnection.connect(_current["dsn"])
    await writer.execute("LOCK TABLE weft_nodes, weft_sources IN ROW EXCLUSIVE MODE")
    reader = _store()

    # Act
    try:
        counted = await asyncio.wait_for(reader.count(), timeout=5.0)
    finally:
        await writer.rollback()
        await writer.close()
        await reader.aclose()

    # Assert
    assert counted == 1
