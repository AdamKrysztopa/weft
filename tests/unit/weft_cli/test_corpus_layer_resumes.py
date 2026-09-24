"""Ledger task 43.20: an interrupted corpus-scoped build resumes, paying only for what is left.

Ledger task **43.20** — an interrupted corpus-scoped build resumes, paying only for what it
had not finished.

A corpus-scoped `raptor` layer summarises every cluster before anything reaches its generation,
so Ctrl-C after the ninth of ten summaries used to leave nothing but a `BUILDING` generation, and
the next run opened another and paid for all ten again. Each summary is now kept in the open
generation as it completes, keyed by its cluster and the layer's identity (prompt, role, model);
a rerun under the same identity adopts the newest `BUILDING` generation of that layer, retracts
any other, and summarises only the clusters it does not hold. A rerun whose identity moved never
adopts. `CancelledError` still propagates.

`raptor` here is the shipped plugin, run through `weft index` with a scripted model: a double
narrower than `raptor` would be `L12.13`'s trap. `cluster_size: 2` with a threshold every pair
clears makes `CLUSTERS` clusters of `LEAVES` leaves, and `max_concurrent_summaries: 1` makes
"after k summaries" a fact rather than a race.
"""

import asyncio
from pathlib import Path

import pytest

from tests.unit.weft_cli.corpus_build_doubles import (
    CLUSTERS,
    TERSE_PROMPT,
    CountingEmbedder,
    GenerationStore,
    ScriptedModel,
    building,
    index,
    interrupt_after,
    kept_in,
    memberships,
    plant_older_orphan,
    published,
    visible_summaries,
    write_corpus,
    write_layer,
    write_two_store_base,
)
from weft_index.payload import RaptorFacts
from weft_store.contract import LayerStatus

#: k of K: none, half, all but one.
_INTERRUPTED_AFTER = pytest.mark.parametrize(
    "done", [0, CLUSTERS // 2, CLUSTERS - 1], ids=["k=0", "k=K/2", "k=K-1"]
)


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    write_layer(tmp_path)
    monkeypatch.chdir(tmp_path)
    ScriptedModel.reset()
    CountingEmbedder.summaries = 0
    return write_corpus(tmp_path)


async def _uninterrupted_tree(corpus: Path) -> set[frozenset[str]]:
    """The clusters an uninterrupted build over `corpus` summarises, then every counter reset."""
    reference = GenerationStore()
    await index(reference, corpus)
    tree = {frozenset(str(i) for i in m) for m in memberships(visible_summaries(reference))}
    ScriptedModel.reset()
    CountingEmbedder.summaries = 0
    return tree


def _tree(store: GenerationStore) -> set[frozenset[str]]:
    return {frozenset(str(i) for i in m) for m in memberships(visible_summaries(store))}


def _rerun(store: GenerationStore) -> None:
    ScriptedModel.calls = []
    ScriptedModel.label = "second"
    ScriptedModel.watched = store
    ScriptedModel.building_seen = []


@pytest.mark.parametrize("done", [CLUSTERS // 2, CLUSTERS - 1], ids=["k=K/2", "k=K-1"])
async def test_each_summary_is_kept_in_the_building_generation_as_it_completes(
    corpus: Path, done: int
) -> None:
    # Arrange
    store = GenerationStore()

    # Act
    raised = await interrupt_after(store, corpus, summaries=done)

    # Assert — the cancellation propagated, and what finished before it is held, unpublished.
    assert isinstance(raised, asyncio.CancelledError)
    (open_generation,) = building(store)
    assert len(kept_in(store, open_generation.id)) == done
    assert visible_summaries(store) == []


@_INTERRUPTED_AFTER
async def test_a_rerun_under_the_same_identity_pays_only_for_the_clusters_not_yet_summarised(
    corpus: Path, done: int
) -> None:
    # Arrange
    expected = await _uninterrupted_tree(corpus)
    store = GenerationStore()
    raised = await interrupt_after(store, corpus, summaries=done)
    assert isinstance(raised, asyncio.CancelledError)
    _rerun(store)

    # Act
    await index(store, corpus)

    # Assert
    assert len(ScriptedModel.calls) == CLUSTERS - done
    assert building(store) == []
    assert len(published(store)) == 1
    assert _tree(store) == expected
    assert len(visible_summaries(store)) == CLUSTERS
    assert {r.layers[0].status for r in store.state.records.values()} == {LayerStatus.ACTIVE}


@_INTERRUPTED_AFTER
async def test_a_resumed_build_adopts_the_open_generation_rather_than_opening_another(
    corpus: Path, done: int
) -> None:
    # Arrange
    store = GenerationStore()
    await interrupt_after(store, corpus, summaries=done)
    _rerun(store)

    # Act
    await index(store, corpus)

    # Assert — every model call of the rerun saw one generation building, never two.
    assert ScriptedModel.building_seen
    assert set(ScriptedModel.building_seen) == {1}


@_INTERRUPTED_AFTER
async def test_a_resumed_tree_states_the_whole_runs_tally_and_each_summary_was_embedded_once(
    corpus: Path, done: int
) -> None:
    # Arrange
    store = GenerationStore()
    await interrupt_after(store, corpus, summaries=done)
    _rerun(store)

    # Act
    await index(store, corpus)

    # Assert — a kept summary carries the tally of the run that finished it, not a placeholder,
    # and no summary was embedded twice across the two runs.
    tallies = {
        (facts.clusters_found, facts.clusters_summarised)
        for node in visible_summaries(store)
        if (facts := node.ext_as(RaptorFacts)) is not None
    }
    assert tallies == {(CLUSTERS, CLUSTERS)}
    assert CountingEmbedder.summaries == CLUSTERS
    assert all(node.embedding is not None for node in visible_summaries(store))


@_INTERRUPTED_AFTER
async def test_a_rerun_whose_prompt_moved_never_adopts_and_pays_for_every_cluster(
    corpus: Path, tmp_path: Path, done: int
) -> None:
    # Arrange
    expected = await _uninterrupted_tree(corpus)
    store = GenerationStore()
    await interrupt_after(store, corpus, summaries=done)
    write_layer(tmp_path, prompt=TERSE_PROMPT)
    _rerun(store)

    # Act
    await index(store, corpus)

    # Assert — nothing the first prompt wrote is published, and the old generation is gone
    # before the first summary of the new one is paid for.
    assert len(ScriptedModel.calls) == CLUSTERS
    assert set(ScriptedModel.building_seen) == {1}
    assert building(store) == []
    assert _tree(store) == expected
    assert len(visible_summaries(store)) == CLUSTERS
    assert all("in the second run" in node.content for node in visible_summaries(store))


async def test_a_rerun_under_another_model_pays_for_every_cluster_and_publishes_none_of_the_old(
    corpus: Path,
) -> None:
    # Arrange — `[llm.roles]` is not part of the layer document, so only the key sees the model.
    expected = await _uninterrupted_tree(corpus)
    store = GenerationStore()
    await interrupt_after(store, corpus, summaries=CLUSTERS - 1, model="m1")
    _rerun(store)

    # Act
    await index(store, corpus, model="m2")

    # Assert
    assert ScriptedModel.calls == ["m2"] * CLUSTERS
    assert set(ScriptedModel.building_seen) == {1}
    assert building(store) == []
    assert _tree(store) == expected
    assert len(visible_summaries(store)) == CLUSTERS
    assert all("written by m2" in node.content for node in visible_summaries(store))


async def test_two_orphaned_building_generations_leave_one_after_adoption_and_none_after_publish(
    corpus: Path,
) -> None:
    # Arrange — an interrupted build, and an older orphan beside it.
    store = GenerationStore()
    await interrupt_after(store, corpus, summaries=CLUSTERS // 2)
    plant_older_orphan(store)
    assert len(building(store)) == 2
    _rerun(store)

    # Act
    await index(store, corpus)

    # Assert — the newer one, holding the kept summaries, is the one adopted.
    assert set(ScriptedModel.building_seen) == {1}
    assert len(ScriptedModel.calls) == CLUSTERS - CLUSTERS // 2
    assert building(store) == []
    assert len(published(store)) == 1


async def test_a_source_added_after_the_interruption_publishes_only_the_tree_over_every_source(
    corpus: Path,
) -> None:
    # Arrange — a new leaf moves the clusters, so some kept summaries answer clusters that no
    # longer exist; they must not reach the published tree.
    store = GenerationStore()
    await interrupt_after(store, corpus, summaries=CLUSTERS - 1)
    (corpus / "doc8.txt").write_text("document number 8 arrives after the interruption.")
    expected = await _uninterrupted_tree(corpus)
    _rerun(store)

    # Act
    await index(store, corpus)

    # Assert
    assert set(ScriptedModel.building_seen) == {1}
    assert building(store) == []
    assert _tree(store) == expected
    assert len(visible_summaries(store)) == len(expected)


async def test_a_resumed_build_over_two_stores_adopts_each_stores_own_generation(
    corpus: Path, tmp_path: Path
) -> None:
    # Arrange — R43.11: every store holds its own generation, so each must be adopted.
    write_two_store_base(tmp_path)
    primary, second = GenerationStore(), GenerationStore()
    await interrupt_after(primary, corpus, summaries=CLUSTERS // 2, second=second)
    _rerun(primary)

    # Act
    await index(primary, corpus, second=second)

    # Assert
    assert len(ScriptedModel.calls) == CLUSTERS - CLUSTERS // 2
    for store in (primary, second):
        assert building(store) == []
        assert len(published(store)) == 1
        assert len(visible_summaries(store)) == CLUSTERS
