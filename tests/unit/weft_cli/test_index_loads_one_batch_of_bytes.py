"""Task 43.1, the ingest half: `run_index` holds one batch's bytes at a time.

The run inventories the corpus with `inventory_source_refs`, decides what changed from the hashes
it took, and loads each batch's files with `load_source_docs` just before that batch runs.
`discover_source_docs` is not called on this path. Records, change detection and the run record's
corpus hashes are unchanged, because the hash is the same sha256 over the same bytes. Each batch's
progress event carries its byte total, so one huge document shows up as the cause of a slow batch.
"""

import hashlib
import io
from collections.abc import Sequence
from functools import partial
from pathlib import Path
from typing import ClassVar

import pytest

from weft_chunk import Chunker
from weft_cli import ingest as ingest_module
from weft_cli.ingest import SourceChange, content_hashes_of, run_index
from weft_cli.progress import BatchProgress
from weft_cli.sinks import PrintingSink
from weft_embed import Embedder
from weft_extract import Extractor
from weft_extract.contract import SourceDoc
from weft_extract.text import (
    SourceRef,
    discover_source_docs,
    inventory_source_refs,
    load_source_docs,
)
from weft_kernel.context import Context
from weft_kernel.payload import NothingToProduce, Outcome, Produced, SourceId
from weft_kernel.registry import Registry
from weft_store import NodeStore, SourceRecord


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
    registry = Registry()
    registry.add(Extractor, "text", _Passthrough, distribution="weft-extract")
    registry.add(Chunker, "fixed-size", _Passthrough, distribution="weft-chunk")
    registry.add(Embedder, "hash", _Passthrough, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", partial(_store_factory, store), distribution="weft-store")
    return registry


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _corpus(tmp_path: Path) -> dict[str, bytes]:
    contents = {f"doc{i}.txt": (f"document {i} " * (i + 1)).encode() for i in range(7)}
    for name, data in contents.items():
        (tmp_path / name).write_bytes(data)
    return contents


class _Loads:
    """Wraps the real loader and records how many refs each call was handed."""

    sizes: ClassVar[list[int]] = []

    def __init__(self) -> None:
        type(self).sizes = []
        self._real = load_source_docs

    def __call__(self, refs: Sequence[SourceRef]) -> tuple[SourceDoc, ...]:
        type(self).sizes.append(len(refs))
        return self._real(refs)


def _no_discovery(*_args: object, **_kwargs: object) -> tuple[SourceDoc, ...]:
    """`raising=False`: the point is that this module reaches no whole-corpus walk, whether or
    not it still binds the name, and requiring the binding would pin the arrangement (`L9.39`)."""
    raise AssertionError("run_index must not read the whole corpus before its first batch")


class _Events:
    def __init__(self) -> None:
        self.seen: list[BatchProgress] = []

    async def __call__(self, event: BatchProgress) -> None:
        self.seen.append(event)


async def test_each_batch_loads_only_its_own_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Arrange
    _corpus(tmp_path)
    monkeypatch.setattr(ingest_module, "load_source_docs", _Loads())
    monkeypatch.setattr(ingest_module, "discover_source_docs", _no_discovery, raising=False)

    # Act
    await run_index(
        tmp_path,
        registry=_registry(_RecordingStore(None)),
        ctx=_ctx(),
        extractor="text",
        batch_size=3,
    )

    # Assert
    assert _Loads.sizes == [3, 3, 1]


async def test_records_carry_the_same_hash_and_a_second_run_loads_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Arrange
    contents = _corpus(tmp_path)
    store = _RecordingStore(None)
    registry = _registry(store)
    monkeypatch.setattr(ingest_module, "load_source_docs", _Loads())
    await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text", batch_size=3)
    assert _Loads.sizes == [3, 3, 1]
    monkeypatch.setattr(ingest_module, "load_source_docs", _Loads())

    # Act
    result = await run_index(
        tmp_path, registry=registry, ctx=_ctx(), extractor="text", batch_size=3
    )

    # Assert
    for name, data in contents.items():
        record = store.records[SourceId(str((tmp_path / name).resolve()))]
        assert record.content_hash == hashlib.sha256(data).hexdigest()
    assert set(result.source_changes.values()) == {SourceChange.UNCHANGED}
    assert _Loads.sizes == []


async def test_the_run_record_hashes_are_those_of_the_bytes(tmp_path: Path) -> None:
    # Arrange
    _corpus(tmp_path)

    # Act
    result = await run_index(
        tmp_path, registry=_registry(_RecordingStore(None)), ctx=_ctx(), extractor="text"
    )

    # Assert
    docs = discover_source_docs(tmp_path, extensions={".txt"})
    assert result.content_hashes == content_hashes_of(docs)
    assert content_hashes_of(inventory_source_refs(tmp_path, extensions={".txt"})) == (
        content_hashes_of(docs)
    )


async def test_each_progress_event_carries_its_batch_s_bytes(tmp_path: Path) -> None:
    # Arrange
    contents = _corpus(tmp_path)
    sizes = [len(contents[name]) for name in sorted(contents)]
    events = _Events()

    # Act
    await run_index(
        tmp_path,
        registry=_registry(_RecordingStore(None)),
        ctx=_ctx(),
        extractor="text",
        batch_size=3,
        on_batch=events,
    )

    # Assert
    assert [e.bytes for e in events.seen] == [sum(sizes[0:3]), sum(sizes[3:6]), sizes[6]]


async def test_the_text_line_ends_with_the_batch_s_size_when_it_is_known() -> None:
    # Arrange
    err = io.StringIO()
    sink = PrintingSink(stream=io.StringIO(), progress_stream=err)
    event = BatchProgress(
        batch=2, batches=4, queryable=50, documents=100, seconds=28.0, bytes=61_200_000
    )

    # Act
    await sink.batch_progress(event)

    # Assert
    assert err.getvalue() == (
        "batch 2/4 · 50/100 documents queryable · 28.0 s since start · 61.2 MB\n"
    )
