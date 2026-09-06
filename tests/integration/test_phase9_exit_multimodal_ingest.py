"""Phase 9's ingest exit, made repeatable — ledger task `9.8`.

The clause, in `01` → Phase 9 **Exit**'s own words: *a directory holding a PDF with at least one
table and one figure is indexed through a **shipped ingest document**; the store holds a `TABLE`
node carrying `TableGrid` and an `IMAGE` node carrying a `BlobRef` whose blob exists under the
configured root; `weft delete` of that source leaves node count and blob count at zero, with both
counts asserted immediately before and after.*

**Why this file exists beside the transcript rather than instead of it.** `9.8` says the
demonstration is run from outside the repository against installed wheels and lands in `manual/`,
and it does. But a transcript proves the day it was pasted and nothing after: Phase 5's exit was
never met while every box under it was ticked, which is why Phase 6 carries `6.21`. `L8.30` is the
narrower version — a close-review measurement read `nodes now stored: 70` and minutes later the
table held one row. So the same property is a test the gate re-runs, with the counts bracketed
either side exactly as `L8.30` requires.

**No shipped document named a PDF extractor until this task**, measured 2026-09-06. `index-pdf`
derives from `index-text` and replaces one stage; everything this exercises downstream of extraction
— a table passing the chunker whole (`9.2`), a grid surviving into `ext` (`9.5`), a figure's pixels
leaving the payload (`9.7`) — is inherited with nothing in that document mentioning any of it.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import psycopg
import pytest
from pydantic import SecretStr

from tests.unit.weft_pdf.minimal_pdf import ruled_table_and_figure
from weft_blob.filesystem_store import FilesystemBlobSettings, FilesystemBlobStore
from weft_blob.payload import BlobRef
from weft_cli.deletion import delete_everywhere, participants
from weft_cli.ingest import run_index
from weft_cli.service_roles import role_table_from_reports
from weft_cli.services import ServiceSelection
from weft_extract.payload import TableGrid
from weft_kernel.context import Context
from weft_kernel.discovery import PackReport, discover
from weft_kernel.payload import MediaType, SourceId
from weft_kernel.registry import Registry
from weft_store.pgvector_store import PgVectorSettings, PgVectorStore
from weft_store.rehydrate import register_from_reports

_DSN = "postgresql://weft:weft@localhost:5433/weft"


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


def _blobs_under(root: Path) -> int:
    return sum(1 for path in root.rglob("*") if path.is_file() and not path.name.startswith("."))


async def test_the_phase_9_ingest_exit(store: PgVectorStore, tmp_path: Path) -> None:
    """One PDF with a table and a figure, in and out again, counts bracketed either side."""
    # Arrange — a corpus of one born-digital PDF, and a blob root of its own.
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "report.pdf").write_bytes(ruled_table_and_figure())
    blob_root = tmp_path / "blobs"
    registry, reports = _discovered(blob_root)
    ctx = Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")
    # `[services] blob = "filesystem"`, exactly as an operator writes it: `run_index` assembles
    # the run's own `ServiceRegistry` from the role table (`9.0`), so a `BlobStore` put on this
    # `Context` by hand would be replaced before the first stage ran. Selecting the role is the
    # supported way and the one the binary takes.
    selection = ServiceSelection(roles={"blob": "filesystem"})
    roles = role_table_from_reports(reports)

    # Assert — the counts before, so the counts after mean something (`L8.30`).
    assert await store.count() == 0
    assert _blobs_under(blob_root) == 0

    # Act — through the shipped document, never a hand-assembled stage list.
    result = await run_index(
        corpus,
        registry=registry,
        ctx=ctx,
        pipeline="index-pdf",
        reports=reports,
        services=selection,
        roles=roles,
    )

    # Assert — both node kinds, the grid on one and the blob on the other.
    assert result.summary.failed == 0
    page = await store.scan()
    nodes = list(page.items)
    tables = [node for node in nodes if node.media_type is MediaType.TABLE]
    figures = [node for node in nodes if node.media_type is MediaType.IMAGE]
    assert len(tables) == 1, [node.media_type for node in nodes]
    assert len(figures) == 1, [node.media_type for node in nodes]

    grid = tables[0].ext_as(TableGrid)
    assert grid is not None
    assert grid.headers

    ref = figures[0].ext_as(BlobRef)
    assert ref is not None
    blobs = FilesystemBlobStore(FilesystemBlobSettings(root=blob_root))
    assert await blobs.open(ref.uri), "the BlobRef points at a blob that is not there"
    assert _blobs_under(blob_root) == 1

    # Act — delete the source, through the same fan-out `weft delete` uses.
    source = SourceId(str((corpus / "report.pdf").resolve()))
    targets = participants(registry=registry, store_names=frozenset({"pgvector"}))
    outcomes = await delete_everywhere(source, targets=targets)

    # Assert — both counts at zero, read immediately after, and both participants reported.
    assert not [outcome for outcome in outcomes if outcome.failed], outcomes
    assert await store.count() == 0
    assert _blobs_under(blob_root) == 0


def _discovered(blob_root: Path) -> tuple[Registry, tuple[PackReport, ...]]:
    """The registry an operator's own `weft.toml` would produce, built here instead.

    `build_dependencies()` reads a project config this test has no directory for, so the store and
    blob packs would fail settings validation and contribute no pipelines at all — the catalogue
    would be empty and `index-pdf` unknown, which is what the first run of this test reported. The
    settings are supplied directly: a real DSN, because this test wants the real container, and a
    blob root inside `tmp_path`, because the deletion half has to reap files this test can count.

    The **reports** are returned alongside, and `run_index` needs them: a pipeline document ships
    inside a pack, so the catalogue is built from `PackReport.contributions` rather than from the
    registry — pass the registry alone and `index-pdf` is unknown, which is exactly what the first
    run of this test reported.
    """
    registry = Registry()
    reports = discover(
        registry,
        pack_settings={"store": {"dsn": _DSN}, "blob": {"root": str(blob_root)}},
    )
    # What `build_dependencies` does after `discover` and this test must do too: a stored node's
    # `ext` is read back by namespace, so a namespace this process never registered rehydrates as
    # nothing at all — `UnknownPluginError` for 'weft-chunk', which is what the run before this
    # line existed reported.
    register_from_reports(reports)
    return registry, reports
