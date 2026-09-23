"""Ledger task **43.17** — the graph layer, per source, and the store need a layer declares.

`enrich-with-facts-and-graph` (shipped by `weft_kg`) runs `cooccurrence-graph` and then
`llm-facts` over leaves a base already stored, so co-occurrence never draws edges over fact and
mention nodes. Its fact nodes are only a graph once a store turns them into entity and relation
rows, so the document says which ext model its base must have a store for:
`layer.store-consumes: <namespace>`. A store says what it turns into rows of its own by declaring
`consumes`, a tuple of `ExtModel` classes, on its class. `weft_cli.layers` reads both and knows
nothing of graphs: over a base with no such store the layer is refused by name before anything
runs, never written into the vector store alone, and the refusal offers every installed store
that declares it.

The stranger doubles are `test_index_layers.py`'s own, copied: a store that pages `matching` two
nodes at a time and implements `put_source` whole (`L28.20`).
"""

from collections.abc import Iterator, Sequence
from functools import partial
from pathlib import Path
from typing import ClassVar

import pytest
from pydantic import Field

from weft_chunk import Chunker
from weft_chunk.fixed_size import FixedSizeChunker
from weft_cli.ingest import IndexResult, run_index
from weft_cli.layers import (
    LayerNeedsConsumingStoreError,
    LayerScope,
    compose_layer,
    installed_layers,
)
from weft_embed import Embedder
from weft_embed.hash_embedder import HashEmbedder
from weft_engine import registry_bootstrap
from weft_engine.registry_bootstrap import Dependencies
from weft_enhance import Enhancer
from weft_extract import Extractor
from weft_extract.text import TextExtractor
from weft_index import Expander
from weft_kernel.context import Context
from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_kernel.payload import (
    ExtModel,
    MediaType,
    Node,
    NodeId,
    NothingToProduce,
    Outcome,
    Produced,
    SourceId,
)
from weft_kernel.registry import Registry
from weft_store import NodeStore
from weft_store.contract import (
    Cursor,
    Filter,
    FilterOp,
    Page,
    Removed,
    SourceRecord,
)

_GRAPH_LAYER = "enrich-with-facts-and-graph"
_PAGE = 2


# --- the shipped document, resolved against the installed packs ---------------------------------


@pytest.fixture
def deps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Dependencies]:
    config = tmp_path / "weft.toml"
    # Resolution builds nothing, so the stores need a DSN and never a reachable one.
    config.write_text(
        '[packs.store]\ndsn = "postgresql://nobody@localhost:1/none"\n\n'
        '[packs.graph]\ndsn = "postgresql://nobody@localhost:1/none"\n'
    )
    monkeypatch.chdir(tmp_path)
    yield registry_bootstrap.build_dependencies(config_path=config)


def test_the_graph_layer_runs_co_occurrence_before_facts_over_a_graph_base(
    deps: Dependencies,
) -> None:
    # Act
    composed = compose_layer(
        _GRAPH_LAYER, base="index-with-graph", registry=deps.registry, reports=deps.reports
    )

    # Assert — both contracts declare `layer_stage`; the base's three tail stages carry the rest.
    assert [(spec.contract, spec.name) for spec in composed.layer_specs] == [
        (Enhancer, "cooccurrence-graph"),
        (Expander, "llm-facts"),
    ]
    assert [(spec.contract, spec.name) for spec in composed.tail_specs] == [
        (Embedder, "hash"),
        (NodeStore, "pgvector"),
        (NodeStore, "pgvector-graph"),
    ]
    assert composed.scope is LayerScope.SOURCE


def test_the_graph_layer_is_an_installed_layer(deps: Dependencies) -> None:
    # Act
    layers = installed_layers(registry=deps.registry, reports=deps.reports)

    # Assert
    assert _GRAPH_LAYER in layers


def test_the_graph_layer_over_a_base_with_no_graph_store_is_refused_offering_one(
    deps: Dependencies,
) -> None:
    # Act
    with pytest.raises(LayerNeedsConsumingStoreError) as refused:
        compose_layer(_GRAPH_LAYER, base="index-text", registry=deps.registry, reports=deps.reports)

    # Assert — offered because its class consumes the fact model, not because of its name.
    assert isinstance(refused.value, WeftError)
    assert isinstance(refused.value, UnresolvedNameError)
    assert "pgvector-graph" in refused.value.valid_options
    assert "pgvector" not in refused.value.valid_options
    message = str(refused.value)
    assert f"'{_GRAPH_LAYER}'" in message
    assert "'index-text'" in message
    assert "pgvector-graph" in message


def test_a_layer_declaring_no_store_need_still_composes_over_any_base(
    deps: Dependencies,
) -> None:
    # Act
    composed = compose_layer(
        "enrich-with-questions", base="index-text", registry=deps.registry, reports=deps.reports
    )

    # Assert
    assert [spec.name for spec in composed.layer_specs] == ["hypothetical-questions"]


# --- a stranger's store and layer, through `weft index` -----------------------------------------


class _StrangerFact(ExtModel):
    """A third party's own fact model, which only its own store turns into rows."""

    __namespace__: ClassVar[str] = "stranger-fact"
    __schema_version__: ClassVar[str] = "1"

    about: str = Field(min_length=1)


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


class _PagingStore:
    """A store holding nodes and records whole, with a `matching` that pages two at a time."""

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


class _ConsumingStore(_PagingStore):
    """`_PagingStore` whose class declares it turns `_StrangerFact` into rows of its own."""

    consumes: ClassVar[tuple[type[ExtModel], ...]] = (_StrangerFact,)
    built: ClassVar[list["_ConsumingStore"]] = []

    def __init__(self, config: object = None) -> None:
        super().__init__(config)
        _ConsumingStore.built.append(self)


class _StrangerFacts:
    """An `Expander`: every leaf back, plus one fact node derived from each."""

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        if not payload:
            return NothingToProduce(reason="no leaves")
        derived = tuple(
            node.derive(content=f"a fact about {node.id}", media_type=MediaType.TEXT).with_ext(
                _StrangerFact(about=str(node.id))
            )
            for node in payload
        )
        return Produced(value=(*payload, *derived))


def _factory(store: _PagingStore, config: object) -> _PagingStore:
    del config
    return store


def _registry(store: _PagingStore) -> Registry:
    registry = Registry()
    registry.add(Extractor, "text", TextExtractor, distribution="weft-extract")
    registry.add(Chunker, "fixed-size", FixedSizeChunker, distribution="weft-chunk")
    registry.add(Embedder, "hash", HashEmbedder, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", partial(_factory, store), distribution="weft-store")
    registry.add(NodeStore, "stranger-graph", _ConsumingStore, distribution="weft-example")
    registry.add(Expander, "stranger-facts", _StrangerFacts, distribution="weft-example")
    return registry


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Six short text files, a stranger's layer document and a base naming its store."""
    docs = tmp_path / "docs"
    docs.mkdir()
    for i in range(6):
        (docs / f"doc{i}.txt").write_text(f"document number {i} says something of its own.")
    pipelines = tmp_path / "pipelines"
    pipelines.mkdir()
    (pipelines / "enrich-with-stranger-facts.yaml").write_text(
        "name: enrich-with-stranger-facts\n"
        "vars:\n  layer.store-consumes: stranger-fact\n"
        "stages:\n  - {id: facts, use: stranger-facts}\n"
    )
    (pipelines / "index-with-stranger-graph.yaml").write_text(
        "name: index-with-stranger-graph\n"
        "stages:\n"
        "  - {id: extract, use: text}\n"
        "  - {id: chunk, use: fixed-size}\n"
        "  - {id: embed, use: hash}\n"
        "  - {id: store, use: pgvector}\n"
        "  - {id: graph-store, use: stranger-graph}\n"
    )
    monkeypatch.chdir(tmp_path)
    _ConsumingStore.built = []
    return docs


async def _index(store: _PagingStore, corpus: Path, *, pipeline: str | None = None) -> IndexResult:
    return await run_index(
        corpus,
        registry=_registry(store),
        ctx=_ctx(),
        pipeline=pipeline,
        batch_size=4,
        layers=("enrich-with-stranger-facts",),
    )


def _held_facts() -> dict[NodeId, Node]:
    return {
        node.id: node
        for store in _ConsumingStore.built
        for node in store.nodes.values()
        if _StrangerFact.__namespace__ in node.ext
    }


async def test_a_layer_whose_base_has_no_consuming_store_is_refused_before_the_base_runs(
    corpus: Path,
) -> None:
    # Arrange — the default base names one store, and that store consumes nothing.
    store = _PagingStore()

    # Act
    with pytest.raises(LayerNeedsConsumingStoreError) as refused:
        await _index(store, corpus)

    # Assert — computed from the installed classes, never a first-party name.
    assert refused.value.valid_options == ("stranger-graph",)
    assert store.adds == []
    message = str(refused.value)
    assert "'enrich-with-stranger-facts'" in message
    assert "stranger-fact" in message
    assert "stranger-graph" in message


async def test_a_layer_whose_base_has_a_consuming_store_writes_its_facts_there(
    corpus: Path,
) -> None:
    # Arrange
    store = _PagingStore()

    # Act
    result = await _index(store, corpus, pipeline="index-with-stranger-graph")

    # Assert — every leaf's fact reached the store that turns it into rows.
    assert result.layers_failed == ()
    assert len(_held_facts()) == 6
    assert all(node.embedding is not None for node in _held_facts().values())
