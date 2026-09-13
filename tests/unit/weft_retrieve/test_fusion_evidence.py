"""Per-arm evidence on a fused `Ranking` — ledger task **21.4**.

Mirrors the new half of `packages/weft-rag/src/weft_retrieve/fusion.py`. `12-roadmap.md` §5g:
`L19.8` is not an argument for a better text arm, it is an argument that **the instrument cannot
currently see one**. Task `21.2` swept text-rank normalisation across three arms and returned
`precision@5` and `recall@5` identical to the digit, because `ReciprocalRankFusion` consumes each
arm as a *rank* and discards its scale — `hybrid._ranked` preserves every `Scored[Node]` in a
`Passage`, and the fuser then ignores those numbers. The raw-score seam already exists; what does
not is anything downstream that can still see what each arm actually said.

**The dimension these tests vary is per-arm score and per-arm rank for one node**, and the fixture
is built so that dimension is actually varied — `L11.42`/`L11.45`'s rule, which is about the
*inputs* rather than the assertions. Concretely: two arms, a node returned by **both** at a
different score *and* a different rank, and a node returned by **only one**. A fixture where the
arms agree would make every assertion below pass against an implementation that copied the fused
score into both arms, and a fixture with one arm cannot distinguish "which arm contributed what"
from "what the ranking says" at all.

**The `payload.ext` assertion is not incidental.** `ReciprocalRankFusion.run` ends
`Ranking(..., ext=payload.ext)`, and `weft_retrieve`'s three existing carrier models —
`BooleanPlan`, `CorrectiveTrace` and `IterativeRetrievalTrace` — all declare
`__namespace__ = "weft-retrieve"`. An `ExtMap` holds one model per namespace, so
evidence filed under that namespace would
**silently destroy** a `CorrectiveTrace` that a `corrective` retriever had put on the `Candidates`
one stage earlier. `test_evidence_does_not_evict_a_carrier_ext_in_the_neighbouring_namespace`
is that case, built with the real `CorrectiveTrace` rather than an invented stand-in (`L12.11`),
and it is why `FusionEvidence` owns `weft-retrieve-fusion` — the sub-namespace shape `weft-kg-fact`
and `weft-index-raptor` already use.

**Missingness is the central fidelity issue and it is asserted as such.** The review this phase
builds from is explicit: *"a document absent from an arm's returned top-k may have a substantial
score below its cutoff; absence is not a measured zero."* So `ArmEvidence.score_for` answers `None`
for a node that arm did not return, and the test asserts `is None` **and** `!= 0.0` — because an
implementation returning `0.0` would satisfy a bare falsiness check and would be the exact defect.
"""

import pytest

from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, Produced
from weft_retrieve.corrective import CorrectiveTrace
from weft_retrieve.fusion import (
    NAME,
    RRF_NAME,
    ArmEvidence,
    FusionEvidence,
    ReciprocalRankFusion,
    ReciprocalRankFusionConfig,
    SingleList,
    fusion_evidence,
)
from weft_retrieve.payload import (
    Candidates,
    Channel,
    Passage,
    Query,
    RankedList,
    Ranking,
)
from weft_store.contract import Scored


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _node(content: str) -> Node:
    return Node.synthetic(content=content, media_type=MediaType.TEXT, reason="fixture")


#: Three distinct nodes, built once so the same identity can appear in two arms — which is the
#: whole point of the fixture. Rebuilding a node per arm would give two ids for one document and
#: the "returned by both arms" case would silently become two "returned by one arm" cases.
_SHARED = _node("mRMR trades relevance against redundancy")
_VECTOR_ONLY = _node("a passage only the dense arm found")
_TEXT_ONLY = _node("a passage only the lexical arm found")

_ASKED = Query(text="why is mRMR preferred to plain relevance ranking?")


def _arm(retriever: str, channel: str, scored: tuple[tuple[Node, float], ...]) -> RankedList:
    """One arm's list, ranked in the order given."""
    return RankedList(
        query=_ASKED,
        retriever=retriever,
        channel=channel,
        hits=tuple(
            Passage(scored=Scored(value=node, score=score), rank=rank, retrieved_by=retriever)
            for rank, (node, score) in enumerate(scored)
        ),
    )


def _two_arms() -> Candidates:
    """Two arms that disagree about the shared node, in both score and rank.

    Vector ranks it **first** at `0.91`; text ranks it **second** at `2.40`. Two different
    numbers on two incomparable scales, at two different positions — so an assertion about
    either cannot be satisfied by reading the other, and neither can be satisfied by the fused
    score, which is a third number again.
    """
    return Candidates(
        origin=_ASKED,
        lists=(
            _arm("hybrid", Channel.VECTOR.value, ((_SHARED, 0.91), (_VECTOR_ONLY, 0.42))),
            _arm("hybrid", Channel.TEXT.value, ((_TEXT_ONLY, 3.10), (_SHARED, 2.40))),
        ),
    )


async def test_each_arm_keeps_its_own_score_and_its_own_rank_for_a_node_both_returned() -> None:
    # Arrange
    fuser = ReciprocalRankFusion(ReciprocalRankFusionConfig())

    # Act
    outcome = await fuser.run(_two_arms(), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    evidence = fusion_evidence(outcome.value)
    assert evidence is not None, "a fuser that ran records what its arms said"
    assert evidence.fuser == RRF_NAME
    vector = evidence.arm("hybrid:vector")
    text = evidence.arm("hybrid:text")
    assert vector is not None and text is not None, "both arms are named"
    # The dimension under test: one node, two arms, two scores and two ranks.
    assert vector.score_for(_SHARED.id) == pytest.approx(0.91)
    assert text.score_for(_SHARED.id) == pytest.approx(2.40)
    assert vector.rank_for(_SHARED.id) == 0
    assert text.rank_for(_SHARED.id) == 1


async def test_a_node_one_arm_never_returned_is_absent_rather_than_scored_zero() -> None:
    """Absence is not a measured zero — the review's *missing scores are the central fidelity
    issue*. A `0.0` here would read as "this arm scored it lowest" when the truth is "this arm
    did not return it within its cutoff", and a normalized fuser that believed the first would
    invent a contribution nobody measured."""
    # Arrange
    fuser = ReciprocalRankFusion(ReciprocalRankFusionConfig())

    # Act
    outcome = await fuser.run(_two_arms(), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    evidence = fusion_evidence(outcome.value)
    assert evidence is not None
    text = evidence.arm("hybrid:text")
    assert text is not None
    missing = text.score_for(_VECTOR_ONLY.id)
    assert missing is None
    assert missing != 0.0, "absence must be distinguishable from a measured zero"


async def test_evidence_does_not_evict_a_carrier_ext_in_the_neighbouring_namespace() -> None:
    """`ReciprocalRankFusion.run` ends `Ranking(..., ext=payload.ext)`, and `CorrectiveTrace`
    already owns `weft-retrieve` on a `Candidates`. One model per namespace, so evidence filed
    under that name would destroy it — with nothing to see afterwards."""
    # Arrange
    trace = CorrectiveTrace(triggered=True, kept=2)
    payload = _two_arms().model_copy(update={"ext": {CorrectiveTrace.__namespace__: trace}})
    fuser = ReciprocalRankFusion(ReciprocalRankFusionConfig())

    # Act
    outcome = await fuser.run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    carried = outcome.value.ext[CorrectiveTrace.__namespace__]
    assert isinstance(carried, CorrectiveTrace)
    assert carried.kept == 2, "the corrective trace survived the fusion it passed through"
    assert fusion_evidence(outcome.value) is not None, "and the evidence is there too"
    assert FusionEvidence.__namespace__ != CorrectiveTrace.__namespace__


async def test_a_fuser_with_no_lists_records_that_it_looked() -> None:
    """`Candidates(lists=())` is `no-retrieval`'s own legitimate output. Evidence with `arms=()`
    says the fuser ran and had nothing to fuse; **no** evidence says nothing recorded it. Those
    are different facts and a reader of the `Ranking` can tell them apart."""
    # Arrange
    fuser = ReciprocalRankFusion(ReciprocalRankFusionConfig())

    # Act
    outcome = await fuser.run(Candidates(origin=_ASKED), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    evidence = fusion_evidence(outcome.value)
    assert evidence is not None
    assert evidence.arms == ()


async def test_single_list_records_its_one_arm_too() -> None:
    """The reader's question is about any fused `Ranking`, not only a fan-out's."""
    # Arrange
    payload = Candidates(
        origin=_ASKED,
        lists=(_arm("vector-top-k", Channel.VECTOR.value, ((_SHARED, 0.91),)),),
    )

    # Act
    outcome = await SingleList().run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    evidence = fusion_evidence(outcome.value)
    assert evidence is not None
    assert evidence.fuser == NAME
    arm = evidence.arm("vector-top-k:vector")
    assert arm is not None
    assert arm.score_for(_SHARED.id) == pytest.approx(0.91)


def test_a_ranking_nothing_recorded_evidence_on_reads_as_an_absence() -> None:
    """`None`, not an empty `FusionEvidence`. A `Ranking` from a fuser that records nothing —
    `boolean-combine`, which owns `BooleanPlan` for its own evidence — has not said its arms
    were empty; it has said nothing, and inventing an empty answer for it is the silent
    fallback this project refuses."""
    # Arrange
    ranking = Ranking(origin=_ASKED)

    # Act
    evidence = fusion_evidence(ranking)

    # Assert
    assert evidence is None


def test_an_arm_with_a_blank_label_is_refused() -> None:
    """`contributor_label` never produces one, so a blank arrives only from a caller that built
    an `ArmEvidence` by hand — and an arm no reader can name is one no fuser can weight, which is
    `Passage.retrieved_by`'s own argument one type down."""
    # Arrange / Act / Assert
    with pytest.raises(ValueError, match="label"):
        ArmEvidence(label="", hits=())
