"""Unit tests for `weft_eval.at_threshold`.

Mirrors `packages/weft-eval/src/weft_eval/at_threshold.py`. `test_the_same_metric_runs_twice_at_
two_thresholds_from_one_registration` is task 4.1's own demonstration — `docs/build-ledger.md`:
"a metric is a plugin, and the same metric runs twice at two thresholds because its registration
carries a typed configuration model" — one registered plugin, resolved once, constructed twice
from two independently-validated `AtThresholdConfig` instances, scoring the identical sample
differently. The other three tests are V4's mutual-exclusivity claim, exercised end to end: a
score, a legitimate absence of one, and a failure are three different `Outcome` types, never a
`score` sitting beside an unread `error`.
"""

import pytest
from pydantic import ValidationError

from weft_eval.at_threshold import AtThresholdConfig, OverlapAtThreshold
from weft_eval.contract import GenerationSample
from weft_kernel.context import Context
from weft_kernel.payload import Failed, NothingToProduce, Produced


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


async def test_the_same_metric_runs_twice_at_two_thresholds_from_one_registration() -> None:
    # Arrange — one plugin class (what `registrar.add` registered once), two configurations a
    # caller who never wrote this class builds and validates independently, mirroring a `with:`
    # block read twice with two different values.
    sample = GenerationSample(
        query="what colour is the sky",
        prediction="the sky is blue",
        reference="sky blue cloud rain",
    )
    lenient = OverlapAtThreshold(AtThresholdConfig.model_validate({"threshold": 0.3}))
    strict = OverlapAtThreshold(AtThresholdConfig.model_validate({"threshold": 0.9}))

    # Act — "sky" and "blue" of the reference's four tokens are present, so overlap is 0.5.
    lenient_outcome = await lenient.evaluate(sample, _ctx())
    strict_outcome = await strict.evaluate(sample, _ctx())

    # Assert — the identical sample, two different, independently-configured verdicts.
    assert isinstance(lenient_outcome, Produced)
    assert lenient_outcome.value.value == 1.0
    assert lenient_outcome.value.metric_name == "overlap_at_threshold@0.3"

    assert isinstance(strict_outcome, Produced)
    assert strict_outcome.value.value == 0.0
    assert strict_outcome.value.metric_name == "overlap_at_threshold@0.9"


async def test_empty_reference_is_nothing_to_produce_not_a_score() -> None:
    # Arrange — the reference's own defect (`token_recall` returning `1.0` unconditionally on an
    # empty reference, `docs/09-release.md` §4.2) fixed at the door: nothing to compare against
    # is reported as such, never as a computed number.
    metric = OverlapAtThreshold(AtThresholdConfig(threshold=0.5))
    sample = GenerationSample(query="q", prediction="anything", reference="")

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert
    assert isinstance(outcome, NothingToProduce)


async def test_no_prediction_fails_rather_than_scoring_zero() -> None:
    # Arrange — V4's own claim: a failed metric is an error, never a zero. `MetricScore` never
    # appears on this branch, so there is no `value` a caller could misread as a real score.
    metric = OverlapAtThreshold(AtThresholdConfig(threshold=0.5))
    sample = GenerationSample(query="q", prediction=None, reference="sky blue")

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert
    assert isinstance(outcome, Failed)
    assert not hasattr(outcome, "value")


def test_config_refuses_a_threshold_outside_zero_to_one() -> None:
    # Act / Assert — the typed configuration model itself is where an invalid threshold is
    # caught, before a metric ever runs one.
    with pytest.raises(ValidationError):
        AtThresholdConfig(threshold=1.5)
