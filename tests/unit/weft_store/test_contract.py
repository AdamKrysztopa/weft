"""Unit tests for `weft_store.contract`.

Mirrors `packages/weft-store/src/weft_store/contract.py`. Covers a full
resolve-then-run of `NodeStore` through `weft_kernel.runner` (`run` calling
`add` and passing its input through, per the module docstring's narrowing
note), the core property G4 settled — a store's capability is *derived* by
`isinstance`, never declared: one class satisfying both `NodeStore` and
`VectorSearch` reports both, one satisfying only `NodeStore` reports only
that — and `Filter`'s shape validation, both a nested `and`/`not` tree that
builds and a comparison op missing its `value` that does not.

`TextSearch` joins the family at task **2.5**, and the two tests that matter
for it are the two halves of the same property: a class implementing
`search_text` advertises the capability with nothing declared, and a store
that only ranks vectors does *not* — which is what stops a retriever needing
text search from silently getting a vector-only store and building an index
of its own.
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
    MetadataFilter,
    NodeStore,
    Page,
    Reconcilable,
    ReconcileEstimate,
    ReconcileMode,
    ReconcileReport,
    Removed,
    Scored,
    SourceRecord,
    TextSearch,
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


def test_text_search_isinstance_needs_only_search_text_not_the_metadata() -> None:
    # Arrange — no `version`, `lifetime`, `requires` or `provides` declared anywhere, the
    # same shape the `VectorSearch` test above checks: capability from the method alone.
    class _BareTextSearch:
        async def search_text(
            self, text: str, top_k: int, filter: Filter | None = None
        ) -> Sequence[Scored[Node]]:
            return ()

    # Act / Assert
    assert isinstance(_BareTextSearch(), TextSearch)


def test_a_store_that_only_ranks_vectors_does_not_advertise_text_search() -> None:
    # Arrange — `_FullStore` implements `search_vector` and no `search_text`, which is
    # every store this tree shipped before task 2.5.
    store = _FullStore(config=None)

    # Act / Assert — the half of derived capability that has teeth: a run that needs text
    # search against this store must be refused, not adapted, and this is what says so.
    assert isinstance(store, VectorSearch)
    assert not isinstance(store, TextSearch)


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
    assert TextSearch.version == STORE_CONTRACT_VERSION
    assert MetadataFilter.version == STORE_CONTRACT_VERSION


def test_the_family_version_moved_when_the_family_grew_a_capability() -> None:
    # Act / Assert — deliberately a literal, and deliberately a test that has to be edited
    # by whoever grows the family again: `STORE_CONTRACT_VERSION` is fitness function 6's
    # subject for this family, and a capability added with the constant left alone is a
    # published surface that changed with nothing recording it. What the number *means* is
    # G9's, settled 2026-08-21; this pins the mechanical fact that publishing `TextSearch` at
    # task 2.5, `MetadataFilter` at task 2.6, `SourceDeletable` at task 5.1a and `Reconcilable`
    # at task 5.1b each moved it off what came before, and that each was a minor — a capability
    # added without breaking an implementation that already satisfied the family. Task **5.1c**
    # moves it again, to `2.0.0` — a *major*, not a minor: it adds `estimate` to `Reconcilable`,
    # an already-published Protocol, and G9's two-audience rule makes that major for an
    # implementer (every existing `Reconcilable` stops satisfying the Protocol until it adds
    # the method) even though it is minor for a caller — the bump is the maximum of the two.
    assert STORE_CONTRACT_VERSION == "2.0.0"


def test_the_filter_ast_version_moved_when_the_operator_set_narrowed() -> None:
    # Act / Assert — the same discipline one version down, and it fires for a *narrowing*
    # rather than an addition: task 2.6 refused ordered comparison against text and identity
    # comparison against floats, so a filter this AST used to accept no longer validates.
    # That is a change to what the data is, which is precisely what this constant watches.
    assert FILTER_AST_VERSION == "1.1.0"


def test_metadata_filter_is_derived_from_having_the_member_not_from_saying_so() -> None:
    # Arrange — `02` §1 specified `MetadataFilter` as a bare marker, and task 2.5 measured
    # what that would have meant: an empty `@runtime_checkable` Protocol has an empty
    # `__protocol_attrs__`, so every object in the language satisfies it. This is the test
    # that the published version has a member, and therefore says something.
    class _FilteringStore(_VectorlessStore):
        async def matching(self, filter: Filter, cursor: Cursor | None = None) -> Page[Node]:
            del filter, cursor
            return Page(items=())

    # Act / Assert
    assert isinstance(_FilteringStore(config=None), MetadataFilter)
    assert not isinstance(_VectorlessStore(config=None), MetadataFilter)
    assert not isinstance(42, MetadataFilter)


def test_reconcilable_requires_estimate_not_only_reconcile() -> None:
    # Arrange — task 5.1c's own reason `STORE_CONTRACT_VERSION` moved to a major: a class
    # satisfying the pre-5.1c shape of `Reconcilable` (`reconcile` alone) no longer does,
    # because `estimate` joined as a second required member rather than an optional one.
    class _ReconcilesOnly:
        async def reconcile(self, ctx: Context, mode: ReconcileMode) -> ReconcileReport:
            del ctx
            return ReconcileReport(mode=mode)

    class _ReconcilesAndEstimates(_ReconcilesOnly):
        async def estimate(self, ctx: Context, mode: ReconcileMode) -> ReconcileEstimate:
            del ctx
            return ReconcileEstimate(mode=mode, description="nothing to converge")

    # Act / Assert
    assert not isinstance(_ReconcilesOnly(), Reconcilable)
    assert isinstance(_ReconcilesAndEstimates(), Reconcilable)


def test_reconcile_estimate_defaults_zero_model_calls_and_pending() -> None:
    # Arrange / Act — the honest floor `docs/03-cli.md`'s worked example names a real number
    # for only when a pack actually has backfill work; every first-party store today has none.
    estimate = ReconcileEstimate(mode=ReconcileMode.FULL, description="no unfinished deletions")

    # Assert
    assert (estimate.pending, estimate.model_calls) == (0, 0)


def test_an_ordered_comparison_against_text_is_refused_where_the_filter_is_built() -> None:
    # Arrange / Act / Assert — refused once, in the data, rather than differently by each
    # store: ordering text means whatever a database's collation means, and the second
    # backend (task 2.6) ranges over numbers only.
    with pytest.raises(ValidationError, match="must be a number"):
        Filter(op=FilterOp.GT, field="ext.weft-pdf.backend", value="pypdf")


def test_identity_against_a_floating_point_number_is_refused_naming_the_range_to_use() -> None:
    # Arrange / Act / Assert — a document store indexes floats for ranges and not for
    # matching, so the same `eq` that selects in SQL selects nothing there, silently.
    with pytest.raises(ValidationError, match="gte"):
        Filter(op=FilterOp.EQ, field="ext.weft-clean.confidence", value=0.5)


@pytest.mark.parametrize("op", [FilterOp.LT, FilterOp.LTE, FilterOp.GT, FilterOp.GTE])
def test_an_ordered_comparison_against_a_fractional_bound_is_the_case_ranges_exist_for(
    op: FilterOp,
) -> None:
    # Arrange / Act — the remedy the identity refusal above *names* is a range with the
    # bounds you meant, and a confidence, a score or a threshold is fractional by nature.
    # Repair for a reviewer finding against task 2.6: the float refusal ran for every
    # comparison op, so the remedy it named was refused by the same validator and no filter
    # anywhere could compare against a fractional number.
    built = Filter(op=op, field="ext.weft-clean.confidence", value=0.8)

    # Assert
    assert built.value == 0.8
