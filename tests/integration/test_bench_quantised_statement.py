"""Phase 29 task **29.8** — the rescoring statement ranks what the store ranks.

With no index and a candidate set as large as the table, the inner quantised ordering cannot drop
a true neighbour, so the outer full-precision ordering must return exactly the ids, in exactly the
order, that `PgVectorStore.search_vector` returns. A statement that rescored by the quantised
distance, or that forgot the outer ordering, fails here; recall below 1.0 in a real run is then a
fact about the quantised index, not about the statement.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import bench_quantised
import psycopg
import pytest
from pgvector import Vector as PgVector
from pgvector.psycopg import register_vector_async
from pydantic import SecretStr

from weft_kernel.payload import MediaType, Node, Vector
from weft_store.pgvector_store import PgVectorSettings, PgVectorStore

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")
_ROWS = 60


def _node(n: int) -> Node:
    angle = n * 0.1
    return Node.synthetic(
        content=f"row {n}", media_type=MediaType.TEXT, reason="29.8 shape check"
    ).with_embedding(Vector(values=(1.0, angle, -angle * angle)))


@pytest.fixture
async def store() -> AsyncIterator[PgVectorStore]:
    try:
        probe = await psycopg.AsyncConnection.connect(_DSN, connect_timeout=2)
    except psycopg.OperationalError as exc:
        pytest.skip(f"WEFT_DATABASE_URL ({_DSN}) is unreachable: {exc}")
    await probe.close()
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


@pytest.mark.parametrize("quantisation", list(bench_quantised.Quantisation))
async def test_rescoring_over_the_whole_table_returns_the_exact_ranking(
    store: PgVectorStore, quantisation: bench_quantised.Quantisation
) -> None:
    # Arrange
    query = (1.0, 2.5, -6.0)
    conn = await psycopg.AsyncConnection.connect(_DSN)
    await register_vector_async(conn)

    # Act
    exact = [scored.value.id for scored in await store.search_vector(Vector(values=query), 10)]
    async with conn.cursor() as cur:
        await cur.execute(
            bench_quantised.rescored_statement(quantisation, width=3, selectivity=None),
            {"vector": PgVector(list(query)), "top_k": 10, "candidates": _ROWS},
        )
        rescored = [row[0] for row in await cur.fetchall()]
    await conn.close()

    # Assert
    assert len(exact) == 10
    assert rescored == exact
