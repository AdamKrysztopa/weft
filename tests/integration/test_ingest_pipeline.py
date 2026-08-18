"""The Phase 0 step 8 exit test: an ingest pipeline over the four built-ins, against pgvector.

`docs/06-phase-0-build.md` step 8 — "**Makes true:** indexing produces
stored nodes. **Runnable:** an ingest pipeline, in a test." This is that
test: a directory of `.txt`/`.md` files runs through `weft_extract.TextExtractor`
→ `weft_chunk.FixedSizeChunker` → `weft_embed.HashEmbedder` →
`weft_store.PgVectorStore`, composed and run by `weft_kernel.runner.Runner`
exactly the way `weft-cli` will compose them at step 9 — an explicit,
written-out `StageSpec` list, per `06`'s minimal choice for G2's second trap.

Against the real container — `docs/06-phase-0-build.md`: "Integration tests
must run against the real container, not a mock, and must be skipped with a
clear reason — never silently passed — when it is absent." See the module
docstring of `tests/unit/weft_store/test_pgvector_store.py` for the same
skip discipline, repeated here rather than shared, because this is the one
test in the tree that exercises all four built-ins as one pipeline and
should read as a single, self-contained scenario.
"""

import os
from collections.abc import AsyncIterator
from pathlib import Path

import psycopg
import pytest
from pydantic import SecretStr

from weft_chunk import Chunker, FixedSizeChunker
from weft_embed import Embedder, HashEmbedder
from weft_extract import Extractor, TextExtractor, discover_source_docs
from weft_kernel.context import Context
from weft_kernel.registry import Registry
from weft_kernel.runner import Runner, StageSpec
from weft_store import NodeStore
from weft_store.pgvector_store import PgVectorSettings, PgVectorStore

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


async def _database_reachable() -> str | None:
    try:
        conn = await psycopg.AsyncConnection.connect(_DSN, connect_timeout=2)
    except psycopg.OperationalError as exc:
        return f"WEFT_DATABASE_URL ({_DSN}) is unreachable: {exc}"
    await conn.close()
    return None


@pytest.fixture
async def store() -> AsyncIterator[PgVectorStore]:
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


async def test_ingest_pipeline_produces_stored_nodes(store: PgVectorStore, tmp_path: Path) -> None:
    # Arrange — a small directory of source documents.
    (tmp_path / "one.txt").write_text("The quick brown fox jumps over the lazy dog.")
    (tmp_path / "two.md").write_text("# Notes\n\nWeft is a microkernel RAG engine.")
    docs = discover_source_docs(tmp_path)
    assert docs, "fixture wrote files discover_source_docs should have found"

    def store_factory(_config: object) -> PgVectorStore:
        return store

    registry = Registry()
    registry.add(Extractor, "text", TextExtractor, distribution="weft-extract")
    registry.add(Chunker, "fixed-size", FixedSizeChunker, distribution="weft-chunk")
    registry.add(Embedder, "hash", HashEmbedder, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", store_factory, distribution="weft-store")
    engine = Runner(registry)
    specs = (
        StageSpec(id="extract", contract=Extractor, name="text"),
        StageSpec(id="chunk", contract=Chunker, name="fixed-size"),
        StageSpec(id="embed", contract=Embedder, name="hash"),
        StageSpec(id="store", contract=NodeStore, name="pgvector"),
    )

    async def batches() -> AsyncIterator[object]:
        yield docs

    # Act
    pipeline = engine.resolve(specs, tenant_id="tenant-a")
    summary = await engine.run(pipeline, batches(), _ctx())

    # Assert — the batch made it through every stage, and the store actually has the nodes.
    assert summary.produced == 1
    stored_count = await store.count()
    assert stored_count > 0
    page = await store.scan()
    assert all(node.embedding is not None for node in page.items)
