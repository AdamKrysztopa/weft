"""Unit tests for `weft_eval.aggregate`.

Mirrors `packages/weft-rag/src/weft_eval/aggregate.py`. Covers `aggregate()`'s exclusion-and-
dispersion shape (happy path, the `n == 1` edge where `stdev` is `None` rather than a claimed
`0.0`, and the all-excluded error case that refuses rather than averaging a fake zero) and
`aggregate_report()`'s R5 check — a report key that disagrees with the name a metric actually
computed, the shape a report key hardcoded to `'precision_at_k'` takes once `k` is
caller-configurable and varies, which a check against `PrecisionAtK.metric_name` alone would
never see because that property can already be correct at every call site while the published
key still lies.
"""

import pytest

from weft_eval.aggregate import (
    MismatchedMetricNameError,
    ReportedNameMismatchError,
    aggregate,
    aggregate_report,
)
from weft_eval.contract import MetricScore
from weft_kernel.payload import Failed, NothingToProduce, Produced


def _score(metric_name: str, value: float) -> Produced[MetricScore]:
    return Produced(value=MetricScore(metric_name=metric_name, value=value))


def test_aggregate_excludes_failures_and_reports_the_exclusion_count() -> None:
    # Arrange — five samples: three real scores, two failures a mean must not silently absorb.
    outcomes = [
        _score("precision@3", 1.0),
        _score("precision@3", 0.5),
        _score("precision@3", 0.0),
        Failed(reason="provider timed out"),
        Failed(reason="provider timed out"),
    ]

    # Act
    outcome = aggregate(outcomes)

    # Assert — the mean is over the 3 real scores only, and the 2 exclusions are a visible count,
    # not a fact a reader has to reconstruct by subtracting a success count from a total.
    assert isinstance(outcome, Produced)
    assert outcome.value.mean == pytest.approx(0.5)
    assert outcome.value.n == 3
    assert outcome.value.excluded == 2
    assert outcome.value.nothing_to_produce == 0
    assert outcome.value.stdev is not None


def test_a_single_observation_carries_no_stdev_rather_than_a_claimed_zero() -> None:
    # Arrange — one real score, nothing else. A standard deviation of one observation is not a
    # real quantity (`docs/build-ledger.md` 4.1's own reasoning for `MetricScore`, honoured here
    # for the aggregate); `0.0` would falsely claim a measured, zero spread.
    outcomes = [_score("precision@3", 0.8)]

    # Act
    outcome = aggregate(outcomes)

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.n == 1
    assert outcome.value.stdev is None
    # And the mean never stands alone — `n`/`stdev` are fields on the identical object, not a
    # bare float a caller could receive without them.
    assert outcome.value.mean == pytest.approx(0.8)


def test_all_failures_refuse_rather_than_averaging_a_fake_zero() -> None:
    # Arrange — every observation failed; there is nothing to average.
    outcomes = [Failed(reason="timeout"), Failed(reason="timeout")]

    # Act
    outcome = aggregate(outcomes)

    # Assert — `Failed`, not a `Produced[MetricAggregate]` with `mean=0.0`, which would repeat
    # the single-score accident (an error becoming an indistinguishable zero) one level up, at
    # the aggregate rather than the single score.
    assert isinstance(outcome, Failed)
    assert "2" in outcome.reason


def test_mixing_two_configurations_names_raises_rather_than_averaging_them_together() -> None:
    # Arrange — `precision@3` and `precision@7` are two different computations of the same
    # registered plugin at two different `k`; folding them into one aggregate would silently
    # average across configurations that were never meant to be compared.
    outcomes = [_score("precision@3", 1.0), _score("precision@7", 0.4)]

    # Act / Assert
    with pytest.raises(MismatchedMetricNameError):
        aggregate(outcomes)


def test_aggregate_report_accepts_a_key_that_matches_the_computed_name() -> None:
    # Arrange — the report key is exactly what the metric itself computed at k=7.
    groups = {"precision@7": [_score("precision@7", 1.0), _score("precision@7", 0.0)]}

    # Act
    report = aggregate_report(groups)

    # Assert
    outcome = report["precision@7"]
    assert isinstance(outcome, Produced)
    assert outcome.value.reported_name == "precision@7"


def test_aggregate_report_refuses_a_hardcoded_report_key_shape() -> None:
    # Arrange — the shape R5 exists to catch: a retrieval aggregate published under the literal
    # report key `'precision_at_k'` while the metric it ran was configured with a caller-supplied
    # `similarity_top_k` and actually computed `'precision@7'` for this run. A check against
    # `PrecisionAtK.metric_name` in isolation would never catch this — that property can already
    # be correct at every call site while the published key still lies. This is the check that
    # runs on the reported name a human actually reads, per R5.
    groups = {"precision_at_k": [_score("precision@7", 1.0), _score("precision@7", 0.0)]}

    # Act / Assert
    with pytest.raises(ReportedNameMismatchError) as excinfo:
        aggregate_report(groups)
    assert excinfo.value.report_key == "precision_at_k"
    assert excinfo.value.computed_name == "precision@7"


def test_aggregate_of_all_nothing_to_produce_is_an_absence_not_a_zero() -> None:
    # Arrange — every sample had an empty reference; nothing to score, and nothing failed either.
    outcomes = [
        NothingToProduce(reason="empty reference"),
        NothingToProduce(reason="empty reference"),
    ]

    # Act
    outcome = aggregate(outcomes)

    # Assert — a legitimate absence, distinct from both a real score and a failure.
    assert isinstance(outcome, NothingToProduce)
