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

import asyncio
from collections.abc import Sequence
from contextlib import suppress
from functools import partial
from pathlib import Path
from typing import ClassVar

from weft_chunk import Chunker
from weft_cli import render
from weft_cli.commands import IndexCommandResult
from weft_cli.exit_codes import ExitCode
from weft_cli.ingest import SourceChange, changes_against_records, run_index
from weft_command.contract import CommandResult
from weft_embed import Embedder
from weft_extract import Extractor
from weft_extract.contract import SourceDoc
from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.payload import Failed, NothingToProduce, Outcome, Produced, SourceId
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


class _CancelledChunker(_Passthrough):
    """A run interrupted rather than failed — ledger **36.1**: since Phase 36 a stage that raises
    or returns `Failed` records the source `FAILED`, so the interruption `17.1` is about is now
    modelled by what a killed task actually receives, `CancelledError`, which records nothing
    beyond the `INDEXING` already written."""

    cancel: ClassVar[bool] = False

    async def run(self, payload: Sequence[object], ctx: Context) -> Outcome[Sequence[object]]:
        if type(self).cancel:
            raise asyncio.CancelledError
        return await super().run(payload, ctx)


class _RefusingChunker(_Passthrough):
    """A stage that returns `Failed` for one named document — carried repair **R36.0**.

    Unlike `_ExplodingChunker` nothing is raised: the runner counts the batch as failed and
    `run_index` returns normally, which is the path a non-UTF-8 file takes through the shipped
    extractor. Keyed on content rather than on a flag so a corpus can hold one good document and
    one refused one in the same run.
    """

    refuse: ClassVar[str | None] = None

    async def run(self, payload: Sequence[object], ctx: Context) -> Outcome[Sequence[object]]:
        refused = type(self).refuse
        if refused is not None and any(refused in str(item) for item in payload):
            return Failed(reason=f"cannot chunk {refused!r}")
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


def _registry(store: _RecordingStore, chunker: type[_Passthrough] = _ExplodingChunker) -> Registry:
    _ExplodingChunker.explode = False
    _CancelledChunker.cancel = False
    _RefusingChunker.refuse = None
    registry = Registry()
    registry.add(Extractor, "text", _Passthrough, distribution="weft-extract")
    registry.add(Chunker, "fixed-size", chunker, distribution="weft-chunk")
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
    registry = _registry(store, chunker=_CancelledChunker)
    _CancelledChunker.cancel = True

    # Act
    with suppress(asyncio.CancelledError):
        await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")

    # Assert
    record = store.records[_source_id(tmp_path, "one.txt")]
    assert record.status is SourceStatus.INDEXING
    assert record.failure is None


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
    registry = _registry(store, chunker=_CancelledChunker)
    _CancelledChunker.cancel = True
    with suppress(asyncio.CancelledError):
        await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")

    # Act — the next run, with nothing on disk changed.
    _CancelledChunker.cancel = False
    result = await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")

    # Assert — it was work, it was done, and the record now says so.
    assert result.documents_indexed == 1
    assert result.source_changes == {str(_source_id(tmp_path, "one.txt")): SourceChange.INCOMPLETE}
    assert store.records[_source_id(tmp_path, "one.txt")].status is SourceStatus.ACTIVE


async def test_a_run_whose_batch_failed_does_not_record_it_active(tmp_path: Path) -> None:
    """Carried repair **R36.0**: a batch the runner counted `Failed` did no work, so its
    documents' records must not claim otherwise.

    Found by running the binary: one non-UTF-8 file failed its batch, every source was recorded
    `ACTIVE`, and the next `weft index` answered `2 unchanged` at exit `0` — the refused file and
    the good one sharing its batch both missing from the corpus, with every later run green.
    """
    # Arrange
    (tmp_path / "bad.txt").write_text("unreadable")
    store = _RecordingStore(None)
    registry = _registry(store, chunker=_RefusingChunker)
    _RefusingChunker.refuse = "bad.txt"

    # Act
    result = await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")

    # Assert
    assert result.summary.failed == 1
    assert store.records[_source_id(tmp_path, "bad.txt")].status is not SourceStatus.ACTIVE


async def test_a_document_whose_batch_failed_is_indexed_again_by_the_next_run(
    tmp_path: Path,
) -> None:
    """The conjunction that makes the record above matter (`L8.29`): the next run, with nothing on
    disk changed, never calls the document unchanged. Since ledger **36.2** it skips it as
    *failed* and says so, and only `--retry-failed` treats it as work (owner, 2026-09-21: paid
    stages sit on the ingest path, so a failure is not retried unasked)."""
    # Arrange — a run whose only batch is refused.
    (tmp_path / "bad.txt").write_text("unreadable")
    store = _RecordingStore(None)
    registry = _registry(store, chunker=_RefusingChunker)
    _RefusingChunker.refuse = "bad.txt"
    await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")

    # Act — the cause is gone, the bytes are not.
    _RefusingChunker.refuse = None
    skipped = await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")
    retried = await run_index(
        tmp_path, registry=registry, ctx=_ctx(), extractor="text", retry_failed=True
    )

    # Assert
    bad = str(_source_id(tmp_path, "bad.txt"))
    assert skipped.source_changes[bad] is SourceChange.FAILED
    assert skipped.documents_indexed == 0
    assert retried.source_changes[bad] is SourceChange.RETRIED
    assert retried.documents_indexed == 1
    assert store.records[_source_id(tmp_path, "bad.txt")].status is SourceStatus.ACTIVE


async def test_a_failed_run_leaves_an_unchanged_documents_record_active(tmp_path: Path) -> None:
    """The control: withholding `ACTIVE` from the run's work must not reach a document the run
    never touched, whose record from the earlier run is still true."""
    # Arrange — one document indexed cleanly, then a second added that the next run refuses.
    (tmp_path / "good.txt").write_text("hello weft")
    store = _RecordingStore(None)
    registry = _registry(store, chunker=_RefusingChunker)
    await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")
    (tmp_path / "bad.txt").write_text("unreadable")
    _RefusingChunker.refuse = "bad.txt"

    # Act
    await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")

    # Assert
    assert store.records[_source_id(tmp_path, "good.txt")].status is SourceStatus.ACTIVE
    assert store.records[_source_id(tmp_path, "bad.txt")].status is not SourceStatus.ACTIVE


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


# --- Task 38.14 — a batch that finished is kept, whatever happens to the batches after it.


class _ExplodingOnChunker(_Passthrough):
    """Raises once a named document's batch reaches it: a run killed part-way, after earlier
    batches finished."""

    explode_on: ClassVar[str | None] = None

    async def run(self, payload: Sequence[object], ctx: Context) -> Outcome[Sequence[object]]:
        named = type(self).explode_on
        if named is not None and any(named in str(item) for item in payload):
            raise RuntimeError("killed mid-index")
        return await super().run(payload, ctx)


async def test_a_batch_that_succeeded_is_active_even_when_a_later_batch_failed(
    tmp_path: Path,
) -> None:
    """`38.6`'s question index re-paid every model call after one failure, because `R36.0`
    withholds `ACTIVE` from all of a run's work when any batch fails. One document per batch
    names exactly which documents failed."""
    # Arrange
    (tmp_path / "a_good.txt").write_text("hello weft")
    (tmp_path / "b_bad.txt").write_text("unreadable")
    store = _RecordingStore(None)
    registry = _registry(store, chunker=_RefusingChunker)
    _RefusingChunker.refuse = "b_bad.txt"

    # Act
    result = await run_index(
        tmp_path, registry=registry, ctx=_ctx(), extractor="text", batch_size=1
    )

    # Assert
    assert result.summary.failed == 1
    assert store.records[_source_id(tmp_path, "a_good.txt")].status is SourceStatus.ACTIVE
    assert store.records[_source_id(tmp_path, "b_bad.txt")].status is not SourceStatus.ACTIVE


async def test_a_run_killed_after_its_first_batch_keeps_that_batch_for_the_next_run(
    tmp_path: Path,
) -> None:
    """The kill `38.6` met twice: the batches before it had finished and were re-paid anyway."""
    # Arrange
    (tmp_path / "a_first.txt").write_text("hello weft")
    (tmp_path / "b_second.txt").write_text("killed here")
    store = _RecordingStore(None)
    registry = _registry(store, chunker=_ExplodingOnChunker)
    _ExplodingOnChunker.explode_on = "b_second.txt"
    with suppress(RuntimeError, WeftError):
        await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text", batch_size=1)

    # Act — the next run, with the cause gone.
    _ExplodingOnChunker.explode_on = None
    result = await run_index(
        tmp_path, registry=registry, ctx=_ctx(), extractor="text", batch_size=1
    )

    # Assert — the finished batch is not redone, and since ledger 36.2 the failed one is skipped
    # as failed rather than retried unasked.
    assert store.records[_source_id(tmp_path, "a_first.txt")].status is SourceStatus.ACTIVE
    assert result.documents_indexed == 0
    assert result.source_changes[str(_source_id(tmp_path, "a_first.txt"))] is SourceChange.UNCHANGED
    assert result.source_changes[str(_source_id(tmp_path, "b_second.txt"))] is SourceChange.FAILED


# --- Repair R38.14 — what an interrupted run wrote is released before the document is redone.


class _DeletingStore(_RecordingStore):
    def __init__(self, config: object) -> None:
        super().__init__(config)
        self.deleted: list[SourceId] = []

    async def delete_source(self, source: SourceId) -> None:
        # A real store's `delete_source` removes the record as well as the nodes; a double that
        # kept it hid 36.1 writing `FAILED` and then deleting what it wrote (found by the exit).
        self.deleted.append(source)
        self.records.pop(source, None)


async def test_an_interrupted_documents_nodes_are_released_before_it_is_indexed_again(
    tmp_path: Path,
) -> None:
    """`38.6`'s fourth run retrieved 22,463 question nodes a killed run had written: the killed
    run left its sources `INDEXING`, the next run read them `INCOMPLETE`, and only
    `CONTENT_CHANGED` and `PIPELINE_CHANGED` were released before re-indexing. Nodes a model wrote
    differ run to run, so they get new ids and pile up even under the same pipeline."""
    # Arrange — a run that dies partway.
    (tmp_path / "one.txt").write_text("hello weft")
    store = _DeletingStore(None)
    registry = _registry(store)
    _ExplodingChunker.explode = True
    with suppress(WeftError):
        await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")

    # Act
    _ExplodingChunker.explode = False
    await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")

    # Assert
    assert store.deleted == [_source_id(tmp_path, "one.txt")]


# --- Ledger 36.1–36.3 — a failed source is recorded, skipped and reported, never lost. Settled by
# the owner at Phase 36's opening (2026-09-21): every member of a failed batch is `FAILED` with one
# `SourceFailure`; the stage comes from the seam's own record; only a batch of one advances an
# attempt count; a `FAILED` source is skipped until `--retry-failed` or a change to its bytes or
# pipeline identity, because paid stages sit on the ingest path.


async def test_a_refused_document_is_recorded_failed_with_the_stage_that_refused_it(
    tmp_path: Path,
) -> None:
    # Arrange
    (tmp_path / "a_good.txt").write_text("hello weft")
    (tmp_path / "b_bad.txt").write_text("unreadable")
    store = _RecordingStore(None)
    registry = _registry(store, chunker=_RefusingChunker)
    _RefusingChunker.refuse = "b_bad.txt"

    # Act
    result = await run_index(
        tmp_path, registry=registry, ctx=_ctx(), extractor="text", batch_size=1
    )

    # Assert
    bad = store.records[_source_id(tmp_path, "b_bad.txt")]
    assert bad.status is SourceStatus.FAILED
    assert bad.failure is not None
    assert bad.failure.error_type == "Failed"
    assert bad.failure.stage == "chunk"
    assert "cannot chunk" in bad.failure.message
    assert bad.failure.attempts == 1
    assert store.records[_source_id(tmp_path, "a_good.txt")].failure is None
    assert result.documents_indexed == 1
    assert result.documents_failed == 1


async def test_a_raised_stage_failure_is_recorded_and_still_raised(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "a_first.txt").write_text("hello weft")
    (tmp_path / "b_second.txt").write_text("explodes here")
    store = _RecordingStore(None)
    registry = _registry(store, chunker=_ExplodingOnChunker)
    _ExplodingOnChunker.explode_on = "b_second.txt"

    # Act
    raised: WeftError | None = None
    try:
        await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text", batch_size=1)
    except WeftError as exc:
        raised = exc

    # Assert — re-raised unchanged, and recorded first.
    assert raised is not None
    failed = store.records[_source_id(tmp_path, "b_second.txt")]
    assert failed.status is SourceStatus.FAILED
    assert failed.failure is not None
    assert failed.failure.error_type == type(raised).__name__
    assert failed.failure.stage == raised.stage
    assert store.records[_source_id(tmp_path, "a_first.txt")].status is SourceStatus.ACTIVE


async def test_a_cancelled_run_records_no_failure(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "one.txt").write_text("hello weft")
    store = _RecordingStore(None)
    registry = _registry(store, chunker=_CancelledChunker)
    _CancelledChunker.cancel = True

    # Act
    with suppress(asyncio.CancelledError):
        await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")

    # Assert
    assert all(record.status is not SourceStatus.FAILED for record in store.records.values())


async def test_a_failed_batch_fails_only_its_bad_document_and_counts_only_its_attempts(
    tmp_path: Path,
) -> None:
    """Carried repair R43.1 supersedes this test's 36.1 form, in which every member of a failed
    batch was `FAILED`. Now the batch's documents are run again one at a time, so the good one is
    `ACTIVE`. One bad file still does not advance anything but its own attempts."""
    # Arrange: the default batch is the whole corpus.
    (tmp_path / "a_good.txt").write_text("hello weft")
    (tmp_path / "b_bad.txt").write_text("unreadable")
    store = _RecordingStore(None)
    registry = _registry(store, chunker=_RefusingChunker)
    _RefusingChunker.refuse = "b_bad.txt"
    await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")

    # Act: retried, still failing.
    await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text", retry_failed=True)

    # Assert
    good = store.records[_source_id(tmp_path, "a_good.txt")]
    bad = store.records[_source_id(tmp_path, "b_bad.txt")]
    assert good.status is SourceStatus.ACTIVE
    assert good.failure is None
    assert bad.status is SourceStatus.FAILED
    assert bad.failure is not None
    assert bad.failure.attempts == 2


async def test_a_document_failing_alone_again_advances_its_attempts(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "bad.txt").write_text("unreadable")
    store = _RecordingStore(None)
    registry = _registry(store, chunker=_RefusingChunker)
    _RefusingChunker.refuse = "bad.txt"
    await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text", batch_size=1)

    # Act
    await run_index(
        tmp_path,
        registry=registry,
        ctx=_ctx(),
        extractor="text",
        batch_size=1,
        retry_failed=True,
    )

    # Assert
    failure = store.records[_source_id(tmp_path, "bad.txt")].failure
    assert failure is not None
    assert failure.attempts == 2


async def test_a_failed_document_whose_bytes_changed_is_indexed_without_the_flag(
    tmp_path: Path,
) -> None:
    # Arrange
    (tmp_path / "bad.txt").write_text("unreadable")
    store = _RecordingStore(None)
    registry = _registry(store, chunker=_RefusingChunker)
    _RefusingChunker.refuse = "unreadable"
    await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")

    # Act
    (tmp_path / "bad.txt").write_text("fixed")
    result = await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")

    # Assert
    record = store.records[_source_id(tmp_path, "bad.txt")]
    assert result.source_changes[str(_source_id(tmp_path, "bad.txt"))] is (
        SourceChange.CONTENT_CHANGED
    )
    assert record.status is SourceStatus.ACTIVE
    assert record.failure is None


async def test_a_failed_documents_partial_nodes_are_released_when_it_fails(
    tmp_path: Path,
) -> None:
    """A failed source is not retried unasked, so nothing it half-wrote may stay retrievable."""
    # Arrange
    (tmp_path / "bad.txt").write_text("unreadable")
    store = _DeletingStore(None)
    registry = _registry(store, chunker=_RefusingChunker)
    _RefusingChunker.refuse = "bad.txt"

    # Act
    await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")

    # Assert — released, and the failure still on record afterwards.
    assert store.deleted == [_source_id(tmp_path, "bad.txt")]
    assert store.records[_source_id(tmp_path, "bad.txt")].status is SourceStatus.FAILED


def _rendered_run(changes: dict[str, SourceChange], *, failed: int) -> tuple[str, ExitCode]:
    outcome: Outcome[CommandResult] = Produced(
        value=IndexCommandResult(
            summary=RunSummary(produced=1, nothing_to_produce=0, failed=failed),
            stored_count=1,
            source_changes=changes,
            documents_discovered=len(changes),
            documents_indexed=0,
        )
    )
    rendered = render.render_outcome(outcome)
    return (rendered.stdout or "") + (rendered.stderr or ""), rendered.exit_code


def test_a_run_that_only_skipped_failed_sources_says_so_and_exits_zero() -> None:
    # Act
    printed, exit_code = _rendered_run(
        {"file:///c/bad.txt": SourceChange.FAILED, "file:///c/good.txt": SourceChange.UNCHANGED},
        failed=0,
    )

    # Assert
    assert "1 failed earlier, skipped — weft index --retry-failed includes it" in printed
    assert exit_code is ExitCode.SUCCESS


def test_a_run_where_something_failed_this_run_exits_one() -> None:
    # Act
    _, exit_code = _rendered_run({"file:///c/bad.txt": SourceChange.RETRIED}, failed=1)

    # Assert
    assert exit_code is ExitCode.OPERATION_FAILED


def test_a_retried_document_is_not_called_unfinished() -> None:
    """`R36.0`'s second gap: a run that finished and failed was reported "did not finish"."""
    # Act
    printed, _ = _rendered_run({"file:///c/bad.txt": SourceChange.RETRIED}, failed=1)

    # Assert
    assert "did not finish" not in printed
    assert "retried" in printed


def test_a_document_that_failed_this_run_is_not_counted_unchanged() -> None:
    """Found running the exit from the wheel: after `36.1` stopped counting a failed document as
    indexed, the summary's `discovered - indexed` called it unchanged."""
    # Arrange
    outcome: Outcome[CommandResult] = Produced(
        value=IndexCommandResult(
            summary=RunSummary(produced=1, nothing_to_produce=0, failed=1),
            stored_count=1,
            source_changes={
                "file:///c/good.txt": SourceChange.NEW,
                "file:///c/bad.txt": SourceChange.NEW,
            },
            documents_discovered=2,
            documents_indexed=1,
            documents_failed=1,
        )
    )

    # Act
    stdout = render.render_outcome(outcome).stdout or ""

    # Assert
    assert "2 documents: 1 indexed, 0 unchanged, 1 failed." in stdout
