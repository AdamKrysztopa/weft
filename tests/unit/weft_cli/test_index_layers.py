"""Ledger task **43.8** — `weft index` runs the configured layers after the base, per batch.

A layer (`43.7`) is composed with the base run's own `embed` and `store` stages. After the last
base batch, the loop walks the sources in batches, selects each batch's stored leaves through
`MetadataFilter.matching` — `lineage.sources` in the batch, no `ext.weft-index.technique`, no
`weft_kg` fact or mention marker — paged, runs the layer over them, and hands only the nodes the
layer created to that tail. Each source's `LayerRecord` flips to `ACTIVE` once its derived nodes
are stored, and that flip is the publication.

The store double **pages** (`matching` returns two nodes and a cursor), because a loop that reads
only the first page passes against a store that never pages. It implements `put_source` whole
(`L28.20`). Six sources against batch four: the second batch is short.
"""

from collections.abc import Sequence
from functools import partial
from pathlib import Path
from typing import ClassVar, Protocol, runtime_checkable

import pytest

from weft_chunk import Chunker
from weft_chunk.fixed_size import FixedSizeChunker
from weft_cli.ingest import IndexResult, run_index
from weft_cli.layers import (
    LayerFailure,
    LayerNeedsMetadataFilterError,
    LayerNodeCollisionError,
    UnknownLayerError,
)
from weft_cli.progress import BatchProgress
from weft_embed import Embedder
from weft_embed.hash_embedder import HashEmbedder
from weft_enhance import Enhancer
from weft_enhance.keybert_stand_in import KeyBertKeywordExtractor
from weft_enhance.keywords import Keywords
from weft_extract import Extractor
from weft_extract.text import TextExtractor
from weft_index import Expander, Revisable
from weft_index.payload import Representation
from weft_kernel.context import Context
from weft_kernel.payload import (
    Failed,
    MediaType,
    Node,
    NodeId,
    NothingToProduce,
    Outcome,
    Produced,
    SourceId,
)
from weft_kernel.registry import Registry
from weft_kernel.runner import Stage
from weft_store import NodeStore
from weft_store.contract import (
    Cursor,
    Filter,
    FilterOp,
    LayerStatus,
    Page,
    Removed,
    SourceRecord,
)

_PAGE = 2


def _holds(node: Node, filter: Filter) -> bool:
    """The operators the layer's selection uses, with the stores' own meaning."""
    if filter.op is FilterOp.AND:
        return all(_holds(node, clause) for clause in filter.clauses)
    if filter.op is FilterOp.NOT:
        return not _holds(node, filter.clauses[0])
    if filter.op is FilterOp.IN and filter.field == "lineage.sources":
        wanted = filter.value if isinstance(filter.value, tuple) else (filter.value,)
        return bool(set(node.lineage.sources) & {SourceId(str(value)) for value in wanted})
    if filter.op is FilterOp.EXISTS and filter.field is not None:
        _, namespace, *_ = filter.field.split(".")
        return namespace in node.ext
    raise AssertionError(f"the layer selection used an operator this double lacks: {filter}")


class _Store:
    """A store holding nodes and records whole. No `matching`: it is not a `MetadataFilter`."""

    def __init__(self, config: object = None) -> None:
        del config
        self.nodes: dict[NodeId, Node] = {}
        self.records: dict[SourceId, SourceRecord] = {}
        self.adds: list[tuple[Node, ...]] = []

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        await self.add(payload)
        return Produced(value=payload)

    async def add(self, nodes: Sequence[Node]) -> None:
        self.adds.append(tuple(nodes))
        for node in nodes:
            self.nodes[node.id] = node

    async def flush(self) -> None:
        return

    async def count(self) -> int:
        return len(self.nodes)

    async def get(self, ids: Sequence[NodeId]) -> Sequence[Node]:
        return tuple(self.nodes[i] for i in ids if i in self.nodes)

    async def scan(self, cursor: Cursor | None = None) -> Page[Node]:
        del cursor
        return Page(items=tuple(self.nodes.values()))

    async def delete_source(self, source_id: SourceId) -> Removed:
        doomed = [i for i, node in self.nodes.items() if source_id in node.lineage.sources]
        for i in doomed:
            del self.nodes[i]
        self.records.pop(source_id, None)
        return Removed(source_id=source_id, node_count=len(doomed))

    async def put_source(self, record: SourceRecord) -> None:
        self.records[record.id] = record

    async def get_source(self, source_id: SourceId) -> SourceRecord | None:
        return self.records.get(source_id)

    async def list_sources(self) -> Sequence[SourceRecord]:
        return tuple(self.records.values())


class _PagingStore(_Store):
    """`_Store` plus a `matching` that pages two nodes at a time."""

    async def matching(self, filter: Filter, cursor: Cursor | None = None) -> Page[Node]:
        selected = sorted(
            (node for node in self.nodes.values() if _holds(node, filter)), key=lambda n: n.id
        )
        start = int(cursor) if cursor is not None else 0
        end = start + _PAGE
        return Page(
            items=tuple(selected[start:end]),
            next_cursor=Cursor(str(end)) if end < len(selected) else None,
        )


class _EchoQuestion:
    """An `Expander`: every leaf back, plus one question derived from each."""

    technique: ClassVar[str] = "echo-question"
    calls: ClassVar[list[int]] = []
    fail: ClassVar[bool] = False

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        _EchoQuestion.calls.append(len(payload))
        if _EchoQuestion.fail:
            return Failed(reason="the model refused")
        if not payload:
            return NothingToProduce(reason="no leaves")
        derived = tuple(
            node.derive(
                content=f"what does {node.content[:12]!r} say?", media_type=MediaType.TEXT
            ).with_ext(Representation(technique=self.technique))
            for node in payload
        )
        return Produced(value=(*payload, *derived))


class _SameQuestion(_EchoQuestion):
    """A second layer deriving the very nodes `_EchoQuestion` does, under another technique."""

    technique: ClassVar[str] = "same-question"


class _TreeQuestion(_EchoQuestion):
    """A layer whose output depends on which leaves share its call, as `raptor`'s does."""

    technique: ClassVar[str] = "tree-question"
    depends_on_batch_membership: ClassVar[bool] = True


def _factory(store: _Store, config: object) -> _Store:
    del config
    return store


def _registry(store: _Store) -> Registry:
    registry = Registry()
    registry.add(Extractor, "text", TextExtractor, distribution="weft-extract")
    registry.add(Chunker, "fixed-size", FixedSizeChunker, distribution="weft-chunk")
    registry.add(Embedder, "hash", HashEmbedder, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", partial(_factory, store), distribution="weft-store")
    registry.add(Expander, "echo-question", _EchoQuestion, distribution="weft-index")
    registry.add(Expander, "same-question", _SameQuestion, distribution="weft-index")
    registry.add(Expander, "tree-question", _TreeQuestion, distribution="weft-index")
    return registry


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Six short text files, and two layer documents in the project's own `pipelines/`."""
    docs = tmp_path / "docs"
    docs.mkdir()
    for i in range(6):
        (docs / f"doc{i}.txt").write_text(f"document number {i} says something of its own.")
    pipelines = tmp_path / "pipelines"
    pipelines.mkdir()
    (pipelines / "enrich-with-echo.yaml").write_text(
        "name: enrich-with-echo\nstages:\n  - {id: echo, use: echo-question}\n"
    )
    (pipelines / "enrich-with-same.yaml").write_text(
        "name: enrich-with-same\nstages:\n  - {id: same, use: same-question}\n"
    )
    (pipelines / "enrich-with-tree.yaml").write_text(
        "name: enrich-with-tree\nstages:\n  - {id: tree, use: tree-question}\n"
    )
    monkeypatch.chdir(tmp_path)
    _EchoQuestion.calls = []
    _EchoQuestion.fail = False
    return docs


def _derived(store: _Store) -> list[Node]:
    return [node for node in store.nodes.values() if "weft-index" in node.ext]


async def _index(
    store: _Store,
    corpus: Path,
    *,
    layers: tuple[str, ...] = (),
    layers_only: bool = False,
    retry_failed: bool = False,
    reprocess: bool = False,
    events: list[BatchProgress] | None = None,
) -> IndexResult:
    async def on_batch(event: BatchProgress) -> None:
        if events is not None:
            events.append(event)

    return await run_index(
        corpus,
        registry=_registry(store),
        ctx=_ctx(),
        batch_size=4,
        layers=layers,
        layers_only=layers_only,
        retry_failed=retry_failed,
        reprocess=reprocess,
        on_batch=on_batch,
    )


async def test_a_layer_derives_from_every_leaf_across_pages_and_embeds_only_what_it_made(
    corpus: Path,
) -> None:
    # Arrange
    store = _PagingStore()

    # Act
    await _index(store, corpus, layers=("enrich-with-echo",))

    # Assert
    derived = _derived(store)
    assert len(derived) == 6
    assert all(node.embedding is not None for node in derived)
    leaves_written = [n for batch in store.adds for n in batch if "weft-index" not in n.ext]
    assert len(leaves_written) == 6, "a leaf reached the tail a second time"


async def test_no_layer_stage_runs_before_the_last_base_batch_is_stored(corpus: Path) -> None:
    # Arrange
    store = _PagingStore()

    # Act
    await _index(store, corpus, layers=("enrich-with-echo",))

    # Assert
    kinds = [
        "derived" if any("weft-index" in n.ext for n in batch) else "base" for batch in store.adds
    ]
    assert kinds.index("derived") > max(i for i, kind in enumerate(kinds) if kind == "base")


async def test_each_source_records_its_layer_active_after_its_questions_are_stored(
    corpus: Path,
) -> None:
    # Arrange
    store = _PagingStore()

    # Act
    await _index(store, corpus, layers=("enrich-with-echo",))

    # Assert
    assert len(store.records) == 6
    for record in store.records.values():
        (layer,) = record.layers
        assert (layer.name, layer.status, layer.attempts) == (
            "enrich-with-echo",
            LayerStatus.ACTIVE,
            1,
        )
        assert layer.pipeline_identity


async def test_a_layer_done_under_the_same_identity_is_skipped(corpus: Path) -> None:
    # Arrange
    store = _PagingStore()
    await _index(store, corpus, layers=("enrich-with-echo",))
    _EchoQuestion.calls = []

    # Act
    await _index(store, corpus, layers=("enrich-with-echo",))

    # Assert
    assert _EchoQuestion.calls == []
    assert len(_derived(store)) == 6


async def test_layers_only_runs_the_layer_over_an_indexed_corpus_without_the_base(
    corpus: Path,
) -> None:
    # Arrange
    store = _PagingStore()
    await _index(store, corpus)
    adds_before = len(store.adds)

    # Act
    await _index(store, corpus, layers=("enrich-with-echo",), layers_only=True)

    # Assert
    assert all("weft-index" in n.ext for batch in store.adds[adds_before:] for n in batch)
    assert len(_derived(store)) == 6


async def test_re_indexing_without_layers_keeps_the_layers_an_unchanged_source_has(
    corpus: Path,
) -> None:
    # Arrange
    store = _PagingStore()
    await _index(store, corpus, layers=("enrich-with-echo",))

    # Act
    await _index(store, corpus)

    # Assert
    assert all(len(record.layers) == 1 for record in store.records.values())


async def test_a_changed_source_loses_its_layer_record_until_the_layer_runs_again(
    corpus: Path,
) -> None:
    # Arrange
    store = _PagingStore()
    await _index(store, corpus, layers=("enrich-with-echo",))
    (corpus / "doc0.txt").write_text("document zero now says something else entirely.")

    # Act
    await _index(store, corpus)

    # Assert
    changed = next(r for r in store.records.values() if r.uri.endswith("doc0.txt"))
    assert changed.layers == ()
    assert sum(1 for r in store.records.values() if r.layers) == 5


async def test_a_layer_that_fails_records_failed_and_is_retried_only_when_asked(
    corpus: Path,
) -> None:
    # Arrange
    store = _PagingStore()
    _EchoQuestion.fail = True
    await _index(store, corpus, layers=("enrich-with-echo",))
    failed = [r.layers[0] for r in store.records.values()]
    _EchoQuestion.fail = False
    _EchoQuestion.calls = []

    # Act
    await _index(store, corpus, layers=("enrich-with-echo",))
    unasked = list(_EchoQuestion.calls)
    await _index(store, corpus, layers=("enrich-with-echo",), retry_failed=True)

    # Assert
    assert {layer.status for layer in failed} == {LayerStatus.FAILED}
    assert all(layer.failure is not None for layer in failed)
    assert unasked == []
    assert {r.layers[0].status for r in store.records.values()} == {LayerStatus.ACTIVE}
    assert {r.layers[0].attempts for r in store.records.values()} == {2}


async def test_a_failed_layer_is_reported_by_the_run_that_failed_it(corpus: Path) -> None:
    """Carried repair **R43.9**: Exit C's corpus RAPTOR refused on all thirty sources and
    `weft index` exited 0 printing nothing, because the loop reported only moved identities.
    """
    # Arrange
    store = _PagingStore()
    _EchoQuestion.fail = True

    # Act
    result = await _index(store, corpus, layers=("enrich-with-echo",))

    # Assert
    assert result.layers_failed == (
        LayerFailure(layer="enrich-with-echo", failed=6, of=6, reason="the model refused"),
    )


async def test_a_layer_skipped_as_failed_earlier_is_not_reported_as_failing_again(
    corpus: Path,
) -> None:
    # Arrange
    store = _PagingStore()
    _EchoQuestion.fail = True
    await _index(store, corpus, layers=("enrich-with-echo",))

    # Act
    result = await _index(store, corpus, layers=("enrich-with-echo",))

    # Assert
    assert result.layers_failed == ()


async def test_a_failed_layer_whose_document_changed_runs_again_unasked(
    corpus: Path, tmp_path: Path
) -> None:
    """R43.9: raptor's refusal says to raise a bound in the stage's `with:`, which moves the
    identity; a failed record then read as `changed` and the remedy did nothing.
    """
    # Arrange
    store = _PagingStore()
    _EchoQuestion.fail = True
    await _index(store, corpus, layers=("enrich-with-echo",))
    _EchoQuestion.fail = False
    (tmp_path / "pipelines" / "enrich-with-echo.yaml").write_text(
        "name: enrich-with-echo\nstages:\n  - {id: echo, use: same-question}\n"
    )

    # Act
    result = await _index(store, corpus, layers=("enrich-with-echo",))

    # Assert
    assert result.layers_changed == ()
    assert {r.layers[0].status for r in store.records.values()} == {LayerStatus.ACTIVE}


async def test_a_layer_whose_output_depends_on_batch_membership_runs_once_per_source(
    corpus: Path,
) -> None:
    """Carried repair **R43.10**: `enrich-with-raptor` is one tree per document, and Exit C
    handed it twenty-five documents' leaves in one call, which is one tree per batch.
    """
    # Arrange
    store = _PagingStore()

    # Act
    await _index(store, corpus, layers=("enrich-with-tree",))

    # Assert
    assert _EchoQuestion.calls == [1] * 6


async def test_a_layer_whose_identity_moved_is_reported_and_not_re_run(
    corpus: Path, tmp_path: Path
) -> None:
    # Arrange
    store = _PagingStore()
    await _index(store, corpus, layers=("enrich-with-echo",))
    (tmp_path / "pipelines" / "enrich-with-echo.yaml").write_text(
        "name: enrich-with-echo\nstages:\n  - {id: echo, use: same-question}\n"
    )
    _EchoQuestion.calls = []

    # Act
    result = await _index(store, corpus, layers=("enrich-with-echo",))

    # Assert
    assert _EchoQuestion.calls == []
    assert result.layers_changed == ("enrich-with-echo",)


async def test_a_store_without_metadata_filter_is_refused_before_the_base_runs(
    corpus: Path,
) -> None:
    # Arrange
    store = _Store()

    # Act
    with pytest.raises(LayerNeedsMetadataFilterError) as refused:
        await _index(store, corpus, layers=("enrich-with-echo",))

    # Assert
    assert "MetadataFilter" in str(refused.value)
    assert store.adds == []


async def test_an_unknown_layer_is_refused_naming_every_installed_layer(corpus: Path) -> None:
    # Arrange
    store = _PagingStore()

    # Act
    with pytest.raises(UnknownLayerError) as refused:
        await _index(store, corpus, layers=("enrich-with-nothing",))

    # Assert
    assert "'enrich-with-nothing'" in str(refused.value)
    assert set(refused.value.valid_options) >= {"enrich-with-echo", "enrich-with-same"}
    assert store.adds == []


async def test_a_second_layer_writing_a_node_the_first_marked_is_refused(corpus: Path) -> None:
    # Arrange
    store = _PagingStore()
    await _index(store, corpus, layers=("enrich-with-echo",))
    marked = {node.id: node.ext for node in _derived(store)}

    # Act
    with pytest.raises(LayerNodeCollisionError) as refused:
        await _index(store, corpus, layers=("enrich-with-same",))

    # Assert
    message = str(refused.value)
    assert "layer 'enrich-with-same' derived node" in message
    assert "which the 'enrich-with-echo' layer already wrote" in message
    assert {node.id: node.ext for node in _derived(store)} == marked


async def test_each_layer_batch_reports_its_progress_naming_the_layer(corpus: Path) -> None:
    # Arrange
    store = _PagingStore()
    events: list[BatchProgress] = []

    # Act
    await _index(store, corpus, layers=("enrich-with-echo",), events=events)

    # Assert
    layered = [e for e in events if e.layer is not None]
    assert [(e.layer, e.batch, e.batches, e.queryable, e.documents) for e in layered] == [
        ("enrich-with-echo", 1, 2, 4, 6),
        ("enrich-with-echo", 2, 2, 6, 6),
    ]
    assert [e.layer for e in events[:2]] == [None, None]


async def test_reprocess_rebuilds_a_layer_whose_identity_moved(
    corpus: Path, tmp_path: Path
) -> None:
    """`R43.7`, the owner's Q6: a moved layer is never rebuilt unasked, and `--reprocess` is how
    it is asked. The source's old derived nodes go with its leaves, so nothing stale survives.
    """
    # Arrange
    store = _PagingStore()
    await _index(store, corpus, layers=("enrich-with-echo",))
    (tmp_path / "pipelines" / "enrich-with-echo.yaml").write_text(
        "name: enrich-with-echo\nstages:\n  - {id: echo, use: same-question}\n"
    )

    # Act
    result = await _index(store, corpus, layers=("enrich-with-echo",), reprocess=True)

    # Assert
    markers = [node.ext.get(Representation.__namespace__) for node in _derived(store)]
    techniques = sorted({m.technique for m in markers if isinstance(m, Representation)})
    assert techniques == ["same-question"]
    assert len(_derived(store)) == 6
    assert result.layers_changed == ()
    assert {r.layers[0].status for r in store.records.values()} == {LayerStatus.ACTIVE}


@runtime_checkable
class _CorpusReader(Stage[Sequence[Node], Sequence[Node]], Protocol):
    """A third party's own layer-stage contract whose stages read the store, as `Revisable`'s do."""

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]: ...


_CorpusReader.layer_stage = True  # pyright: ignore[reportAttributeAccessIssue]
_CorpusReader.reads_corpus = True  # pyright: ignore[reportAttributeAccessIssue]


class _StoreReading:
    """A layer stage that reads the store it is handed, then derives one node per leaf."""

    counted: ClassVar[list[int]] = []

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        _StoreReading.counted.append(await ctx.require(NodeStore).count())
        derived = tuple(
            node.derive(content=f"read {node.content[:8]!r}", media_type=MediaType.TEXT).with_ext(
                Representation(technique="store-reading")
            )
            for node in payload
        )
        return Produced(value=(*payload, *derived))


async def _index_with(
    store: _Store, corpus: Path, contract: type[object], layer: str
) -> IndexResult:
    registry = _registry(store)
    registry.add(contract, "store-reading", _StoreReading, distribution="weft-example-stranger")
    (corpus.parent / "pipelines" / f"{layer}.yaml").write_text(
        f"name: {layer}\nstages:\n  - {{id: read, use: store-reading}}\n"
    )
    return await run_index(corpus, registry=registry, ctx=_ctx(), batch_size=4, layers=(layer,))


@pytest.mark.parametrize("contract", [_CorpusReader, Revisable])
async def test_a_layer_stage_whose_contract_reads_the_corpus_is_handed_the_store(
    corpus: Path, monkeypatch: pytest.MonkeyPatch, contract: type[object]
) -> None:
    # Arrange — R43.20: only a base naming a `Revisable` was handed the store, by identity.
    monkeypatch.setattr(_StoreReading, "counted", [])
    store = _PagingStore()

    # Act
    result = await _index_with(store, corpus, contract, "enrich-with-reading")

    # Assert
    assert result.layers_failed == ()
    assert _StoreReading.counted
    assert all(count > 0 for count in _StoreReading.counted)
    assert len([n for n in store.nodes.values() if "weft-index" in n.ext]) == 6


def test_revisable_declares_it_reads_the_corpus_and_expander_does_not() -> None:
    # Act / Assert
    assert getattr(Revisable, "reads_corpus", False) is True
    assert getattr(Expander, "reads_corpus", False) is False


async def test_a_layer_that_enriches_leaves_in_place_stores_the_enrichment(
    corpus: Path,
) -> None:
    # Arrange — R43.19: an `Enhancer` hands back every node under its own id, so a tail fed
    # only the nodes with new ids received nothing, and the enrichment was discarded.
    store = _PagingStore()
    registry = _registry(store)
    registry.add(
        Enhancer, "term-frequency-keywords", KeyBertKeywordExtractor, distribution="weft-enhance"
    )
    (corpus.parent / "pipelines" / "enrich-with-keywords.yaml").write_text(
        "name: enrich-with-keywords\nstages:\n  - {id: keywords, use: term-frequency-keywords}\n"
    )

    # Act
    result = await run_index(
        corpus, registry=registry, ctx=_ctx(), batch_size=4, layers=("enrich-with-keywords",)
    )

    # Assert
    assert result.layers_failed == ()
    leaves = [n for n in store.nodes.values() if "weft-index" not in n.ext]
    assert len(leaves) == 6
    assert all(n.ext_as(Keywords) is not None for n in leaves)
    assert all(n.embedding is not None for n in leaves)
