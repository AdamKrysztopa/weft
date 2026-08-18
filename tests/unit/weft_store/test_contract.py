"""Unit tests for `weft_store.contract`.

Mirrors `packages/weft-store/src/weft_store/contract.py`. Covers a full
resolve-then-run of `NodeStore` through `weft_kernel.runner` (`run` calling
`add` and passing its input through, per the module docstring's narrowing
note), the core property G4 settled — a store's capability is *derived* by
`isinstance`, never declared: one class satisfying both `NodeStore` and
`VectorSearch` reports both, one satisfying only `NodeStore` reports only
that — and `Filter`'s shape validation, both a nested `and`/`not` tree that
builds and a comparison op missing its `value` that does not.
"""

from collections.abc import AsyncIterator, Sequence

import pytest
from pydantic import ValidationError

from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, NodeId, Outcome, Produced, SourceId, Vector
from weft_kernel.registry import Registry
from weft_kernel.runner import Lifetime, Runner, StageSpec
from weft_store.contract import (
    FILTER_AST_VERSION,
    STORE_CONTRACT_VERSION,
    Cursor,
    Filter,
    FilterOp,
    NodeStore,
    Page,
    Removed,
    Scored,
    SourceRecord,
    VectorSearch,
)


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _node(content: str) -> Node:
    return Node.synthetic(content=content, media_type=MediaType.TEXT, reason="test fixture")


class _FullStore:
    """Satisfies both `NodeStore` and `VectorSearch` — one class, two capabilities."""

    version = STORE_CONTRACT_VERSION
    lifetime = Lifetime.RUN
    requires: tuple[type, ...] = ()
    provides: tuple[type, ...] = ()

    def __init__(self, config: object) -> None:
        self._nodes: dict[NodeId, Node] = {}

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        await self.add(payload)
        return Produced(value=payload)

    async def add(self, nodes: Sequence[Node]) -> None:
        for node in nodes:
            self._nodes[node.id] = node

    async def flush(self) -> None:
        return

    async def get(self, ids: Sequence[NodeId]) -> Sequence[Node]:
        return [self._nodes[node_id] for node_id in ids]

    async def delete_source(self, source_id: SourceId) -> Removed:
        return Removed(source_id=source_id, node_count=0)

    async def scan(self, cursor: Cursor | None = None) -> Page[Node]:
        return Page(items=tuple(self._nodes.values()))

    async def count(self) -> int:
        return len(self._nodes)

    async def put_source(self, record: SourceRecord) -> None:
        return

    async def get_source(self, source_id: SourceId) -> SourceRecord | None:
        return None

    async def list_sources(self) -> Sequence[SourceRecord]:
        return ()

    async def search_vector(
        self, vector: Vector, top_k: int, filter: Filter | None = None
    ) -> Sequence[Scored[Node]]:
        return [Scored(value=node, score=1.0) for node in list(self._nodes.values())[:top_k]]


class _VectorlessStore:
    """Satisfies only `NodeStore` — no `search_vector`, so no `VectorSearch` capability."""

    version = STORE_CONTRACT_VERSION
    lifetime = Lifetime.RUN
    requires: tuple[type, ...] = ()
    provides: tuple[type, ...] = ()

    def __init__(self, config: object) -> None:
        self._nodes: dict[NodeId, Node] = {}

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        await self.add(payload)
        return Produced(value=payload)

    async def add(self, nodes: Sequence[Node]) -> None:
        for node in nodes:
            self._nodes[node.id] = node

    async def flush(self) -> None:
        return

    async def get(self, ids: Sequence[NodeId]) -> Sequence[Node]:
        return [self._nodes[node_id] for node_id in ids]

    async def delete_source(self, source_id: SourceId) -> Removed:
        return Removed(source_id=source_id, node_count=0)

    async def scan(self, cursor: Cursor | None = None) -> Page[Node]:
        return Page(items=tuple(self._nodes.values()))

    async def count(self) -> int:
        return len(self._nodes)

    async def put_source(self, record: SourceRecord) -> None:
        return

    async def get_source(self, source_id: SourceId) -> SourceRecord | None:
        return None

    async def list_sources(self) -> Sequence[SourceRecord]:
        return ()


async def test_node_store_composes_through_the_runner_and_adds_every_batch() -> None:
    # Arrange
    registry = Registry()
    registry.add(NodeStore, "fake", _FullStore, distribution="weft-test-pack")
    engine = Runner(registry)
    specs = (StageSpec(id="store", contract=NodeStore, name="fake"),)
    node = _node("hello")

    async def batches() -> AsyncIterator[list[Node]]:
        yield [node]

    # Act
    pipeline = engine.resolve(specs, tenant_id="tenant-a")
    summary = await engine.run(pipeline, batches(), _ctx())

    # Assert
    store = pipeline.stages[0].instance
    assert isinstance(store, _FullStore)
    assert summary.produced == 1
    assert await store.count() == 1


def test_store_capability_is_derived_by_isinstance_not_declared() -> None:
    # Act / Assert
    full_store = _FullStore(config=None)
    vectorless_store = _VectorlessStore(config=None)

    assert isinstance(full_store, NodeStore)
    assert isinstance(full_store, VectorSearch)
    assert isinstance(vectorless_store, NodeStore)
    assert not isinstance(vectorless_store, VectorSearch)


def test_node_store_isinstance_needs_only_the_nine_methods_not_the_metadata() -> None:
    # Arrange — no `version`, `lifetime`, `requires` or `provides` anywhere on this class.
    # Capability must come from implementing the methods alone, per G4.
    class _BareStore:
        def __init__(self, config: object) -> None:
            self._nodes: dict[NodeId, Node] = {}

        async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
            return Produced(value=payload)

        async def add(self, nodes: Sequence[Node]) -> None:
            return

        async def flush(self) -> None:
            return

        async def get(self, ids: Sequence[NodeId]) -> Sequence[Node]:
            return ()

        async def delete_source(self, source_id: SourceId) -> Removed:
            return Removed(source_id=source_id, node_count=0)

        async def scan(self, cursor: Cursor | None = None) -> Page[Node]:
            return Page(items=())

        async def count(self) -> int:
            return 0

        async def put_source(self, record: SourceRecord) -> None:
            return

        async def get_source(self, source_id: SourceId) -> SourceRecord | None:
            return None

        async def list_sources(self) -> Sequence[SourceRecord]:
            return ()

    # Act / Assert
    assert isinstance(_BareStore(config=None), NodeStore)


def test_vector_search_isinstance_needs_only_search_vector_not_the_metadata() -> None:
    # Arrange — no `version`, `lifetime`, `requires` or `provides` declared anywhere.
    class _BareVectorSearch:
        async def search_vector(
            self, vector: Vector, top_k: int, filter: Filter | None = None
        ) -> Sequence[Scored[Node]]:
            return ()

    # Act / Assert
    assert isinstance(_BareVectorSearch(), VectorSearch)


def test_filter_accepts_a_nested_and_not_tree() -> None:
    # Arrange
    leaf_a = Filter(op=FilterOp.EQ, field="media_type", value="text")
    leaf_b = Filter(op=FilterOp.CONTAINS, field="lineage.sources", value="doc-1")
    negated = Filter(op=FilterOp.NOT, clauses=(leaf_b,))

    # Act
    combined = Filter(op=FilterOp.AND, clauses=(leaf_a, negated))

    # Assert
    assert combined.op is FilterOp.AND
    assert combined.clauses == (leaf_a, negated)


def test_filter_refuses_a_comparison_op_missing_its_value() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        Filter(op=FilterOp.EQ, field="media_type")


def test_filter_refuses_a_combinator_with_the_wrong_number_of_clauses() -> None:
    # Arrange — the arity half of the shape rules the module docstring states: `and`/`or`
    # carry two or more clauses, `not` exactly one. Without this, removing either branch
    # leaves every other filter test passing.
    leaf = Filter(op=FilterOp.EQ, field="media_type", value="text")

    # Act / Assert
    with pytest.raises(ValidationError):
        Filter(op=FilterOp.AND, clauses=(leaf,))
    with pytest.raises(ValidationError):
        Filter(op=FilterOp.NOT, clauses=(leaf, leaf))


def test_filter_ast_version_is_declared_on_the_filter_itself() -> None:
    # Act / Assert — versioned separately from the store family, per `docs/09-release.md`.
    assert Filter.version == FILTER_AST_VERSION


def test_store_family_contracts_share_one_declared_version() -> None:
    # Act / Assert
    assert NodeStore.version == STORE_CONTRACT_VERSION
    assert VectorSearch.version == STORE_CONTRACT_VERSION
