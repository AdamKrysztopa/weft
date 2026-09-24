"""Carried repair R43.29: a query reads the tree it opened on until it ends.

Carried repair **R43.29** — a query that opened before a corpus layer's publish reads the tree it
opened on until it ends.

A handle fixes its manifest when it opens (`43.14`), and the layer loop retracted the superseded
generation right after publishing its replacement, deleting the nodes only it held. A reader holding
the old manifest was left with nothing (`43.24`'s exit script, Qdrant, 2 of 4 runs). The loop now
withdraws a superseded published generation when the store is `GenerationWithdrawing`, which
changes no node, and reclaims the layer's withdrawn generations before it opens that layer's next
one. `weft reconcile` reclaims them too. An abandoned `BUILDING` generation is still retracted, and
a store that cannot withdraw still retracts.

The store is `corpus_build_doubles.GenerationStore`, subclassed here to log every generation
lifecycle call in order and, for the withdrawing variant, to hold withdrawn generations.
"""

from functools import partial
from pathlib import Path
from typing import cast

import pytest

from tests.unit.weft_cli.corpus_build_doubles import (
    LAYER,
    TERSE_PROMPT,
    GenerationStore,
    ScriptedModel,
    State,
    index,
    interrupt_after,
    llm_section,
    make_ctx,
    published,
    registry_for,
    visible_summaries,
    write_corpus,
    write_layer,
)
from weft_cli.ingest import IndexResult, run_index
from weft_cli.reconcile import participants, reconcile_everywhere
from weft_index.payload import RaptorFacts
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, NodeId, SourceId
from weft_kernel.registry import Registry
from weft_store import NodeStore
from weft_store.contract import (
    Filter,
    FilterOp,
    GenerationId,
    GenerationRecord,
    GenerationStatus,
    ReconcileEstimate,
    ReconcileMode,
    ReconcileReport,
    Removed,
)

_SUMMARIES = Filter(op=FilterOp.EXISTS, field=f"ext.{RaptorFacts.__namespace__}.clusters_found")


class _LoggedState(State):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, str]] = []


class _LoggingStore(GenerationStore):
    """A store that cannot withdraw: every lifecycle call is logged, then behaves as before."""

    def __init__(self, state: State | None = None, generation: GenerationId | None = None) -> None:
        super().__init__(state if state is not None else _LoggedState(), generation)

    @property
    def calls(self) -> list[tuple[str, str]]:
        return cast(_LoggedState, self.state).calls

    async def open_generation(self, layer: str) -> GenerationRecord:
        record = await super().open_generation(layer)
        self.calls.append(("open", record.id))
        return record

    async def publish_generation(self, generation: GenerationId) -> GenerationRecord:
        self.calls.append(("publish", generation))
        return await super().publish_generation(generation)

    async def retract_generation(self, generation: GenerationId) -> Removed:
        self.calls.append(("retract", generation))
        return await super().retract_generation(generation)


class _WithdrawingStore(_LoggingStore):
    """`GenerationWithdrawing` on the double: a withdraw changes no node, a reclaim retracts."""

    async def withdraw_generation(self, generation: GenerationId) -> GenerationRecord:
        self.calls.append(("withdraw", generation))
        record = self._known(generation)
        if record.status is not GenerationStatus.PUBLISHED:
            raise AssertionError(f"the loop withdrew a {record.status} generation: {generation}")
        withdrawn = record.model_copy(update={"status": GenerationStatus.WITHDRAWN})
        self.state.generations[generation] = withdrawn
        return withdrawn

    async def reclaim_withdrawn(self, layer: str) -> Removed:
        self.calls.append(("reclaim", layer))
        doomed = [
            record.id
            for record in self.state.generations.values()
            if record.layer == layer and record.status is GenerationStatus.WITHDRAWN
        ]
        removed = 0
        for generation in doomed:
            removed += (await GenerationStore.retract_generation(self, generation)).node_count
        return Removed(source_id=SourceId(layer), node_count=removed)


class _ReconcilingWithdrawingStore(_WithdrawingStore):
    """A `Reconcilable` participant with nothing of its own to converge."""

    async def reconcile(self, ctx: Context, mode: ReconcileMode) -> ReconcileReport:
        del ctx
        return ReconcileReport(mode=mode)

    async def estimate(self, ctx: Context, mode: ReconcileMode) -> ReconcileEstimate:
        del ctx
        return ReconcileEstimate(mode=mode, description="nothing pending")


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    write_layer(tmp_path)
    monkeypatch.chdir(tmp_path)
    ScriptedModel.reset()
    return write_corpus(tmp_path)


async def _rebuild(store: GenerationStore, corpus: Path, *, label: str) -> IndexResult:
    """`weft index --layers <LAYER> --layers-only --reprocess` after the layer's prompt moved."""
    ScriptedModel.label = label
    return await run_index(
        corpus,
        registry=registry_for(store),
        ctx=make_ctx(),
        llm=llm_section("m1"),
        layers=(LAYER,),
        layers_only=True,
        reprocess=True,
    )


async def _summaries_seen_by(handle: GenerationStore) -> set[NodeId]:
    """Every summary `handle` finds; its first call fixes its manifest."""
    seen: set[NodeId] = set()
    page = await handle.matching(_SUMMARIES)
    seen |= {node.id for node in page.items}
    while page.next_cursor is not None:
        page = await handle.matching(_SUMMARIES, page.next_cursor)
        seen |= {node.id for node in page.items}
    return seen


def _published_id(store: GenerationStore) -> GenerationId:
    (record,) = published(store)
    return record.id


def _summary(content: str) -> Node:
    return Node.synthetic(
        content=content,
        media_type=MediaType.TEXT,
        reason="R43.29",
        sources=frozenset({SourceId("doc0")}),
    )


async def test_a_rebuild_withdraws_the_published_tree_so_an_open_reader_keeps_it(
    corpus: Path, tmp_path: Path
) -> None:
    # Arrange
    store = _WithdrawingStore()
    await index(store, corpus)
    old = _published_id(store)
    old_tree = {node.id for node in visible_summaries(store)}
    reader = _WithdrawingStore(store.state)
    assert await _summaries_seen_by(reader) == old_tree
    write_layer(tmp_path, prompt=TERSE_PROMPT)

    # Act
    await _rebuild(store, corpus, label="second")

    # Assert
    assert await _summaries_seen_by(reader) == old_tree, "an open reader lost its tree"
    assert ("retract", old) not in store.calls, "the superseded published tree was retracted"
    assert ("withdraw", old) in store.calls
    new_tree = {node.id for node in visible_summaries(store)}
    assert new_tree and not new_tree & old_tree
    assert await _summaries_seen_by(_WithdrawingStore(store.state)) == new_tree
    assert store.state.generations[old].status is GenerationStatus.WITHDRAWN


async def test_the_next_build_of_the_layer_reclaims_the_withdrawn_tree_before_it_opens_one(
    corpus: Path, tmp_path: Path
) -> None:
    # Arrange — built, then rebuilt, so the first tree is withdrawn.
    store = _WithdrawingStore()
    await index(store, corpus)
    first = _published_id(store)
    first_tree = {node.id for node in visible_summaries(store)}
    write_layer(tmp_path, prompt=TERSE_PROMPT)
    await _rebuild(store, corpus, label="second")
    second = _published_id(store)
    write_layer(tmp_path)
    since = len(store.calls)

    # Act
    await _rebuild(store, corpus, label="third")

    # Assert
    third_build = store.calls[since:]
    assert ("reclaim", LAYER) in third_build, f"the build reclaimed nothing: {third_build}"
    opened = next(i for i, (call, _) in enumerate(third_build) if call == "open")
    assert third_build.index(("reclaim", LAYER)) < opened, third_build
    assert first not in store.state.generations
    assert not first_tree & set(store.state.nodes)
    assert store.state.generations[second].status is GenerationStatus.WITHDRAWN


async def test_a_store_that_cannot_withdraw_still_retracts_the_superseded_tree(
    corpus: Path, tmp_path: Path
) -> None:
    # Arrange
    store = _LoggingStore()
    await index(store, corpus)
    old = _published_id(store)
    old_tree = {node.id for node in visible_summaries(store)}
    write_layer(tmp_path, prompt=TERSE_PROMPT)

    # Act
    await _rebuild(store, corpus, label="second")

    # Assert
    assert ("retract", old) in store.calls
    assert old not in store.state.generations
    assert not old_tree & set(store.state.nodes)
    assert len(published(store)) == 1


async def test_an_abandoned_building_generation_is_retracted_even_by_a_store_that_withdraws(
    corpus: Path, tmp_path: Path
) -> None:
    # Arrange — interrupted, then rerun under another prompt, so nothing is adopted.
    store = _WithdrawingStore()
    await interrupt_after(store, corpus, summaries=1)
    abandoned = next(
        record.id
        for record in store.state.generations.values()
        if record.status is GenerationStatus.BUILDING
    )
    write_layer(tmp_path, prompt=TERSE_PROMPT)

    # Act
    await index(store, corpus)

    # Assert
    assert ("retract", abandoned) in store.calls
    assert ("withdraw", abandoned) not in store.calls
    assert abandoned not in store.state.generations


async def test_reconcile_reclaims_every_withdrawn_generation_a_participant_holds() -> None:
    # Arrange — two trees of one layer, the older withdrawn, on a reconcilable store.
    state = _LoggedState()
    store = _ReconcilingWithdrawingStore(state)
    old_node, new_node = _summary("the old tree"), _summary("the new tree")
    old = await store.open_generation(LAYER)
    await (await store.bind_generation(old.id)).add([old_node])
    await store.publish_generation(old.id)
    new = await store.open_generation(LAYER)
    await (await store.bind_generation(new.id)).add([new_node])
    await store.publish_generation(new.id)
    await store.withdraw_generation(old.id)
    registry = Registry()
    registry.add(
        NodeStore,
        "pgvector",
        partial(_ReconcilingWithdrawingStore, state),
        distribution="weft-store",
    )
    targets = participants(registry=registry, store_names=frozenset({"pgvector"}))
    assert [target.name for target in targets] == ["pgvector"]

    # Act
    (outcome,) = await reconcile_everywhere(ReconcileMode.REPAIR, targets=targets, ctx=make_ctx())

    # Assert
    assert outcome.error is None, outcome.error
    assert ("reclaim", LAYER) in state.calls, f"reconcile reclaimed nothing: {state.calls}"
    assert old.id not in state.generations
    assert old_node.id not in state.nodes
    assert state.generations[new.id].status is GenerationStatus.PUBLISHED
    assert new_node.id in state.nodes
