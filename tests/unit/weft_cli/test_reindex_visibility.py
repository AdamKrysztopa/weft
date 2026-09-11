"""Re-indexing with a different pipeline is visible — ledger task `9.17`.

`SourceRecord` has carried `content_hash` since G4 and `pipeline` since ledger 6.24, and `02` §1
says what they are for: *"`pipeline` is what lets `weft index` say 'already indexed, by a different
pipeline' rather than silently skipping or silently duplicating."* Measured 2026-09-06: **nothing
compares either one.** Every use in `packages/` is a write, a read-back into a model, or a copy —
`docs/internal/lessons.md` `L9.37`, confirmed independently by the survey for this task.

**What the task's own framing gets slightly wrong, corrected here rather than inherited.** `9.17`
says the risk is *"silently keeping whichever parse arrived first"*. It is not — node ids are
content digests (`weft_kernel.payload.node._content_digest`), so a different parse produces
*different* ids and `ON CONFLICT (id)` never fires: the old nodes and the new nodes **coexist**,
both retrievable, and the source row is overwritten so nothing records that the corpus was ever
built another way. Not "the first wins" — "both win, and the evidence is gone". That is worse, and
it is `L9.37`'s finding.

**This task makes it visible; it does not make it clean.** Removing the stale nodes is a deletion
on the ingest path and a larger change than this line asks for — `L9.37` says it "owes a ledger task
before it owes a rule", and that task is not this one. What lands here is the comparison and the
report, so an operator learns at the moment it happens rather than from a retrieval that quietly
mixes two parses.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from weft_chunk import Chunker
from weft_cli.ingest import SourceChange, changes_against_records, run_index
from weft_embed import Embedder
from weft_extract import Extractor
from weft_extract.contract import SourceDoc
from weft_kernel.context import Context
from weft_kernel.payload import NothingToProduce, Outcome, Produced, SourceId
from weft_kernel.registry import Registry
from weft_store import NodeStore, SourceRecord

_NOW = datetime(2026, 9, 6, tzinfo=UTC)


def _doc(content: bytes = b"hello") -> SourceDoc:
    return SourceDoc(source_id=SourceId("s-1"), uri="file:///a.txt", content=content)


def _record(*, content_hash: str, identity: str) -> SourceRecord:
    return SourceRecord(
        id=SourceId("s-1"),
        uri="file:///a.txt",
        content_hash=content_hash,
        indexed_at=_NOW,
        pipeline="index-text",
        pipeline_identity=identity,
    )


def _hash_of(content: bytes) -> str:
    import hashlib

    return hashlib.sha256(content).hexdigest()


def test_a_source_nothing_has_indexed_before_is_new() -> None:
    """The first index of anything, and the case every existing corpus is in."""
    # Act / Assert
    assert changes_against_records([_doc()], {}, identity="abc") == {
        SourceId("s-1"): SourceChange.NEW
    }


def test_the_same_bytes_through_the_same_pipeline_is_unchanged() -> None:
    """The common re-index, and the one an operator wants to hear nothing about."""
    # Arrange
    doc = _doc()
    records = {doc.source_id: _record(content_hash=_hash_of(doc.content), identity="abc")}

    # Act / Assert
    assert changes_against_records([doc], records, identity="abc") == {
        doc.source_id: SourceChange.UNCHANGED
    }


def test_different_bytes_through_the_same_pipeline_is_a_changed_document() -> None:
    """The document was edited. Distinct from a reparse, because the *source* moved."""
    # Arrange
    doc = _doc(b"edited")
    records = {doc.source_id: _record(content_hash=_hash_of(b"original"), identity="abc")}

    # Act / Assert
    assert changes_against_records([doc], records, identity="abc") == {
        doc.source_id: SourceChange.CONTENT_CHANGED
    }


def test_the_same_bytes_through_a_different_pipeline_is_a_reparse() -> None:
    """9.17's own case: the file did not move, the parser or the model did.

    This is the one that was invisible — the source row is overwritten and the old nodes stay.
    """
    # Arrange
    doc = _doc()
    records = {doc.source_id: _record(content_hash=_hash_of(doc.content), identity="old")}

    # Act / Assert
    assert changes_against_records([doc], records, identity="new") == {
        doc.source_id: SourceChange.PIPELINE_CHANGED
    }


def test_both_changing_at_once_reports_the_document_rather_than_the_pipeline() -> None:
    """An edited file through a new pipeline is re-parsed either way, so the reason an operator
    needs is the one they can act on: the document moved. Reporting the pipeline here would send
    someone looking for a configuration change that is not the interesting fact.
    """
    # Arrange
    doc = _doc(b"edited")
    records = {doc.source_id: _record(content_hash=_hash_of(b"original"), identity="old")}

    # Act / Assert
    assert changes_against_records([doc], records, identity="new") == {
        doc.source_id: SourceChange.CONTENT_CHANGED
    }


def test_a_record_written_before_this_task_reports_a_reparse_rather_than_unchanged() -> None:
    """The upgrade case, and the honest answer for it.

    Every `SourceRecord` already on disk has an empty `pipeline_identity`, because the field did
    not exist when it was written. That is not evidence the pipeline is unchanged — it is the
    absence of evidence, and `02` §1's own rule is that an empty answer is never a fact about the
    world. Reporting `UNCHANGED` here would claim a comparison nobody made.
    """
    # Arrange
    doc = _doc()
    records = {doc.source_id: _record(content_hash=_hash_of(doc.content), identity="")}

    # Act / Assert
    assert changes_against_records([doc], records, identity="abc") == {
        doc.source_id: SourceChange.PIPELINE_CHANGED
    }


def test_a_record_for_a_source_this_run_did_not_see_is_not_reported() -> None:
    """`weft index` reports on what it indexed. A source elsewhere in the corpus is not its news."""
    # Arrange
    other = SourceRecord(
        id=SourceId("s-2"),
        uri="file:///b.txt",
        content_hash="whatever",
        indexed_at=_NOW,
        pipeline="index-text",
        pipeline_identity="abc",
    )

    # Act
    changes = changes_against_records([_doc()], {other.id: other}, identity="abc")

    # Assert
    assert set(changes) == {SourceId("s-1")}


def test_the_record_a_run_writes_carries_the_identity_it_ran_under() -> None:
    """Otherwise the next run compares against nothing and every re-index reports a reparse."""
    # Act
    record = SourceRecord(
        id=SourceId("s-1"),
        uri="file:///a.txt",
        content_hash="h",
        indexed_at=_NOW,
        pipeline="index-text",
        pipeline_identity="abc",
    )

    # Assert
    assert record.pipeline_identity == "abc"


def test_the_identity_field_defaults_empty_so_every_existing_writer_keeps_working() -> None:
    """Additive for both of G9's audiences — `STORE_CONTRACT_VERSION` moves one minor."""
    # Act
    record = SourceRecord(
        id=SourceId("s-1"),
        uri="file:///a.txt",
        content_hash="h",
        indexed_at=_NOW,
        pipeline="index-text",
    )

    # Assert
    assert record.pipeline_identity == ""


class _RecordingStore:
    """A `NodeStore` double that also keeps `SourceRecord`s, so `run_index`'s own wiring of the
    comparison is exercised rather than only `changes_against_records`' arithmetic.

    Every test above this line hands `changes_against_records` a record mapping it built by hand.
    That proves the comparison and proves nothing about whether `run_index` ever computes an
    identity worth comparing — which is exactly where `9.17` was broken: verified through
    `weft index --pipeline …`, dead on `weft index <dir>`. See `docs/internal/lessons.md` `L9.64`.
    """

    def __init__(self, config: object) -> None:
        del config
        self.nodes: list[object] = []
        self.records: dict[SourceId, SourceRecord] = {}

    async def run(self, payload: Sequence[object], ctx: Context) -> Outcome[Sequence[object]]:
        del ctx
        self.nodes.extend(payload)
        return Produced(value=payload)

    async def add(self, nodes: Sequence[object]) -> None:
        self.nodes.extend(nodes)

    async def flush(self) -> None:
        return

    async def count(self) -> int:
        return len(self.nodes)

    async def put_source(self, record: SourceRecord) -> None:
        self.records[record.id] = record

    async def list_sources(self) -> Sequence[SourceRecord]:
        return tuple(self.records.values())


class _Passthrough:
    extensions: tuple[str, ...] = (".txt",)
    destroys: tuple[type, ...] = ()

    def __init__(self, config: object) -> None:
        del config

    async def run(self, payload: Sequence[object], ctx: Context) -> Outcome[Sequence[object]]:
        del ctx
        if not payload:
            return NothingToProduce(reason="nothing to pass through")
        return Produced(value=payload)


class _OtherExtractor(_Passthrough):
    """A second extractor claiming the same suffix — the thing `--extract` selects between."""


def _default_path_registry() -> tuple[Registry, _RecordingStore]:
    registry = Registry()
    registry.add(Extractor, "text", _Passthrough, distribution="weft-extract")
    registry.add(Extractor, "text-other", _OtherExtractor, distribution="acme-extract")
    registry.add(Chunker, "fixed-size", _Passthrough, distribution="weft-chunk")
    registry.add(Embedder, "hash", _Passthrough, distribution="weft-embed")
    store = _RecordingStore(None)

    def _store_factory(config: object) -> _RecordingStore:
        del config
        return store

    registry.add(NodeStore, "pgvector", _store_factory, distribution="weft-store")
    return registry, store


def _source_id(tmp_path: Path) -> SourceId:
    """What `weft_extract.text.discover_source_docs` assigns: the resolved absolute path.

    Spelled out here rather than hardcoded, because `tests/unit/weft_cli/test_ingest.py`'s own
    `document_ids` assertion pins the same convention on the same path and the two must not be
    free to drift apart.
    """
    return SourceId(str((tmp_path / "one.txt").resolve()))


def _default_ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


async def test_the_default_path_reports_a_reparse_when_the_extractor_changes(
    tmp_path: Path,
) -> None:
    """`weft index --extract A` then `--extract B`, with no `--pipeline`, is a reparse.

    The default four-stage path never calls `weft_kernel.resolution.resolve`, so it has no
    `ResolvedPipeline` — and `9.17` therefore left its identity as `""`, which made two different
    extractors indistinguishable on the one invocation a user reaches first. `L9.64`.
    """
    # Arrange
    (tmp_path / "one.txt").write_text("hello weft")
    registry, _store = _default_path_registry()

    # Act — two runs over identical bytes, differing only in which extractor ran.
    await run_index(tmp_path, registry=registry, ctx=_default_ctx(), extractor="text")
    second = await run_index(
        tmp_path, registry=registry, ctx=_default_ctx(), extractor="text-other"
    )

    # Assert
    assert second.source_changes == {_source_id(tmp_path): SourceChange.PIPELINE_CHANGED}


async def test_the_default_path_reports_unchanged_when_nothing_moved(tmp_path: Path) -> None:
    """The other half, and the one a false positive would break: the same run twice is quiet.

    An identity that moved between two identical runs would report a reparse that did not happen,
    which `pipeline_identity`'s own docstring names as worse than no detector at all.
    """
    # Arrange
    (tmp_path / "one.txt").write_text("hello weft")
    registry, _store = _default_path_registry()

    # Act
    await run_index(tmp_path, registry=registry, ctx=_default_ctx(), extractor="text")
    second = await run_index(tmp_path, registry=registry, ctx=_default_ctx(), extractor="text")

    # Assert
    assert second.source_changes == {_source_id(tmp_path): SourceChange.UNCHANGED}


async def test_the_default_path_identity_is_not_empty(tmp_path: Path) -> None:
    """The identity a default-path run writes is a real digest, so a record it leaves is
    comparable by a later run — an empty string compares equal to every other empty string.
    """
    # Arrange
    (tmp_path / "one.txt").write_text("hello weft")
    registry, store = _default_path_registry()

    # Act
    result = await run_index(tmp_path, registry=registry, ctx=_default_ctx(), extractor="text")

    # Assert
    assert result.pipeline_identity != ""
    assert store.records[_source_id(tmp_path)].pipeline_identity == result.pipeline_identity
