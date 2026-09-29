"""Gold-referee calibration of the pairwise judge — task 44.43b, the owner's choice 2026-09-29.

On a question set with gold answers, two arms' answers whose gold-based `answer_correctness`
differs clearly have a known better answer. The pairwise judge's verdict on those pairs is scored
against it: agreement over the pairs the judge decided, with a Wilson interval, and ties counted
apart. The selection and the arithmetic are pure; only the judging calls a model.
"""

from __future__ import annotations

import pytest
from pairwise_gold_calibration import CalibrationRow, agreement, clear_pairs


def test_only_pairs_whose_gold_scores_differ_by_the_threshold_are_chosen() -> None:
    # Arrange
    scores = {
        "dense": {"q1": 0.9, "q2": 0.5, "q3": 0.1},
        "wide": {"q1": 0.2, "q2": 0.6, "q3": 0.1},
        "ctx": {"q1": 0.9, "q2": 0.0},
    }

    # Act
    pairs = clear_pairs(scores, threshold=0.3)

    # Assert — ordered by arm pair then question; q3 is absent from ctx.
    assert pairs == [
        ("ctx", "dense", "q2"),
        ("ctx", "wide", "q1"),
        ("ctx", "wide", "q2"),
        ("dense", "wide", "q1"),
    ]


def test_agreement_counts_decided_pairs_and_keeps_ties_apart() -> None:
    # Arrange — 3 agree, 1 disagrees, 1 tie.
    rows = [
        CalibrationRow(question="q1", gold="a", judge="a"),
        CalibrationRow(question="q2", gold="b", judge="b"),
        CalibrationRow(question="q3", gold="a", judge="a"),
        CalibrationRow(question="q4", gold="a", judge="b"),
        CalibrationRow(question="q5", gold="b", judge="tie"),
    ]

    # Act
    result = agreement(rows)

    # Assert
    assert (result.agree, result.decided, result.ties) == (3, 4, 1)
    assert result.rate == pytest.approx(0.75)
    assert result.low is not None and result.high is not None
    assert result.low < 0.75 < result.high


def test_no_decided_pair_has_no_rate() -> None:
    # Act
    result = agreement([CalibrationRow(question="q1", gold="a", judge="tie")])

    # Assert
    assert result.rate is None and result.low is None and result.high is None
