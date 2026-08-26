"""`NodeStore.list_sources()` answers the question `02` §1 says it answers — ledger task **6.24**.

`docs/02-extension-model.md` §1, corrected at task 6.21 rather than left standing: the claim that
*"`list_sources`, `scan` and `count` already answer what should exist"* was **true of the contract
and false of the running system**. Nothing on the ingest path called `put_source` — one caller
existed in the whole tree, inside `weft_qdrant.store` itself — so `weft_sources` was empty after a
real `weft index` and `list_sources()` returned `()`. A `reconcile --mode repair` pass built on
that deleted every graph node the `kg` pipeline had just written. It was found by running the
binary, and not by the tests, whose hand-written corpus double populated the method the system did
not (`docs/lessons.md` L6.14).

**So this is deliberately an integration test against the real store**, not a unit test with a
double. A double is what hid the defect for a whole phase: it answered a question the running
system could not, and every assertion built on it was true about the double and false about Weft.
The subject here is the actual ingest path writing to an actual `PgVectorStore`, read back through
the published contract.

**The container discipline is this directory's own**, repeated rather than shared for the reason
every module here already gives: each should read as one self-contained scenario. An absent
container means skipped with the reason printed, never silently passed —
`docs/06-phase-0-build.md`.

**What `02` §1 says the record is for**, and therefore what is asserted: "`id`, `uri`,
`content_hash`, `indexed_at`, `pipeline`, `status` — one structure serving change detection
(re-index skips an unchanged file instead of re-paying for every enhancer's LLM calls), cascade
resumption, and `doctor`'s inventory. `pipeline` is what lets `weft index` say *'already indexed,
by a different pipeline'* rather than silently skipping or silently duplicating."
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest
from pydantic import SecretStr

from weft_cli.ingest import run_index
from weft_cli.registry_bootstrap import build_dependencies
from weft_kernel.context import Context
from weft_store.contract import SourceStatus
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
async def clean_database() -> AsyncIterator[None]:
    reason = await _database_reachable()
    if reason is not None:
        pytest.skip(reason)
    schema_forcer = PgVectorStore(PgVectorSettings(dsn=SecretStr(_DSN)))
    await schema_forcer.count()
    await schema_forcer.aclose()
    conn = await psycopg.AsyncConnection.connect(_DSN, autocommit=True)
    async with conn.cursor() as cur:
        await cur.execute("TRUNCATE weft_nodes, weft_sources")
    await conn.close()
    yield


@pytest.fixture
async def store() -> AsyncIterator[PgVectorStore]:
    instance = PgVectorStore(PgVectorSettings(dsn=SecretStr(_DSN)))
    yield instance
    await instance.aclose()


async def test_indexing_records_a_source_for_every_document_it_indexed(
    clean_database: None,
    store: PgVectorStore,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The property, read back through the published contract rather than off a table."""
    # Arrange
    del clean_database
    monkeypatch.setenv("WEFT_DATABASE_URL", _DSN)
    (tmp_path / "fox.txt").write_text("The quick brown fox jumps over the lazy dog.")
    (tmp_path / "notes.md").write_text("# Notes\n\nWeft is a microkernel RAG engine.")
    deps = build_dependencies(config_path=tmp_path / "weft.toml")
    before = datetime.now(UTC)

    # Act
    await run_index(tmp_path, registry=deps.registry, ctx=_ctx())
    recorded = await store.list_sources()

    # Assert
    assert len(recorded) == 2, (
        f"two files were indexed and `list_sources()` returned {len(recorded)}. `02` §1 says "
        f"this method answers *what should exist*, and a reconcile pass built on it deleted a "
        f"corpus when it answered emptily (`docs/lessons.md` L6.14)."
    )
    assert {Path(record.uri).name for record in recorded} == {"fox.txt", "notes.md"}
    assert all(record.status is SourceStatus.ACTIVE for record in recorded)
    assert all(record.indexed_at >= before for record in recorded)


async def test_the_recorded_hash_is_of_the_bytes_that_were_indexed(
    clean_database: None,
    store: PgVectorStore,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`content_hash` serves change detection — "re-index skips an unchanged file instead of
    re-paying for every enhancer's LLM calls" (`02` §1). A hash of anything other than the
    document's own bytes cannot do that, so the fact asserted is the hash's *meaning*, not its
    presence.
    """
    # Arrange
    del clean_database
    monkeypatch.setenv("WEFT_DATABASE_URL", _DSN)
    content = b"The quick brown fox jumps over the lazy dog."
    (tmp_path / "fox.txt").write_bytes(content)
    deps = build_dependencies(config_path=tmp_path / "weft.toml")

    # Act
    await run_index(tmp_path, registry=deps.registry, ctx=_ctx())
    [record] = await store.list_sources()

    # Assert
    assert record.content_hash == hashlib.sha256(content).hexdigest()


async def test_re_indexing_the_same_directory_updates_rather_than_duplicates(
    clean_database: None,
    store: PgVectorStore,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A source has one record, whatever it has been indexed by — `SourceRecord.id` is the
    identity. `02` §1's own purpose for `pipeline` depends on this: `weft index` can only say
    *"already indexed, by a different pipeline"* if the previous record is still findable and
    singular.
    """
    # Arrange
    del clean_database
    monkeypatch.setenv("WEFT_DATABASE_URL", _DSN)
    document = tmp_path / "fox.txt"
    document.write_text("The quick brown fox jumps over the lazy dog.")
    deps = build_dependencies(config_path=tmp_path / "weft.toml")
    await run_index(tmp_path, registry=deps.registry, ctx=_ctx())
    [first] = await store.list_sources()

    # Act — the same file, changed, indexed again.
    document.write_text("A different sentence entirely.")
    await run_index(tmp_path, registry=deps.registry, ctx=_ctx())
    recorded = await store.list_sources()

    # Assert
    assert len(recorded) == 1, "one source, one record — re-indexing must not accumulate rows"
    assert recorded[0].id == first.id
    assert recorded[0].content_hash != first.content_hash, (
        "the file changed, so the recorded hash must have changed with it — otherwise change "
        "detection would skip a document that is not the one it was told about"
    )


async def test_a_recorded_source_names_the_pipeline_that_indexed_it(
    clean_database: None,
    store: PgVectorStore,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`02` §1: `pipeline` "is what lets `weft index` say *'already indexed, by a different
    pipeline'*". The default path resolves no `ResolvedPipeline` at all (`IndexResult`'s own
    docstring), so what it records is the built-in path's own stable name — a field that means
    "which pipeline" cannot be left empty on the one path most corpora are indexed by.
    """
    # Arrange
    del clean_database
    monkeypatch.setenv("WEFT_DATABASE_URL", _DSN)
    (tmp_path / "fox.txt").write_text("The quick brown fox jumps over the lazy dog.")
    deps = build_dependencies(config_path=tmp_path / "weft.toml")

    # Act
    await run_index(tmp_path, registry=deps.registry, ctx=_ctx())
    [record] = await store.list_sources()

    # Assert
    assert record.pipeline, "a source record with no pipeline cannot answer 'by which pipeline'"
