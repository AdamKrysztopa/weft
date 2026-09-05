"""Unit tests for `weft_retrieve.fusion`.

Mirrors `packages/weft-rag/src/weft_retrieve/fusion.py`. Task **2.7**: "fusion and
reranking are composable plugins a third party can retune, not a fixed ladder." This module
covers the fusion half — the happy path (one list unwrapped into a `Ranking` that keeps the
question, the hits and a contributor label naming what fed it), the edge case (no lists at
all, which is `no-retrieval`'s own output and must arrive as an empty `Ranking` rather than
as `NothingToProduce`), the error case (two lists, which this plugin refuses by name rather
than picking a winner), the contributor label shape every later fuser shares, and a drive
through `weft_kernel.seam.wrap` — the one path a registered plugin is actually called
through in production.

`out.origin == in.origin` is asserted here rather than assumed: `QuerySet.origin` is a
contract term nothing in the kernel checks, so task 2.4's ledger line leaves the obligation
with each query-path plugin, and `tests/unit/weft_retrieve/test_vector_top_k.py` carries the
same assertion for the retriever one seam earlier.
"""

import pytest

from weft_kernel.context import Context
from weft_kernel.payload import ExtModel, Failed, MediaType, Node, Produced
from weft_kernel.seam import wrap
from weft_retrieve.boolean import NAME as BOOLEAN_RETRIEVAL_NAME
from weft_retrieve.boolean import BooleanPlan, BoolExpr, BoolOp, index_leaves
from weft_retrieve.contract import Fuser
from weft_retrieve.fusion import (
    BOOLEAN_COMBINE_NAME,
    NAME,
    RRF_NAME,
    BooleanCombine,
    BooleanCombineConfig,
    EmptyConjunction,
    ReciprocalRankFusion,
    ReciprocalRankFusionConfig,
    SingleList,
    contributor_label,
)
from weft_retrieve.payload import (
    Candidates,
    Channel,
    Passage,
    Query,
    QueryOrigin,
    RankedList,
    Ranking,
)
from weft_store.contract import Scored


class _Note(ExtModel):
    """A carrier extension, to prove `ext` survives the arity reduction — G5's mechanism is
    the settled answer to "a strategy needs to pass something along", and a fuser that drops
    it would kill every such pass-along at the one seam every query path crosses."""

    __namespace__ = "test-fusion"
    __schema_version__ = "1.0.0"

    text: str


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _passage(content: str, score: float, rank: int) -> Passage:
    node = Node.synthetic(content=content, media_type=MediaType.TEXT, reason="fixture")
    return Passage(scored=Scored(value=node, score=score), rank=rank, retrieved_by="vector-top-k")


async def test_one_list_is_unwrapped_into_a_ranking_that_names_what_fed_it() -> None:
    # Arrange
    asked = Query(text="why is mRMR preferred to plain relevance ranking?")
    hits = (_passage("a", 0.9, 0), _passage("b", 0.5, 1))
    payload = Candidates(
        origin=asked,
        lists=(
            RankedList(
                query=asked, retriever="vector-top-k", channel=Channel.VECTOR.value, hits=hits
            ),
        ),
        ext={_Note.__namespace__: _Note(text="carried")},
    )

    # Act
    outcome = await SingleList().run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    ranking: Ranking = outcome.value
    assert ranking.origin == asked
    assert ranking.hits == hits
    assert ranking.contributors == ("vector-top-k:vector",)
    assert ranking.ext == payload.ext


async def test_no_lists_at_all_fuses_to_an_empty_ranking_rather_than_stopping_the_pipeline() -> (
    None
):
    # Arrange — `no-retrieval` produces exactly this, and the emptiness rule on every contract
    # in `weft_retrieve.contract` says a stage that ran and found nothing answers `Produced`
    # carrying an empty collection. `NothingToProduce` here would mean no `Answer` at all.
    asked = Query(text="a question nothing was ever asked about")
    payload = Candidates(origin=asked, lists=())

    # Act
    outcome = await SingleList().run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value == Ranking(origin=asked, hits=(), contributors=())


async def test_two_lists_are_refused_by_name_rather_than_silently_reduced() -> None:
    # Arrange — the whole point of the name: this plugin cannot merge, and the operator is
    # told which registered plugin can. Choosing one list, concatenating both or interleaving
    # them are three different answers, and picking one silently is the fallback the project
    # rules forbid.
    asked = Query(text="two arms searched, and nothing here can weigh them against each other")
    payload = Candidates(
        origin=asked,
        lists=(
            RankedList(query=asked, retriever="hybrid", channel=Channel.VECTOR.value),
            RankedList(query=asked, retriever="hybrid", channel=Channel.TEXT.value),
        ),
    )

    # Act
    outcome = await SingleList().run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Failed)
    assert "reciprocal-rank-fusion" in outcome.reason
    assert "2" in outcome.reason


@pytest.mark.parametrize(
    ("retriever", "channel", "expected"),
    [
        ("vector-top-k", "vector", "vector-top-k:vector"),
        ("no-retrieval", "", "no-retrieval"),
    ],
)
def test_a_contributor_label_names_the_retriever_and_the_arm_when_there_is_one(
    retriever: str, channel: str, expected: str
) -> None:
    # Arrange
    asked = Query(text="what fed this ranking?")
    ranked = RankedList(query=asked, retriever=retriever, channel=channel)

    # Act / Assert — one spelling, shared by every fuser, so `weights` keyed on it in ledger
    # 2.18 cannot be keyed on a second one written a task later.
    assert contributor_label(ranked) == expected


async def test_driving_single_list_through_the_seam_produces_a_ranking() -> None:
    """Fitness function 7(b) against the one path a registered plugin is actually called
    through in production — `weft_kernel.seam.wrap`, not a direct method call a registered
    instance never receives."""
    # Arrange
    asked = Query(text="does this pass through the seam?")
    payload = Candidates(
        origin=asked,
        lists=(
            RankedList(
                query=asked,
                retriever="vector-top-k",
                channel=Channel.VECTOR.value,
                hits=(_passage("hit", 0.8, 0),),
            ),
        ),
    )
    fuser = SingleList()
    wrapped = wrap(fuser.run, distribution="weft-retrieve", contract="Fuser", plugin=NAME)

    # Act
    outcome = await wrapped(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert [passage.node.content for passage in outcome.value.hits] == ["hit"]
    assert isinstance(fuser, Fuser)


def test_the_declared_cost_bound_is_zero_zero() -> None:
    # Act / Assert — this plugin resolves no service at all: `run` takes what it was handed
    # and returns it in one shape or refuses. An operator reads the bound before running it.
    assert SingleList.cost_bound == (0, 0)


async def test_reciprocal_rank_fusion_merges_two_lists_by_the_2009_formula() -> None:
    # Arrange — the happy path: Cormack, Clarke & Büttcher's own formula, `k=60` by default,
    # weight `1.0` for a contributor named in no `weights` mapping. Doc "b" is found by both
    # lists and must outrank doc "a" and doc "c", each found by only one.
    asked = Query(text="why is mRMR preferred to plain relevance ranking?")
    vector_list = RankedList(
        query=asked,
        retriever="hybrid",
        channel=Channel.VECTOR.value,
        hits=(_passage("a", 0.9, 0), _passage("b", 0.7, 1)),
    )
    text_list = RankedList(
        query=asked,
        retriever="hybrid",
        channel=Channel.TEXT.value,
        hits=(_passage("b", 0.8, 0), _passage("c", 0.6, 1)),
    )
    payload = Candidates(origin=asked, lists=(vector_list, text_list))

    # Act
    outcome = await ReciprocalRankFusion().run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    ranking: Ranking = outcome.value
    assert ranking.origin == asked
    assert [passage.node.content for passage in ranking.hits] == ["b", "a", "c"]
    assert ranking.hits[0].score == pytest.approx(1 / 62 + 1 / 61)
    assert ranking.hits[1].score == pytest.approx(1 / 61)
    assert ranking.hits[2].score == pytest.approx(1 / 62)
    assert [passage.rank for passage in ranking.hits] == [0, 1, 2]
    # "b" ties at rank 0 in both lists' own local rank-0 slot is not the case here — it is
    # rank 1 in vector_list and rank 0 in text_list, so the smaller (better) rank wins the
    # `retrieved_by` label, naming which arm actually found it best.
    assert ranking.hits[0].retrieved_by == "hybrid:text"
    assert ranking.contributors == ("hybrid:vector", "hybrid:text")


async def test_reciprocal_rank_fusion_weights_and_top_k_are_honoured() -> None:
    # Arrange — the edge case: two named knobs away from their defaults at once. A heavily
    # down-weighted list cannot out-vote the other, and `top_k` truncates the fused result —
    # both configuration, per requirement 6's second clause, never a number in `run`.
    asked = Query(text="what causes overfitting?")
    strong = RankedList(
        query=asked,
        retriever="vector-top-k",
        channel=Channel.VECTOR.value,
        hits=(_passage("x", 0.9, 0),),
    )
    weak = RankedList(
        query=asked,
        retriever="vector-top-k",
        channel=Channel.TEXT.value,
        hits=(_passage("y", 0.9, 0),),
    )
    payload = Candidates(origin=asked, lists=(strong, weak))

    # Act
    outcome = await ReciprocalRankFusion(
        ReciprocalRankFusionConfig(weights={"vector-top-k:text": 0.01}, top_k=1)
    ).run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    ranking: Ranking = outcome.value
    assert [passage.node.content for passage in ranking.hits] == ["x"]


async def test_reciprocal_rank_fusion_serves_hybrid_and_fan_out_from_the_same_accumulation() -> (
    None
):
    # Arrange — task 2.18's own claim, checked directly rather than by prose: one list pair
    # sharing a contributor label (`vector-top-k:vector` twice, the fan-out shape — the same
    # retriever and channel, two different queries) and one list carrying a distinct label
    # (`vector-top-k:text`, the hybrid shape) are handed to the *same* `run`, with no branch
    # anywhere asking which kind of multiplicity produced them.
    asked = Query(text="what limits catalyst lifetime?")
    variant = Query(text="what accelerates catalyst deactivation?", produced_by="multi-query")
    fanout_one = RankedList(
        query=asked,
        retriever="vector-top-k",
        channel=Channel.VECTOR.value,
        hits=(_passage("shared", 0.9, 0),),
    )
    fanout_two = RankedList(
        query=variant,
        retriever="vector-top-k",
        channel=Channel.VECTOR.value,
        hits=(_passage("shared", 0.8, 0),),
    )
    hybrid_arm = RankedList(
        query=asked,
        retriever="vector-top-k",
        channel=Channel.TEXT.value,
        hits=(_passage("other", 0.7, 0),),
    )
    payload = Candidates(origin=asked, lists=(fanout_one, fanout_two, hybrid_arm))

    # Act
    outcome = await ReciprocalRankFusion().run(payload, _ctx())

    # Assert — "shared" was found twice at rank 0 (once per fan-out list) and outscores
    # "other", found once; the two same-label lists contribute one entry to `contributors`,
    # not two, because they are one retriever/arm's worth of evidence, repeated over queries.
    assert isinstance(outcome, Produced)
    ranking: Ranking = outcome.value
    assert [passage.node.content for passage in ranking.hits] == ["shared", "other"]
    assert ranking.hits[0].score == pytest.approx(2 / 61)
    assert ranking.contributors == ("vector-top-k:vector", "vector-top-k:text")


async def test_reciprocal_rank_fusion_no_lists_fuses_to_an_empty_ranking() -> None:
    # Arrange — the edge case shared with `single-list`: `no-retrieval`'s own output must
    # arrive as an empty `Ranking`, never `NothingToProduce`.
    asked = Query(text="a question nothing was ever asked about")
    payload = Candidates(origin=asked, lists=())

    # Act
    outcome = await ReciprocalRankFusion().run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value == Ranking(origin=asked, hits=(), contributors=())


def test_reciprocal_rank_fusion_k_must_be_at_least_one() -> None:
    # Act / Assert — the error case: `k=0` would divide by a rank alone, silently changing
    # the formula's own shape rather than refusing a value Cormack et al. never intended.
    with pytest.raises(ValueError, match="k"):
        ReciprocalRankFusionConfig(k=0)


async def test_reciprocal_rank_fusion_carries_ext_across_the_arity_reduction() -> None:
    # Arrange — the same `ext`-survives assertion `single-list`'s own test makes, for the
    # identical reason: G5's namespaced extension is the settled answer to "a strategy needs
    # to pass something along."
    asked = Query(text="does ext survive two lists, not just one?")
    payload = Candidates(
        origin=asked,
        lists=(
            RankedList(
                query=asked,
                retriever="hybrid",
                channel=Channel.VECTOR.value,
                hits=(_passage("a", 0.9, 0),),
            ),
            RankedList(
                query=asked,
                retriever="hybrid",
                channel=Channel.TEXT.value,
                hits=(_passage("b", 0.8, 0),),
            ),
        ),
        ext={_Note.__namespace__: _Note(text="carried")},
    )

    # Act
    outcome = await ReciprocalRankFusion().run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.ext == payload.ext


async def test_driving_reciprocal_rank_fusion_through_the_seam_produces_a_ranking() -> None:
    """Fitness function 7(b) against the one path a registered plugin is actually called
    through in production — `weft_kernel.seam.wrap`, not a direct method call a registered
    instance never receives."""
    # Arrange
    asked = Query(text="does this pass through the seam?")
    payload = Candidates(
        origin=asked,
        lists=(
            RankedList(
                query=asked,
                retriever="hybrid",
                channel=Channel.VECTOR.value,
                hits=(_passage("a", 0.9, 0),),
            ),
            RankedList(
                query=asked,
                retriever="hybrid",
                channel=Channel.TEXT.value,
                hits=(_passage("b", 0.8, 0),),
            ),
        ),
    )
    fuser = ReciprocalRankFusion()
    wrapped = wrap(fuser.run, distribution="weft-retrieve", contract="Fuser", plugin=RRF_NAME)

    # Act
    outcome = await wrapped(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert [passage.node.content for passage in outcome.value.hits] == ["a", "b"]
    assert isinstance(fuser, Fuser)


def test_reciprocal_rank_fusion_config_defaults_match_the_design_records_table() -> None:
    # Act / Assert — requirement 6's second clause, read off the config model.
    config = ReciprocalRankFusionConfig()
    assert config.k == 60
    assert config.weights == {}
    assert config.top_k is None
    assert ReciprocalRankFusion.config_model is ReciprocalRankFusionConfig


def test_reciprocal_rank_fusion_declared_cost_bound_is_zero_zero() -> None:
    # Act / Assert — pure computation: no service is ever resolved.
    assert ReciprocalRankFusion.cost_bound == (0, 0)


# --- `BooleanCombine`: set algebra over `Node.id`, driven by a `BooleanPlan`. ---------------


def _leaf_query(term: str, index: int, producer: str = BOOLEAN_RETRIEVAL_NAME) -> Query:
    return Query(text=term, origin=QueryOrigin.DERIVED, produced_by=f"{producer}#{index}")


def _leaf_list(
    term: str, index: int, hits: tuple[Passage, ...], producer: str = BOOLEAN_RETRIEVAL_NAME
) -> RankedList:
    return RankedList(
        query=_leaf_query(term, index, producer),
        retriever="vector-top-k",
        channel=Channel.VECTOR.value,
        hits=hits,
    )


def _plan(expr: BoolExpr, producer: str = BOOLEAN_RETRIEVAL_NAME) -> dict[str, BooleanPlan]:
    return {BooleanPlan.__namespace__: BooleanPlan(expr=index_leaves(expr), producer=producer)}


def _term(t: str) -> BoolExpr:
    return BoolExpr(op=BoolOp.TERM, term=t)


async def test_and_intersects_two_leaves_by_node_id() -> None:
    # Arrange — the happy path: "cats AND dogs", where only one retrieved document was found
    # by both leaves.
    asked = Query(text="cats AND dogs")
    shared = _passage("shared", 0.9, 0)
    only_cats = _passage("only cats", 0.8, 1)
    only_dogs = _passage("only dogs", 0.7, 1)
    lists = (
        _leaf_list("cats", 0, (shared, only_cats)),
        _leaf_list("dogs", 1, (shared, only_dogs)),
    )
    payload = Candidates(
        origin=asked,
        lists=lists,
        ext=_plan(BoolExpr(op=BoolOp.AND, clauses=(_term("cats"), _term("dogs")))),
    )

    # Act
    outcome = await BooleanCombine().run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    ranking: Ranking = outcome.value
    assert ranking.origin == asked
    assert [passage.node.content for passage in ranking.hits] == ["shared"]
    assert ranking.note == ""


async def test_an_empty_conjunction_is_reported_never_silently_turned_into_a_union() -> None:
    # Arrange — the edge case ledger 2.23's own second clause is about: "cats AND dogs" where
    # the two leaves found disjoint documents. Silently returning the union here would report
    # a match neither leaf actually supports; `on_empty_conjunction` defaults to `report`,
    # which must produce a genuinely empty `Ranking`, never the two documents unioned.
    asked = Query(text="cats AND dogs")
    lists = (
        _leaf_list("cats", 0, (_passage("only cats", 0.9, 0),)),
        _leaf_list("dogs", 1, (_passage("only dogs", 0.9, 0),)),
    )
    payload = Candidates(
        origin=asked,
        lists=lists,
        ext=_plan(BoolExpr(op=BoolOp.AND, clauses=(_term("cats"), _term("dogs")))),
    )

    # Act
    outcome = await BooleanCombine().run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    ranking: Ranking = outcome.value
    assert ranking.hits == ()
    assert "cats" in ranking.note
    assert "dogs" in ranking.note


async def test_an_empty_conjunction_fails_the_stage_when_configured_to() -> None:
    # Arrange — the error case: `on_empty_conjunction=fail` stops the pipeline instead of
    # answering with no evidence.
    asked = Query(text="cats AND dogs")
    lists = (
        _leaf_list("cats", 0, (_passage("only cats", 0.9, 0),)),
        _leaf_list("dogs", 1, (_passage("only dogs", 0.9, 0),)),
    )
    payload = Candidates(
        origin=asked,
        lists=lists,
        ext=_plan(BoolExpr(op=BoolOp.AND, clauses=(_term("cats"), _term("dogs")))),
    )
    combiner = BooleanCombine(BooleanCombineConfig(on_empty_conjunction=EmptyConjunction.FAIL))

    # Act
    outcome = await combiner.run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Failed)
    assert "cats" in outcome.reason and "dogs" in outcome.reason


async def test_or_unions_two_leaves() -> None:
    # Arrange
    asked = Query(text="cats OR dogs")
    lists = (
        _leaf_list("cats", 0, (_passage("a", 0.9, 0),)),
        _leaf_list("dogs", 1, (_passage("b", 0.8, 0),)),
    )
    payload = Candidates(
        origin=asked,
        lists=lists,
        ext=_plan(BoolExpr(op=BoolOp.OR, clauses=(_term("cats"), _term("dogs")))),
    )

    # Act
    outcome = await BooleanCombine().run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert {passage.node.content for passage in outcome.value.hits} == {"a", "b"}


async def test_and_not_subtracts_the_negated_leaf_from_the_positive_one() -> None:
    # Arrange — "cats AND NOT dogs": well-defined without a corpus-wide complement, because
    # the subtraction is bounded by what "cats" itself retrieved.
    asked = Query(text="cats AND NOT dogs")
    shared = _passage("shared", 0.9, 0)
    only_cats = _passage("only cats", 0.8, 1)
    lists = (
        _leaf_list("cats", 0, (shared, only_cats)),
        _leaf_list("dogs", 1, (shared,)),
    )
    expr = BoolExpr(
        op=BoolOp.AND, clauses=(_term("cats"), BoolExpr(op=BoolOp.NOT, clauses=(_term("dogs"),)))
    )
    payload = Candidates(origin=asked, lists=lists, ext=_plan(expr))

    # Act
    outcome = await BooleanCombine().run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert [passage.node.content for passage in outcome.value.hits] == ["only cats"]


async def test_not_as_a_direct_operand_of_or_is_refused_by_name() -> None:
    # Arrange — "cats OR NOT dogs" has no bounded universe to complement "dogs" against.
    asked = Query(text="cats OR NOT dogs")
    lists = (
        _leaf_list("cats", 0, (_passage("a", 0.9, 0),)),
        _leaf_list("dogs", 1, (_passage("b", 0.8, 0),)),
    )
    expr = BoolExpr(
        op=BoolOp.OR, clauses=(_term("cats"), BoolExpr(op=BoolOp.NOT, clauses=(_term("dogs"),)))
    )
    payload = Candidates(origin=asked, lists=lists, ext=_plan(expr))

    # Act
    outcome = await BooleanCombine().run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Failed)
    assert "not" in outcome.reason


async def test_a_candidates_with_no_boolean_plan_is_refused_by_name() -> None:
    # Arrange — the defensive check: `requires` refuses this at resolution, but a direct
    # call (as this test makes) bypasses that, and the failure must still name what is
    # missing rather than raise a bare `KeyError`.
    asked = Query(text="cats AND dogs")
    payload = Candidates(origin=asked, lists=(_leaf_list("cats", 0, ()),))

    # Act
    outcome = await BooleanCombine().run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Failed)
    assert "BooleanPlan" in outcome.reason
    assert BOOLEAN_RETRIEVAL_NAME in outcome.reason


async def test_a_second_query_transform_is_attributed_by_its_own_registered_name() -> None:
    # Arrange — repair for the reviewer finding on `packages/weft-rag/src/
    # weft_retrieve/fusion.py`: leaf attribution must key off the producer `BooleanPlan`
    # itself names, not off `weft_retrieve.boolean`'s own hardcoded `NAME`. A second, honestly
    # implemented `QueryTransform` (any third party providing `BooleanPlan`) stamps
    # `produced_by` and `BooleanPlan.producer` with its *own* registered name — here
    # "cheap-boolean-parser", never "boolean-retrieval" — and `boolean-combine` must still
    # intersect its leaves correctly rather than silently attributing nothing.
    asked = Query(text="cats AND dogs")
    other_producer = "cheap-boolean-parser"
    shared = _passage("shared", 0.9, 0)
    only_cats = _passage("only cats", 0.8, 1)
    lists = (
        _leaf_list("cats", 0, (shared, only_cats), producer=other_producer),
        _leaf_list("dogs", 1, (shared,), producer=other_producer),
    )
    payload = Candidates(
        origin=asked,
        lists=lists,
        ext=_plan(
            BoolExpr(op=BoolOp.AND, clauses=(_term("cats"), _term("dogs"))),
            producer=other_producer,
        ),
    )

    # Act
    outcome = await BooleanCombine().run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert [passage.node.content for passage in outcome.value.hits] == ["shared"]


async def test_boolean_combine_fails_loudly_when_no_list_can_be_attributed_to_any_leaf() -> None:
    # Arrange — the defensive net: a `BooleanPlan` names a producer that does not match the
    # `produced_by` stamp any retrieved list actually carries (a misconfigured or buggy
    # `QueryTransform`). This must not silently fall through to an empty-conjunction note that
    # blames a disjoint intersection that was never actually evaluated — it must fail, naming
    # the mismatch, per rule 5 ("an unknown name fails loudly").
    asked = Query(text="cats AND dogs")
    lists = (
        _leaf_list("cats", 0, (_passage("only cats", 0.9, 0),), producer="stray-transform"),
        _leaf_list("dogs", 1, (_passage("only dogs", 0.9, 0),), producer="stray-transform"),
    )
    payload = Candidates(
        origin=asked,
        lists=lists,
        ext=_plan(
            BoolExpr(op=BoolOp.AND, clauses=(_term("cats"), _term("dogs"))),
            producer=BOOLEAN_RETRIEVAL_NAME,
        ),
    )

    # Act
    outcome = await BooleanCombine().run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Failed)
    assert BOOLEAN_RETRIEVAL_NAME in outcome.reason
    assert "attribute" in outcome.reason


async def test_driving_boolean_combine_through_the_seam_produces_a_ranking() -> None:
    """Fitness function 7(b) against the one path a registered plugin is actually called
    through in production — `weft_kernel.seam.wrap`, not a direct method call a registered
    instance never receives."""
    # Arrange
    asked = Query(text="cats AND dogs")
    shared = _passage("shared", 0.9, 0)
    lists = (_leaf_list("cats", 0, (shared,)), _leaf_list("dogs", 1, (shared,)))
    payload = Candidates(
        origin=asked,
        lists=lists,
        ext=_plan(BoolExpr(op=BoolOp.AND, clauses=(_term("cats"), _term("dogs")))),
    )
    combiner = BooleanCombine()
    wrapped = wrap(
        combiner.run, distribution="weft-retrieve", contract="Fuser", plugin=BOOLEAN_COMBINE_NAME
    )

    # Act
    outcome = await wrapped(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert [passage.node.content for passage in outcome.value.hits] == ["shared"]
    assert isinstance(combiner, Fuser)


def test_boolean_combine_config_defaults_and_cost_bound() -> None:
    # Act / Assert
    assert BooleanCombineConfig().on_empty_conjunction is EmptyConjunction.REPORT
    assert BooleanCombine.cost_bound == (0, 0)
    assert BooleanCombine.requires == (BooleanPlan,)
