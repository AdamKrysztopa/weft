"""E5, offline: which profile features identify the regimes the experiments measure — task 44.52.

A routing rule may test a feature only if the feature says something reliable about the question.
Over question sets whose axes carry a gold label (MuSiQue's `control`, QASPER's `answer-type`),
each boolean feature of `profile_query` is scored against each label value: precision is how
often the label holds when the feature fires, recall how often the feature fires when the label
holds. A feature is **routable** for a label only when precision reaches 0.80 on the train split
and again on held-out; below that it stays descriptive. No model is called.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from profile_validity import ROUTABLE_PRECISION, FeatureValidity, validity

from weft_eval.question_set import Question, QuestionField


def _question(identifier: str, text: str, axes: Mapping[str, str]) -> Question:
    return Question.model_validate(
        {
            "id": identifier,
            "text": text,
            "language": "en",
            "relevant_documents": ("doc.txt",),
            "axes": dict(axes),
            "absent": frozenset(QuestionField),
            "absent_reason": "a validity fixture",
        }
    )


def _row(rows: list[FeatureValidity], feature: str, value: str) -> FeatureValidity:
    return next(row for row in rows if row.feature == feature and row.label_value == value)


def test_precision_and_recall_are_counted_per_split() -> None:
    # Arrange — "how many" marks aggregation; three of four dev questions carry the label.
    questions = (
        _question("d1", "How many looms?", {"kind": "count", "split": "dev"}),
        _question("d2", "How many spindles?", {"kind": "count", "split": "dev"}),
        _question("d3", "How many reeds are there?", {"kind": "other", "split": "dev"}),
        _question("d4", "Which loom is oldest?", {"kind": "count", "split": "dev"}),
        _question("t1", "How many shuttles?", {"kind": "count", "split": "test"}),
        _question("t2", "Who wove it?", {"kind": "other", "split": "test"}),
    )

    # Act
    rows = validity(questions, axis="kind")

    # Assert
    row = _row(rows, "query.cue.aggregation", "count")
    assert row.train.support == 3
    assert row.train.precision == pytest.approx(2 / 3)
    assert row.train.recall == pytest.approx(2 / 3)
    assert row.held_out.precision == pytest.approx(1.0)
    assert row.held_out.recall == pytest.approx(1.0)
    assert row.routable is False


def test_a_feature_precise_on_three_firings_is_not_yet_routable() -> None:
    # Arrange
    questions = (
        _question("d1", "How many looms?", {"kind": "count", "split": "dev"}),
        _question("d2", "How many reeds?", {"kind": "count", "split": "dev"}),
        _question("d3", "Why weave?", {"kind": "other", "split": "dev"}),
        _question("t1", "How many shuttles?", {"kind": "count", "split": "test"}),
        _question("t2", "Who wove it?", {"kind": "other", "split": "test"}),
    )

    # Act
    rows = validity(questions, axis="kind")

    # Assert
    row = _row(rows, "query.cue.aggregation", "count")
    assert row.train.precision == pytest.approx(1.0)
    assert row.held_out.precision == pytest.approx(1.0)
    assert row.routable is False
    assert ROUTABLE_PRECISION == 0.80


def test_a_feature_that_never_fires_has_no_precision_and_is_not_routable() -> None:
    # Arrange
    questions = (
        _question("d1", "Why weave?", {"kind": "other", "split": "dev"}),
        _question("t1", "Who wove it?", {"kind": "other", "split": "test"}),
    )

    # Act
    rows = validity(questions, axis="kind")

    # Assert
    row = _row(rows, "query.cue.comparison", "other")
    assert row.train.precision is None
    assert row.routable is False


def test_every_boolean_feature_is_scored_against_every_label_value() -> None:
    # Arrange
    questions = (
        _question("d1", "How many looms?", {"kind": "count", "split": "dev"}),
        _question("t1", "Why?", {"kind": "other", "split": "test"}),
    )

    # Act
    rows = validity(questions, axis="kind")

    # Assert
    features = {row.feature for row in rows}
    assert "query.cue.aggregation" in features
    assert "query.locale_fallback" in features
    assert "query.word_count" not in features
    assert {row.label_value for row in rows} == {"count", "other"}


def test_a_question_without_the_axis_is_refused_naming_it() -> None:
    # Arrange
    questions = (_question("d1", "How many looms?", {"split": "dev"}),)

    # Act / Assert
    with pytest.raises(ValueError, match="d1"):
        validity(questions, axis="kind")


def test_a_perfect_precision_on_a_handful_of_firings_is_not_routable() -> None:
    # Arrange — the feature fires on 5 dev and 5 held-out questions, always on the label: a
    # precision of 1.0 whose 95% lower bound (Wilson) is still well under 0.80.
    questions = tuple(
        _question(f"{split}{index}", "How many looms?", {"kind": "count", "split": split})
        for split in ("dev", "test")
        for index in range(5)
    ) + tuple(
        _question(f"{split}o{index}", "Why weave?", {"kind": "other", "split": split})
        for split in ("dev", "test")
        for index in range(20)
    )

    # Act
    rows = validity(questions, axis="kind")

    # Assert
    row = _row(rows, "query.cue.aggregation", "count")
    assert row.train.precision == pytest.approx(1.0)
    assert row.train.precision_lower is not None
    assert row.train.precision_lower < ROUTABLE_PRECISION
    assert row.routable is False


def test_many_firings_that_all_hold_are_routable() -> None:
    # Arrange — 40 firings per split, every one on the label: the lower bound clears 0.80.
    questions = tuple(
        _question(f"{split}{index}", "How many looms?", {"kind": "count", "split": split})
        for split in ("dev", "test")
        for index in range(40)
    )

    # Act
    rows = validity(questions, axis="kind")

    # Assert
    row = _row(rows, "query.cue.aggregation", "count")
    assert row.train.precision_lower is not None
    assert row.train.precision_lower >= ROUTABLE_PRECISION
    assert row.routable is True
