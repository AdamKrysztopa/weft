"""`docs/build-ledger.md` **2.34**: every document `corpus/manifest.toml` names indexes.

Before this task, `corpus/arxiv/2508.18901v1.pdf` — declared at
`corpus/manifest.toml:122-129` — extracted through `weft-pdf`'s `pdf-text`
backend to a `Produced` `Node` whose `content` carried 65 NUL bytes (measured
directly against `PdfTextExtractor.run`, 2026-08-18), and `weft-store`'s
`weft_nodes.content` column (`weft_store/pgvector_store.py:138`) is `TEXT
NOT NULL` — Postgres refuses a NUL byte in a `TEXT` value, so the real
`PgVectorStore` against the real container answered `DataError: PostgreSQL
text fields cannot contain NUL (0x00) bytes` for this document specifically.

This is the exit demonstration `docs/build-ledger.md` → 2.34 names: this same
document, run through the ordinary ingest pipeline — `pdf-text` → `fixed-
size` → `hash` → `pgvector`, composed by `weft_kernel.runner.Runner` exactly
as `tests/integration/test_ingest_pipeline.py` composes the built-in four —
now reaches the real container and is stored, because `weft_kernel.seam.wrap`
(every stage call in this pipeline goes through it — `runner.py:210`)
replaces every NUL byte with a space and counts them before a `Produced`
`Node` ever reaches `PgVectorStore.upsert`.

Against the real container, same skip discipline as `test_ingest_pipeline.py`.
"""

import os
from collections.abc import AsyncIterator
from pathlib import Path

import psycopg
import pytest
from pydantic import SecretStr

from weft_chunk import Chunker, FixedSizeChunker
from weft_chunk.payload import ChunkOffset
from weft_embed import Embedder, HashEmbedder
from weft_extract.contract import Extractor, SourceDoc
from weft_kernel.context import Context
from weft_kernel.payload import ExtModel, SourceId
from weft_kernel.registry import Registry
from weft_kernel.runner import Runner, StageSpec
from weft_pdf import PdfPages, PdfTextExtractor
from weft_store import NodeStore
from weft_store.pgvector_store import PgVectorSettings, PgVectorStore

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")

#: `corpus/manifest.toml:122-129` — one of the two `fetch`-tier PDFs 2.34's own note
#: names as carrying NUL bytes in its extracted text.
_PDF_PATH = Path(__file__).resolve().parents[2] / "corpus" / "arxiv" / "2508.18901v1.pdf"


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _ensure_rehydrates(model: type[ExtModel]) -> None:
    """Register `model` with `weft_store.rehydrate` if nothing has claimed its namespace yet.

    This test hand-assembles a `Registry` and never calls `weft_kernel.discovery.discover`,
    so `weft_chunk`/`weft_pdf`'s own `register()` — which now buffers `ChunkOffset`/
    `PdfPages` through `PackRegistrar.add_ext_model` (task 5.2g) — never runs either.
    `weft_store.rehydrate.register_from_reports` is the real, generic consumer of that
    buffer; this wraps one bare model in a throwaway `PackReport` and hands it that same
    function, rather than re-deriving its idempotent-or-refuse logic by hand a second time.
    `store.scan()` needs both namespaces reconstructable to prove the stored node
    round-trips clean, not only that the insert succeeded.
    """
    from weft_kernel.discovery import PackReport, PackStatus
    from weft_store.rehydrate import register_from_reports

    report = PackReport(
        distribution=model.__namespace__, status=PackStatus.ACTIVE, ext_models=(model,)
    )
    register_from_reports((report,))


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


async def test_the_corpus_pdf_carrying_nul_bytes_indexes_into_the_real_store(
    store: PgVectorStore,
) -> None:
    # Arrange — the exact document 2.34's own note measured, read as `weft index` would.
    _ensure_rehydrates(ChunkOffset)
    _ensure_rehydrates(PdfPages)
    if not _PDF_PATH.is_file():
        pytest.skip(f"corpus fixture missing: {_PDF_PATH}")
    content = _PDF_PATH.read_bytes()
    doc = SourceDoc(source_id=SourceId("ax-2508.18901v1"), uri=str(_PDF_PATH), content=content)

    def store_factory(_config: object) -> PgVectorStore:
        return store

    registry = Registry()
    registry.add(Extractor, "pdf-text", PdfTextExtractor, distribution="weft-pdf")
    registry.add(Chunker, "fixed-size", FixedSizeChunker, distribution="weft-chunk")
    registry.add(Embedder, "hash", HashEmbedder, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", store_factory, distribution="weft-store")
    engine = Runner(registry)
    specs = (
        StageSpec(id="extract", contract=Extractor, name="pdf-text"),
        StageSpec(id="chunk", contract=Chunker, name="fixed-size"),
        StageSpec(id="embed", contract=Embedder, name="hash"),
        StageSpec(id="store", contract=NodeStore, name="pgvector"),
    )

    async def batches() -> AsyncIterator[object]:
        yield [doc]

    # Act — the same run that answered `DataError` before this task.
    pipeline = engine.resolve(specs, tenant_id="tenant-a")
    summary = await engine.run(pipeline, batches(), _ctx())

    # Assert — the document is stored, and no NUL byte survived into a stored node's content.
    assert summary.produced > 0
    stored_count = await store.count()
    assert stored_count > 0
    page = await store.scan()
    assert page.items, "the store returned no nodes to check"
    assert all("\x00" not in node.content for node in page.items)
