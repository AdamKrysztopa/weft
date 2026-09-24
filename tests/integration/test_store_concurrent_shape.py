"""Phase 29 task **29.1(b)** — the concurrent shape: one process, one store, eight searches at once.

`fix-plans/05` found that nothing shipped fanned out on one store. Since 43.20, `raptor` fans out
checkpoint keeps, and `LayerCheckpoints` serialises them because a `Lifetime.RUN` store owes no
concurrency (R43.40). psycopg's per-connection lock orders statements, not transactions. So this
is a forward measurement of concurrent *reads* for an application embedding Weft in its own event
loop, not a property of the binary.
It cannot be a script — fitness function 7(a) keeps `asyncio.run` out of `scripts/` — so it is a
test, and it measures only a database the harness loaded and named in `WEFT_BENCH_DATABASE_URL`.
Run with `-s` to read the line it prints.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Sequence

import psycopg
import pytest
from pydantic import SecretStr

from weft_kernel.payload import Node, Vector
from weft_store import Scored
from weft_store.pgvector_store import PgVectorSettings, PgVectorStore

_BENCH_DSN = os.environ.get("WEFT_BENCH_DATABASE_URL", "").strip()
_CALLS = 8
_TOP_K = 10


async def _query_vectors(dsn: str) -> list[Vector]:
    conn = await psycopg.AsyncConnection.connect(dsn)
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT embedding::text FROM weft_nodes WHERE embedding IS NOT NULL "
                "ORDER BY id LIMIT %s",
                (_CALLS,),
            )
            rows = await cur.fetchall()
    finally:
        await conn.close()
    return [
        Vector(values=tuple(float(v) for v in str(row[0]).strip("[]").split(","))) for row in rows
    ]


async def _timed(store: PgVectorStore, vector: Vector) -> tuple[float, Sequence[Scored[Node]]]:
    started = time.monotonic()
    found = await store.search_vector(vector, _TOP_K)
    return time.monotonic() - started, found


async def test_eight_concurrent_searches_on_one_store_against_the_benchmark_database() -> None:
    if not _BENCH_DSN:
        pytest.skip(
            "WEFT_BENCH_DATABASE_URL is unset: task 29.1's concurrent-shape arm measures a "
            "benchmark database the harness loaded, never the test database"
        )
    # Arrange
    store = PgVectorStore(PgVectorSettings(dsn=SecretStr(_BENCH_DSN)))
    try:
        before = await store.count()
        assert before >= _CALLS, f"the benchmark database holds {before} rows; load it first"
        vectors = await _query_vectors(_BENCH_DSN)

        # Act
        sequential_started = time.monotonic()
        sequential = [await _timed(store, vector) for vector in vectors]
        sequential_total = time.monotonic() - sequential_started
        gathered_started = time.monotonic()
        gathered = await asyncio.gather(*(_timed(store, vector) for vector in vectors))
        gathered_total = time.monotonic() - gathered_started
        after = await store.count()
    finally:
        await store.aclose()

    # Assert
    assert after == before, (
        f"before: {before:,} rows   after: {after:,} rows — measurement abandoned"
    )
    expected = min(_TOP_K, before)
    assert all(len(found) == expected for _, found in (*sequential, *gathered))
    print(
        f"concurrent shape: calls: {_CALLS}  width: {len(vectors[0].values)}  "
        f"sequential total: {sequential_total * 1000:.1f} ms  "
        f"gather total: {gathered_total * 1000:.1f} ms  "
        f"slowest gathered call: {max(seconds for seconds, _ in gathered) * 1000:.1f} ms  "
        f"before: {before:,} rows  after: {after:,} rows"
    )
