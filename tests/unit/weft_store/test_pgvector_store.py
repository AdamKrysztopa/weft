"""Tests for `weft_store.pgvector_store`, against a real Postgres + pgvector container.

Mirrors `packages/weft-store/src/weft_store/pgvector_store.py`. Per
`docs/06-phase-0-build.md` step 8, "integration tests must run against the
real container, not a mock, and must be skipped with a clear reason — never
silently passed — when it is absent." `docker compose up -d` (`compose.yaml`,
repository root) brings the container up; `WEFT_DATABASE_URL` names it. If
the connection attempt below fails for any reason, every test in this module
is skipped with that reason attached, rather than quietly reporting green.

Covers the happy path (round-tripping a node through `add`/`get`, including
its lineage, its `SyntheticOrigin` ext data and its embedding — pgvector's
own single-precision storage means the embedding is compared with tolerance,
not exact equality), the edge case of `search_vector` ranking by cosine
distance, and the error case of a `Filter` this store does not yet translate.
"""

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import psycopg
import pytest
from pydantic import SecretStr

from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, SourceId, Vector
from weft_kernel.registry import Registry
from weft_kernel.runner import Runner, StageSpec
from weft_store.contract import Filter, FilterOp, NodeStore, SourceRecord, VectorSearch
from weft_store.pgvector_store import PgVectorSettings, PgVectorStore, UnsupportedFilterError

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


async def _database_reachable() -> str | None:
    """`None` if a real connection to `_DSN` succeeds; otherwise the reason it did not."""
    try:
        conn = await psycopg.AsyncConnection.connect(_DSN, connect_timeout=2)
    except psycopg.OperationalError as exc:
        return f"WEFT_DATABASE_URL ({_DSN}) is unreachable: {exc}"
    await conn.close()
    return None


@pytest.fixture
async def store() -> AsyncIterator[PgVectorStore]:
    """A `PgVectorStore` against a truncated schema — skips the whole module if unreachable."""
    reason = await _database_reachable()
    if reason is not None:
        pytest.skip(reason)
    instance = PgVectorStore(PgVectorSettings(dsn=SecretStr(_DSN)))
    await instance.count()  # forces schema creation (extension + tables) through public API
    conn = await psycopg.AsyncConnection.connect(_DSN, autocommit=True)
    async with conn.cursor() as cur:
        await cur.execute("TRUNCATE weft_nodes, weft_sources")
    await conn.close()
    yield instance
    await instance.aclose()


def _node(content: str, *, sources: frozenset[SourceId] = frozenset()) -> Node:
    return Node.synthetic(
        content=content, media_type=MediaType.TEXT, reason="test fixture", sources=sources
    )


async def test_add_and_get_round_trip_a_node_including_lineage_and_ext(
    store: PgVectorStore,
) -> None:
    # Arrange
    node = _node("hello world", sources=frozenset({SourceId("doc-1")})).with_embedding(
        Vector(values=(0.5, -0.25, 0.75))
    )

    # Act
    await store.add([node])
    [fetched] = await store.get([node.id])

    # Assert
    assert fetched.id == node.id
    assert fetched.content == node.content
    assert fetched.lineage.sources == node.lineage.sources
    assert fetched.ext == node.ext
    assert fetched.embedding is not None and node.embedding is not None
    assert fetched.embedding.values == pytest.approx(node.embedding.values, abs=1e-6)


async def test_run_composes_through_the_kernel_runner_as_a_node_store_stage(
    store: PgVectorStore,
) -> None:
    # Arrange
    def factory(_config: object) -> PgVectorStore:
        return store

    registry = Registry()
    registry.add(NodeStore, "pgvector", factory, distribution="weft-store")
    engine = Runner(registry)
    specs = (StageSpec(id="store", contract=NodeStore, name="pgvector"),)
    node = _node("via the runner")

    async def batches() -> AsyncIterator[list[Node]]:
        yield [node]

    # Act
    pipeline = engine.resolve(specs, tenant_id="tenant-a")
    summary = await engine.run(pipeline, batches(), _ctx())

    # Assert
    assert summary.produced == 1
    assert await store.count() == 1


async def test_search_vector_ranks_by_cosine_distance_and_advertises_vector_search(
    store: PgVectorStore,
) -> None:
    # Arrange
    near = _node("near").with_embedding(Vector(values=(1.0, 0.0)))
    far = _node("far").with_embedding(Vector(values=(-1.0, 0.0)))
    await store.add([near, far])

    # Act
    results = await store.search_vector(Vector(values=(1.0, 0.0)), top_k=2)

    # Assert
    assert isinstance(store, VectorSearch)
    assert [scored.value.id for scored in results] == [near.id, far.id]
    assert results[0].score > results[1].score


async def test_search_vector_refuses_an_unimplemented_filter(store: PgVectorStore) -> None:
    # Arrange
    a_filter = Filter(op=FilterOp.EXISTS, field="media_type")

    # Act / Assert
    with pytest.raises(UnsupportedFilterError):
        await store.search_vector(Vector(values=(1.0,)), top_k=5, filter=a_filter)


async def test_delete_source_removes_every_node_carrying_that_source(
    store: PgVectorStore,
) -> None:
    # Arrange
    doomed = _node("doomed", sources=frozenset({SourceId("doc-1")}))
    survivor = _node("survivor", sources=frozenset({SourceId("doc-2")}))
    await store.add([doomed, survivor])
    await store.put_source(
        SourceRecord(
            id=SourceId("doc-1"),
            uri="file:///doomed.txt",
            content_hash="abc",
            indexed_at=datetime.now(UTC),
            pipeline="base",
        )
    )

    # Act
    removed = await store.delete_source(SourceId("doc-1"))

    # Assert
    assert removed.node_count == 1
    assert await store.count() == 1
    assert await store.get_source(SourceId("doc-1")) is None
