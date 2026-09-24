"""This pack's own tests for `InMemoryNodeStore` — the whole store family in one class."""

from datetime import UTC, datetime
from typing import cast

from weft_example_ingest.store import InMemoryNodeStore

from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, NodeId, Produced, SourceId, Vector
from weft_kernel.seam import wrap
from weft_store.contract import (
    Filter,
    FilterOp,
    MetadataFilter,
    NodeStore,
    ReconcileMode,
    SourceRecord,
    SourceStatus,
    TextSearch,
    VectorSearch,
)


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _node(content: str, *, embedding: Vector | None = None) -> Node:
    node = Node.synthetic(content=content, media_type=MediaType.TEXT, reason="fixture")
    return node if embedding is None else node.with_embedding(embedding)


async def test_add_and_run_are_the_same_write_path_through_the_seam() -> None:
    # Arrange
    store = InMemoryNodeStore()
    wrapped = wrap(
        store.run, distribution="weft-example-ingest", contract="NodeStore", plugin="example-store"
    )
    node = _node("alpha")

    # Act
    outcome = await wrapped([node], _ctx())

    # Assert — `run` is additive to `add`: the node is both passed through and stored.
    assert isinstance(outcome, Produced)
    assert outcome.value == [node]
    assert await store.count() == 1
    assert (await store.get([node.id]))[0] == node


async def test_get_silently_omits_an_unknown_id() -> None:
    # Arrange
    store = InMemoryNodeStore()
    node = _node("alpha")
    await store.add([node])

    # Act
    found = await store.get([node.id, NodeId("sha256:not-a-real-id")])

    # Assert
    assert list(found) == [node]


async def test_delete_source_removes_only_nodes_from_that_source() -> None:
    # Arrange
    store = InMemoryNodeStore()
    kept = Node.synthetic(
        content="kept",
        media_type=MediaType.TEXT,
        reason="fixture",
        sources=frozenset({SourceId("src-b")}),
    )
    removed = Node.synthetic(
        content="removed",
        media_type=MediaType.TEXT,
        reason="fixture",
        sources=frozenset({SourceId("src-a")}),
    )
    await store.add([kept, removed])

    # Act
    result = await store.delete_source(SourceId("src-a"))

    # Assert
    assert result.node_count == 1
    assert await store.get([removed.id]) == ()
    assert (await store.get([kept.id]))[0] == kept


async def test_search_vector_ranks_by_cosine_similarity() -> None:
    # Arrange
    store = InMemoryNodeStore()
    near = _node("near", embedding=Vector(values=(1.0, 0.0)))
    far = _node("far", embedding=Vector(values=(0.0, 1.0)))
    await store.add([near, far])

    # Act
    hits = await store.search_vector(Vector(values=(1.0, 0.0)), top_k=2)

    # Assert
    assert [scored.value.id for scored in hits] == [near.id, far.id]
    assert hits[0].score > hits[1].score


async def test_search_text_ranks_by_word_overlap_and_ignores_no_match() -> None:
    # Arrange
    store = InMemoryNodeStore()
    match = _node("weft is a rag engine")
    unrelated = _node("nothing shared here at all")
    await store.add([match, unrelated])

    # Act
    hits = await store.search_text("weft engine", top_k=5)

    # Assert
    assert [scored.value.id for scored in hits] == [match.id]


async def test_matching_evaluates_a_metadata_filter_over_extension_data() -> None:
    # Arrange
    store = InMemoryNodeStore()
    named = Node.synthetic(content="a", media_type=MediaType.TEXT, reason="fixture")
    other = Node.synthetic(content="b", media_type=MediaType.TEXT, reason="fixture")
    await store.add([named, other])
    filter = Filter(op=FilterOp.EQ, field="content", value="a")

    # Act
    page = await store.matching(filter)

    # Assert
    assert [node.id for node in page.items] == [named.id]


async def test_put_source_and_list_sources_round_trip() -> None:
    # Arrange
    store = InMemoryNodeStore()
    record = SourceRecord(
        id=SourceId("src-a"),
        uri="file:///a.txt",
        content_hash="deadbeef",
        indexed_at=datetime.now(tz=UTC),
        pipeline="example",
    )

    # Act
    await store.put_source(record)

    # Assert
    assert await store.get_source(SourceId("src-a")) == record
    assert record in await store.list_sources()


def test_store_satisfies_the_whole_capability_family_structurally() -> None:
    # Act / Assert — no import of any of the four contracts in store.py itself.
    store = InMemoryNodeStore()
    assert isinstance(store, NodeStore)
    assert isinstance(store, VectorSearch)
    assert isinstance(store, TextSearch)
    assert isinstance(store, MetadataFilter)


async def test_reconcile_finishes_a_deletion_that_was_interrupted() -> None:
    """`Reconcilable` from a stranger's own pack — the backlog is the tombstone, so the pass
    that finds it finishes it and the next one has nothing to do.
    """
    # Arrange — a source whose deletion began, and two nodes it should have taken.
    store = InMemoryNodeStore()
    await store.add(
        (
            Node.synthetic(
                content="one",
                media_type=MediaType.TEXT,
                reason="t",
                sources=frozenset({SourceId("src-a")}),
            ),
            Node.synthetic(
                content="two",
                media_type=MediaType.TEXT,
                reason="t",
                sources=frozenset({SourceId("src-a")}),
            ),
        )
    )
    await store.put_source(
        SourceRecord(
            id=SourceId("src-a"),
            uri="file:///a.txt",
            content_hash="h",
            indexed_at=datetime.now(UTC),
            pipeline="example",
            status=SourceStatus.DELETING,
        )
    )

    # Act
    first = await store.reconcile(_ctx(), ReconcileMode.REPAIR)
    second = await store.reconcile(_ctx(), ReconcileMode.FULL)

    # Assert
    assert (first.examined, first.removed, first.converged) == (1, 2, True)
    assert (second.examined, second.removed, second.backfilled) == (0, 0, 0)
    assert await store.count() == 0


async def test_a_strangers_store_holds_targets_and_passes_the_published_target_checks() -> None:
    """Ledger **34.3**: `TargetHolding` is published, so a store written outside the tree proves it
    with the published kit alone — FF9 clause (c)'s stranger for the new capability.
    """
    # Arrange
    from weft_store.conformance import checks_for
    from weft_store.contract import TargetHolding

    target_checks = [
        check
        for check in checks_for(InMemoryNodeStore())
        if check.__annotations__.get("store") == "TargetHoldingStore"
    ]

    # Act — a fresh store per check: the kit owns no lifecycle.
    for check in target_checks:
        await check(InMemoryNodeStore())

    # Assert
    assert isinstance(InMemoryNodeStore(), TargetHolding)
    assert len(target_checks) == 13


async def test_a_source_s_layers_round_trip_through_the_published_check() -> None:
    """Ledger **43.6**: the in-memory store keeps a record whole, layers included."""
    # Arrange
    from weft_store.conformance import (
        check_a_source_records_layers_round_trip_whole_and_are_listed,
    )

    # Act / Assert — a stranger's store need not carry the Protocol's `version`.
    await check_a_source_records_layers_round_trip_whole_and_are_listed(
        cast("NodeStore", InMemoryNodeStore())
    )


async def test_a_strangers_store_holds_generations_and_passes_the_published_checks() -> None:
    """Ledger **43.14**: `GenerationHolding` is published, so a store written outside the tree
    proves it with the published kit alone — fitness function 9(c)'s stranger for the new
    capability, on `34.3`'s footing.
    """
    # Arrange
    from weft_store.conformance import checks_for
    from weft_store.contract import GenerationHolding

    generation_checks = [
        check
        for check in checks_for(InMemoryNodeStore())
        if check.__annotations__.get("store") == "GenerationHoldingStore"
    ]

    # Act — a fresh store per check: the kit owns no lifecycle.
    for check in generation_checks:
        await check(InMemoryNodeStore())

    # Assert
    assert isinstance(InMemoryNodeStore(), GenerationHolding)
    assert len(generation_checks) == 10


async def test_a_strangers_store_carries_generations_and_passes_the_published_checks() -> None:
    """Ledger **43.22**: `GenerationCarrying` is published, so the stranger proves it with the
    kit alone — fitness function 9(c) for the new capability, on `43.14`'s footing.
    """
    # Arrange
    from weft_store.conformance import checks_for
    from weft_store.contract import GenerationCarrying

    carrying_checks = [
        check
        for check in checks_for(InMemoryNodeStore())
        if check.__annotations__.get("store") == "GenerationCarryingStore"
    ]

    # Act — a fresh store per check: the kit owns no lifecycle.
    for check in carrying_checks:
        await check(InMemoryNodeStore())

    # Assert
    assert isinstance(InMemoryNodeStore(), GenerationCarrying)
    assert len(carrying_checks) == 2


async def test_a_strangers_store_withdraws_generations_and_passes_the_published_checks() -> None:
    """Repair **R43.29**: `GenerationWithdrawing` is published, so the stranger proves it with the
    kit alone — fitness function 9(c) for the new capability, on `43.22`'s footing.
    """
    # Arrange
    from weft_store.conformance import checks_for
    from weft_store.contract import GenerationWithdrawing

    withdrawing_checks = [
        check
        for check in checks_for(InMemoryNodeStore())
        if check.__annotations__.get("store") == "GenerationWithdrawingStore"
    ]

    # Act — a fresh store per check: the kit owns no lifecycle.
    for check in withdrawing_checks:
        await check(InMemoryNodeStore())

    # Assert
    assert isinstance(InMemoryNodeStore(), GenerationWithdrawing)
    assert len(withdrawing_checks) == 4


async def test_a_strangers_store_admits_one_writer_and_passes_the_published_checks() -> None:
    """Ledger **43.18**: `SingleWriter` is published, so the stranger proves it with the kit —
    fitness function 9(c) for the new capability.
    """
    # Arrange
    from weft_store.conformance import checks_for
    from weft_store.contract import SingleWriter

    writer_checks = [
        check
        for check in checks_for(InMemoryNodeStore())
        if check.__annotations__.get("store") == "SingleWriterStore"
    ]

    # Act
    for check in writer_checks:
        await check(InMemoryNodeStore())

    # Assert
    assert isinstance(InMemoryNodeStore(), SingleWriter)
    assert len(writer_checks) == 2
