"""Unit tests for `eval/check_baseline.py` — the judgement nobody chose a number for.

Mirrors `eval/check_baseline.py`. Every case here is one sentence of `docs/09-release.md` §4.3
made executable: a later run reproduces the baseline when every metric falls inside the interval
the baseline's own repetitions spanned, a deterministic baseline admits no drift at all, and a
comparison against a run that measured something else is refused rather than scored.
"""

import pytest
from check_baseline import IncomparableRunsError, regressions
from metrics import MetricRecord
from run_baseline import BaselineRun, CorpusRecord, DistributionRecord, StageRecord


def _run(*, metrics: tuple[MetricRecord, ...], corpus: str = "a" * 64) -> BaselineRun:
    return BaselineRun(
        recorded_at="2026-08-17T12:00:00+00:00",
        corpus=CorpusRecord(
            name="mrmr-v1", corpus_id=corpus, tiers=("fetch",), documents=("doc-a",)
        ),
        reproducible=True,
        questions=("q001",),
        repeats=len(metrics[0].values),
        retrieval_depth=10,
        pipeline=(StageRecord(stage="embed", plugin="openai"),),
        pipeline_sha256="b" * 64,
        models={"embed": "openai:text-embedding-3-small"},
        distributions=(DistributionRecord(name="weft-cli", version="0.1.0", status="active"),),
        wall_clock_seconds=1.0,
        metrics=metrics,
    )


def _metric(name: str, values: tuple[float, ...]) -> MetricRecord:
    return MetricRecord(
        metric=name,
        depth=10,
        values=values,
        mean=sum(values) / len(values),
        low=min(values),
        high=max(values),
        n_scored=len(values),
        n_excluded=0,
    )


def test_a_later_run_inside_the_interval_reproduces_the_baseline() -> None:
    # Arrange
    baseline = _run(metrics=(_metric("quote-recall@10", (0.40, 0.50)),))
    later = _run(metrics=(_metric("quote-recall@10", (0.44, 0.46)),))

    # Act
    failures = regressions(baseline, later)

    # Assert
    assert failures == ()


def test_a_later_run_outside_the_interval_is_named_with_both_bounds() -> None:
    # The message has to carry the interval, because the reader's next question is always "by
    # how much" — and a tolerance that is derived rather than declared is only readable if the
    # bounds travel with the failure.
    # Arrange
    baseline = _run(metrics=(_metric("quote-recall@10", (0.40, 0.50)),))
    later = _run(metrics=(_metric("quote-recall@10", (0.30, 0.30)),))

    # Act
    (failure,) = regressions(baseline, later)

    # Assert
    assert "quote-recall@10" in failure
    assert "0.4" in failure and "0.5" in failure


def test_a_zero_width_interval_admits_no_drift_at_all() -> None:
    # `09` §4.3 names this and calls it correct: "a system that is deterministic records a
    # zero-width interval and admits no drift at all, which is correct and strict."
    # Arrange
    baseline = _run(metrics=(_metric("document-mrr@10", (0.75, 0.75)),))
    later = _run(metrics=(_metric("document-mrr@10", (0.75, 0.7500001)),))

    # Act
    failures = regressions(baseline, later)

    # Assert
    assert len(failures) == 1


def test_a_metric_the_later_run_stopped_measuring_is_a_failure_not_a_silence() -> None:
    # A suite that quietly compares only the metrics both runs happen to have shrinks to the
    # ones that still pass. The baseline decides what must be reproduced.
    # Arrange
    baseline = _run(
        metrics=(_metric("quote-recall@10", (0.4, 0.5)), _metric("quote-ndcg@10", (0.3, 0.4)))
    )
    later = _run(metrics=(_metric("quote-recall@10", (0.45, 0.45)),))

    # Act
    (failure,) = regressions(baseline, later)

    # Assert
    assert "quote-ndcg@10" in failure
    assert "did not measure it" in failure


def test_a_run_over_a_different_corpus_is_refused_rather_than_compared() -> None:
    # V3's failure clause: an improvement "reported against a baseline from a different corpus,
    # pipeline or model version". A number that came out of that comparison would look ordinary,
    # which is what makes refusing better than scoring.
    # Arrange
    baseline = _run(metrics=(_metric("quote-recall@10", (0.4, 0.5)),))
    later = _run(metrics=(_metric("quote-recall@10", (0.45, 0.45)),), corpus="c" * 64)

    # Act / Assert
    with pytest.raises(IncomparableRunsError, match="corpus"):
        regressions(baseline, later)
