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

**`test_a_pack_declared_ext_model_reaches_the_store_with_no_cli_edit`, task 5.2g's own
round-trip proof.** Every other proof in this tree either registers an `ExtModel` by hand
(`test_store_conformance.py`'s own module-level `register_ext_model(PdfPages)`) or never
calls `weft_kernel.discovery.discover` at all, as the test above does not. This one runs
the real mechanism end to end: `discover()` against the real, installed `weft-index` pack,
whose own `register()` now buffers `weft_index.payload.Representation` through
`PackRegistrar.add_ext_model`, then `weft_store.rehydrate.register_from_reports` — the
generic consumer `weft_cli.registry_bootstrap.build_dependencies` calls — with
`Representation` named nowhere in that test except to build the node and check what came
back. `Representation` is the subject rather than `PdfPages` on purpose: before this task
it had no rehydration path at all, not even a hand-written shim, so its round trip is the
cleanest demonstration that `register_from_reports` closes the gap generically.
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
from weft_extract import Extractor, TextExtractor, discover_source_docs
from weft_kernel.context import Context
from weft_kernel.discovery import PackReport, PackStatus
from weft_kernel.payload import MediaType, Node, SourceId
from weft_kernel.registry import Registry
from weft_kernel.runner import Runner, StageSpec
from weft_store import NodeStore
from weft_store.pgvector_store import PgVectorSettings, PgVectorStore
from weft_store.rehydrate import register_from_reports

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
    docs = discover_source_docs(tmp_path, extensions=TextExtractor.extensions)
    assert docs, "fixture wrote files discover_source_docs should have found"

    def store_factory(_config: object) -> PgVectorStore:
        return store

    # `weft-chunk`'s own `ExtModel` — ledger task **6.17**. A hand-built `Registry` runs no pack's
    # `register()`, so nothing calls `PackRegistrar.add_ext_model` and nothing reaches
    # `weft_store.rehydrate`'s process-global namespace registry. Reading a chunk back then fails
    # with `no 'weft-chunk' is registered for ExtModel`, and this file passed only because some
    # *other* test file had run a real `discover()` first — a test that passes because another
    # file ran before it is a defect in the test (`docs/lessons.md` L5.21).
    #
    # Through `register_from_reports`, not `register_ext_model`: the latter refuses a second call
    # even for the same class, so the fix would work alone and fail in the full suite. That
    # difference contradicts `rehydrate.py`'s own docstring and is `docs/lessons.md` L6.28.
    register_from_reports(
        [
            PackReport(
                pack="chunk",
                distribution="weft-chunk",
                status=PackStatus.ACTIVE,
                ext_models=(ChunkOffset,),
            )
        ]
    )
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


def _discover_and_wire_ext_models() -> None:
    """The real mechanism, end to end: `discover()`, then the one generic call
    `weft_cli.registry_bootstrap.build_dependencies` makes right after it — see the module
    docstring's own paragraph on the test below.

    Imported lazily so this module's own top-level imports stay narrow — nothing else here
    needs `weft_kernel.discovery` or `weft_store.rehydrate`. `allow` is restricted to
    `weft-index` and the packs its own `register()` needs to import cleanly, rather than
    left open, for the identical reason `test_ff2_no_privileged_builtins.py` restricts it:
    an open `discover()` would also import `weft-canary`.
    """
    from weft_kernel.discovery import discover
    from weft_kernel.registry import Registry
    from weft_store.rehydrate import register_from_reports

    registry = Registry()
    reports = discover(
        registry,
        allow=frozenset({"weft-index", "weft-store", "weft-prompts"}),
        pack_settings={"store": {"dsn": _DSN}},
    )
    register_from_reports(reports)


async def test_a_pack_declared_ext_model_reaches_the_store_with_no_cli_edit(
    store: PgVectorStore,
) -> None:
    # Arrange — the real registration path, then a node carrying the namespace it unlocks.
    from weft_index.payload import Representation

    _discover_and_wire_ext_models()
    node = Node.synthetic(
        content="a generated question standing in for its parent chunk",
        media_type=MediaType.TEXT,
        reason="ext-model round-trip proof",
        sources=frozenset({SourceId("source-a")}),
    ).with_ext(Representation(technique="hypothetical-questions"))

    # Act
    await store.add((node,))
    await store.flush()
    found = await store.get([node.id])

    # Assert — the namespace that had no rehydration path at all before task 5.2g now
    # survives, reconstructed by the class `weft_index`'s own `register()` declared.
    assert len(found) == 1
    assert found[0].ext_as(Representation) == Representation(technique="hypothetical-questions")
