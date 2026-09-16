"""`weft eval compare --slice axis=value` — ledger task **38.2**.

`--kind` restricted a comparison to one class of question by reading each run's per-kind slice.
Questions now declare any number of axes, so the restriction names the axis as well as the value,
and `--kind X` is the one case `--slice kind=X`. A value neither run recorded is refused by name
with the `axis=value` pairs that are there, never compared as two absent numbers.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from weft_cli.eval_commands import (
    EvalCompareArgs,
    UnknownSliceError,
    metrics_comparison_for_kind,
    metrics_comparison_for_slice,
)
from weft_eval.aggregate import MetricAggregate, PartitionSlice
from weft_eval.contract import MetricKind
from weft_eval.run_record import CorpusIdentity, MetricRunResult, RunRecord
from weft_kernel.payload import Produced
from weft_kernel.resolution import ResolvedPipeline


def _aggregate(
    mean: float, *, axes: dict[str, dict[str, float]], kinds: dict[str, float] | None = None
) -> Produced[MetricAggregate]:
    return Produced(
        value=MetricAggregate(
            reported_name="recall@5",
            mean=mean,
            n=4,
            stdev=0.1,
            excluded=0,
            nothing_to_produce=0,
            kind=MetricKind.RETRIEVAL,
            by_question_kind={
                name: PartitionSlice(mean=value, n=2, stdev=None)
                for name, value in (kinds or {}).items()
            },
            by_axis={
                axis: {
                    value: PartitionSlice(mean=mean_, n=2, stdev=None)
                    for value, mean_ in values.items()
                }
                for axis, values in axes.items()
            },
        )
    )


def _record(
    run_id: str,
    mean: float,
    *,
    axes: dict[str, dict[str, float]],
    kinds: dict[str, float] | None = None,
) -> RunRecord:
    return RunRecord(
        recorded_at="2026-09-16T00:00:00+00:00",
        resolved_pipeline=ResolvedPipeline(name=run_id),
        corpus=CorpusIdentity(name="corpus", digest="h"),
        metrics={"recall@5": _aggregate(mean, axes=axes, kinds=kinds)},
    )


def _mean(result: MetricRunResult) -> float:
    assert isinstance(result, Produced)
    return result.value.mean


def test_a_slice_restricts_both_sides_to_that_axis_values_own_number() -> None:
    # Arrange
    a = _record("run-a", 0.5, axes={"evidence": {"text": 0.8, "text-table": 0.2}})
    b = _record("run-b", 0.5, axes={"evidence": {"text": 0.6, "text-table": 0.4}})

    # Act
    comparison = metrics_comparison_for_slice(a, b, slice_="evidence=text-table")

    # Assert
    assert _mean(comparison["recall@5"].a) == pytest.approx(0.2)
    assert _mean(comparison["recall@5"].b) == pytest.approx(0.4)


def test_no_slice_compares_the_whole_run() -> None:
    # Arrange
    a = _record("run-a", 0.5, axes={"evidence": {"text": 0.8}})
    b = _record("run-b", 0.7, axes={"evidence": {"text": 0.6}})

    # Act
    comparison = metrics_comparison_for_slice(a, b, slice_=None)

    # Assert
    assert _mean(comparison["recall@5"].a) == pytest.approx(0.5)
    assert _mean(comparison["recall@5"].b) == pytest.approx(0.7)


def test_a_kind_slice_is_the_kind_restriction() -> None:
    # Arrange
    a = _record("run-a", 0.5, axes={}, kinds={"definitional": 0.9})
    b = _record("run-b", 0.5, axes={}, kinds={"definitional": 0.3})

    # Act
    sliced = metrics_comparison_for_slice(a, b, slice_="kind=definitional")
    kinded = metrics_comparison_for_kind(a, b, kind="definitional")

    # Assert
    assert _mean(sliced["recall@5"].a) == _mean(kinded["recall@5"].a)
    assert _mean(sliced["recall@5"].b) == _mean(kinded["recall@5"].b)


@pytest.mark.parametrize(
    "requested",
    ["evidence=video", "modality=text", "evidence"],
    ids=["an-unrecorded-value", "an-unrecorded-axis", "no-equals-sign"],
)
def test_a_slice_neither_run_recorded_is_refused_with_the_pairs_that_are_there(
    requested: str,
) -> None:
    # Arrange
    a = _record("run-a", 0.5, axes={"evidence": {"text": 0.8}}, kinds={"definitional": 0.9})
    b = _record("run-b", 0.5, axes={"evidence": {"text-table": 0.6}})

    # Act
    with pytest.raises(UnknownSliceError) as raised:
        metrics_comparison_for_slice(a, b, slice_=requested)

    # Assert
    assert raised.value.slice == requested
    assert set(raised.value.valid_options) == {
        "evidence=text",
        "evidence=text-table",
        "kind=definitional",
    }
    assert "evidence=text-table" in str(raised.value)


def test_the_args_model_takes_a_slice_or_a_kind_and_not_both() -> None:
    # Act / Assert
    assert EvalCompareArgs(a="run-a", b="run-b").slice is None
    assert EvalCompareArgs(a="run-a", b="run-b", slice="split=dev").slice == "split=dev"
    with pytest.raises(ValidationError, match="--kind"):
        EvalCompareArgs(a="run-a", b="run-b", slice="split=dev", kind="definitional")
