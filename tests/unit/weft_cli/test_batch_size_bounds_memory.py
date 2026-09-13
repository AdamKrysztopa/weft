"""Memory is bounded by batch size, and an unsplittable pipeline is refused — task **17.3**.

`02`:590 has claimed since Phase 0 that *"the kernel runner owns batching, so memory is bounded by
batch size rather than corpus size"*. That is true of the runner and false of the only caller that
matters: `run_index` defines `batches()` to yield the entire corpus in one go, so **"batch" has
meant "one `weft index` invocation"** and the bound has been the corpus. This task makes the
sentence true.

**The hazard is not memory, it is meaning, and it is why this task took a gate.**
`weft_kernel.runner.Runner.run` walks its batches with a plain `async for` and puts each one
through the whole stage list independently. A stage whose output depends on *which other nodes
shared its call* therefore computes a different thing when the chunk size changes — and one such
stage ships. `raptor` reads no store (G15) and clusters over the payload it was handed, which
`01`:1012 records as **batch-wide, not corpus-wide**. So `--batch-size` would turn one tree per
command into *N* trees per command, with no error, no failed exit and no output an operator could
read as wrong: retrieval would still return passages and the corpus would be silently worse.

**Settled by the owner, 2026-09-13: refuse the combination, loudly** — `12-roadmap.md` §5d, *The
half that took a decision*. The alternative considered and rejected was buffering corpus-scoped
stages in the runner, which preserves the semantics exactly and reinstates corpus-sized memory for
precisely the stage the chunking was performed for, while making the kernel name a capability.

**The refusal comes before anything is written or deleted.** `_release_reparsed_sources` deletes a
changed document's earlier parse, and `_record_sources` writes `INDEXING` rows; a refusal after
either would leave a corpus half-dismantled by a run that then declined to proceed.
"""

from collections.abc import Sequence
from functools import partial
from pathlib import Path
from typing import ClassVar

import pytest

from weft_chunk import Chunker
from weft_cli.ingest import BatchScopedStageError, run_index
from weft_embed import Embedder
from weft_extract import Extractor
from weft_kernel.context import Context
from weft_kernel.payload import NothingToProduce, Outcome, Produced, SourceId
from weft_kernel.registry import Registry
from weft_store import NodeStore, SourceRecord


class _CountingStage:
    """Records the size of every payload it was handed, so batching is assertable at all.

    `len(calls)` is how many batches reached the pipeline and `calls` is their shape — the two
    facts `02`:590's claim is about. A double that recorded only a total would pass identically
    against one batch and against seven (`L11.42`'s shape: a fixture symmetric in the dimension
    under test).
    """

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
    """A stage that says its output depends on batch membership — `raptor`'s declaration, on a
    double, because the refusal is about *any* stage that declares it and not about one plugin.
    """

    depends_on_batch_membership: ClassVar[bool] = True


class _RecordingStore(_Passthrough):
    def __init__(self, config: object) -> None:
        super().__init__(config)
        self.nodes: list[object] = []
        self.records: dict[SourceId, SourceRecord] = {}
        self.deleted: list[SourceId] = []

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

    async def delete_source(self, source: SourceId) -> None:
        self.deleted.append(source)


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


async def test_a_corpus_larger_than_the_batch_arrives_in_several_batches(tmp_path: Path) -> None:
    """The happy path, and what `02`:590 has been claiming since Phase 0.

    Seven and three rather than six and three: an exact multiple cannot show whether the last,
    short batch is yielded at all, and a corpus that divides evenly is a fixture symmetric in the
    dimension under test.
    """
    # Arrange
    _corpus(tmp_path, 7)
    store = _RecordingStore(None)
    registry = _registry(store)

    # Act
    await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text", batch_size=3)

    # Assert
    assert _CountingStage.calls == [3, 3, 1]


async def test_without_the_flag_the_whole_corpus_is_one_batch(tmp_path: Path) -> None:
    """The control, and today's behaviour. Chunking is opt-in: a default that split every run
    would change what every existing pipeline computes without anyone asking for it.
    """
    # Arrange
    _corpus(tmp_path, 7)
    store = _RecordingStore(None)
    registry = _registry(store)

    # Act
    await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")

    # Assert
    assert _CountingStage.calls == [7]


async def test_a_pipeline_that_cannot_survive_being_split_is_refused(tmp_path: Path) -> None:
    """The decision this task carries, and the refusal names both halves of what to do.

    The message is asserted on its **claims** — which plugin, and which rung to use instead — never
    on the whole sentence: a substring of the subject would match a message that said the opposite
    about it (`L12.12`).
    """
    # Arrange
    _corpus(tmp_path, 7)
    store = _RecordingStore(None)
    registry = _registry(store, clustering=True)

    # Act / Assert
    with pytest.raises(BatchScopedStageError) as caught:
        await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text", batch_size=3)
    message = str(caught.value)
    assert "hash" in message
    assert "--batch-size" in message
    assert "index-with-adrap" in message


async def test_the_refusal_happens_before_anything_is_written_or_deleted(tmp_path: Path) -> None:
    """The edge case, and the one that makes the refusal safe rather than merely correct.

    `_release_reparsed_sources` deletes a changed document's earlier parse and `_record_sources`
    writes `INDEXING` rows, both before the run. A refusal after either would leave the corpus
    half-dismantled by a command that then declined to proceed — which is worse than the silent
    wrong answer it exists to prevent.
    """
    # Arrange — a corpus already indexed once, so there is something to release and something to
    # overwrite. Edited afterwards, so `_release_reparsed_sources` has real work queued.
    _corpus(tmp_path, 3)
    store = _RecordingStore(None)
    await run_index(tmp_path, registry=_registry(store), ctx=_ctx(), extractor="text")
    (tmp_path / "doc0.txt").write_text("edited")
    before = dict(store.records)

    # Act
    with pytest.raises(BatchScopedStageError):
        await run_index(
            tmp_path,
            registry=_registry(store, clustering=True),
            ctx=_ctx(),
            extractor="text",
            batch_size=2,
        )

    # Assert
    assert store.deleted == []
    assert store.records == before


async def test_the_same_pipeline_without_the_flag_is_not_refused(tmp_path: Path) -> None:
    """The other control. A refusal keyed on the stage alone would satisfy the test above and
    break every existing `index-with-raptor` run, which is the opposite of the repair.
    """
    # Arrange
    _corpus(tmp_path, 7)
    store = _RecordingStore(None)
    registry = _registry(store, clustering=True)

    # Act
    await run_index(tmp_path, registry=registry, ctx=_ctx(), extractor="text")

    # Assert
    assert _CountingStage.calls == [7]


async def test_a_batch_size_below_one_is_refused(tmp_path: Path) -> None:
    """`ValueError`, not a `WeftError`: this is a caller handing a library function a value no
    corpus could make sensible, which is Python's own vocabulary for the case. The CLI never
    produces it — `IndexArgs` bounds the flag — so it needs no troubleshooting entry.
    """
    # Arrange
    _corpus(tmp_path, 2)
    store = _RecordingStore(None)

    # Act / Assert
    with pytest.raises(ValueError, match="batch_size"):
        await run_index(
            tmp_path, registry=_registry(store), ctx=_ctx(), extractor="text", batch_size=0
        )
