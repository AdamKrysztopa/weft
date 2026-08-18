"""Unit tests for `weft_retrieve.payload`.

Mirrors `packages/weft-retrieve/src/weft_retrieve/payload.py`. Covers the three
invariants the design record singles out as load-bearing rather than decorative — a
`QuerySet` that always carries at least one query alongside the user's own untouched
words, a `Passage` that refuses to say nothing produced it, and the difference between
"a retriever looked and found nothing" and "nobody asked" being readable off the data
with no flag to check.
"""

import pytest
from pydantic import ValidationError

from weft_kernel.payload import MediaType, Node
from weft_retrieve.payload import (
    Candidates,
    Channel,
    Passage,
    Passages,
    Query,
    QueryOrigin,
    QuerySet,
    RankedList,
    Ranking,
)
from weft_store.contract import Scored


def _passage(rank: int = 0, label: str = "") -> Passage:
    node = Node.synthetic(
        content=f"a passage {rank}", media_type=MediaType.TEXT, reason="test fixture"
    )
    return Passage(
        scored=Scored(value=node, score=0.5), rank=rank, retrieved_by="vector-top-k", label=label
    )


def test_a_query_set_carries_the_users_own_words_and_what_will_be_retrieved_for() -> None:
    # Arrange
    asked = Query(text="why is mRMR preferred?")

    # Act
    queries = QuerySet(
        origin=asked,
        queries=(
            asked,
            Query(
                text="mRMR beats plain relevance",
                origin=QueryOrigin.DERIVED,
                produced_by="hyde",
                channels=(Channel.VECTOR,),
            ),
        ),
    )

    # Assert
    assert queries.origin.text == "why is mRMR preferred?"
    assert queries.queries[1].produced_by == "hyde"
    assert queries.queries[1].channels == (Channel.VECTOR,)


def test_a_query_set_with_no_queries_is_unconstructable() -> None:
    # Arrange
    asked = Query(text="why is mRMR preferred?")

    # Act / Assert
    with pytest.raises(ValidationError):
        QuerySet(origin=asked, queries=())


def test_a_passage_that_names_nobody_as_its_source_is_refused() -> None:
    # Arrange
    node = Node.synthetic(content="a passage", media_type=MediaType.TEXT, reason="test fixture")

    # Act / Assert
    with pytest.raises(ValidationError):
        Passage(scored=Scored(value=node, score=0.5), rank=0, retrieved_by="")


def test_a_passage_reads_its_node_and_score_off_scored_rather_than_restating_them() -> None:
    # Arrange
    passage = _passage()

    # Act / Assert
    assert passage.node is passage.scored.value
    assert passage.score == 0.5


def test_an_empty_ranked_list_and_no_ranked_list_at_all_are_different_facts() -> None:
    # Arrange
    asked = Query(text="why is mRMR preferred?")

    # Act
    looked_and_found_nothing = Candidates(
        origin=asked, lists=(RankedList(query=asked, retriever="vector-top-k"),)
    )
    never_asked = Candidates(origin=asked)

    # Assert — distinguishable by inspection, with no flag on either
    assert len(looked_and_found_nothing.lists) == 1
    assert looked_and_found_nothing.lists[0].hits == ()
    assert never_asked.lists == ()


def test_a_ranking_records_which_arms_fed_the_fusion() -> None:
    # Arrange
    asked = Query(text="why is mRMR preferred?")

    # Act
    fused = Ranking(
        origin=asked,
        hits=(_passage(0), _passage(1)),
        contributors=("vector-top-k:vector", "vector-top-k:text"),
    )

    # Assert
    assert fused.contributors == ("vector-top-k:vector", "vector-top-k:text")
    assert len(fused.hits) == 2


def test_a_packed_passage_that_carries_no_citation_label_is_unconstructable() -> None:
    # Arrange — a packer that forgets to label is the quiet half: no citation can ever
    # match a blank marker, so the generator's only valid output becomes `citations=()`.
    asked = Query(text="why is mRMR preferred?")

    # Act / Assert
    with pytest.raises(ValidationError) as caught:
        Passages(origin=asked, passages=(_passage(0, label="1"), _passage(1)))
    assert "label" in str(caught.value)


def test_two_packed_passages_sharing_one_label_are_unconstructable() -> None:
    # Arrange — `[1]` resolving to two different passages is a citation nobody can follow
    # back to *a* passage, which is exactly what task 2.9 makes unconstructable.
    asked = Query(text="why is mRMR preferred?")

    # Act / Assert
    with pytest.raises(ValidationError) as caught:
        Passages(origin=asked, passages=(_passage(0, label="1"), _passage(1, label="1")))
    assert "1" in str(caught.value)


def test_packed_passages_that_are_labelled_once_each_are_accepted() -> None:
    # Arrange
    asked = Query(text="why is mRMR preferred?")

    # Act
    packed = Passages(origin=asked, passages=(_passage(0, label="1"), _passage(1, label="2")))

    # Assert — and packing nothing is still a legitimate result, not a violation
    assert [passage.label for passage in packed.passages] == ["1", "2"]
    assert Passages(origin=asked).passages == ()


def test_an_arm_nobody_here_anticipated_can_be_named_targeted_and_reported() -> None:
    # Arrange — the third party of `01` requirement 2: a graph add-on whose store publishes
    # a traversal search and whose retriever queries it, installed with zero edits here.
    asked = Query(text="why is mRMR preferred?")
    for_the_graph = Query(
        text="mRMR :: redundancy", origin=QueryOrigin.DERIVED, channels=("graph",)
    )

    # Act
    produced = RankedList(query=for_the_graph, retriever="graph-walk", channel="graph")

    # Assert — and the two first-party names are still written verbatim off the enum
    assert produced.channel == "graph"
    assert for_the_graph.channels == ("graph",)
    assert RankedList(query=asked, retriever="vector-top-k", channel=Channel.VECTOR).channel == (
        Channel.VECTOR
    )


def test_a_blank_channel_name_is_refused_the_way_a_blank_provenance_is() -> None:
    # Act / Assert — an arm nothing can group, weight or target is the same defect as a
    # passage whose provenance is a blank string.
    with pytest.raises(ValidationError):
        Query(text="why is mRMR preferred?", channels=("",))


def test_every_carrier_is_frozen_and_refuses_an_unknown_field() -> None:
    # Arrange
    asked = Query(text="why is mRMR preferred?")
    fused = Ranking(origin=asked)

    # Act / Assert
    with pytest.raises(ValidationError):
        Ranking(origin=asked, bogus=1)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        fused.origin = asked  # type: ignore[misc]
