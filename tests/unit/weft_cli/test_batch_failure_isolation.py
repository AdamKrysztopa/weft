"""Carried repair R43.1: a document that fails fails only itself.

Found at `43.0`: three of 1,000 PDFs fail in `pdf-text`, and each took its whole batch down. The
default `weft index`, which has one batch, indexed none of the 1,000. The owner chose, 2026-09-22:
when a batch returns `Failed`, its documents are run again one at a time, and only a document that
fails alone is recorded `FAILED`. A batch that *raises* is unchanged: a service fault stops the run
(`L28.1`), so nothing is re-run after a dead API.

The doubles are copied from `test_an_interrupted_index_says_so.py`. The refusing chunker is keyed
on a set of names so one batch can hold two failures.
"""

from collections.abc import Sequence
from functools import partial
from pathlib import Path
from typing import ClassVar

from weft_chunk import Chunker
from weft_cli.ingest import run_index
from weft_embed import Embedder
from weft_extract import Extractor
from weft_kernel.context import Context
from weft_kernel.payload import Failed, NothingToProduce, Outcome, Produced, SourceId
from weft_kernel.registry import Registry
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


class _RefusingChunker(_Passthrough):
    """Returns `Failed` for a payload holding any refused name, and counts every call."""

    refuse: ClassVar[frozenset[str]] = frozenset()
    calls: ClassVar[list[int]] = []

    async def run(self, payload: Sequence[object], ctx: Context) -> Outcome[Sequence[object]]:
        type(self).calls.append(len(payload))
        hit = sorted(name for name in type(self).refuse if any(name in str(i) for i in payload))
        if hit:
            return Failed(reason=f"cannot chunk {hit[0]!r}")
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


def _registry(store: _RecordingStore, *, refuse: frozenset[str]) -> Registry:
    _RefusingChunker.refuse = refuse
    _RefusingChunker.calls = []
    registry = Registry()
    registry.add(Extractor, "text", _Passthrough, distribution="weft-extract")
    registry.add(Chunker, "fixed-size", _RefusingChunker, distribution="weft-chunk")
    registry.add(Embedder, "hash", _Passthrough, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", partial(_store_factory, store), distribution="weft-store")
    return registry


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _corpus(tmp_path: Path, names: Sequence[str]) -> dict[str, SourceId]:
    for name in names:
        (tmp_path / name).write_text(f"content of {name}")
    return {name: SourceId(str((tmp_path / name).resolve())) for name in names}


async def test_one_failing_document_in_the_only_batch_leaves_the_others_active(
    tmp_path: Path,
) -> None:
    # Arrange
    ids = _corpus(tmp_path, ["a.txt", "b_bad.txt", "c.txt", "d.txt"])
    store = _RecordingStore(None)
    registry = _registry(store, refuse=frozenset({"b_bad.txt"}))

    # Act
    result = await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")

    # Assert
    statuses = {name: store.records[sid].status for name, sid in ids.items()}
    assert statuses == {
        "a.txt": SourceStatus.ACTIVE,
        "b_bad.txt": SourceStatus.FAILED,
        "c.txt": SourceStatus.ACTIVE,
        "d.txt": SourceStatus.ACTIVE,
    }
    assert result.documents_indexed == 3
    assert result.documents_failed == 1
    assert result.summary.failed == 1
    assert result.summary.produced == 3


async def test_each_failed_document_keeps_its_own_reason(tmp_path: Path) -> None:
    # Arrange
    ids = _corpus(tmp_path, ["a.txt", "b_bad.txt", "c.txt", "d_bad.txt", "e.txt"])
    store = _RecordingStore(None)
    registry = _registry(store, refuse=frozenset({"b_bad.txt", "d_bad.txt"}))

    # Act
    await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text", batch_size=5)

    # Assert
    b_failure = store.records[ids["b_bad.txt"]].failure
    d_failure = store.records[ids["d_bad.txt"]].failure
    assert b_failure is not None and "'b_bad.txt'" in b_failure.message
    assert d_failure is not None and "'d_bad.txt'" in d_failure.message
    assert "d_bad" not in b_failure.message
    assert store.records[ids["e.txt"]].status is SourceStatus.ACTIVE


async def test_only_the_batch_that_failed_is_run_again_per_document(tmp_path: Path) -> None:
    # Arrange
    _corpus(tmp_path, ["a.txt", "b.txt", "c_bad.txt", "d.txt", "e.txt"])
    store = _RecordingStore(None)
    registry = _registry(store, refuse=frozenset({"c_bad.txt"}))

    # Act
    await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text", batch_size=2)

    # Assert: batches [a, b], [c_bad, d], [e]; only the second is re-run, one document at a time.
    assert _RefusingChunker.calls == [2, 2, 1, 1, 1]


async def test_a_good_document_in_a_failed_batch_is_stored_once(tmp_path: Path) -> None:
    # Arrange
    _corpus(tmp_path, ["a.txt", "b_bad.txt", "c.txt"])
    store = _RecordingStore(None)
    registry = _registry(store, refuse=frozenset({"b_bad.txt"}))

    # Act
    await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")

    # Assert
    stored = [str(node) for node in store.nodes]
    assert sum("a.txt" in s for s in stored) == 1
    assert sum("c.txt" in s for s in stored) == 1
    assert not any("b_bad.txt" in s for s in stored)


async def test_a_run_with_no_failure_runs_each_batch_once(tmp_path: Path) -> None:
    # Arrange
    _corpus(tmp_path, ["a.txt", "b.txt", "c.txt"])
    store = _RecordingStore(None)
    registry = _registry(store, refuse=frozenset())

    # Act
    await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text", batch_size=2)

    # Assert
    assert _RefusingChunker.calls == [2, 1]
