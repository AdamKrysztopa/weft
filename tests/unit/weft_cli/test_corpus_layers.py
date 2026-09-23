"""Ledger task **43.15** — a corpus-scoped layer is built as one generation and published whole.

A layer document whose `vars` say `layer.scope: corpus` (a RAPTOR tree over every document is the
shipped case) runs once over the leaves of every indexed source, writes what it makes into a
generation opened for it (`43.14`), and publishes that generation only when the whole build
succeeded. Until then its nodes are invisible, so a half-built tree is never searched. The
previous build's generation is retracted once the new one is published. A source indexed after
the build leaves the layer **stale**: `weft index` says so, and the next run that names the layer
rebuilds it. A store that cannot hold generations is refused by name before anything is written.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import ClassVar, Self

import pytest

from weft_chunk import Chunker
from weft_chunk.fixed_size import FixedSizeChunker
from weft_cli.ingest import IndexResult, run_index
from weft_cli.layers import LayerNeedsGenerationHoldingError, compose_layer
from weft_embed import Embedder
from weft_embed.hash_embedder import HashEmbedder
from weft_engine import registry_bootstrap
from weft_extract import Extractor
from weft_extract.text import TextExtractor
from weft_index import Expander
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
    Vector,
)
from weft_kernel.registry import Registry
from weft_store import NodeStore
from weft_store.contract import (
    Cursor,
    Filter,
    FilterOp,
    GenerationId,
    GenerationRecord,
    GenerationStatus,
    LayerStatus,
    Page,
    Removed,
    SourceRecord,
    UnknownGenerationError,
)

_PAGE = 2
_WHEN_OPENED = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)


def _holds(node: Node, filter: Filter) -> bool:
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


class _State:
    """What every handle onto one store shares: nodes, records, generations, members."""

    def __init__(self) -> None:
        self.nodes: dict[NodeId, Node] = {}
        self.members: dict[NodeId, set[str]] = {}
        self.records: dict[SourceId, SourceRecord] = {}
        self.generations: dict[GenerationId, GenerationRecord] = {}
        self.adds: list[tuple[Node, ...]] = []


class _Store:
    """A store without `GenerationHolding` — it cannot build a corpus-scoped layer."""

    def __init__(self, state: _State | None = None, generation: GenerationId | None = None) -> None:
        self._state = state if state is not None else _State()
        self._generation = generation
        self._published: frozenset[str] | None = None

    @property
    def state(self) -> _State:
        return self._state

    def _touch(self) -> frozenset[str]:
        if self._published is None:
            self._published = frozenset(
                g
                for g, r in self._state.generations.items()
                if r.status is GenerationStatus.PUBLISHED
            )
        return self._published

    def _visible(self, node: Node) -> bool:
        own: set[str] = {self._generation} if self._generation else set()
        seen: frozenset[str] = self._touch() | {""} | own
        return bool(self._state.members.get(node.id, {""}) & seen)

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        await self.add(payload)
        return Produced(value=payload)

    async def add(self, nodes: Sequence[Node]) -> None:
        self._touch()
        self._state.adds.append(tuple(nodes))
        marker = self._generation or ""
        for node in nodes:
            self._state.nodes[node.id] = node
            self._state.members.setdefault(node.id, set()).add(marker)

    async def flush(self) -> None:
        return

    async def count(self) -> int:
        return len(self._state.nodes)

    async def get(self, ids: Sequence[NodeId]) -> Sequence[Node]:
        return tuple(self._state.nodes[i] for i in ids if i in self._state.nodes)

    async def scan(self, cursor: Cursor | None = None) -> Page[Node]:
        del cursor
        return Page(items=tuple(self._state.nodes.values()))

    async def delete_source(self, source_id: SourceId) -> Removed:
        doomed = [i for i, n in self._state.nodes.items() if source_id in n.lineage.sources]
        for i in doomed:
            del self._state.nodes[i]
            self._state.members.pop(i, None)
        self._state.records.pop(source_id, None)
        return Removed(source_id=source_id, node_count=len(doomed))

    async def put_source(self, record: SourceRecord) -> None:
        self._state.records[record.id] = record

    async def get_source(self, source_id: SourceId) -> SourceRecord | None:
        return self._state.records.get(source_id)

    async def list_sources(self) -> Sequence[SourceRecord]:
        return tuple(self._state.records.values())

    async def matching(self, filter: Filter, cursor: Cursor | None = None) -> Page[Node]:
        selected = sorted(
            (n for n in self._state.nodes.values() if self._visible(n) and _holds(n, filter)),
            key=lambda n: n.id,
        )
        start = int(cursor) if cursor is not None else 0
        end = start + _PAGE
        return Page(
            items=tuple(selected[start:end]),
            next_cursor=Cursor(str(end)) if end < len(selected) else None,
        )


class _GenerationStore(_Store):
    """`_Store` plus `GenerationHolding`, implemented whole (`L28.20`)."""

    async def open_generation(self, layer: str) -> GenerationRecord:
        record = GenerationRecord(
            id=GenerationId(f"g-{len(self._state.generations) + 1}"),
            layer=layer,
            status=GenerationStatus.BUILDING,
            opened_at=_WHEN_OPENED,
        )
        self._state.generations[record.id] = record
        return record

    def _known(self, generation: GenerationId) -> GenerationRecord:
        if generation not in self._state.generations:
            raise UnknownGenerationError(generation, valid_options=tuple(self._state.generations))
        return self._state.generations[generation]

    async def bind_generation(self, generation: GenerationId) -> Self:
        self._known(generation)
        return type(self)(self._state, generation)

    async def publish_generation(self, generation: GenerationId) -> GenerationRecord:
        record = self._known(generation).model_copy(
            update={"status": GenerationStatus.PUBLISHED, "published_at": _WHEN_OPENED}
        )
        self._state.generations[generation] = record
        return record

    async def retract_generation(self, generation: GenerationId) -> Removed:
        self._known(generation)
        doomed = [i for i, m in self._state.members.items() if m == {generation}]
        for i in doomed:
            self._state.nodes.pop(i, None)
            del self._state.members[i]
        for m in self._state.members.values():
            m.discard(generation)
        del self._state.generations[generation]
        return Removed(source_id=SourceId(generation), node_count=len(doomed))

    async def generations(self) -> tuple[GenerationRecord, ...]:
        return tuple(self._state.generations.values())


class _Summary:
    """A corpus-scope `Expander`: every leaf back, plus one summary over all of them, embedded
    by this stage itself, as `raptor` embeds its own summaries."""

    calls: ClassVar[list[int]] = []
    fail: ClassVar[bool] = False

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        _Summary.calls.append(len(payload))
        if _Summary.fail:
            return Failed(reason="the model refused")
        if not payload:
            return NothingToProduce(reason="no leaves")
        summary = (
            Node.combine(payload, content="a summary of everything", media_type=MediaType.TEXT)
            .with_ext(Representation(technique="echo-summary"))
            .with_embedding(Vector(values=tuple(0.5 for _ in range(64))))
        )
        return Produced(value=(*payload, summary))


class _CountingEmbedder(HashEmbedder):
    seen: ClassVar[list[int]] = []

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        _CountingEmbedder.seen.append(len(payload))
        return await super().run(payload, ctx)


def _factory(store: _Store, config: object) -> _Store:
    del config
    return store


def _registry(store: _Store) -> Registry:
    registry = Registry()
    registry.add(Extractor, "text", TextExtractor, distribution="weft-extract")
    registry.add(Chunker, "fixed-size", FixedSizeChunker, distribution="weft-chunk")
    registry.add(Embedder, "hash", _CountingEmbedder, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", partial(_factory, store), distribution="weft-store")
    registry.add(Expander, "echo-summary", _Summary, distribution="weft-index")
    return registry


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    docs = tmp_path / "docs"
    docs.mkdir()
    for i in range(6):
        (docs / f"doc{i}.txt").write_text(f"document number {i} says something of its own.")
    (tmp_path / "pipelines").mkdir()
    (tmp_path / "pipelines" / "enrich-with-summary.yaml").write_text(
        "name: enrich-with-summary\n"
        "vars:\n  layer.scope: corpus\n"
        "stages:\n  - {id: summary, use: echo-summary}\n"
    )
    monkeypatch.chdir(tmp_path)
    _Summary.calls = []
    _Summary.fail = False
    _CountingEmbedder.seen = []
    return docs


async def _index(store: _Store, corpus: Path, *, layers: tuple[str, ...] = ()) -> IndexResult:
    return await run_index(
        corpus, registry=_registry(store), ctx=_ctx(), batch_size=4, layers=layers
    )


def _summaries(store: _Store) -> list[Node]:
    return [n for n in store.state.nodes.values() if "weft-index" in n.ext]


async def test_a_corpus_layer_runs_once_over_every_source_and_publishes_one_generation(
    corpus: Path,
) -> None:
    # Arrange
    store = _GenerationStore()

    # Act
    await _index(store, corpus, layers=("enrich-with-summary",))

    # Assert — one call over all six leaves, never one per batch of four.
    assert _Summary.calls == [6]
    (generation,) = await store.generations()
    assert (generation.layer, generation.status) == (
        "enrich-with-summary",
        GenerationStatus.PUBLISHED,
    )
    (summary,) = _summaries(store)
    assert store.state.members[summary.id] == {generation.id}
    assert {r.layers[0].status for r in store.state.records.values()} == {LayerStatus.ACTIVE}


async def test_a_node_the_layer_embedded_itself_is_not_embedded_again(corpus: Path) -> None:
    # Arrange
    store = _GenerationStore()
    await _index(store, corpus)
    _CountingEmbedder.seen = []

    # Act
    await _index(store, corpus, layers=("enrich-with-summary",))

    # Assert — the summary arrived with its vector, so the base's embedder is never handed it.
    assert _CountingEmbedder.seen == []
    assert len(_summaries(store)) == 1


async def test_a_store_that_cannot_hold_generations_is_refused_before_the_base_runs(
    corpus: Path,
) -> None:
    # Arrange
    store = _Store()

    # Act
    with pytest.raises(LayerNeedsGenerationHoldingError) as refused:
        await _index(store, corpus, layers=("enrich-with-summary",))

    # Assert
    assert "GenerationHolding" in str(refused.value)
    assert "'enrich-with-summary'" in str(refused.value)
    assert store.state.adds == []


async def test_a_built_corpus_layer_is_not_rebuilt_while_nothing_changed(corpus: Path) -> None:
    # Arrange
    store = _GenerationStore()
    await _index(store, corpus, layers=("enrich-with-summary",))
    _Summary.calls = []

    # Act
    await _index(store, corpus, layers=("enrich-with-summary",))

    # Assert
    assert _Summary.calls == []
    assert len(await store.generations()) == 1


async def test_a_source_added_later_leaves_the_layer_stale_until_it_is_rebuilt(
    corpus: Path,
) -> None:
    # Arrange
    store = _GenerationStore()
    await _index(store, corpus, layers=("enrich-with-summary",))
    (first,) = await store.generations()
    (corpus / "doc6.txt").write_text("document number 6 arrives after the tree was built.")
    _Summary.calls = []

    # Act
    stale = await _index(store, corpus)
    rebuilt = await _index(store, corpus, layers=("enrich-with-summary",))

    # Assert — reported, not rebuilt unasked; then rebuilt whole, and the old tree retracted.
    assert stale.layers_stale == ("enrich-with-summary",)
    assert _Summary.calls == [7]
    assert rebuilt.layers_stale == ()
    (second,) = await store.generations()
    assert second.id != first.id
    assert second.status is GenerationStatus.PUBLISHED
    assert len(_summaries(store)) == 1
    assert {r.layers[0].status for r in store.state.records.values()} == {LayerStatus.ACTIVE}


async def test_a_failed_corpus_build_leaves_no_generation_behind(corpus: Path) -> None:
    # Arrange
    store = _GenerationStore()
    _Summary.fail = True

    # Act
    await _index(store, corpus, layers=("enrich-with-summary",))

    # Assert
    assert await store.generations() == ()
    assert _summaries(store) == []
    assert {r.layers[0].status for r in store.state.records.values()} == {LayerStatus.FAILED}


def test_enrich_with_raptor_ships_source_scoped_and_composes_with_a_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    config = tmp_path / "weft.toml"
    config.write_text('[packs.store]\ndsn = "postgresql://nobody@localhost:1/none"\n')
    monkeypatch.chdir(tmp_path)
    deps = registry_bootstrap.build_dependencies(config_path=config)

    # Act
    composed = compose_layer(
        "enrich-with-raptor", base="index-text", registry=deps.registry, reports=deps.reports
    )

    # Assert — no `layer.scope` means per source; a project derives it with `layer.scope: corpus`.
    assert [spec.name for spec in composed.layer_specs] == ["raptor"]
    assert "layer.scope" not in composed.resolved.vars
