"""Carried repair **R43.23** — every node a layer creates is stored carrying `LayerMember`.

`adrap` reads the stored RAPTOR tree to join new leaves into it, and a store that also held an
`enrich-with-raptor` layer's tree gave it that tree too. `weft_cli.layers` now stamps each node
a layer creates with `LayerMember(layer=<the layer's name>)` before the tail stores it, in both
scopes, so a base-pipeline stage can tell a layer's nodes from its own. A leaf the layer was
handed — passed through, or enriched in place — is the base pipeline's node and stays
unstamped.

The doubles are `test_index_layers.py`'s (source scope) and `test_corpus_layers.py`'s (corpus
scope), cut to what these tests drive.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Self

import pytest

from weft_chunk import Chunker
from weft_chunk.fixed_size import FixedSizeChunker
from weft_cli.ingest import IndexResult, run_index
from weft_embed import Embedder
from weft_embed.hash_embedder import HashEmbedder
from weft_enhance import Enhancer
from weft_enhance.keybert_stand_in import KeyBertKeywordExtractor
from weft_enhance.keywords import Keywords
from weft_extract import Extractor
from weft_extract.text import TextExtractor
from weft_index import Expander
from weft_index.payload import LayerMember, Representation
from weft_kernel.context import Context
from weft_kernel.payload import (
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
    def __init__(self) -> None:
        self.nodes: dict[NodeId, Node] = {}
        self.members: dict[NodeId, set[str]] = {}
        self.records: dict[SourceId, SourceRecord] = {}
        self.generations: dict[GenerationId, GenerationRecord] = {}


class _Store:
    """A paging `MetadataFilter` store whose handles share one `_State`.

    A paging `MetadataFilter` store whose handles share one `_State`; a handle bound to a
    generation marks what it writes, and reads what is published plus its own.
    """

    def __init__(self, state: _State | None = None, generation: GenerationId | None = None) -> None:
        self._state = state if state is not None else _State()
        self._generation = generation
        self._published: frozenset[str] | None = None

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


class _EchoQuestion:
    """A source-scope `Expander`: every leaf back, plus one question derived from each."""

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        if not payload:
            return NothingToProduce(reason="no leaves")
        derived = tuple(
            node.derive(
                content=f"what does {node.content[:12]!r} say?", media_type=MediaType.TEXT
            ).with_ext(Representation(technique="echo-question"))
            for node in payload
        )
        return Produced(value=(*payload, *derived))


class _Summary:
    """A corpus-scope `Expander` returning every leaf plus one self-embedded summary over them.

    A corpus-scope `Expander`: every leaf back, plus one summary over all of them, embedded
    by this stage itself, as `raptor` embeds its own summaries.
    """

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        if not payload:
            return NothingToProduce(reason="no leaves")
        summary = (
            Node.combine(payload, content="a summary of everything", media_type=MediaType.TEXT)
            .with_ext(Representation(technique="echo-summary"))
            .with_embedding(Vector(values=tuple(0.5 for _ in range(64))))
        )
        return Produced(value=(*payload, summary))


def _factory(store: _Store, config: object) -> _Store:
    del config
    return store


def _registry(store: _Store, second: _Store | None = None) -> Registry:
    registry = Registry()
    registry.add(Extractor, "text", TextExtractor, distribution="weft-extract")
    registry.add(Chunker, "fixed-size", FixedSizeChunker, distribution="weft-chunk")
    registry.add(Embedder, "hash", HashEmbedder, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", partial(_factory, store), distribution="weft-store")
    if second is not None:
        registry.add(NodeStore, "second", partial(_factory, second), distribution="weft-example")
    registry.add(Expander, "echo-question", _EchoQuestion, distribution="weft-index")
    registry.add(Expander, "echo-summary", _Summary, distribution="weft-index")
    registry.add(
        Enhancer, "term-frequency-keywords", KeyBertKeywordExtractor, distribution="weft-enhance"
    )
    return registry


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    docs = tmp_path / "docs"
    docs.mkdir()
    for i in range(6):
        (docs / f"doc{i}.txt").write_text(f"document number {i} says something of its own.")
    pipelines = tmp_path / "pipelines"
    pipelines.mkdir()
    (pipelines / "enrich-with-echo.yaml").write_text(
        "name: enrich-with-echo\nstages:\n  - {id: echo, use: echo-question}\n"
    )
    (pipelines / "enrich-with-keywords.yaml").write_text(
        "name: enrich-with-keywords\nstages:\n  - {id: keywords, use: term-frequency-keywords}\n"
    )
    (pipelines / "enrich-with-summary.yaml").write_text(
        "name: enrich-with-summary\n"
        "vars:\n  layer.scope: corpus\n"
        "stages:\n  - {id: summary, use: echo-summary}\n"
    )
    (pipelines / "index-two-stores.yaml").write_text(
        "name: index-two-stores\n"
        "stages:\n"
        "  - {id: extract, use: text}\n"
        "  - {id: chunk, use: fixed-size}\n"
        "  - {id: embed, use: hash}\n"
        "  - {id: store, use: pgvector}\n"
        "  - {id: second-store, use: second}\n"
    )
    monkeypatch.chdir(tmp_path)
    return docs


async def _index(
    store: _Store,
    corpus: Path,
    *,
    layers: tuple[str, ...],
    second: _Store | None = None,
) -> IndexResult:
    return await run_index(
        corpus,
        registry=_registry(store, second),
        ctx=_ctx(),
        pipeline="index-two-stores" if second is not None else None,
        batch_size=4,
        layers=layers,
    )


async def _stored(store: _Store) -> list[Node]:
    return list((await store.scan()).items)


def _stamps(nodes: Sequence[Node]) -> list[str | None]:
    return [stamp.layer if (stamp := n.ext_as(LayerMember)) else None for n in nodes]


async def test_a_source_scoped_layer_stamps_every_node_it_created_and_no_leaf(
    corpus: Path,
) -> None:
    # Arrange
    store = _Store()

    # Act
    result = await _index(store, corpus, layers=("enrich-with-echo",))

    # Assert
    assert result.layers_failed == ()
    stored = await _stored(store)
    created = [n for n in stored if n.ext_as(Representation) is not None]
    leaves = [n for n in stored if n.ext_as(Representation) is None]
    assert len(created) == 6
    assert _stamps(created) == ["enrich-with-echo"] * 6
    assert _stamps(leaves) == [None] * len(leaves)


async def test_a_leaf_a_source_scoped_layer_enriched_in_place_is_stored_unstamped(
    corpus: Path,
) -> None:
    # Arrange
    store = _Store()

    # Act
    result = await _index(store, corpus, layers=("enrich-with-keywords",))

    # Assert
    assert result.layers_failed == ()
    enriched = [n for n in await _stored(store) if n.ext_as(Keywords) is not None]
    assert len(enriched) == 6
    assert _stamps(enriched) == [None] * 6


async def test_a_corpus_scoped_layer_stamps_the_node_it_created_and_no_leaf(
    corpus: Path,
) -> None:
    # Arrange
    store = _GenerationStore()

    # Act
    result = await _index(store, corpus, layers=("enrich-with-summary",))

    # Assert
    assert result.layers_failed == ()
    stored = await _stored(store)
    (summary,) = [n for n in stored if n.ext_as(Representation) is not None]
    leaves = [n for n in stored if n.ext_as(Representation) is None]
    assert _stamps((summary,)) == ["enrich-with-summary"]
    assert len(leaves) == 6
    assert _stamps(leaves) == [None] * 6


async def test_a_corpus_scoped_layer_over_two_stores_stamps_what_each_store_holds(
    corpus: Path,
) -> None:
    # Arrange
    primary, second = _GenerationStore(), _GenerationStore()

    # Act
    result = await _index(primary, corpus, layers=("enrich-with-summary",), second=second)

    # Assert
    assert result.layers_failed == ()
    for store in (primary, second):
        (summary,) = [n for n in await _stored(store) if n.ext_as(Representation) is not None]
        assert _stamps((summary,)) == ["enrich-with-summary"]
