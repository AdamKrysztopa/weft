"""Phase 29 task **29.7** — the harness's filtered statement has the store's own shape.

`fix-plans/07` → 29.7: *"Selectivity is a bucket value written into the throwaway database under
the JSONB path `_predicate` builds, so the predicate has the store's own shape."* A string compare
against the store's SQL would pin a copy to a copy. So this asks the question that matters: over
one table, does the statement the harness times return exactly the ids, in exactly the order, that
`PgVectorStore.search_vector` returns for the equivalent `Filter`?
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import ClassVar

import bench_filtered
import psycopg
import pytest
from pgvector import Vector as PgVector
from pgvector.psycopg import register_vector_async
from pydantic import SecretStr

from weft_kernel.payload import ExtModel, MediaType, Node, SyntheticOrigin, Vector
from weft_kernel.registry import Registry
from weft_store import rehydrate
from weft_store.contract import Filter, FilterOp
from weft_store.pgvector_store import PgVectorSettings, PgVectorStore

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")
_ROWS = 60


class _BenchBuckets(ExtModel):
    __namespace__: ClassVar[str] = bench_filtered.BENCH_NAMESPACE
    __schema_version__: ClassVar[str] = "1.0.0"

    s50: bool
    s10: bool
    s1: bool
    s01: bool


def _node(n: int) -> Node:
    content = f"row {n}"
    buckets = {s.key: bench_filtered.in_bucket(content, s) for s in bench_filtered.Selectivity}
    angle = n * 0.1
    return (
        Node.synthetic(content=content, media_type=MediaType.TEXT, reason="29.7 shape check")
        .with_ext(_BenchBuckets(**buckets))
        .with_embedding(Vector(values=(1.0, angle, angle * angle)))
    )


@pytest.fixture
async def store(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[PgVectorStore]:
    try:
        probe = await psycopg.AsyncConnection.connect(_DSN, connect_timeout=2)
    except psycopg.OperationalError as exc:
        pytest.skip(f"WEFT_DATABASE_URL ({_DSN}) is unreachable: {exc}")
    await probe.close()
    fresh = Registry()
    monkeypatch.setattr(rehydrate, "ext_models", fresh)
    rehydrate.register_ext_model(SyntheticOrigin)
    rehydrate.register_ext_model(_BenchBuckets)
    instance = PgVectorStore(PgVectorSettings(dsn=SecretStr(_DSN)))
    await instance.count()
    conn = await psycopg.AsyncConnection.connect(_DSN, autocommit=True)
    async with conn.cursor() as cur:
        await cur.execute("TRUNCATE weft_nodes, weft_sources, weft_node_productions")
        # G22 commits the column to the first embedding's width, and that survives a
        # TRUNCATE. This fixture shares one database with every other suite, so the width
        # goes back to bare here or whichever test ran first refuses this one at setup.
        await cur.execute("ALTER TABLE weft_nodes ALTER COLUMN embedding TYPE vector")
    await conn.close()
    await instance.add([_node(n) for n in range(_ROWS)])
    yield instance
    await instance.aclose()


@pytest.mark.parametrize(
    "selectivity", [bench_filtered.Selectivity.HALF, bench_filtered.Selectivity.TENTH]
)
async def test_the_timed_statement_returns_what_the_store_returns_for_the_same_filter(
    store: PgVectorStore, selectivity: bench_filtered.Selectivity
) -> None:
    # Arrange
    query = (1.0, 2.5, 6.25)
    field = f"ext.{bench_filtered.BENCH_NAMESPACE}.{selectivity.key}"
    wanted = Filter(op=FilterOp.EQ, field=field, value=True)
    conn = await psycopg.AsyncConnection.connect(_DSN)
    await register_vector_async(conn)

    # Act
    found = await store.search_vector(Vector(values=query), 10, wanted)
    through_store = [scored.value.id for scored in found]
    async with conn.cursor() as cur:
        await cur.execute(
            bench_filtered.filtered_statement(selectivity),
            {"vector": PgVector(list(query)), "top_k": 10},
        )
        through_harness = [row[0] for row in await cur.fetchall()]
    await conn.close()

    # Assert — the filter really narrowed, so agreement is not two unfiltered scans agreeing.
    assert 0 < len(through_store) <= 10
    assert len(through_store) < _ROWS
    members = sum(bench_filtered.in_bucket(f"row {n}", selectivity) for n in range(_ROWS))
    assert len(through_store) == min(10, members)
    assert through_harness == through_store
