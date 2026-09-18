"""`anchor-promote` — ledger **40.3**: dense's own pool, reordered by the anchors a passage holds.

Phase 39 fused a lexical list per anchor with dense and fitted its weight to about zero. This is the
weight→∞ limit restricted to dense's own candidates: a passage holding more of the question's
anchors moves above one holding fewer, dense's order decides within a tie, and a question with no
anchor leaves the ranking exactly as it arrived. The matcher and the promotion are public because
Phase 40's ceiling and its oracle control call the same two functions this stage does.
"""

from __future__ import annotations

from typing import ClassVar

import pytest
from pydantic import ValidationError

from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import ExtModel, MediaType, Node, Produced
from weft_kernel.registry import Registry
from weft_retrieve import Reranker, Settings, register
from weft_retrieve.anchor_promote import (
    NAME,
    AnchorBranch,
    AnchorPromote,
    AnchorPromoteConfig,
    AnchorPromotion,
    anchor_contained,
    promote,
)
from weft_retrieve.payload import Passage, Query, Ranking
from weft_store import Scored


class _Upstream(ExtModel):
    """An entry an earlier stage left on the ranking, which promotion must carry untouched."""

    __namespace__: ClassVar[str] = "test-upstream"
    __schema_version__: ClassVar[str] = "1"

    said: str


def _ctx() -> Context:
    return Context(tenant_id="t", run_id="r", trace_id="tr", locale="en")


def _hit(words: str, score: float, rank: int) -> Passage:
    node = Node.synthetic(content=words, media_type=MediaType.TEXT, reason="fixture")
    return Passage(scored=Scored(value=node, score=score), rank=rank, retrieved_by="vector-top-k")


def _ranking(question: str, *hits: Passage) -> Ranking:
    return Ranking(
        origin=Query(text=question),
        hits=hits,
        contributors=("vector-top-k",),
        note="an upstream note",
        ext={_Upstream.__namespace__: _Upstream(said="kept")},
    )


@pytest.mark.parametrize(
    ("anchor", "text", "contained"),
    [
        ("WRH123", "the wrh123 controller", True),
        ("WRH-123", "the WRH123 controller", True),
        ("WRH123", "the WRH-123 controller", True),
        ("WRH12", "the WRH123 controller", False),
        ("7.5.0.2", "fixed in version 7.5.0.2 of the agent", True),
        ("7.5.0.2", "fixed in version 7.5.0.21 of the agent", False),
        ("SQL30081N", "error sql30081n on connect", True),
        ("CVE-2019-4102", "see cve-2019-4102.", True),
    ],
)
def test_an_anchor_is_contained_only_as_whole_tokens_whatever_its_case_or_hyphens(
    anchor: str, text: str, contained: bool
) -> None:
    assert anchor_contained(anchor, text) is contained


def test_promotion_moves_passages_holding_more_anchors_up_and_keeps_dense_order_within_a_tie() -> (
    None
):
    # Arrange — dense order n0..n3; n2 holds both anchors, n1 and n3 one each, n0 none.
    hits = (
        _hit("nothing here", 0.9, 0),
        _hit("mentions A1 only", 0.8, 1),
        _hit("mentions A1 and B2", 0.7, 2),
        _hit("mentions B2 only", 0.6, 3),
    )

    # Act
    promoted, count = promote(hits, ("A1", "B2"))

    # Assert
    assert [p.node.content for p in promoted] == [
        "mentions A1 and B2",
        "mentions A1 only",
        "mentions B2 only",
        "nothing here",
    ]
    assert [p.score for p in promoted] == pytest.approx([6.7, 3.8, 3.6, 0.9])
    assert [p.rank for p in promoted] == [0, 1, 2, 3]
    assert count == 3


async def test_a_question_with_no_anchor_leaves_the_ranking_exactly_as_it_arrived() -> None:
    # Arrange
    payload = _ranking(
        "what is a good controller for rc boats", _hit("a", 0.9, 0), _hit("b", 0.4, 1)
    )

    # Act
    outcome = await AnchorPromote().run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    ranking = outcome.value
    record = ranking.ext[AnchorPromotion.__namespace__]
    assert isinstance(record, AnchorPromotion)
    assert record.branch is AnchorBranch.NO_ANCHOR
    assert ranking.model_copy(update={"ext": payload.ext}) == payload
    assert ranking.ext[_Upstream.__namespace__] == payload.ext[_Upstream.__namespace__]


async def test_anchors_no_passage_holds_leave_the_order_and_say_so() -> None:
    # Arrange
    payload = _ranking("what does WRH123 mean", _hit("a", 0.9, 0), _hit("b", 0.4, 1))

    # Act
    outcome = await AnchorPromote().run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    record = outcome.value.ext[AnchorPromotion.__namespace__]
    assert isinstance(record, AnchorPromotion)
    assert (record.branch, record.anchors, record.hits_promoted) == (
        AnchorBranch.NONE_CONTAINED,
        ("WRH123",),
        0,
    )
    assert [p.node.content for p in outcome.value.hits] == ["a", "b"]


async def test_a_passage_holding_the_questions_anchor_moves_above_those_that_do_not() -> None:
    # Arrange
    payload = _ranking(
        "what does WRH123 mean",
        _hit("the STX58 manual", 0.9, 0),
        _hit("another page", 0.8, 1),
        _hit("WRH123 is the reset code", 0.5, 2),
    )

    # Act
    outcome = await AnchorPromote().run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    ranking = outcome.value
    assert [p.node.content for p in ranking.hits][0] == "WRH123 is the reset code"
    record = ranking.ext[AnchorPromotion.__namespace__]
    assert isinstance(record, AnchorPromotion)
    assert (record.branch, record.hits_promoted) == (AnchorBranch.PROMOTED, 1)
    assert ranking.ext[_Upstream.__namespace__] == payload.ext[_Upstream.__namespace__]
    assert (ranking.origin, ranking.contributors, ranking.note) == (
        payload.origin,
        payload.contributors,
        payload.note,
    )


@pytest.mark.parametrize(
    ("record", "sentence"),
    [
        (
            AnchorPromotion(branch=AnchorBranch.NO_ANCHOR, anchors=(), hits_promoted=0),
            "branch: no-anchor, ranking unchanged",
        ),
        (
            AnchorPromotion(branch=AnchorBranch.NONE_CONTAINED, anchors=("X1",), hits_promoted=0),
            "branch: none-contained, anchors 1, ranking unchanged",
        ),
        (
            AnchorPromotion(branch=AnchorBranch.PROMOTED, anchors=("X1", "Y2"), hits_promoted=3),
            "branch: promoted, anchors 2, hits promoted 3",
        ),
    ],
)
def test_the_record_says_in_one_sentence_which_branch_ran(
    record: AnchorPromotion, sentence: str
) -> None:
    assert record.explained() == sentence
    assert record.produced_by == NAME


def test_it_is_registered_as_a_reranker_that_calls_no_model_and_offers_no_model_extractor() -> None:
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-rag")
    register(registrar, Settings())
    registrar.commit()

    # Act
    plugin = registry.entry(Reranker, NAME).factory(None)

    # Assert
    assert isinstance(plugin, AnchorPromote)
    assert AnchorPromote.cost_bound == (0, 0)
    assert isinstance(getattr(AnchorPromote, "score_semantics", None), str)
    with pytest.raises(ValidationError):
        AnchorPromoteConfig.model_validate({"method": "model"})
