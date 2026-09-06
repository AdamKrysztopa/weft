"""A metric result carries the modality of the query that produced it — ledger task `9.12`.

`11` §1.4 records the scar this exists to prevent, and it is not a hypothetical: a comparable
evaluation suite *"modelled modality as first-class and then measured none of it"* — filtering
functions for modality existed, `source ∈ {text, text-image, text-table, text-image}` was stored on
every result, **and the aggregation step never sliced by it**, while three call sites hardcoded
images out of the corpus entirely. Storing the fact is the easy half and the half that already
failed somewhere else. So this file asserts the *slice*, not the field.

**Why the slice rather than a second run.** `09` §4.3's V3 asks that a baseline be repeated and each
metric carry the interval its repetitions produced. A mean over a corpus that is nine parts text and
one part image moves by a tenth of whatever the image slice does — inside any interval a repeated
baseline would record. A multimodal regression is therefore invisible to V3 by construction unless
the slice is reported beside the mean, which is what `11` §3 D8 means by *"retrieval and generation
are two baselines with two intervals, not one"*.

**`kind` is on the result, not looked up at report time.** `weft trace` renders a persisted
`RunRecord` from disk and has no registry to ask whether `precision@5` came from a `RetrievalMetric`
or a `GenerationMetric`. The harness knows — it fetched the metric from one contract or the other —
so it records it. A reporter that had to re-derive this would need the registry that produced the
run, on the machine reading it, which is exactly the reach-through `RunRecord` exists to avoid.
"""

import pytest
from pydantic import ValidationError

from weft_eval.aggregate import MetricAggregate, ModalitySlice, aggregate
from weft_eval.contract import (
    GenerationSample,
    MetricKind,
    MetricScore,
    QueryModality,
    RetrievalSample,
)
from weft_kernel.payload import Failed, Produced


def _scored(value: float) -> Produced[MetricScore]:
    return Produced(value=MetricScore(metric_name="recall@5", value=value))


def test_a_query_is_text_unless_something_says_otherwise() -> None:
    """Every question written before this task is a text question, and stays one."""
    # Act / Assert
    assert (
        RetrievalSample(query="q", retrieved=(), relevant_ids=frozenset()).modality
        is QueryModality.TEXT
    )
    assert GenerationSample(query="q").modality is QueryModality.TEXT


def test_a_sample_can_declare_it_came_from_an_image_query() -> None:
    """`describe-query-image` is reserved and unbuilt, but `9.10` measures an image-question
    slice, and the slice has to be nameable before it can be measured."""
    # Act
    sample = RetrievalSample(
        query="q", retrieved=(), relevant_ids=frozenset(), modality=QueryModality.IMAGE
    )

    # Assert
    assert sample.modality is QueryModality.IMAGE


def test_an_aggregate_slices_by_modality() -> None:
    """The half the scar's original never did: the fact is stored *and* the numbers are split.

    The text slice and the image slice must be separately readable, or a mean is all anyone has.
    """
    # Arrange
    slices = {
        QueryModality.TEXT: ModalitySlice(mean=0.9, n=9, stdev=0.05),
        QueryModality.IMAGE: ModalitySlice(mean=0.1, n=1, stdev=None),
    }

    # Act
    result = aggregate(
        [_scored(0.9)] * 9 + [_scored(0.1)],
        kind=MetricKind.RETRIEVAL,
        by_modality=slices,
    )

    # Assert
    assert isinstance(result, Produced)
    assert dict(result.value.by_modality) == slices


def test_a_regression_in_one_modality_is_visible_beside_a_mean_that_hides_it() -> None:
    """The property, stated as the failure it prevents.

    Nine text questions at 0.9 and one image question at 0.1 average to 0.82 — a number no
    interval a repeated baseline records would flag. The image slice reads 0.1 and is unmissable.
    """
    # Arrange
    result = aggregate(
        [_scored(0.9)] * 9 + [_scored(0.1)],
        kind=MetricKind.RETRIEVAL,
        by_modality={
            QueryModality.TEXT: ModalitySlice(mean=0.9, n=9, stdev=0.0),
            QueryModality.IMAGE: ModalitySlice(mean=0.1, n=1, stdev=None),
        },
    )

    # Act / Assert
    assert isinstance(result, Produced)
    assert result.value.mean == pytest.approx(0.82)
    assert result.value.by_modality[QueryModality.IMAGE].mean == pytest.approx(0.1)


def test_an_aggregate_records_which_contract_produced_it() -> None:
    """So `weft trace` can group retrieval and generation without a registry to ask."""
    # Act
    retrieval = aggregate([_scored(1.0)], kind=MetricKind.RETRIEVAL)
    generation = aggregate([_scored(1.0)], kind=MetricKind.GENERATION)

    # Assert
    assert isinstance(retrieval, Produced)
    assert isinstance(generation, Produced)
    assert retrieval.value.kind is MetricKind.RETRIEVAL
    assert generation.value.kind is MetricKind.GENERATION


def test_a_run_that_scored_one_modality_slices_into_one() -> None:
    """A text-only corpus is the common case and must not grow a fabricated image slice."""
    # Act
    result = aggregate(
        [_scored(0.5)],
        kind=MetricKind.RETRIEVAL,
        by_modality={QueryModality.TEXT: ModalitySlice(mean=0.5, n=1, stdev=None)},
    )

    # Assert
    assert isinstance(result, Produced)
    assert set(result.value.by_modality) == {QueryModality.TEXT}


def test_slices_are_absent_rather_than_empty_when_nothing_asked_for_them() -> None:
    """`{}` is the honest answer for a caller that did not partition, and every caller before
    this task is one. Never a single slice fabricated from the whole."""
    # Act
    result = aggregate([_scored(0.5)], kind=MetricKind.RETRIEVAL)

    # Assert
    assert isinstance(result, Produced)
    assert dict(result.value.by_modality) == {}


def test_a_slice_carrying_no_observations_is_refused() -> None:
    """`MetricAggregate.n` is `ge=1` for the reason `aggregate()`'s docstring gives — there is
    nothing to average over zero observations. A slice is the same quantity one level down."""
    # Act / Assert
    with pytest.raises(ValidationError):
        ModalitySlice(mean=0.0, n=0, stdev=None)


def test_a_failed_observation_still_excludes_rather_than_scoring_zero() -> None:
    """V4's rule, unchanged by this task — asserted here because `aggregate()`'s signature moved
    and a defaulted parameter is exactly where an existing property gets lost (`L8.24`)."""
    # Act
    result = aggregate([_scored(1.0), Failed(reason="boom")], kind=MetricKind.RETRIEVAL)

    # Assert
    assert isinstance(result, Produced)
    assert result.value.excluded == 1
    assert result.value.mean == pytest.approx(1.0)


def test_the_aggregate_round_trips_with_its_slices_through_json() -> None:
    """It is persisted inside a `RunRecord`, and FF19 now actually reaches it (`L9.59`)."""
    # Arrange
    result = aggregate(
        [_scored(0.9)],
        kind=MetricKind.RETRIEVAL,
        by_modality={QueryModality.TEXT: ModalitySlice(mean=0.9, n=1, stdev=None)},
    )
    assert isinstance(result, Produced)

    # Act
    rebuilt = MetricAggregate.model_validate(result.value.model_dump(mode="json"))

    # Assert
    assert rebuilt == result.value
