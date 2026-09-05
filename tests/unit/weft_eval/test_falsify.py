"""Unit tests for `weft_eval.falsify` — ledger task **8.8**, the falsification instrument.

Mirrors `packages/weft-rag/src/weft_eval/falsify.py`. The property under test is the one
`docs/09-release.md` §4.3 derives and this module applies to a *difference* rather than to a
value: the interval a baseline's own repetitions spanned is what that system's variability
measures, so a difference between two rungs that is no larger than that interval's width is
indistinguishable from the baseline repeating itself, and reporting it as an improvement is the
unfalsifiable claim §4.2 exists to refuse.

**No threshold is asserted anywhere below, and that is the point.** Every number in these tests
is a mean some run produced; the only comparison is against a width those means themselves
produced. A test that pinned a tolerance would be specifying exactly the constant `09` §4.4
forbids, and the implementation would be right to satisfy it.

Covers: the happy path (a difference larger than the spread, and one that is not), the two edge
cases `09` §4.3 names by hand (a deterministic baseline records a zero-width interval and admits
no drift; a baseline run once records no interval at all), and the error cases where there is
nothing to judge — a metric one repetition did not produce, a metric one compared run did not
produce, and a metric the baseline never measured. Each of those is a named verdict carrying its
own reason, never a silent omission and never a difference reported as real by default.
"""

from __future__ import annotations

import pytest

from weft_eval.aggregate import MetricAggregate
from weft_eval.falsify import (
    BaselineSpread,
    DifferenceJudgement,
    NoSpread,
    TooFewRepetitionsError,
    Verdict,
    baseline_spreads,
    judge_differences,
)
from weft_eval.run_record import CorpusIdentity, RunRecord, build_run_record
from weft_kernel.payload import Outcome, Produced
from weft_kernel.resolution import ResolvedPipeline


def _scored(name: str, mean: float) -> Produced[MetricAggregate]:
    """One metric's aggregate for one run — only `mean` matters to this module."""
    return Produced(
        value=MetricAggregate(
            reported_name=name, mean=mean, n=4, stdev=0.0, excluded=0, nothing_to_produce=0
        )
    )


def _record(pipeline: str, **means: float) -> RunRecord:
    """A run of `pipeline` that scored each named metric at the given mean."""
    metrics: dict[str, Outcome[MetricAggregate]] = {
        name: _scored(name, mean) for name, mean in means.items()
    }
    return build_run_record(
        recorded_at="2026-09-05T00:00:00+00:00",
        resolved_pipeline=ResolvedPipeline(name=pipeline),
        corpus=CorpusIdentity(name="corpus", digest="a" * 64),
        metrics=metrics,
    )


def test_a_difference_larger_than_the_baselines_own_spread_is_outside_it() -> None:
    # Arrange — three repetitions of one baseline pipeline, whose means span 0.02. Two rungs
    # then differ by 0.15, which is far more than the baseline varied against itself.
    repetitions = [
        _record("vector-top-k", **{"precision@5": 0.40}),
        _record("vector-top-k", **{"precision@5": 0.42}),
        _record("vector-top-k", **{"precision@5": 0.41}),
    ]
    rung_a = _record("vector-top-k", **{"precision@5": 0.41})
    rung_b = _record("hybrid-then-generate", **{"precision@5": 0.56})

    # Act
    spreads = baseline_spreads(repetitions)
    judgements = judge_differences(rung_a, rung_b, spreads)

    # Assert — the spread is the one those repetitions produced, and nothing wider.
    spread = spreads["precision@5"]
    assert isinstance(spread, BaselineSpread)
    assert (spread.low, spread.high) == (0.40, 0.42)
    assert spread.width == pytest.approx(0.02)

    judgement = judgements["precision@5"]
    assert judgement.verdict is Verdict.OUTSIDE_BASELINE_SPREAD
    assert judgement.difference == pytest.approx(0.15)
    assert judgement.spread == spread


def test_a_difference_no_larger_than_the_spread_is_not_shown_to_be_real() -> None:
    # Arrange — the claim this whole task exists to be able to refuse: a positive delta that
    # the baseline's own repetitions already produced by doing nothing at all.
    repetitions = [
        _record("vector-top-k", **{"precision@5": 0.40}),
        _record("vector-top-k", **{"precision@5": 0.46}),
    ]
    rung_a = _record("vector-top-k", **{"precision@5": 0.42})
    rung_b = _record("rerank-then-generate", **{"precision@5": 0.46})

    # Act
    judgements = judge_differences(rung_a, rung_b, baseline_spreads(repetitions))

    # Assert — a real, positive, four-hundredths improvement, and no evidence behind it.
    judgement = judgements["precision@5"]
    assert judgement.verdict is Verdict.WITHIN_BASELINE_SPREAD
    assert judgement.difference == pytest.approx(0.04)


def test_a_deterministic_baseline_records_a_zero_width_spread_and_admits_no_drift() -> None:
    # Arrange — `09` §4.3 by name: "a system that is deterministic records a zero-width
    # interval and admits no drift at all, which is correct and strict."
    repetitions = [
        _record("vector-top-k", **{"recall@5": 0.70}),
        _record("vector-top-k", **{"recall@5": 0.70}),
    ]
    spreads = baseline_spreads(repetitions)

    # Act — one pair that differs at all, and one that does not.
    drifted = judge_differences(
        _record("a", **{"recall@5": 0.70}), _record("b", **{"recall@5": 0.71}), spreads
    )
    identical = judge_differences(
        _record("a", **{"recall@5": 0.70}), _record("b", **{"recall@5": 0.70}), spreads
    )

    # Assert
    spread = spreads["recall@5"]
    assert isinstance(spread, BaselineSpread)
    assert spread.width == 0.0
    assert drifted["recall@5"].verdict is Verdict.OUTSIDE_BASELINE_SPREAD
    assert identical["recall@5"].verdict is Verdict.WITHIN_BASELINE_SPREAD


def test_a_baseline_run_once_records_no_interval_and_is_refused() -> None:
    # Arrange — V3's own failure clause: "the baseline was run once, in which case it records
    # no interval and no later run can be judged against it." Refused where the spread is
    # built, so no caller can reach a verdict computed from a single measurement.
    once = [_record("vector-top-k", **{"precision@5": 0.40})]

    # Act / Assert
    with pytest.raises(TooFewRepetitionsError) as caught:
        baseline_spreads(once)
    assert "1" in str(caught.value)
    assert caught.value.repetitions == 1


def test_a_metric_missing_from_one_repetition_gets_no_spread_and_no_verdict() -> None:
    # Arrange — the spread would understate the baseline's variability if it were taken over
    # the repetitions that happen to have scored, so it is not taken at all. `09` §4.2's own
    # list has this exact shape: "missing ground-truth files are tolerated."
    repetitions = [
        _record("vector-top-k", **{"precision@5": 0.40, "recall@5": 0.70}),
        _record("vector-top-k", **{"precision@5": 0.42}),
    ]

    # Act
    spreads = baseline_spreads(repetitions)
    judgements = judge_differences(
        _record("a", **{"recall@5": 0.10}), _record("b", **{"recall@5": 0.90}), spreads
    )

    # Assert — an enormous difference, and still no claim, because nothing measured the noise.
    assert isinstance(spreads["recall@5"], NoSpread)
    assert isinstance(spreads["precision@5"], BaselineSpread)
    judgement = judgements["recall@5"]
    assert judgement.verdict is Verdict.UNJUDGEABLE
    assert judgement.spread is None
    assert "recall@5" in judgement.reason


def test_a_metric_only_one_compared_run_scored_is_unjudgeable_not_a_difference() -> None:
    # Arrange — task 4.9 already refuses to fabricate a number for an unmeasured metric in
    # `weft eval compare`; a verdict must refuse the same way rather than treating the
    # absent side as a zero.
    repetitions = [
        _record("vector-top-k", **{"precision@5": 0.40}),
        _record("vector-top-k", **{"precision@5": 0.42}),
    ]
    rung_a = _record("vector-top-k")
    rung_b = _record("hybrid-then-generate", **{"precision@5": 0.90})

    # Act
    judgements = judge_differences(rung_a, rung_b, baseline_spreads(repetitions))

    # Assert
    judgement = judgements["precision@5"]
    assert judgement.verdict is Verdict.UNJUDGEABLE
    assert judgement.difference is None


def test_a_metric_the_baseline_never_measured_is_unjudgeable_naming_that() -> None:
    # Arrange — the two rungs both scored it; the baseline did not, so there is no interval
    # this difference could be judged against and saying so is the whole answer.
    repetitions = [
        _record("vector-top-k", **{"precision@5": 0.40}),
        _record("vector-top-k", **{"precision@5": 0.42}),
    ]
    rung_a = _record("vector-top-k", **{"ndcg@10": 0.30})
    rung_b = _record("hybrid-then-generate", **{"ndcg@10": 0.80})

    # Act
    judgements = judge_differences(rung_a, rung_b, baseline_spreads(repetitions))

    # Assert
    judgement = judgements["ndcg@10"]
    assert isinstance(judgement, DifferenceJudgement)
    assert judgement.verdict is Verdict.UNJUDGEABLE
    assert judgement.spread is None
    assert "ndcg@10" in judgement.reason
