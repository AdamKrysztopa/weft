"""`normalized-score-fusion` — ledger task **21.5**.

Mirrors the second score fuser in `packages/weft-rag/src/weft_retrieve/fusion.py`. `12-roadmap.md`
§5g: RRF combines *rankings* and discards the gaps between scores, which is the mechanism `L19.8`
measured — `21.2`'s normalisation sweep moved `precision@5` and `recall@5` not at all, because the
value it varied was consumed as an ordering. This fuser is the arm of the crossed experiment at
`21.9` that can see that field.

**The dimension under test is the score gap, and the fixture isolates it by making RRF blind to the
answer.** `_two_arms_rrf_cannot_separate` builds two arms in which `X` and `Y` swap rank — `X` first
then second, `Y` second then first — so their reciprocal-rank sums are **exactly equal** and RRF's
ordering between them falls to `dict` insertion order. Their *scores* are not close: `Y` loses the
first arm by `0.01` and wins the second by `0.90`. A fuser that reads scores must put `Y` first; a
fuser that reads ranks cannot tell.

**The control is the real `ReciprocalRankFusion`, not a literal.**
`test_the_fixture_is_one_rrf_genuinely_cannot_separate` runs the shipped RRF over the same
`Candidates` and asserts it scores `X` and `Y` equally. That is what makes the next test
non-vacuous: without it, `normalized-score-fusion` ranking `Y` first would be equally consistent
with it having reimplemented RRF, and `L5.6`'s one-source shape would be hiding in the fixture
rather than in a comparison.

**What this fuser is not.** It is **not** `tm2c2`. The review this phase builds from is explicit:
faithful TM2C2 normalizes over the candidate *union* and assumes both arms can score that union,
which needs a score-by-ID completion path neither `TextSearch` nor `VectorSearch` promises — *"do
not claim to implement TM2C2 by applying min-max independently to two truncated lists and inventing
zeros."* So the name is descriptive, and a node an arm never returned contributes **nothing** from
that arm rather than a fabricated zero. `10` §2.1 rule 4 as a build constraint.

**Every degenerate case has a stated convention, because the review requires one:** *"define
deterministic handling of ties, zero range, empty legitimate lists and missing candidates. Reject
non-finite scores."* Each has a test below, and the zero-range convention — every hit in an arm
whose scores are all equal normalises to `1.0` — is asserted rather than left to the arithmetic,
because `0.0` is the other plausible reading and it would silently erase that arm's whole
contribution.
"""

import math

import pytest

from weft_kernel.context import Context
from weft_kernel.payload import Failed, MediaType, Node, Produced
from weft_retrieve.fusion import (
    NORMALIZED_SCORE_FUSION_NAME,
    FusionEvidence,
    NormalizedScoreFusion,
    NormalizedScoreFusionConfig,
    ReciprocalRankFusion,
    fusion_evidence,
)
from weft_retrieve.payload import Candidates, Channel, Passage, Query, RankedList
from weft_store.contract import Scored


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _node(content: str) -> Node:
    return Node.synthetic(content=content, media_type=MediaType.TEXT, reason="fixture")


_X = _node("the passage the dense arm is sure about")
_Y = _node("the passage the lexical arm is sure about")
_W = _node("the passage neither arm rates")

_ASKED = Query(text="which passage do the two arms disagree about?")


def _arm(retriever: str, channel: str, scored: tuple[tuple[Node, float], ...]) -> RankedList:
    return RankedList(
        query=_ASKED,
        retriever=retriever,
        channel=channel,
        hits=tuple(
            Passage(scored=Scored(value=node, score=score), rank=rank, retrieved_by=retriever)
            for rank, (node, score) in enumerate(scored)
        ),
    )


def _two_arms_rrf_cannot_separate() -> Candidates:
    """`X` and `Y` swap rank between the arms, so their reciprocal-rank sums are identical.

    Arm one: `X` 1.00, `Y` 0.99, `W` 0.00 — `Y` loses by a hundredth.
    Arm two: `Y` 1.00, `X` 0.10, `W` 0.00 — `X` loses by nine tenths.

    Min-max per arm makes that asymmetry visible: `X` contributes `1.0 + 0.1`, `Y` contributes
    `0.99 + 1.0`. Reciprocal rank makes it invisible: both are `1/61 + 1/62`.
    """
    return Candidates(
        origin=_ASKED,
        lists=(
            _arm("hybrid", Channel.VECTOR.value, ((_X, 1.00), (_Y, 0.99), (_W, 0.00))),
            _arm("hybrid", Channel.TEXT.value, ((_Y, 1.00), (_X, 0.10), (_W, 0.00))),
        ),
    )


async def test_the_fixture_is_one_rrf_genuinely_cannot_separate() -> None:
    """The control, run through the shipped `ReciprocalRankFusion` rather than from a literal.

    The control, run through the shipped `ReciprocalRankFusion` rather than asserted from a
    literal. If this ever stops holding, the test below is no longer measuring what it claims.
    """
    # Arrange / Act
    outcome = await ReciprocalRankFusion().run(_two_arms_rrf_cannot_separate(), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    by_id = {hit.node.id: hit.score for hit in outcome.value.hits}
    assert by_id[_X.id] == pytest.approx(by_id[_Y.id]), (
        "the fixture is supposed to tie under reciprocal rank — if it does not, the score "
        "dimension is no longer isolated and the next test proves nothing"
    )


async def test_the_arm_that_is_sure_wins_because_its_score_gap_is_read() -> None:
    # Arrange
    fuser = NormalizedScoreFusion(NormalizedScoreFusionConfig())

    # Act
    outcome = await fuser.run(_two_arms_rrf_cannot_separate(), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    order = [hit.node.id for hit in outcome.value.hits]
    assert order[0] == _Y.id, "Y wins its arm outright and loses the other by a hundredth"
    assert order == [_Y.id, _X.id, _W.id]
    by_id = {hit.node.id: hit.score for hit in outcome.value.hits}
    # 0.99 + 1.0 against 1.0 + 0.1 — the arithmetic the name describes, stated so a change to
    # the normalisation is a change to this number rather than a silent re-ranking.
    assert by_id[_Y.id] == pytest.approx(1.99)
    assert by_id[_X.id] == pytest.approx(1.10)


async def test_an_arm_that_never_returned_a_node_contributes_nothing_for_it() -> None:
    """Not a zero — nothing.

    `X` appears in one arm only, so its fused score is that arm's normalised value and no more; a
    fabricated `0.0` from the other arm would be identical here but would make `tm2c2`'s claim,
    which this plugin does not implement.
    """
    # Arrange
    payload = Candidates(
        origin=_ASKED,
        lists=(
            _arm("hybrid", Channel.VECTOR.value, ((_X, 1.00), (_W, 0.00))),
            _arm("hybrid", Channel.TEXT.value, ((_Y, 1.00), (_W, 0.50))),
        ),
    )

    # Act
    outcome = await NormalizedScoreFusion(NormalizedScoreFusionConfig()).run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    by_id = {hit.node.id: hit.score for hit in outcome.value.hits}
    assert by_id[_X.id] == pytest.approx(1.0)
    assert by_id[_Y.id] == pytest.approx(1.0)
    # W is last in both arms, so it normalises to the floor of each range.
    assert by_id[_W.id] == pytest.approx(0.0)


async def test_an_arm_whose_scores_are_all_equal_contributes_its_whole_weight() -> None:
    """The zero-range convention, asserted because the alternative is silent.

    With `max == min` every hit is simultaneously the arm's best and worst; mapping them all to
    `1.0` says the arm ranked them equally, and mapping them to `0.0` would delete the arm from the
    fusion without saying so.
    """
    # Arrange
    payload = Candidates(
        origin=_ASKED,
        lists=(
            _arm("flat", "", ((_X, 0.5), (_Y, 0.5))),
            _arm("hybrid", Channel.TEXT.value, ((_Y, 1.0), (_X, 0.0))),
        ),
    )

    # Act
    outcome = await NormalizedScoreFusion(NormalizedScoreFusionConfig()).run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    by_id = {hit.node.id: hit.score for hit in outcome.value.hits}
    assert by_id[_Y.id] == pytest.approx(2.0)
    assert by_id[_X.id] == pytest.approx(1.0)


async def test_weights_are_applied_by_contributor_label() -> None:
    """The same spelling `Ranking.contributors` and `reciprocal-rank-fusion`'s `weights` use.

    The same spelling `Ranking.contributors` and `reciprocal-rank-fusion`'s own `weights`
    use, so a document's block cannot name a key no fuser produces without being noticed.
    """
    # Arrange
    config = NormalizedScoreFusionConfig(weights={"hybrid:text": 0.5})

    # Act
    outcome = await NormalizedScoreFusion(config).run(_two_arms_rrf_cannot_separate(), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    by_id = {hit.node.id: hit.score for hit in outcome.value.hits}
    # Y: 0.99 from the unweighted arm + 1.0 * 0.5; X: 1.0 + 0.1 * 0.5.
    assert by_id[_Y.id] == pytest.approx(1.49)
    assert by_id[_X.id] == pytest.approx(1.05)


async def test_a_non_finite_score_is_refused_by_name_rather_than_propagated() -> None:
    """An `inf` or a `nan` poisons a min-max range and then every comparison downstream.

    An `inf` or a `nan` poisons a min-max range and then every comparison downstream, and
    `nan` does it silently: it compares false against everything, so a sort puts it wherever the
    algorithm happened to look. The refusal names the plugin and the arm.
    """
    # Arrange
    payload = Candidates(
        origin=_ASKED,
        lists=(_arm("hybrid", Channel.VECTOR.value, ((_X, math.inf), (_Y, 0.5))),),
    )

    # Act
    outcome = await NormalizedScoreFusion(NormalizedScoreFusionConfig()).run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Failed)
    assert "hybrid:vector" in outcome.reason
    assert NORMALIZED_SCORE_FUSION_NAME in outcome.reason


async def test_no_lists_at_all_fuses_to_an_empty_ranking_rather_than_stopping_the_pipeline() -> (
    None
):
    """`no-retrieval`'s own legitimate output is `Produced` carrying an empty `Ranking`.

    `no-retrieval`'s own legitimate output, and the emptiness rule every contract in this pack
    states: `Produced` carrying an empty `Ranking`, never `NothingToProduce`.
    """
    # Arrange / Act
    outcome = await NormalizedScoreFusion(NormalizedScoreFusionConfig()).run(
        Candidates(origin=_ASKED), _ctx()
    )

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.hits == ()
    assert outcome.value.contributors == ()


async def test_an_empty_but_legitimate_list_is_a_contributor_that_contributed_nothing() -> None:
    """`RankedList(hits=())` says an arm looked and found nothing.

    A different fact from the arm not existing, per `Candidates`' own docstring. It stays named in
    `contributors`.
    """
    # Arrange
    payload = Candidates(
        origin=_ASKED,
        lists=(
            _arm("hybrid", Channel.VECTOR.value, ((_X, 1.0), (_Y, 0.0))),
            _arm("hybrid", Channel.TEXT.value, ()),
        ),
    )

    # Act
    outcome = await NormalizedScoreFusion(NormalizedScoreFusionConfig()).run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.contributors == ("hybrid:vector", "hybrid:text")
    assert [hit.node.id for hit in outcome.value.hits] == [_X.id, _Y.id]


async def test_it_records_per_arm_evidence_the_way_every_score_fuser_does() -> None:
    """Task `21.4`'s mechanism, which this fuser is the first real reason for."""
    # Arrange / Act
    outcome = await NormalizedScoreFusion(NormalizedScoreFusionConfig()).run(
        _two_arms_rrf_cannot_separate(), _ctx()
    )

    # Assert
    assert isinstance(outcome, Produced)
    evidence = fusion_evidence(outcome.value)
    assert evidence is not None
    assert evidence.fuser == NORMALIZED_SCORE_FUSION_NAME
    text = evidence.arm("hybrid:text")
    assert text is not None
    # The arm's own number, not the normalised one — evidence records what the arm said.
    assert text.score_for(_X.id) == pytest.approx(0.10)


async def test_top_k_bounds_what_survives_the_fusion() -> None:
    # Arrange
    config = NormalizedScoreFusionConfig(top_k=2)

    # Act
    outcome = await NormalizedScoreFusion(config).run(_two_arms_rrf_cannot_separate(), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert [hit.node.id for hit in outcome.value.hits] == [_Y.id, _X.id]


def test_the_name_is_descriptive_and_does_not_claim_tm2c2() -> None:
    """`10` §2.1 rule 4.

    Faithful TM2C2 normalizes over the candidate union with a valid theoretical lower bound and
    needs score completion for documents an arm did not return; this plugin normalizes two truncated
    lists and lets absence mean absence.
    """
    # Arrange
    doc = NormalizedScoreFusion.__doc__

    # Assert
    assert NORMALIZED_SCORE_FUSION_NAME == "normalized-score-fusion"
    assert doc is not None, "the class documents what it does and does not implement"
    assert "tm2c2" not in doc.lower()


def test_fusion_evidence_is_attached_under_its_own_namespace() -> None:
    """Guards task 21.4's decision from this task.

    A second fuser filing under `weft-retrieve` would evict a `CorrectiveTrace` exactly as the first
    one would have.
    """
    # Arrange / Act / Assert
    assert FusionEvidence.__namespace__ == "weft-retrieve-fusion"
