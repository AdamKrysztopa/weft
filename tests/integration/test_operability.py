"""`09` §5.2's *Operability* promises, executed rather than asserted — ledger task **6.8**.

Two items on the production-ready checklist, each of which `09` states with the condition that
**fails** it:

- "A cancelled run leaves the store durable to its last finished batch, per `02` §1's `flush`
  guarantee, and a resumable delete finishes on the next command. *Fails if a crash mid-delete
  leaves a store that no later command repairs.*"
- "An upgrade path exists and was executed once: a store written by release *n* is read by release
  *n+1*. *Fails if this has never been run.*"

**Every mechanism these rest on already existed and every one was unit-tested; none had been run
end to end against the real store.** That gap is the whole of this task, and it is the gap
`docs/lessons.md` L6.14 was written about one task ago: `list_sources()` was true of the contract,
unit-tested against a double, and false of the running system. A promise on a release checklist is
worth exactly what has been executed of it.

**So each scenario is driven through the real objects.** A real `Runner` over a real
`PgVectorStore`, interrupted from inside the batch generator; a real tombstone written the way a
crash leaves one, finished by a real `reconcile` pass; a real `ExtModel` stored under one schema
version and read back under the next.

**Non-vacuity is the risk here, not failure.** Nothing needed building for this task, so every
scenario passed on its first run — which is precisely the condition under which a check proves
nothing (`docs/lessons.md` L5.19). Each test therefore establishes the *precondition* before the
act: the first batch really is in the store before the interruption, the tombstone really is
standing before the repair, and the stored payload really is at the older version before it is
read.

**The container discipline is this directory's own**, repeated rather than shared so each module
reads as one self-contained scenario: an absent container means the scenario is skipped with the
reason printed, never silently passed (`docs/06-phase-0-build.md`).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

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
from weft_kernel.payload.ext import ExtModel
from weft_kernel.registry import Registry
from weft_kernel.runner import Runner, StageSpec
from weft_store import NodeStore
from weft_store.contract import ReconcileMode, SourceRecord, SourceStatus
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
    await instance.count()
    conn = await psycopg.AsyncConnection.connect(_DSN, autocommit=True)
    async with conn.cursor() as cur:
        await cur.execute("TRUNCATE weft_nodes, weft_sources")
    await conn.close()
    yield instance
    await instance.aclose()


def _ingest_registry(store: PgVectorStore) -> Registry:
    """The four built-ins, wired by hand — and **the ext model `weft-chunk` declares**.

    A hand-built `Registry` never runs any pack's `register()`, so nothing calls
    `PackRegistrar.add_ext_model` and nothing reaches `weft_store.rehydrate`'s namespace
    registry. Reading a chunk back out then fails with `no 'weft-chunk' is registered for
    ExtModel`. That is not a quirk of this file: it is exactly the latent dependency ledger
    task **6.17** names in `tests/integration/test_ingest_pipeline.py`, which passes today only
    because some *other* test file ran a real `discover()` first and populated a process-global
    registry. A test that depends on file order is a defect in the test (`docs/lessons.md`
    L5.21), so this module registers what it needs and depends on nothing having gone before it.

    **Through `register_from_reports`, not `register_ext_model`.** `rehydrate.py`'s own module
    docstring says the two give "the identical idempotent-or-refuse behaviour either way" and
    names this exact caller — "a test, or a caller that builds a registry without running full
    discovery". Measured, they differ: `register_ext_model` refuses a second call even for the
    same class, so a suite where another file ran a real `discover()` first fails here with
    `DuplicateRegistrationError`. Only `register_from_reports` skips a namespace its own class
    already claimed. `docs/lessons.md` L6.28.
    """

    def store_factory(_config: object) -> PgVectorStore:
        return store

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
    return registry


_INGEST_SPECS = (
    StageSpec(id="extract", contract=Extractor, name="text"),
    StageSpec(id="chunk", contract=Chunker, name="fixed-size"),
    StageSpec(id="embed", contract=Embedder, name="hash"),
    StageSpec(id="store", contract=NodeStore, name="pgvector"),
)


async def test_an_interrupted_run_keeps_everything_the_last_finished_batch_stored(
    store: PgVectorStore, tmp_path: Path
) -> None:
    """`02` §1's `flush` guarantee, executed: what finished is durable, what was interrupted is
    simply absent. Nothing unwinds what the store already committed.
    """
    # Arrange — two batches from two directories, so "the last finished batch" is a real
    # boundary rather than a figure of speech.
    first_dir, second_dir = tmp_path / "first", tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    (first_dir / "one.txt").write_text("The quick brown fox jumps over the lazy dog.")
    (second_dir / "two.txt").write_text("A second document that never finishes.")
    first = discover_source_docs(first_dir, extensions=TextExtractor.extensions)
    second = discover_source_docs(second_dir, extensions=TextExtractor.extensions)
    assert first and second, "the fixture wrote files `discover_source_docs` should have found"
    runner = Runner(_ingest_registry(store))
    pipeline = runner.resolve(_INGEST_SPECS, tenant_id="tenant-a")
    seen_first = False

    async def batches() -> AsyncIterator[object]:
        nonlocal seen_first
        yield first
        seen_first = True
        # The interruption lands where a real one would: after one batch has been through
        # every stage, the store included.
        raise TimeoutError("interrupted after the first batch")
        yield second  # pragma: no cover - unreachable, and the point

    # Act
    with pytest.raises(TimeoutError):
        await runner.run(pipeline, batches(), _ctx())

    # Assert — the precondition first, so a store that never received anything cannot pass this.
    assert seen_first, "the first batch was never yielded; this scenario checked nothing"
    stored = await store.count()
    assert stored > 0, (
        "the run was interrupted after a batch the store had already accepted, and the store "
        "holds nothing. `02` §1's `flush` guarantee is that what finished is durable."
    )
    page = await store.scan()
    assert all(node.embedding is not None for node in page.items)
    assert not any("never finishes" in node.content for node in page.items), (
        "a document from the batch that was never yielded reached the store"
    )


async def test_a_delete_interrupted_after_its_tombstone_is_finished_by_the_next_command(
    store: PgVectorStore,
) -> None:
    """`02` §1: "a crash leaves `status=DELETING`, so the next call or `weft doctor` can finish
    the job rather than leaving it half-deleted and invisible."

    The crash is simulated at the one point where it matters — after `delete_source` wrote the
    tombstone and before it deleted the nodes. Writing the tombstone directly is what makes that
    reachable: the real method does both in one call, so there is no way to interrupt between
    them from outside, and a test that called `delete_source` and then checked the result would
    be testing the happy path under a different name.
    """
    # Arrange — a source with nodes, and a tombstone standing over it.
    source_id = SourceId("doomed-source")
    node = Node.synthetic(
        content="A document that a crash caught mid-deletion.",
        media_type=MediaType.TEXT,
        reason="a fixture for the resumable-delete scenario",
        sources=frozenset({source_id}),
    )
    await store.add([node])
    await store.put_source(
        SourceRecord(
            id=source_id,
            uri="file:///doomed",
            content_hash="0" * 64,
            indexed_at=datetime.now(UTC),
            pipeline="built-in",
            status=SourceStatus.DELETING,
        )
    )
    before = await store.count()
    assert before == 1, "the precondition failed: the node under the tombstone is not stored"
    estimate = await store.estimate(_ctx(), ReconcileMode.REPAIR)
    assert estimate.pending == 1, (
        "the store does not see an unfinished deletion to finish, so the pass below would "
        "converge by having nothing to do — which is not the same as repairing anything"
    )

    # Act — the next command, exactly as `weft reconcile` invokes it.
    report = await store.reconcile(_ctx(), ReconcileMode.REPAIR)

    # Assert
    assert report.removed == 1
    assert report.converged, "a pass that leaves the tombstone standing has not finished the job"
    assert await store.count() == 0
    assert list(await store.list_sources()) == []


class _Reading(ExtModel):
    """A pack's stored payload at the schema version release *n* wrote."""

    __namespace__: ClassVar[str] = "operability-reading"
    __schema_version__: ClassVar[str] = "1"

    celsius: float


class _ReadingV2(ExtModel):
    """The same payload as release *n+1* defines it — renamed field, and an `upgrade` that knows
    how to read what *n* wrote. This is the whole of what "an upgrade path exists" means for data
    at rest: G9's second axis, `ExtModel.__schema_version__`, whose base `upgrade` **refuses**
    rather than guessing.
    """

    __namespace__: ClassVar[str] = "operability-reading"
    __schema_version__: ClassVar[str] = "2"

    degrees_celsius: float

    @classmethod
    def upgrade(cls, data: Mapping[str, object], from_version: str | None) -> Mapping[str, object]:
        if from_version == "1":
            return {"degrees_celsius": data["celsius"]}
        return super().upgrade(data, from_version)


async def test_a_store_written_at_one_schema_version_is_read_at_the_next(
    store: PgVectorStore,
) -> None:
    """ "An upgrade path exists and was executed once" (`09` §5.2), for the only unit that can
    carry one before anything is published.

    **What "release *n* → *n+1*" can honestly mean today.** Nothing is on an index yet — that is
    ledger task **6.13** — so there is no *n+1* release to install. What there *is* is the axis
    G9 settled for exactly this problem: the contract version is not available at the read site,
    because the pack that wrote a row may not be installed, so the stored bytes carry
    `__schema_version__` and a reader **upgrades or refuses**. That is the upgrade path, and this
    executes it against the real store: bytes written under `1`, read back by the class that calls
    itself `2`.
    """
    # Arrange — the row is written by version 1's class. Only version 2 is *registered*, which
    # is the honest shape of an upgrade: the process reading the store runs release n+1's pack,
    # and release n's class is not installed any more. Writing needs no registration — `with_ext`
    # dumps — so the two halves come from two different classes exactly as they would in life.
    register_from_reports(
        [
            PackReport(
                pack="operability-test",
                distribution="weft-operability-test",
                status=PackStatus.ACTIVE,
                ext_models=(_ReadingV2,),
            )
        ]
    )
    source_id = SourceId("versioned-source")
    node = Node.synthetic(
        content="It was 21 degrees.",
        media_type=MediaType.TEXT,
        reason="a fixture for the schema-upgrade scenario",
        sources=frozenset({source_id}),
    ).with_ext(_Reading(celsius=21.0))
    await store.add([node])

    # Act — read it back through the registry release n+1 would have.
    page = await store.scan()

    # Assert — the value survived the version change rather than being refused or silently lost.
    [reread] = page.items
    upgraded = reread.ext_as(_ReadingV2)
    assert upgraded is not None, "the stored payload did not rehydrate under the newer class"
    assert upgraded.degrees_celsius == 21.0
