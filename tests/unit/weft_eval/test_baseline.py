"""Unit tests for `weft_eval.baseline` — what a number means before any of them is measured.

Mirrors `weft_eval.baseline`, which carried `eval/metrics.py` into the wheel at repair `R22.4a`.
The corpus, the store and the CLI are all absent here on purpose: every rule these tests pin is a
rule about *scoring*, not plumbing — a metric named `ndcg_at_10` computed over four candidates, a
failure scored as `0.0` and averaged into a mean, a ground truth the harness accepted and never
read (`docs/09-release.md` §4.2).
"""

from math import log2

import pytest

from weft_eval.baseline import (
    BaselineReport,
    BaselineScoringError,
    DepthTooShallowError,
    Excluded,
    ExclusionKind,
    Granularity,
    Hit,
    MetricRecord,
    Unscoreable,
    aggregate_repetitions,
    measure,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank_at_k,
)
from weft_eval.question_set import Difficulty, Kind, Question, Quote
from weft_eval.run_record import CorpusIdentity, RunRecord
from weft_kernel.errors import WeftError
from weft_kernel.resolution import ResolvedPipeline, ResolvedStage


def _question(**overrides: object) -> Question:
    """An answerable question quoting one span of one document, unless overridden."""
    fields: dict[str, object] = {
        "id": "q-test",
        "text": "why does mRMR subtract redundancy?",
        "language": "en",
        "kind": Kind.METHODOLOGICAL,
        "difficulty": Difficulty.EASY,
        "relevant_documents": ("doc-a",),
        "reference_answer": "Because relevance alone re-selects the same information.",
        "notes": "Written for this test.",
        "quote": (Quote(document="doc-a", page=1, text="subtracts the redundancy term"),),
    }
    return Question.model_validate(fields | overrides)


def _hit(rank: int, *, content: str = "unrelated passage", document: str = "doc-b") -> Hit:
    return Hit(
        rank=rank,
        node_id=f"node-{rank}",
        score=1.0 / rank,
        documents=(document,),
        content=content,
    )


def test_a_quote_found_inside_a_retrieved_passage_is_a_hit_at_its_rank() -> None:
    # The judgement is pinned to a literal span (`eval/check_questions.py`), so it resolves
    # against whatever unit the pipeline retrieved — which is what survives re-chunking, rather
    # than falling back to counting any chunk of the right paper as a hit.
    # Arrange
    question = _question()
    hits = (
        _hit(1),
        _hit(2, content="… which subtracts the redundancy term from …", document="doc-a"),
        _hit(3),
    )

    # Act
    scored = measure(question, hits, depths=(3,), retrieval_depth=3)

    # Assert
    assert not isinstance(scored, Unscoreable)
    values = scored.values
    assert values["quote-recall@3"] == 1.0
    assert values["quote-mrr@3"] == pytest.approx(0.5)
    assert values["quote-ndcg@3"] == pytest.approx((1 / log2(3)) / (1 / log2(2)))


def test_the_right_paper_without_the_span_scores_at_one_granularity_and_not_the_other() -> None:
    # Both families are reported and neither is a fallback for the other. A paper-level fallback
    # that counts any chunk of the right document as a hit pushes precision toward 1.0 for
    # answers the passage never actually supports — so here it scores where it is true (the
    # document was found) and nowhere else (the passage the answer rests on was not).
    # Arrange
    question = _question()
    hits = (_hit(1, content="a paragraph about something else", document="doc-a"),)

    # Act
    scored = measure(question, hits, depths=(1,), retrieval_depth=1)

    # Assert
    assert not isinstance(scored, Unscoreable)
    values = scored.values
    assert values["document-recall@1"] == 1.0
    assert values["quote-recall@1"] == 0.0


def test_an_unanswerable_question_is_unscoreable_rather_than_zero() -> None:
    # V4's rule at the door: "a failed metric is an error, never a zero". An unanswerable
    # question names no document and carries no quote, so every retrieval metric would compute
    # 0.0 over it and drag every mean toward zero for a question the corpus is *right* not to
    # answer. The return type is a different type, so no caller can average it by accident.
    # Arrange
    question = _question(
        kind=Kind.UNANSWERABLE, relevant_documents=(), quote=(), reference_answer="Not in corpus."
    )

    # Act
    scored = measure(question, (_hit(1),), depths=(1,), retrieval_depth=1)

    # Assert
    assert isinstance(scored, Unscoreable)
    assert scored.kind is ExclusionKind.NO_JUDGEMENT
    assert "unanswerable" in scored.detail


def test_a_metric_may_not_be_named_for_a_depth_deeper_than_was_asked_for() -> None:
    # A metric named `ndcg_at_10` computed over a list sliced to `similarity_top_k = 4`
    # (`docs/09-release.md` §4.2) reports a depth it never reached. V4 makes the rule explicit
    # — "the `k` in a metric's name equals the `k` it computed" — and this is that rule
    # refusing rather than documenting.
    # Arrange
    question = _question()

    # Act / Assert
    with pytest.raises(DepthTooShallowError, match="10.*5|5.*10"):
        measure(question, (_hit(1),), depths=(10,), retrieval_depth=5)


def test_a_short_result_list_is_not_a_shallow_retrieval() -> None:
    # The complement, and the reason the refusal above reads `retrieval_depth` rather than
    # `len(hits)`: a store holding three nodes answers a request for ten with three, and that
    # is a fact about the corpus, not a metric named for a depth nobody asked for.
    # Arrange
    question = _question()

    # Act
    scored = measure(question, (_hit(1),), depths=(10,), retrieval_depth=10)

    # Assert
    assert not isinstance(scored, Unscoreable)
    assert scored.values["quote-recall@10"] == 0.0


def test_ndcg_rewards_the_ordering_and_not_only_the_presence() -> None:
    # Arrange — the same two relevant units, first at the top and then at the bottom.
    top = (True, True, False, False)
    bottom = (False, False, True, True)

    # Act
    best = ndcg_at_k(top, k=4)
    worst = ndcg_at_k(bottom, k=4)

    # Assert
    assert best == 1.0
    assert 0.0 < worst < best


def test_recall_counts_judgements_and_mrr_counts_ranks() -> None:
    # Two different questions about one ranking, kept apart because a mean of them would answer
    # neither: recall asks how much of the ground truth was reached at all, MRR how soon the
    # first of it was.
    # Arrange
    first_rank_per_judgement = (2, None, 5)
    relevant_by_rank = (False, True, False, False, True)

    # Act / Assert
    assert recall_at_k(first_rank_per_judgement, k=3) == pytest.approx(1 / 3)
    assert recall_at_k(first_rank_per_judgement, k=5) == pytest.approx(2 / 3)
    assert reciprocal_rank_at_k(relevant_by_rank, k=5) == pytest.approx(0.5)
    assert reciprocal_rank_at_k(relevant_by_rank, k=1) == 0.0


def test_a_metric_record_refuses_a_single_repetition() -> None:
    # V3's own failure clause, as a refusal rather than a note: "the baseline was run once, in
    # which case it records no interval and no later run can be judged against it."
    # Act / Assert
    with pytest.raises(ValueError, match="repetition"):
        MetricRecord(
            metric="quote-recall@10",
            depth=10,
            values=(0.4,),
            mean=0.4,
            low=0.4,
            high=0.4,
            n_scored=95,
            n_excluded=0,
        )


def test_a_metric_record_refuses_bounds_its_own_values_do_not_span() -> None:
    # The interval is *derived* — min and max of what the repetitions produced. A file whose
    # bounds were widened by hand would make every later run reproduce the baseline, which is
    # the one way a derived tolerance can quietly become a chosen number.
    # Act / Assert
    with pytest.raises(ValueError, match="low"):
        MetricRecord(
            metric="quote-recall@10",
            depth=10,
            values=(0.4, 0.6),
            mean=0.5,
            low=0.0,
            high=1.0,
            n_scored=190,
            n_excluded=0,
        )


def test_the_granularity_of_every_metric_name_is_one_of_the_two_that_exist() -> None:
    # A name is what a later run is compared by, so a metric whose name did not say which
    # granularity it measured would be compared against the other one's interval.
    # Arrange
    question = _question()

    # Act
    scored = measure(question, (_hit(1),), depths=(1,), retrieval_depth=1)

    # Assert
    assert not isinstance(scored, Unscoreable)
    prefixes = {name.split("-", 1)[0] for name in scored.values}
    assert prefixes == {member.value for member in Granularity}


def test_a_scoring_refusal_is_a_weft_error_the_cli_can_render() -> None:
    # A command that scores a baseline reaches this refusal, and the CLI renders a `WeftError`
    # with its exit code and troubleshooting entry — anything else arrives as a traceback.
    # Arrange
    question = _question()

    # Act
    with pytest.raises(DepthTooShallowError) as caught:
        measure(question, (_hit(1),), depths=(10,), retrieval_depth=5)

    # Assert
    assert isinstance(caught.value, BaselineScoringError)
    assert isinstance(caught.value, WeftError)


def _record() -> RunRecord:
    return RunRecord(
        recorded_at="2026-08-20T12:00:00+00:00",
        resolved_pipeline=ResolvedPipeline(
            name="baseline",
            stages=(
                ResolvedStage(
                    id="embed",
                    contract="Embedder",
                    use="hash",
                    distribution="weft-rag",
                    provenance="baseline",
                ),
            ),
        ),
        corpus=CorpusIdentity(name="pl-wiki-v1", digest="a" * 64),
        model_versions={},
        active_distributions=("weft-rag",),
    )


def _report(**overrides: object) -> BaselineReport:
    """A written run with one metric, as a real pass would build it."""
    fields: dict[str, object] = {
        "recorded_at": "2026-08-20T12:00:00+00:00",
        "corpus_name": "pl-wiki-v1",
        "tiers": ("fetch",),
        "extractor": "text",
        "documents": ("doc-a",),
        "reproducible": True,
        "record": _record(),
        "questions": ("q001",),
        "repeats": 2,
        "retrieval_depth": 10,
        "wall_clock_seconds": 1.0,
        "metrics": (
            MetricRecord(
                metric="quote-recall@10",
                depth=10,
                values=(0.4, 0.6),
                mean=0.5,
                low=0.4,
                high=0.6,
                n_scored=2,
                n_excluded=0,
            ),
        ),
        "excluded": (),
    }
    return BaselineReport.model_validate(fields | overrides)


def test_the_recorded_interval_is_the_one_the_repetitions_spanned() -> None:
    # V3: "a later run reproduces the baseline when every metric falls inside that recorded
    # interval". Nobody chooses the bounds — they are min and max of what happened.
    # Arrange
    per_repetition = ({"quote-recall@5": 0.4}, {"quote-recall@5": 0.55}, {"quote-recall@5": 0.5})

    # Act
    (record,) = aggregate_repetitions(
        per_repetition, excluded=(), depths=(5,), scored_counts=(90, 90, 90)
    )

    # Assert
    assert (record.low, record.high) == (0.4, 0.55)
    assert record.mean == pytest.approx(0.48333333, abs=1e-6)
    assert record.depth == 5


def test_a_deterministic_pass_records_a_zero_width_interval_rather_than_room_to_move() -> None:
    # `docs/09-release.md` §4.3: a deterministic system "records a zero-width interval and admits
    # no drift at all". Widening it "to be safe" would be choosing the tolerance after all.
    # Arrange
    per_repetition = ({"document-mrr@10": 0.75}, {"document-mrr@10": 0.75})

    # Act
    (record,) = aggregate_repetitions(
        per_repetition, excluded=(), depths=(10,), scored_counts=(95, 95)
    )

    # Assert
    assert (record.low, record.high) == (0.75, 0.75)
    assert record.outside(0.7500001)


def test_a_metric_at_a_depth_the_run_did_not_ask_for_is_refused() -> None:
    # Arrange
    per_repetition = ({"quote-recall@7": 0.4}, {"quote-recall@7": 0.5})

    # Act
    with pytest.raises(BaselineScoringError) as caught:
        aggregate_repetitions(per_repetition, excluded=(), depths=(5, 10), scored_counts=(2, 2))

    # Assert
    assert "quote-recall@7" in str(caught.value)


def test_a_run_whose_exclusion_count_no_reason_backs_is_refused() -> None:
    # V4: "aggregates exclude errored metrics and report how many were excluded". The count is on
    # the metric and the reasons are on the run, and this is what stops the two drifting.
    # Act / Assert
    with pytest.raises(ValueError, match="n_excluded"):
        _report(
            metrics=(
                MetricRecord(
                    metric="quote-recall@10",
                    depth=10,
                    values=(0.4, 0.6),
                    mean=0.5,
                    low=0.4,
                    high=0.6,
                    n_scored=2,
                    n_excluded=4,
                ),
            )
        )


def test_a_run_whose_exclusion_count_its_reasons_back_is_accepted() -> None:
    # The complement, so the refusal above is not passing for the wrong reason.
    # Act
    report = _report(
        excluded=(
            Excluded(
                question_id="q001",
                repetition=1,
                kind=ExclusionKind.NO_JUDGEMENT,
                detail="unanswerable",
            ),
        ),
        metrics=(
            MetricRecord(
                metric="quote-recall@10",
                depth=10,
                values=(0.4, 0.6),
                mean=0.5,
                low=0.4,
                high=0.6,
                n_scored=2,
                n_excluded=1,
            ),
        ),
    )

    # Assert
    assert report.metrics[0].n_excluded == len(report.excluded) == 1
