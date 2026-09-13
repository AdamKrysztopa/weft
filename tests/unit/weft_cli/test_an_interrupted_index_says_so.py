"""An index that was interrupted says so — ledger task **17.1**.

`SourceRecord.status` has existed since Phase 0 and has meant exactly one thing: the tombstone
`delete_source` writes before it deletes by filter, so a crash mid-deletion leaves
`status=DELETING` and the next `reconcile` can finish the job. `02` §1 → *Deletion is idempotent
and resumable* is the argument, and it is a good one.

**Indexing had no such record, and the asymmetry is the defect.** `_record_sources` writes a
`SourceRecord` *after* the run, so a run killed halfway leaves the documents it had already
written with **no record at all** — indistinguishable from documents nobody has ever indexed —
and the ones it was midway through with the *previous* run's record, which says `ACTIVE` and is a
lie. Task `17.0` turns that lie into lost work: an interrupted document whose bytes and pipeline
still match its stale record now reports `UNCHANGED` and is **skipped forever**, its partial nodes
sitting in the store, until somebody edits the file.

So this task writes the record before the work and rewrites it after — `delete_source`'s own
shape, applied to the other direction — and teaches the comparison that a record which is not
`ACTIVE` cannot claim anything about what the store holds.

**`SourceStatus.INDEXING` has a production writer from the moment it exists**, which is
`docs/internal/lessons.md` `L19.3` applied rather than quoted: `ACTIVE` has none — every value of
it arrives from the field default, because `_record_sources` passes no `status=` — so a grep for
it across `packages/` returns test files only, and a third member added the same way would be a
state nothing writes and every reader answers emptily about (`L6.14`). The assertions below are
on the records a real `run_index` left behind, never on the enum.
"""

from collections.abc import Sequence
from contextlib import suppress
from functools import partial
from pathlib import Path
from typing import ClassVar

from weft_chunk import Chunker
from weft_cli import render
from weft_cli.commands import IndexCommandResult
from weft_cli.ingest import SourceChange, changes_against_records, run_index
from weft_command.contract import CommandResult
from weft_embed import Embedder
from weft_extract import Extractor
from weft_extract.contract import SourceDoc
from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.payload import NothingToProduce, Outcome, Produced, SourceId
from weft_kernel.registry import Registry
from weft_kernel.runner import RunSummary
from weft_store import NodeStore, SourceRecord, SourceStatus


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


class _ExplodingChunker(_Passthrough):
    """A stage that raises once the payload reaches it — the interruption, made reproducible.

    The real failure this models is a process killed mid-run, which a unit test cannot produce.
    What matters is not *how* the run ended but that it ended **after** the pre-run record was
    written and **before** the post-run one was, and a raising stage sits in exactly that window.
    A test that instead asserted the pre-run write by calling a private helper would be asserting
    the arrangement rather than the property (`L9.39`).
    """

    explode: ClassVar[bool] = False

    async def run(self, payload: Sequence[object], ctx: Context) -> Outcome[Sequence[object]]:
        if type(self).explode:
            raise RuntimeError("killed mid-index")
        return await super().run(payload, ctx)


class _RecordingStore(_Passthrough):
    def __init__(self, config: object) -> None:
        super().__init__(config)
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


def _store_factory(store: _RecordingStore, config: object) -> _RecordingStore:
    del config
    return store


def _registry(store: _RecordingStore) -> Registry:
    _ExplodingChunker.explode = False
    registry = Registry()
    registry.add(Extractor, "text", _Passthrough, distribution="weft-extract")
    registry.add(Chunker, "fixed-size", _ExplodingChunker, distribution="weft-chunk")
    registry.add(Embedder, "hash", _Passthrough, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", partial(_store_factory, store), distribution="weft-store")
    return registry


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _source_id(tmp_path: Path, name: str) -> SourceId:
    return SourceId(str((tmp_path / name).resolve()))


def _doc(content: bytes = b"hello") -> SourceDoc:
    return SourceDoc(source_id=SourceId("s-1"), uri="file:///a.txt", content=content)


def _record(*, status: SourceStatus) -> SourceRecord:
    import hashlib
    from datetime import UTC, datetime

    return SourceRecord(
        id=SourceId("s-1"),
        uri="file:///a.txt",
        content_hash=hashlib.sha256(b"hello").hexdigest(),
        indexed_at=datetime(2026, 9, 13, tzinfo=UTC),
        pipeline="index-text",
        pipeline_identity="abc",
        status=status,
    )


async def test_a_run_that_finishes_leaves_every_record_active(tmp_path: Path) -> None:
    """The happy path, and the half that makes the other one mean something.

    A pre-run `INDEXING` write that is never cleared would make every record say the index was
    interrupted, which is the same defect as never writing one — a status that is always the same
    value carries no information either way.
    """
    # Arrange
    (tmp_path / "one.txt").write_text("hello weft")
    store = _RecordingStore(None)
    registry = _registry(store)

    # Act
    await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")

    # Assert
    record = store.records[_source_id(tmp_path, "one.txt")]
    assert record.status is SourceStatus.ACTIVE


async def test_a_run_killed_midway_leaves_the_record_saying_indexing(tmp_path: Path) -> None:
    """The property this task exists for.

    Before it, a killed run left the document with no record at all — identical to one nobody has
    ever indexed — while its partial nodes sat in the store.
    """
    # Arrange
    (tmp_path / "one.txt").write_text("hello weft")
    store = _RecordingStore(None)
    registry = _registry(store)
    _ExplodingChunker.explode = True

    # Act
    # `WeftError`, not `RuntimeError`: the seam attributes a stage's failure to the stage that
    # raised it, so what escapes `run_index` is `'chunk' failed: killed mid-index`. The exception
    # is not this test's subject — surviving it to read the record is.
    with suppress(WeftError):
        await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")

    # Assert
    record = store.records[_source_id(tmp_path, "one.txt")]
    assert record.status is SourceStatus.INDEXING


async def test_a_record_left_indexing_is_not_reported_unchanged(tmp_path: Path) -> None:
    """The edge case, and the one that turns a stale status into lost work.

    Task `17.0` skips a document reported `UNCHANGED`. An interrupted document's bytes and
    pipeline identity both still match the record the *previous* run left, so without this the
    next `weft index` would skip it forever and its partial nodes would stay — a corpus quietly
    missing a document with every command exiting `0`.
    """
    # Act / Assert
    changes = changes_against_records(
        [_doc()], {SourceId("s-1"): _record(status=SourceStatus.INDEXING)}, identity="abc"
    )
    assert changes == {SourceId("s-1"): SourceChange.INCOMPLETE}


async def test_an_active_record_with_matching_bytes_is_still_unchanged() -> None:
    """The control for the case above, because a comparison that reported `INCOMPLETE` for
    everything would satisfy it and mean nothing. Same document, same identity, one field apart.
    """
    # Act / Assert
    changes = changes_against_records(
        [_doc()], {SourceId("s-1"): _record(status=SourceStatus.ACTIVE)}, identity="abc"
    )
    assert changes == {SourceId("s-1"): SourceChange.UNCHANGED}


async def test_an_interrupted_document_is_indexed_again_by_the_next_run(tmp_path: Path) -> None:
    """End to end, because the two halves above are individually true of a build where the second
    run still skips — `INCOMPLETE` has to be a member `17.0`'s filter treats as work, and nothing
    above asserts that.

    This is the conjunction `docs/internal/lessons.md` `L8.29` says to check first: two clauses
    built by two tasks, joined by a word neither owns.
    """
    # Arrange — a run that dies partway.
    (tmp_path / "one.txt").write_text("hello weft")
    store = _RecordingStore(None)
    registry = _registry(store)
    _ExplodingChunker.explode = True
    # `WeftError`, not `RuntimeError`: the seam attributes a stage's failure to the stage that
    # raised it, so what escapes `run_index` is `'chunk' failed: killed mid-index`. The exception
    # is not this test's subject — surviving it to read the record is.
    with suppress(WeftError):
        await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")

    # Act — the next run, with nothing on disk changed.
    _ExplodingChunker.explode = False
    result = await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")

    # Assert — it was work, it was done, and the record now says so.
    assert result.documents_indexed == 1
    assert result.source_changes == {str(_source_id(tmp_path, "one.txt")): SourceChange.INCOMPLETE}
    assert store.records[_source_id(tmp_path, "one.txt")].status is SourceStatus.ACTIVE


def _rendered(changes: "dict[str, SourceChange]") -> str:
    """`weft index`'s stdout for a run that saw `changes`, through the renderer a caller reaches."""
    # Annotated as the base type because `Produced` is invariant in its parameter and
    # `render_outcome` takes `Outcome[CommandResult]`.
    outcome: Outcome[CommandResult] = Produced(
        value=IndexCommandResult(
            summary=RunSummary(produced=1, nothing_to_produce=0, failed=0),
            stored_count=1,
            source_changes=changes,
            documents_discovered=len(changes),
            documents_indexed=len(changes),
        )
    )
    return render.render_outcome(outcome).stdout or ""


def test_an_interrupted_run_is_reported_once_and_not_once_per_document() -> None:
    """Found by running the binary, and not by any test above it.

    A `kill -9` partway through a 3,000-document index leaves every one of them `INDEXING`, so the
    next run reported **3,000 identical lines** saying a previous index did not finish. That is
    `_reparse_lines`' own stated principle failing for a new member: *"a corpus of a thousand
    unchanged files must not print a thousand lines saying so, which is what makes the two that
    print worth reading."*

    `CONTENT_CHANGED` and `PIPELINE_CHANGED` stay per-document because they are facts about
    *that* document — somebody edited it, or a pipeline was pointed at it — and they arrive a
    handful at a time. `INCOMPLETE` is a fact about **one interrupted run**, arrives in bulk by
    construction, and naming each document individually tells an operator nothing the count does
    not. So it is summarised, and the summary names the number, because a line saying only *"some
    documents were incomplete"* is the vague half of the same defect.
    """
    # Arrange — one of each reportable kind, so the summary cannot swallow its neighbours.
    # Through `render_outcome` rather than the private helper: the property is what an operator
    # reads, and a test on `_reparse_lines` would assert the arrangement (`L9.39`).
    result = _rendered(
        {
            "a.txt": SourceChange.INCOMPLETE,
            "b.txt": SourceChange.INCOMPLETE,
            "c.txt": SourceChange.CONTENT_CHANGED,
        }
    )

    # Assert
    assert result.splitlines()[1:] == [
        "  c.txt: changed on disk — re-parsed, and its earlier parse released",
        "  2 documents: a previous index did not finish — indexed again",
    ]


def test_one_incomplete_document_still_says_which_one() -> None:
    """The boundary, because a summary that also hides the single case has traded one kind of
    unreadable output for another: with one document the id *is* the useful fact.
    """
    # Act
    rendered = _rendered({"a.txt": SourceChange.INCOMPLETE})

    # Assert
    assert rendered.splitlines()[1:] == [
        "  a.txt: a previous index of this document did not finish — indexed again"
    ]
