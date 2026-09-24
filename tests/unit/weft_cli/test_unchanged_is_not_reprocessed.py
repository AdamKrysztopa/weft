"""A document that has not moved is not processed again — ledger task **17.0**.

`changes_against_records` has computed a `SourceChange` for every document on every run since task
`9.17`, and `run_index` uses the result for exactly two things: releasing a changed document's
previous parse (`_release_reparsed_sources`, which reads only the two *changed* members) and
printing a line. **The set handed to the runner is untouched** — `run_index`'s `batches()` yields
the whole `docs` list, the same list that went into the comparison.

So a re-index of an unchanged corpus re-runs extraction, chunking, **every enhancer's LLM call**
and every embedding, and writes rows the store deduplicates by content digest. `ON CONFLICT (id)`
is what makes that *idempotent*; nothing makes it *cheap*. `12-roadmap.md` §5d owns the argument.

**Three things this task decides, each of which an assertion below pins.**

*The skip is the default and the escape hatch is named.* `--reprocess` does the work anyway, for
the case `pipeline_identity` cannot see: a hosted model that changed behind a stable name. The
identity is a digest over the resolved pipeline, so a different plugin or a different configured
model already reports `PIPELINE_CHANGED` and needs no flag.

*The report does not shrink when the work does.* `source_changes` still carries every document
this run saw, `UNCHANGED` included — that is the operator's answer to *what did this run do* — and
`document_ids`/`content_hashes` still cover every **discovered** document, because task `16.0`
made them the corpus identity and a digest that moves when a document is skipped is a digest over
what happened rather than over what is there.

*A comparison nobody could make skips nothing.* A store with no callable `list_sources` answers
`{}`, and `changes_against_records` then reports every source `NEW` — so the absence of evidence
costs a full re-index rather than a silent skip. That is the direction `02` §1's *an empty answer
is never a fact about the world* requires, and it is asserted here rather than left to follow from
the arithmetic, because it is the failure that would be silent.
"""

from collections.abc import Sequence
from functools import partial
from pathlib import Path
from typing import ClassVar

from weft_chunk import Chunker
from weft_cli.ingest import SourceChange, run_index
from weft_embed import Embedder
from weft_extract import Extractor
from weft_kernel.context import Context
from weft_kernel.payload import NothingToProduce, Outcome, Produced, SourceId
from weft_kernel.registry import Registry
from weft_store import NodeStore, SourceRecord


class _CountingStage:
    """A stage that records every payload it was handed, so *what the runner saw* is assertable.

    The dimension under test is **which documents reach the pipeline**, and no existing double in
    this tree records that — `test_reindex_visibility.py`'s `_RecordingStore` counts nodes, which
    a store deduplicating by digest makes identical across a skipped and an unskipped run. A
    fixture that cannot distinguish the two would make every assertion here vacuous
    (`docs/internal/lessons.md` `L11.42`'s shape, one level out).
    """

    extensions: tuple[str, ...] = (".txt",)
    destroys: tuple[type, ...] = ()

    #: Class-level because the registry constructs the plugin itself: `Chunker` lists `destroys`
    #: in its required declarations and `unwrap_factory` reads that off the registered object, so
    #: a `lambda` closing over one instance is refused at registration. Reset in each Arrange.
    calls: ClassVar[list[int]] = []

    def __init__(self, config: object) -> None:
        del config

    async def run(self, payload: Sequence[object], ctx: Context) -> Outcome[Sequence[object]]:
        del ctx
        type(self).calls.append(len(payload))
        if not payload:
            return NothingToProduce(reason="nothing to pass through")
        return Produced(value=payload)


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


class _AmnesiacStore(_Passthrough):
    """A store that writes `SourceRecord`s and **cannot list them back**.

    Not a contrivance: `_recorded_sources` reaches `list_sources` through `getattr` and guards for
    its absence, so this is the shape a real store without that capability presents. It is the
    base class rather than a subclass on purpose — a double that *has* the method cannot be made
    not to have it without a suppression, and the direction this case resolves in is the whole
    point of the last test in this file.
    """

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


class _RecordingStore(_AmnesiacStore):
    """The ordinary case: a store that can say what it already holds."""

    async def list_sources(self) -> Sequence[SourceRecord]:
        return tuple(self.records.values())


def _registry(store: _AmnesiacStore) -> Registry:
    """A four-stage default path whose chunker counts what it was handed.

    `_CountingStage.calls` is reset here rather than in each test, so a test that forgets cannot
    read a previous one's numbers — the fixture and the reset are one act.
    """
    _CountingStage.calls = []
    registry = Registry()
    registry.add(Extractor, "text", _Passthrough, distribution="weft-extract")
    registry.add(Chunker, "fixed-size", _CountingStage, distribution="weft-chunk")
    registry.add(Embedder, "hash", _Passthrough, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", partial(_store_factory, store), distribution="weft-store")
    return registry


def _store_factory(store: _AmnesiacStore, config: object) -> _AmnesiacStore:
    """The one store instance a run's stages share, so a second run sees the first run's records."""
    del config
    return store


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _source_id(tmp_path: Path, name: str) -> SourceId:
    return SourceId(str((tmp_path / name).resolve()))


async def test_a_document_that_has_not_moved_is_not_handed_to_the_pipeline_twice(
    tmp_path: Path,
) -> None:
    """The happy path, and the whole point of the task.

    Asserted on **what the stage was handed**, not on what the store holds: the store deduplicates
    by content digest, so its contents are identical whether the work was skipped or re-paid, and
    an assertion over them would pass against the defect.
    """
    # Arrange
    (tmp_path / "one.txt").write_text("hello weft")
    store = _RecordingStore(None)
    registry = _registry(store)
    chunker = _CountingStage

    # Act — two runs over bytes that did not move.
    await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")
    calls_after_first = list(chunker.calls)
    await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")

    # Assert — the second run handed the chunker nothing.
    assert calls_after_first == [1]
    assert chunker.calls == [1]


async def test_the_edge_case_only_the_moved_document_is_processed(tmp_path: Path) -> None:
    """One of two documents is edited. The other is not work this run owes."""
    # Arrange
    (tmp_path / "one.txt").write_text("hello weft")
    (tmp_path / "two.txt").write_text("second document")
    store = _RecordingStore(None)
    registry = _registry(store)
    chunker = _CountingStage
    await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")

    # Act
    (tmp_path / "two.txt").write_text("second document, edited")
    second = await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")

    # Assert — one document reached the pipeline, and the report names both.
    assert chunker.calls == [2, 1]
    assert second.source_changes == {
        str(_source_id(tmp_path, "one.txt")): SourceChange.UNCHANGED,
        str(_source_id(tmp_path, "two.txt")): SourceChange.CONTENT_CHANGED,
    }


async def test_the_report_and_the_corpus_identity_still_cover_every_discovered_document(
    tmp_path: Path,
) -> None:
    """The work shrinks and the answer does not.

    `document_ids` and `content_hashes` are what task `16.0` made the corpus identity, and a
    digest that moved because a document was skipped would describe the run rather than the
    corpus — so two runs over an unchanged corpus must produce the same pair.
    """
    # Arrange
    (tmp_path / "one.txt").write_text("hello weft")
    (tmp_path / "two.txt").write_text("second document")
    store = _RecordingStore(None)
    registry = _registry(store)

    # Act
    first = await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")
    second = await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")

    # Assert
    assert second.document_ids == first.document_ids
    assert second.content_hashes == first.content_hashes
    assert set(second.source_changes.values()) == {SourceChange.UNCHANGED}


async def test_reprocess_does_the_work_anyway(tmp_path: Path) -> None:
    """Guards that `reprocess=True` re-runs a source whose bytes and identity are unchanged.

    The escape hatch, for the change `pipeline_identity` is structurally unable to see: a
    hosted model that moved behind a stable name.
    """
    # Arrange
    (tmp_path / "one.txt").write_text("hello weft")
    store = _RecordingStore(None)
    registry = _registry(store)
    chunker = _CountingStage
    await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")

    # Act
    second = await run_index(
        tmp_path, registry=registry, ctx=_ctx(), extractor="text", reprocess=True
    )

    # Assert — the work was done, and the report still says the document did not move.
    assert chunker.calls == [1, 1]
    assert second.source_changes == {str(_source_id(tmp_path, "one.txt")): SourceChange.UNCHANGED}


async def test_a_store_that_cannot_compare_skips_nothing(tmp_path: Path) -> None:
    """The error case, and the only direction that is safe.

    A store with no callable `list_sources` cannot say what it already holds. `02` §1: an empty
    answer is never a fact about the world — so the absence of a comparison costs a full
    re-index, never a silent skip. The opposite resolution is the failure with no symptom: a
    corpus that never gets indexed and a command that exits `0` every time.
    """
    # Arrange
    (tmp_path / "one.txt").write_text("hello weft")
    store = _AmnesiacStore(None)
    registry = _registry(store)
    chunker = _CountingStage

    # Act
    await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")
    second = await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")

    # Assert
    assert chunker.calls == [1, 1]
    assert second.source_changes == {str(_source_id(tmp_path, "one.txt")): SourceChange.NEW}


async def test_the_result_carries_how_many_documents_actually_ran(tmp_path: Path) -> None:
    """Ledger task **17.4** — the wire, not the sentence.

    `weft_cli.render._render_index` cannot compute how many documents a run indexed, and it
    cannot derive it either: `document_ids` is what was *discovered*, and the difference between
    that and what ran is the whole fact the line exists to print. `docs/internal/lessons.md`
    `L9.79`: where a value's only job is to travel from one layer to another, a test has to watch
    it arrive, or a renderer reading a zero looks exactly like a renderer reading nothing.

    Asserted across three states, because a field hardcoded to `len(docs)` and a field correctly
    derived are indistinguishable from the all-new case alone.
    """
    # Arrange
    (tmp_path / "one.txt").write_text("hello weft")
    (tmp_path / "two.txt").write_text("second document")
    store = _RecordingStore(None)
    registry = _registry(store)

    # Act — everything new, then nothing changed, then one document edited.
    first = await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")
    unchanged = await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")
    (tmp_path / "two.txt").write_text("second document, edited")
    partial = await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")

    # Assert
    assert (len(first.document_ids), first.documents_indexed) == (2, 2)
    assert (len(unchanged.document_ids), unchanged.documents_indexed) == (2, 0)
    assert (len(partial.document_ids), partial.documents_indexed) == (2, 1)
