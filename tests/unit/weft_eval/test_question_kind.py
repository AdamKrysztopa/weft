"""A metric result carries the *kind* of question that produced it — ledger task `11.12`.

`09` §4 asks that a rung's claim about one class of question be a number over that class.
`eval/questions/*.toml` has carried `kind` per question since V2 — 136 questions across seven
kinds, measured 2026-09-09 — and **nothing in the shipped tree has ever read it**: `MetricAggregate`
reports one aggregate per metric, so a rung that is better at cross-document questions and worse at
definitional ones reports a single mean in which the two cancel. That is the producing-side-with-no-
consuming-side shape `L5.15` names, sitting in a data file rather than in code.

**The shape is 9.12's and is deliberately not re-invented.** That task built the identical
partition for *modality* — a mapping of slices beside the whole-run mean rather than instead of it,
each slice carrying `mean`/`n`/`stdev`, a partition with no observations **absent entirely** rather
than present with a zero `n`. Building a second, differently-shaped partition next to it is
`L9.17`'s convergence failure, so this task reuses the slice type and renames it to what it
actually is: `PartitionSlice`, one shape for one concept, with no alias left behind.

**`kind` is an open vocabulary and is a `str`, which is a decision and not an oversight.**
`eval/check_questions.py` pins a seven-member `Kind` StrEnum, but that script is *this
repository's own question set's* schema and ships nothing; the model here is loaded from a file a
third party writes about their own corpus. Two settled precedents in this tree say open: `Channel`
is "a vocabulary, not a field type… a closed enum would force a core edit every time somebody added
a base", and `Removed.removed`'s kinds are "an open vocabulary the participant owns" (task `9.3`).
Task `11.13` will add `requires-graph-hop` to this repository's own set, which under a closed
shipped enum would be a core edit for a question somebody wrote.

**The field is `by_question_kind`, not `by_kind`.** `MetricAggregate.kind` already means which
*contract* produced the observations (`MetricKind.RETRIEVAL`/`GENERATION`), and one name meaning
two things on one model is how a reader ends up slicing the wrong axis.

**Where this diverges from the owner's prior work, said at the point of use.** The evaluation layer
of the owner's `graph-study` is what contributes the idea of slicing a baseline by question class;
its shape is **not** carried and the difference is the interesting part — there, an empty subset
reports `0.0`, which is a number nobody measured standing where an absence belongs. Here an empty
partition is absent, and a comparison restricted to a kind no run recorded is refused by name. No
line of that work is carried, so `NOTICE` case 2 is not engaged; only the divergence is recorded,
which is what `10` asks of a name that makes a claim.
"""

import pytest
from pydantic import ValidationError

from weft_eval.aggregate import MetricAggregate, PartitionSlice, aggregate
from weft_eval.contract import MetricKind, MetricScore, QueryModality, RetrievalSample
from weft_kernel.payload import Failed, Produced


def _scored(value: float) -> Produced[MetricScore]:
    return Produced(value=MetricScore(metric_name="recall@5", value=value))


def _sample(kind: str = "", *, query: str = "q") -> RetrievalSample:
    return RetrievalSample(query=query, kind=kind)


def test_a_question_has_no_kind_unless_something_says_so() -> None:
    """The default is the empty string, so a question set written before this task loads
    unchanged — 9.12's own reasoning for defaulting `modality` to `TEXT`, one field over."""
    # Act
    sample = RetrievalSample(query="what does mRMR trade off?")

    # Assert
    assert sample.kind == ""
    assert sample.modality is QueryModality.TEXT


def test_a_sample_can_declare_a_kind_this_repository_has_never_heard_of() -> None:
    """The open-vocabulary decision, asserted rather than left to the type.

    `cross-document` is one of this repository's seven; `citation-chain` is not, and a third
    party's corpus is exactly where one would come from.
    """
    # Act / Assert
    assert _sample("cross-document").kind == "cross-document"
    assert _sample("citation-chain").kind == "citation-chain"


def test_an_aggregate_slices_by_question_kind_beside_the_mean_it_does_not_replace() -> None:
    """The whole-run mean survives; the slices sit beside it."""
    # Arrange — two kinds, deliberately far apart so a mean over both describes neither.
    outcomes = [_scored(0.9), _scored(0.9), _scored(0.1), _scored(0.1)]
    slices = {
        "definitional": PartitionSlice(mean=0.9, n=2, stdev=0.0),
        "cross-document": PartitionSlice(mean=0.1, n=2, stdev=0.0),
    }

    # Act
    outcome = aggregate(outcomes, kind=MetricKind.RETRIEVAL, by_question_kind=slices)

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert result.mean == pytest.approx(0.5)
    assert result.kind is MetricKind.RETRIEVAL
    assert set(result.by_question_kind) == {"definitional", "cross-document"}
    assert result.by_question_kind["definitional"].mean == pytest.approx(0.9)
    assert result.by_question_kind["cross-document"].mean == pytest.approx(0.1)


def test_a_rung_that_is_worse_at_one_kind_says_so_where_the_mean_does_not() -> None:
    """The property this task exists for, stated as the failure it prevents.

    Two rungs with the *same* whole-run mean, one of which has collapsed on cross-document
    questions and made it up on definitional ones. The mean cannot tell them apart and the
    slices can — which is `09` §4's "a number over that class".
    """
    # Arrange
    even = aggregate(
        [_scored(0.5), _scored(0.5)],
        by_question_kind={
            "definitional": PartitionSlice(mean=0.5, n=1, stdev=None),
            "cross-document": PartitionSlice(mean=0.5, n=1, stdev=None),
        },
    )
    lopsided = aggregate(
        [_scored(0.9), _scored(0.1)],
        by_question_kind={
            "definitional": PartitionSlice(mean=0.9, n=1, stdev=None),
            "cross-document": PartitionSlice(mean=0.1, n=1, stdev=None),
        },
    )

    # Assert
    assert isinstance(even, Produced) and isinstance(lopsided, Produced)
    assert even.value.mean == pytest.approx(lopsided.value.mean)
    assert even.value.by_question_kind["cross-document"].mean != pytest.approx(
        lopsided.value.by_question_kind["cross-document"].mean
    )


def test_a_kind_nothing_scored_is_absent_rather_than_zero() -> None:
    """9.12's settled rule, and the point at which this deliberately diverges from the work
    that contributed the idea: an empty subset there reports `0.0`, which is a number nobody
    measured standing where an absence belongs."""
    # Act
    outcome = aggregate([_scored(0.4)], by_question_kind={})

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.by_question_kind == {}
    assert "unanswerable" not in outcome.value.by_question_kind


def test_a_slice_carrying_no_observations_is_refused() -> None:
    """`n` is `ge=1`: there is nothing to average over zero observations, so a zero-`n` entry
    cannot be constructed at all rather than being filtered out downstream."""
    # Act / Assert
    with pytest.raises(ValidationError):
        PartitionSlice(mean=0.0, n=0, stdev=None)


def test_a_failed_observation_excludes_rather_than_scoring_zero() -> None:
    """A metric that could not score is not a metric that scored badly — the distinction
    `MetricAggregate.excluded` already keeps, asserted here because a per-kind slice is exactly
    where a zero would be mistaken for a measurement."""
    # Arrange
    outcomes = [_scored(0.8), Failed(reason="the judge did not answer")]

    # Act
    outcome = aggregate(outcomes)

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.mean == pytest.approx(0.8)
    assert outcome.value.excluded == 1


def test_the_aggregate_round_trips_with_its_question_kinds_through_json() -> None:
    """A `RunRecord` is read back off disk by `weft trace` and `weft eval compare`, so a slice
    that does not survive serialisation is a slice no comparison can be asked for."""
    # Arrange
    outcome = aggregate(
        [_scored(0.7)],
        by_question_kind={"limitation": PartitionSlice(mean=0.7, n=1, stdev=None)},
    )
    assert isinstance(outcome, Produced)

    # Act
    restored = MetricAggregate.model_validate_json(outcome.value.model_dump_json())

    # Assert
    assert restored.by_question_kind["limitation"].mean == pytest.approx(0.7)
    assert restored.by_question_kind["limitation"].n == 1


def test_the_slice_type_is_one_shape_under_one_name() -> None:
    """`ModalitySlice` is renamed to `PartitionSlice` with no alias left behind: the type is
    three numbers describing a partition, and two names for it is how a second, subtly different
    copy starts (`L9.17`). `by_modality` and `by_question_kind` are the same type."""
    # Act
    import weft_eval.aggregate as aggregate_module

    # Assert
    assert not hasattr(aggregate_module, "ModalitySlice")
    slice_ = PartitionSlice(mean=0.5, n=2, stdev=0.1)
    modal = aggregate(
        [_scored(0.5), _scored(0.5)],
        by_modality={QueryModality.TEXT: slice_},
        by_question_kind={"definitional": slice_},
    )
    assert isinstance(modal, Produced)
    assert type(modal.value.by_modality[QueryModality.TEXT]) is PartitionSlice
    assert type(modal.value.by_question_kind["definitional"]) is PartitionSlice
