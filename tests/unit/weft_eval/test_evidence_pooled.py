"""The evidence interval pools repetitions — task 44.9, owner decision D7.

Two repetitions of the same questions carry information an interval over repetition 1 alone
discards. Pooling them pairs each repetition with the baseline's own repetition of the same number,
and resamples **questions**, taking every repetition of each: a question asked twice is still one
question, so pooling must not narrow the interval as if twice as many had been asked.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.weft_eval.replay_records import METRIC, experiment_of, record_of
from weft_eval.evidence import evidence_table, render_evidence_table
from weft_eval.falsify import (
    UnpairableRecordsError,
    paired_differences,
    pooled_paired_differences,
)

_QUESTIONS = tuple(f"q{index:02d}" for index in range(40))


def _varied(offset: float) -> dict[str, float | None]:
    return {key: ((index * 7) % 10) / 10 + offset for index, key in enumerate(_QUESTIONS)}


def test_pooling_pairs_each_repetition_and_counts_every_pair(tmp_path: Path) -> None:
    # Arrange — repetition 1 moves nothing, repetition 2 moves both questions by one.
    experiment = experiment_of(tmp_path, ("base", "arm"))
    pairs = [
        (
            record_of(experiment, "base", {"q1": 0.0, "q2": 0.0}),
            record_of(experiment, "arm", {"q1": 0.0, "q2": 0.0}),
        ),
        (
            record_of(experiment, "base", {"q1": 0.0, "q2": 0.0}, repetition=2),
            record_of(experiment, "arm", {"q1": 1.0, "q2": 1.0}, repetition=2),
        ),
    ]

    # Act
    pooled = pooled_paired_differences(pairs)[METRIC]

    # Assert
    assert pooled.n == 4
    assert pooled.mean == pytest.approx(0.5)
    assert pooled.differing == 2


def test_one_repetition_pools_to_exactly_the_unpooled_difference(tmp_path: Path) -> None:
    # Arrange — so every table whose arms ran once is unchanged by pooling.
    experiment = experiment_of(tmp_path, ("base", "arm"))
    base = record_of(experiment, "base", _varied(0.0))
    arm = record_of(experiment, "arm", _varied(0.05))

    # Act
    pooled = pooled_paired_differences([(base, arm)])[METRIC]
    single = paired_differences(base, arm)[METRIC]

    # Assert
    assert pooled == single


def test_a_repeated_question_is_resampled_as_one_question(tmp_path: Path) -> None:
    # Arrange — repetition 2 repeats repetition 1 exactly. Pooling adds no information, so the
    # interval must not narrow the way doubling the questions would (about 1/sqrt(2)).
    experiment = experiment_of(tmp_path, ("base", "arm"))
    base_scores = _varied(0.0)
    arm_scores = {key: 1.0 - value for key, value in base_scores.items() if value is not None}
    first = (
        record_of(experiment, "base", base_scores),
        record_of(experiment, "arm", arm_scores),
    )
    second = (
        record_of(experiment, "base", base_scores, repetition=2),
        record_of(experiment, "arm", arm_scores, repetition=2),
    )

    # Act
    pooled = pooled_paired_differences([first, second])[METRIC]
    single = paired_differences(*first)[METRIC]

    # Assert
    assert pooled.low is not None and pooled.high is not None
    assert single.low is not None and single.high is not None
    assert pooled.mean == pytest.approx(single.mean)
    assert (pooled.high - pooled.low) > 0.85 * (single.high - single.low)


def test_a_pair_over_different_question_sets_is_refused(tmp_path: Path) -> None:
    # Arrange
    experiment = experiment_of(tmp_path, ("base", "arm"))
    pairs = [
        (
            record_of(experiment, "base", {"q1": 0.0}, question_set_digest="1" * 64),
            record_of(experiment, "arm", {"q1": 1.0}, question_set_digest="2" * 64),
        )
    ]

    # Act / Assert
    with pytest.raises(UnpairableRecordsError, match="question set differs"):
        pooled_paired_differences(pairs)


def test_the_evidence_table_pools_and_says_so(tmp_path: Path) -> None:
    # Arrange — both repetitions of both arms; repetition 2 is where the arm differs.
    experiment = experiment_of(tmp_path, ("base", "arm"))
    records = [
        record_of(experiment, "base", {"q1": 0.0, "q2": 0.0}),
        record_of(experiment, "base", {"q1": 0.0, "q2": 0.0}, repetition=2),
        record_of(experiment, "arm", {"q1": 0.0, "q2": 0.0}),
        record_of(experiment, "arm", {"q1": 1.0, "q2": 1.0}, repetition=2),
    ]

    # Act
    table = evidence_table(experiment, records)
    markdown = render_evidence_table(table)

    # Assert
    comparison = next(c for c in table.comparisons if c.metric == METRIC)
    assert comparison.paired is not None
    assert comparison.paired.n == 4
    assert comparison.paired.mean == pytest.approx(0.5)
    header = next(line for line in markdown.splitlines() if line.startswith("interval and"))
    assert "pooled over" in header
    assert "repetition 1," not in header
