"""Task 43.2: `weft index` with no `--batch-size` runs bounded batches by default and says so.

`43.0` measured it: batch 25 brings first ACTIVE from 226.7 s to 49.1 s on 100 PDFs at no total
cost. The default reaches `run_index` as `default_batch_size`, which only `IndexCommand` passes.
The eval paths keep whole-corpus runs, so their `ingest_seconds` stay comparable, and
`batch_size` keeps meaning "the operator typed `--batch-size`". A pipeline whose stage computes
over its batch keeps whole-corpus behaviour under the default and names that stage. An explicit
`--batch-size` still refuses it, as `test_batch_size_bounds_memory.py` holds.

Progress goes to an async `on_batch` callback. `IndexCommand` feeds it to a sink that satisfies
`ProgressReporter`: `PrintingSink` writes a line to stderr, and `JsonSink` writes a
`batch-progress` line. A token sink an API caller supplies stays quiet.
"""

import io
import json
from collections.abc import Sequence
from functools import partial
from pathlib import Path
from typing import ClassVar

import pytest

from weft_chunk import Chunker
from weft_cli import commands
from weft_cli import ingest as ingest_module
from weft_cli.cli import _EmissionTrackingSink  # pyright: ignore[reportPrivateUsage]
from weft_cli.ingest import DEFAULT_BATCH_SIZE, IndexResult, run_index
from weft_cli.progress import BatchProgress, ProgressReporter
from weft_cli.sinks import JsonSink, LineKind, PrintingSink
from weft_embed import Embedder
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_extract import Extractor
from weft_kernel.context import Context
from weft_kernel.discovery import PackReport, PackStatus
from weft_kernel.payload import NothingToProduce, Outcome, Produced, SourceId
from weft_kernel.registry import Registry
from weft_kernel.runner import RunSummary
from weft_llm.client import NullSink
from weft_store import NodeStore, SourceRecord


class _CountingStage:
    extensions: tuple[str, ...] = (".txt",)
    destroys: tuple[type, ...] = ()
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


class _Clusters(_Passthrough):
    depends_on_batch_membership: ClassVar[bool] = True


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


def _registry(store: _RecordingStore, *, clustering: bool = False) -> Registry:
    _CountingStage.calls = []
    registry = Registry()
    registry.add(Extractor, "text", _Passthrough, distribution="weft-extract")
    registry.add(Chunker, "fixed-size", _CountingStage, distribution="weft-chunk")
    embedder: type[_Passthrough] = _Clusters if clustering else _Passthrough
    registry.add(Embedder, "hash", embedder, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", partial(_store_factory, store), distribution="weft-store")
    return registry


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _corpus(tmp_path: Path, how_many: int) -> None:
    for i in range(how_many):
        (tmp_path / f"doc{i}.txt").write_text(f"document number {i}")


def _null_factory(config: object) -> object:
    del config
    return object()


class _Events:
    def __init__(self) -> None:
        self.seen: list[BatchProgress] = []

    async def __call__(self, event: BatchProgress) -> None:
        self.seen.append(event)


def test_the_default_batch_is_the_measured_twenty_five() -> None:
    assert DEFAULT_BATCH_SIZE == 25


async def test_the_default_splits_the_corpus_and_reports_each_batch(tmp_path: Path) -> None:
    # Arrange
    _corpus(tmp_path, 7)
    registry = _registry(_RecordingStore(None))
    events = _Events()

    # Act
    await run_index(
        tmp_path,
        registry=registry,
        ctx=_ctx(),
        extractor="text",
        default_batch_size=3,
        on_batch=events,
    )

    # Assert
    assert _CountingStage.calls == [3, 3, 1]
    assert [(e.batch, e.batches, e.queryable, e.documents) for e in events.seen] == [
        (1, 3, 3, 7),
        (2, 3, 6, 7),
        (3, 3, 7, 7),
    ]
    seconds = [e.seconds for e in events.seen]
    assert seconds == sorted(seconds)
    assert all(e.whole_corpus_for == () for e in events.seen)


async def test_an_explicit_batch_size_overrides_the_default(tmp_path: Path) -> None:
    # Arrange
    _corpus(tmp_path, 7)
    registry = _registry(_RecordingStore(None))

    # Act
    await run_index(
        tmp_path,
        registry=registry,
        ctx=_ctx(),
        extractor="text",
        batch_size=2,
        default_batch_size=3,
    )

    # Assert
    assert _CountingStage.calls == [2, 2, 2, 1]


async def test_with_no_default_the_corpus_is_one_batch_and_still_reported(tmp_path: Path) -> None:
    # Arrange
    _corpus(tmp_path, 7)
    registry = _registry(_RecordingStore(None))
    events = _Events()

    # Act
    await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text", on_batch=events)

    # Assert
    assert _CountingStage.calls == [7]
    assert [(e.batch, e.batches, e.queryable, e.documents) for e in events.seen] == [(1, 1, 7, 7)]


async def test_a_batch_scoped_stage_keeps_the_whole_corpus_under_the_default_and_is_named(
    tmp_path: Path,
) -> None:
    # Arrange
    _corpus(tmp_path, 7)
    registry = _registry(_RecordingStore(None), clustering=True)
    events = _Events()

    # Act
    await run_index(
        tmp_path,
        registry=registry,
        ctx=_ctx(),
        extractor="text",
        default_batch_size=3,
        on_batch=events,
    )

    # Assert
    assert _CountingStage.calls == [7]
    assert [e.whole_corpus_for for e in events.seen] == [("hash",)]


async def test_weft_index_passes_the_default_and_its_sink_s_progress(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Arrange
    registry = Registry()
    registry.add(Embedder, "hash", _null_factory, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", _null_factory, distribution="weft-store")
    reports = tuple(
        PackReport(pack=p, distribution=f"weft-{p}", status=PackStatus.ACTIVE)
        for p in ("extract", "chunk", "embed", "store")
    )
    sink = PrintingSink(stream=io.StringIO(), progress_stream=io.StringIO())
    deps = Dependencies(
        registry=registry, reports=reports, services=ServiceSelection(), token_sink=sink
    )
    ctx = _ctx()
    ctx.services.add(Dependencies, deps)
    captured: dict[str, object] = {}

    async def _fake_run_index(*_args: object, **kwargs: object) -> IndexResult:
        captured.update(kwargs)
        return IndexResult(
            summary=RunSummary(produced=1, nothing_to_produce=0, failed=0), stored_count=1
        )

    monkeypatch.setattr(ingest_module, "run_index", _fake_run_index)

    # Act
    await commands.IndexCommand().run(commands.IndexArgs(path=str(tmp_path)), ctx)

    # Assert
    assert captured["batch_size"] is None
    assert captured["default_batch_size"] == DEFAULT_BATCH_SIZE
    assert captured["on_batch"] == sink.batch_progress


def test_both_shipped_sinks_report_progress() -> None:
    assert isinstance(PrintingSink(), ProgressReporter)
    assert isinstance(JsonSink(), ProgressReporter)


async def test_the_text_sink_writes_one_progress_line_to_its_progress_stream() -> None:
    # Arrange
    out, err = io.StringIO(), io.StringIO()
    sink = PrintingSink(stream=out, progress_stream=err)
    event = BatchProgress(batch=1, batches=3, queryable=3, documents=7, seconds=0.4)

    # Act
    await sink.batch_progress(event)

    # Assert
    assert err.getvalue() == "batch 1/3 · 3/7 documents queryable · 0.4 s since start\n"
    assert out.getvalue() == ""


async def test_the_text_sink_names_the_stage_that_kept_the_corpus_whole() -> None:
    # Arrange
    err = io.StringIO()
    sink = PrintingSink(stream=io.StringIO(), progress_stream=err)
    event = BatchProgress(
        batch=1, batches=1, queryable=7, documents=7, seconds=2.0, whole_corpus_for=("raptor",)
    )

    # Act
    await sink.batch_progress(event)

    # Assert
    assert "one batch: 'raptor' computes over the whole corpus" in err.getvalue()


async def test_the_json_sink_writes_a_batch_progress_line() -> None:
    # Arrange
    out = io.StringIO()
    sink = JsonSink(stream=out)
    event = BatchProgress(batch=2, batches=3, queryable=6, documents=7, seconds=1.25)

    # Act
    await sink.batch_progress(event)

    # Assert
    line = json.loads(out.getvalue())
    assert line["kind"] == LineKind.BATCH_PROGRESS == "batch-progress"
    assert (line["batch"], line["batches"], line["queryable"], line["documents"]) == (2, 3, 6, 7)


async def test_the_sink_the_cli_really_hands_a_command_still_reports_progress() -> None:
    """Found by running the binary: `run_command` hands every command `_EmissionTrackingSink`
    around the real sink, which forwarded `emit`, `close` and `show_only_stage` only, so no
    progress line was ever written. `L12.13` on the same wrapper, one method over.
    """
    # Arrange
    err = io.StringIO()
    wrapped = _EmissionTrackingSink(PrintingSink(stream=io.StringIO(), progress_stream=err))
    event = BatchProgress(batch=1, batches=2, queryable=25, documents=50, seconds=3.0)

    # Act
    assert isinstance(wrapped, ProgressReporter)
    await wrapped.batch_progress(event)

    # Assert
    assert err.getvalue() == "batch 1/2 · 25/50 documents queryable · 3.0 s since start\n"


async def test_a_quiet_run_s_wrapped_sink_drops_progress_without_failing() -> None:
    # Arrange
    wrapped = _EmissionTrackingSink(NullSink())
    event = BatchProgress(batch=1, batches=2, queryable=25, documents=50, seconds=3.0)

    # Act / Assert: nothing to write to, and nothing raised.
    await wrapped.batch_progress(event)
