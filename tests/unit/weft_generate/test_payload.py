"""Unit tests for `weft_generate.payload`.

Mirrors `packages/weft-generate/src/weft_generate/payload.py`. Covers task 2.9's
constructional half — an `Answer` carrying a citation nobody can follow back to a
passage is unconstructable, not merely discouraged — and the three-valued `stance` that
keeps "the corpus does not contain it" and "the engine could not decide" from collapsing
into one boolean.
"""

import pytest
from pydantic import ValidationError

from weft_generate.payload import Answer, AnswerStance, Citation
from weft_kernel.payload import MediaType, Node
from weft_retrieve.payload import Passage, Query
from weft_store.contract import Scored


def _labelled(label: str, body: str = "") -> Passage:
    """One packed passage. `body` varies so two fixtures are two *different* nodes.

    `Node.synthetic` derives the id from a content digest, so two passages built from the
    same words are one node under two labels — which would make the marker/node pairing
    below untestable by accident rather than by design.
    """
    node = Node.synthetic(
        content=body or f"a passage labelled {label}",
        media_type=MediaType.TEXT,
        reason="test fixture",
    )
    return Passage(
        scored=Scored(value=node, score=0.5), rank=0, retrieved_by="vector-top-k", label=label
    )


def test_an_answer_whose_citations_resolve_into_its_own_evidence_is_accepted() -> None:
    # Arrange
    used = _labelled("1")
    asked = Query(text="why is mRMR preferred?")

    # Act
    answer = Answer(
        origin=asked,
        text="Because redundancy is penalised [1].",
        citations=(
            Citation(marker="1", node_id=used.node.id, source_id=None, uri="file:///paper.pdf"),
        ),
        used=(used,),
        answered_by="cited-answer",
    )

    # Assert
    assert answer.stance is AnswerStance.ANSWERED
    assert answer.citations[0].marker == "1"


def test_a_citation_marking_a_passage_that_never_entered_the_prompt_is_unconstructable() -> None:
    # Arrange
    used = _labelled("1")
    asked = Query(text="why is mRMR preferred?")

    # Act / Assert
    with pytest.raises(ValidationError) as caught:
        Answer(
            origin=asked,
            text="Because redundancy is penalised [7].",
            citations=(
                Citation(marker="7", node_id=used.node.id, source_id=None, uri="file:///paper.pdf"),
            ),
            used=(used,),
            answered_by="cited-answer",
        )
    assert "7" in str(caught.value)


def test_a_citation_naming_a_node_that_never_entered_the_prompt_is_unconstructable() -> None:
    # Arrange
    used = _labelled("1")
    other = Node.synthetic(content="elsewhere", media_type=MediaType.TEXT, reason="test fixture")
    asked = Query(text="why is mRMR preferred?")

    # Act / Assert
    with pytest.raises(ValidationError):
        Answer(
            origin=asked,
            text="Because redundancy is penalised [1].",
            citations=(
                Citation(marker="1", node_id=other.id, source_id=None, uri="file:///other.pdf"),
            ),
            used=(used,),
            answered_by="cited-answer",
        )


def test_a_citation_whose_marker_and_node_name_two_different_passages_is_unconstructable() -> None:
    # Arrange — the renumbering case, and the single most likely generator bug: the marker
    # and the node id each resolve, but not to the same passage, so a reader who follows
    # footnote [1] lands on the passage the answer does *not* claim to rest on.
    first = _labelled("1")
    second = _labelled("2")
    asked = Query(text="why is mRMR preferred?")

    # Act / Assert
    with pytest.raises(ValidationError) as caught:
        Answer(
            origin=asked,
            text="Because redundancy is penalised [1].",
            citations=(Citation(marker="1", node_id=second.node.id),),
            used=(first, second),
            answered_by="cited-answer",
        )
    assert "1" in str(caught.value)


def test_two_used_passages_sharing_one_label_make_the_answer_unconstructable() -> None:
    # Arrange — a marker that resolves to two passages resolves to none of them.
    first = _labelled("1", body="the first passage")
    second = _labelled("1", body="the second passage")
    asked = Query(text="why is mRMR preferred?")

    # Act / Assert
    with pytest.raises(ValidationError) as caught:
        Answer(
            origin=asked,
            text="Because redundancy is penalised [1].",
            citations=(Citation(marker="1", node_id=first.node.id),),
            used=(first, second),
            answered_by="cited-answer",
        )
    assert "1" in str(caught.value)


def test_not_in_corpus_and_undetermined_are_different_facts() -> None:
    # Arrange
    asked = Query(text="what is the airspeed of an unladen swallow?")

    # Act
    absent = Answer(
        origin=asked, text="", stance=AnswerStance.NOT_IN_CORPUS, answered_by="cited-answer"
    )
    unknown = Answer(
        origin=asked, text="", stance=AnswerStance.UNDETERMINED, answered_by="cited-answer"
    )

    # Assert
    assert absent.stance is not unknown.stance
