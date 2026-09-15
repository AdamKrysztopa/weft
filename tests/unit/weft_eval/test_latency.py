"""Query latency percentiles per rung — ledger task **33.8**.

*The Tail at Scale* (Dean & Barroso, CACM 56(2), 2013) is why a mean is not enough: "Temporary high
latency episodes which are unimportant in moderate size systems may come to dominate overall service
performance at large scale." Task 33.7 persisted each question's seconds; this module reads them.

**Nearest rank, and withheld when the rank is the last sample** — the owner's Q4, 2026-09-15. The
value at rank ⌈q·n⌉ of the sorted samples is a real observation, never an interpolation. When that
rank is n, the "percentile" is the maximum under another name, so it is reported as not aggregated
with its sample count. With the 66 shipped questions p99 is withheld and p95 is not. That is
arithmetic, not a borrowed constant, and it is never a gate (`01` rejected duration thresholds as
machine-dependent).
"""

from weft_eval.latency import LatencySummary, latency_summary, nearest_rank
from weft_eval.run_record import NotAggregated, PerQuestionSeconds, QuestionKey
from weft_kernel.payload import Produced


def test_a_percentile_is_the_observation_at_its_nearest_rank() -> None:
    # Arrange
    samples = [float(value) for value in range(1, 101)]

    # Act
    p95 = nearest_rank(samples, 0.95)

    # Assert
    assert p95 == Produced(value=95.0)


def test_the_order_samples_arrive_in_does_not_move_a_percentile() -> None:
    # Arrange
    samples = [float(value) for value in reversed(range(1, 101))]

    # Act / Assert
    assert nearest_rank(samples, 0.5) == Produced(value=50.0)


def test_a_percentile_whose_rank_is_the_last_sample_is_withheld_with_the_count() -> None:
    # Arrange — 66 samples, the shipped question set's size.
    samples = [float(value) for value in range(66)]

    # Act
    p99 = nearest_rank(samples, 0.99)
    p95 = nearest_rank(samples, 0.95)

    # Assert
    assert isinstance(p99, NotAggregated)
    assert "66" in p99.reason
    assert isinstance(p95, Produced)


def test_no_samples_is_not_aggregated_rather_than_zero() -> None:
    # Act
    result = nearest_rank([], 0.5)

    # Assert
    assert isinstance(result, NotAggregated)


def test_a_summary_reads_p50_p95_p99_off_a_records_question_seconds() -> None:
    # Arrange
    seconds = PerQuestionSeconds(
        keyed_by=QuestionKey.POSITION,
        seconds={str(index): float(index + 1) for index in range(200)},
    )

    # Act
    summary = latency_summary(seconds)

    # Assert
    assert summary == LatencySummary(
        samples=200,
        p50=Produced(value=100.0),
        p95=Produced(value=190.0),
        p99=Produced(value=198.0),
    )


def test_a_record_that_measured_nothing_has_no_summary() -> None:
    # Act / Assert
    assert latency_summary(None) is None
