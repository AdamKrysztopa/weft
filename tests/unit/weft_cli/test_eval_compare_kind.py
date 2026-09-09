"""`weft eval compare --kind <kind>` restricts a comparison to one class of question — `11.12`.

The second half of that task: `09` §4 asks that *"a rung's claim about one class of question is a
number over that class"*, and a per-kind slice on a `MetricAggregate` only becomes that claim once
a comparison can be asked for the slice instead of the mean. `01` → Phase 11's Exit is the first
caller — `weft eval compare graph-then-generate retrieve-then-generate --baseline
retrieve-then-generate`, restricted to `kind = requires-graph-hop` — and either answer discharges
it, which is only true if the restriction is real.

**A kind neither run recorded is refused, by name, listing what is present.** The alternative is
the divergence this task's other half records: the evaluation layer of the owner's `graph-study`
reports `0.0` for an empty subset, and a comparison of two zeroes nobody measured is a verdict a
reader cannot tell from a real one. `UnresolvedNameError`'s family is where this belongs, so the
refusal carries `valid_options` structurally the way fitness function 12 requires of every
unresolvable name in this tree, and the exit code is the one that family already maps to.

**`--kind` is derived, not declared.** `weft_cli.argparse_gen`'s mechanical floor — a field with no
default is a positional, one with a default is an optional flag — is what makes this a flag, the
same rule `EvalMetricsArgs.name`'s own paragraph states. So the test asserts the *behaviour* through
the args model and the comparison, not the parser's spelling.
"""

import pytest

from weft_cli.eval_commands import (
    EvalCompareArgs,
    UnknownQuestionKindError,
    metrics_comparison_for_kind,
)
from weft_eval.aggregate import MetricAggregate, PartitionSlice
from weft_eval.contract import MetricKind
from weft_eval.run_record import CorpusIdentity, RunRecord
from weft_kernel.payload import Produced
from weft_kernel.resolution import ResolvedPipeline


def _aggregate(mean: float, kinds: dict[str, float]) -> Produced[MetricAggregate]:
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
                name: PartitionSlice(mean=value, n=2, stdev=None) for name, value in kinds.items()
            },
        )
    )


def _record(run_id: str, mean: float, kinds: dict[str, float]) -> RunRecord:
    """A persisted run carrying one metric.

    The field set is `RunRecord`'s own — `recorded_at`, `resolved_pipeline`, `corpus` — copied
    from `tests/unit/weft_cli/test_render.py`'s existing builder rather than written from the
    shape this file's author expected. It was written the other way first, and the whole file
    failed at fixture construction; `L11.17` is that rule and this is its second instance.
    """
    return RunRecord(
        recorded_at="2026-09-09T00:00:00+00:00",
        resolved_pipeline=ResolvedPipeline(name=run_id),
        corpus=CorpusIdentity(name="corpus", digest="h"),
        metrics={"recall@5": _aggregate(mean, kinds)},
    )


def test_no_kind_asked_for_compares_the_whole_run_as_it_always_did() -> None:
    """The default is unchanged behaviour: `--kind` absent means the mean, not an empty
    restriction — "no verdict was asked for" and "a verdict was reached" stay distinguishable,
    which is `falsification`'s own settled rule one flag over."""
    # Arrange
    a = _record("run-a", 0.5, {"definitional": 0.9, "cross-document": 0.1})
    b = _record("run-b", 0.5, {"definitional": 0.1, "cross-document": 0.9})

    # Act
    comparison = metrics_comparison_for_kind(a, b, kind=None)

    # Assert
    a_side, b_side = comparison["recall@5"].a, comparison["recall@5"].b
    assert isinstance(a_side, Produced) and isinstance(b_side, Produced)
    assert a_side.value.mean == pytest.approx(0.5)
    assert b_side.value.mean == pytest.approx(0.5)


def test_a_kind_restricts_both_sides_to_that_kinds_own_number() -> None:
    """The property: two runs whose whole-run means are identical and whose cross-document
    numbers are opposite compare as opposite once the kind is named."""
    # Arrange
    a = _record("run-a", 0.5, {"definitional": 0.9, "cross-document": 0.1})
    b = _record("run-b", 0.5, {"definitional": 0.1, "cross-document": 0.9})

    # Act
    comparison = metrics_comparison_for_kind(a, b, kind="cross-document")

    # Assert
    a_side, b_side = comparison["recall@5"].a, comparison["recall@5"].b
    assert isinstance(a_side, Produced) and isinstance(b_side, Produced)
    assert a_side.value.mean == pytest.approx(0.1)
    assert b_side.value.mean == pytest.approx(0.9)
    # The restricted aggregate still names the metric it is about, so a reader of the printed
    # result reads it under the same key the unrestricted one uses.
    assert a_side.value.reported_name == "recall@5"


def test_a_kind_no_run_recorded_is_refused_by_name_with_the_kinds_that_are_there() -> None:
    """The refusal, and the point at which this deliberately does not report `0.0`."""
    # Arrange
    a = _record("run-a", 0.5, {"definitional": 0.9})
    b = _record("run-b", 0.5, {"definitional": 0.1})

    # Act / Assert
    with pytest.raises(UnknownQuestionKindError) as raised:
        metrics_comparison_for_kind(a, b, kind="requires-graph-hop")
    assert "requires-graph-hop" in str(raised.value)
    assert raised.value.valid_options == ("definitional",)


def test_a_kind_only_one_run_recorded_is_not_a_refusal_and_not_a_zero() -> None:
    """One run measured the kind and the other did not, which is a real and different fact from
    neither having measured it: the side that has a number keeps it and the side that does not
    reports not-measured, exactly as `_metrics_comparison` already does for a whole metric."""
    # Arrange
    a = _record("run-a", 0.5, {"definitional": 0.9, "cross-document": 0.2})
    b = _record("run-b", 0.5, {"definitional": 0.1})

    # Act
    comparison = metrics_comparison_for_kind(a, b, kind="cross-document")

    # Assert
    a_side, b_side = comparison["recall@5"].a, comparison["recall@5"].b
    assert isinstance(a_side, Produced)
    assert a_side.value.mean == pytest.approx(0.2)
    assert not isinstance(b_side, Produced)


def test_the_args_model_carries_kind_as_an_optional_flag() -> None:
    """`argparse_gen` derives the flag from the default, so the default is the decision."""
    # Act
    args = EvalCompareArgs(a="run-a", b="run-b")

    # Assert
    assert args.kind is None
    assert EvalCompareArgs(a="run-a", b="run-b", kind="cross-document").kind == "cross-document"
