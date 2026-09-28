"""Offline replay: every fixed arm and the oracle from recorded scores — task 44.6a.

Every arm of one experiment answered the same questions and each record keeps one score per
question, so what any per-question choice among those arms would have scored is computable with no
model call. The oracle, each question's best arm, is the ceiling a router over those arms could
reach. The self-oracle, each question's better repetition of the best arm, is what judge noise alone
lets an oracle reach, and is what an arm oracle is read against.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.weft_eval.replay_records import (
    METRIC,
    experiment_of,
    record_of,
    records_of,
)
from weft_eval.evidence import AmbiguousInvocationError, IncompleteExperimentError
from weft_eval.falsify import UnpairableRecordsError
from weft_eval.replay import ReplayRow, UnscoredMetricError, render_replay_table, replay


def _rows(rows: tuple[ReplayRow, ...]) -> dict[str, ReplayRow]:
    return {row.label: row for row in rows}


def test_the_oracle_takes_each_question_s_best_arm(tmp_path: Path) -> None:
    # Arrange — a wins q1, b wins q2; neither arm alone reaches both.
    experiment = experiment_of(tmp_path, ("a", "b"))
    records = records_of(experiment, {"a": {"q1": 1.0, "q2": 0.0}, "b": {"q1": 0.0, "q2": 1.0}})

    # Act
    table = replay(experiment, records, metric=METRIC)

    # Assert
    rows = _rows(table.rows)
    assert rows["oracle"].mean == pytest.approx(1.0)
    assert rows["oracle"].n == 2
    assert rows["always a"].mean == pytest.approx(0.5)
    assert table.best_arm in {"a", "b"}
    oracle_delta = rows["oracle"].delta
    assert oracle_delta is not None
    assert oracle_delta.mean == pytest.approx(0.5)
    assert oracle_delta.n == 2


def test_the_oracle_skips_an_arm_that_did_not_score_a_question(tmp_path: Path) -> None:
    # Arrange — b did not score q2; the oracle takes a's 0.2 there, never b's miss as a zero.
    experiment = experiment_of(tmp_path, ("a", "b"))
    records = records_of(experiment, {"a": {"q1": 0.0, "q2": 0.2}, "b": {"q1": 1.0, "q2": None}})

    # Act
    table = replay(experiment, records, metric=METRIC)

    # Assert
    oracle = _rows(table.rows)["oracle"]
    assert oracle.mean == pytest.approx(0.6)
    assert oracle.n == 2
    assert table.unscored == 0


def test_a_question_no_arm_scored_is_excluded_from_every_row_and_counted(tmp_path: Path) -> None:
    # Arrange
    experiment = experiment_of(tmp_path, ("a", "b"))
    records = records_of(
        experiment,
        {"a": {"q1": 1.0, "q2": None, "q3": 0.5}, "b": {"q1": 0.0, "q2": None, "q3": 0.5}},
    )

    # Act
    table = replay(experiment, records, metric=METRIC)

    # Assert
    assert table.unscored == 1
    assert {row.n for row in table.rows} == {2}


def test_always_x_replays_to_exactly_arm_x(tmp_path: Path) -> None:
    # Arrange
    experiment = experiment_of(tmp_path, ("a", "b"))
    records = records_of(experiment, {"a": {"q1": 0.3, "q2": 0.7}, "b": {"q1": 0.1, "q2": 0.4}})

    # Act
    table = replay(experiment, records, metric=METRIC)

    # Assert
    rows = _rows(table.rows)
    assert rows["always a"].mean == pytest.approx(0.5)
    assert rows["always b"].mean == pytest.approx(0.25)
    assert table.best_arm == "a"
    best_delta = rows["always a"].delta
    assert best_delta is not None
    assert best_delta.mean == 0.0
    assert best_delta.differing == 0
    other_delta = rows["always b"].delta
    assert other_delta is not None
    assert other_delta.mean == pytest.approx(-0.25)


def test_the_arm_rows_keep_the_document_s_arm_order(tmp_path: Path) -> None:
    # Arrange — the document declares b before a, and a is the better arm.
    experiment = experiment_of(tmp_path, ("b", "a"))
    records = records_of(experiment, {"b": {"q1": 0.0, "q2": 0.0}, "a": {"q1": 1.0, "q2": 1.0}})

    # Act
    table = replay(experiment, records, metric=METRIC)

    # Assert
    labels = [row.label for row in table.rows]
    assert labels.index("always b") < labels.index("always a") < labels.index("oracle")


def test_the_self_oracle_takes_each_question_s_better_repetition_of_the_best_arm(
    tmp_path: Path,
) -> None:
    # Arrange — a's two repetitions disagree question by question; b never beats a.
    experiment = experiment_of(tmp_path, ("a", "b"))
    records = records_of(
        experiment,
        {"a": {"q1": 1.0, "q2": 0.0}, "b": {"q1": 0.0, "q2": 0.0}},
        second={"a": {"q1": 0.0, "q2": 1.0}},
    )

    # Act
    table = replay(experiment, records, metric=METRIC)

    # Assert — the arms give no headroom; judge noise alone gives 0.5.
    rows = _rows(table.rows)
    assert table.best_arm == "a"
    oracle_delta = rows["oracle"].delta
    assert oracle_delta is not None
    assert oracle_delta.mean == 0.0
    self_oracle = rows["self-oracle"]
    assert self_oracle.mean == pytest.approx(1.0)
    assert self_oracle.delta is not None
    assert self_oracle.delta.mean == pytest.approx(0.5)


def test_replay_refuses_arms_over_different_questions(tmp_path: Path) -> None:
    # Arrange
    experiment = experiment_of(tmp_path, ("a", "b"))
    records = [
        record_of(experiment, "a", {"q1": 1.0}, question_set_digest="1" * 64),
        record_of(experiment, "a", {"q1": 1.0}, repetition=2, question_set_digest="1" * 64),
        record_of(experiment, "b", {"q1": 1.0}, question_set_digest="2" * 64),
        record_of(experiment, "b", {"q1": 1.0}, repetition=2, question_set_digest="2" * 64),
    ]

    # Act / Assert
    with pytest.raises(UnpairableRecordsError, match="question set differs"):
        replay(experiment, records, metric=METRIC)


def test_replay_refuses_arms_over_different_corpora(tmp_path: Path) -> None:
    # Arrange — the same questions asked of two corpora are two measurements, not a choice.
    experiment = experiment_of(tmp_path, ("a", "b"))
    records = [
        record_of(experiment, "a", {"q1": 1.0}, corpus_digest="1" * 64),
        record_of(experiment, "a", {"q1": 1.0}, repetition=2, corpus_digest="1" * 64),
        record_of(experiment, "b", {"q1": 1.0}, corpus_digest="2" * 64),
        record_of(experiment, "b", {"q1": 1.0}, repetition=2, corpus_digest="2" * 64),
    ]

    # Act / Assert
    with pytest.raises(UnpairableRecordsError, match="corpus differs"):
        replay(experiment, records, metric=METRIC)


def test_a_metric_no_record_scored_is_refused_naming_the_metrics_that_were(
    tmp_path: Path,
) -> None:
    # Arrange
    experiment = experiment_of(tmp_path, ("a", "b"))
    records = records_of(experiment, {"a": {"q1": 1.0}, "b": {"q1": 0.0}})

    # Act
    with pytest.raises(UnscoredMetricError, match="token_recall") as refused:
        replay(experiment, records, metric="token_recall")

    # Assert
    assert METRIC in refused.value.valid_options
    assert "token_recall" not in refused.value.valid_options


def test_a_metric_every_question_failed_is_not_offered_as_scored(tmp_path: Path) -> None:
    # Arrange
    experiment = experiment_of(tmp_path, ("a", "b"))
    records = records_of(experiment, {"a": {"q1": None}, "b": {"q1": None}})

    # Act
    with pytest.raises(UnscoredMetricError) as refused:
        replay(experiment, records, metric=METRIC)

    # Assert
    assert METRIC not in refused.value.valid_options


def test_a_named_invocation_is_the_one_replayed(tmp_path: Path) -> None:
    # Arrange
    experiment = experiment_of(tmp_path, ("a", "b"))
    records = records_of(
        experiment, {"a": {"q1": 0.0}, "b": {"q1": 0.0}}, invocation="inv-1"
    ) + records_of(experiment, {"a": {"q1": 1.0}, "b": {"q1": 0.0}}, invocation="inv-2")

    # Act
    table = replay(experiment, records, metric=METRIC, invocation="inv-2")

    # Assert
    assert table.invocation == "inv-2"
    assert _rows(table.rows)["always a"].mean == pytest.approx(1.0)


def test_two_complete_invocations_are_refused_unless_one_is_named(tmp_path: Path) -> None:
    # Arrange
    experiment = experiment_of(tmp_path, ("a", "b"))
    records = records_of(
        experiment, {"a": {"q1": 0.0}, "b": {"q1": 0.0}}, invocation="inv-1"
    ) + records_of(experiment, {"a": {"q1": 1.0}, "b": {"q1": 0.0}}, invocation="inv-2")

    # Act / Assert
    with pytest.raises(AmbiguousInvocationError):
        replay(experiment, records, metric=METRIC)


def test_an_invocation_missing_an_arm_is_refused(tmp_path: Path) -> None:
    # Arrange
    experiment = experiment_of(tmp_path, ("a", "b"))
    records = records_of(experiment, {"a": {"q1": 1.0}})

    # Act / Assert
    with pytest.raises(IncompleteExperimentError, match="arm 'b'"):
        replay(experiment, records, metric=METRIC)


def test_the_rendered_table_states_the_interval_before_the_point_estimate(
    tmp_path: Path,
) -> None:
    # Arrange
    experiment = experiment_of(tmp_path, ("a", "b"))
    records = records_of(
        experiment,
        {"a": {"q1": 1.0, "q2": 0.0, "q3": 1.0}, "b": {"q1": 0.0, "q2": 1.0, "q3": 0.0}},
    )
    table = replay(experiment, records, metric=METRIC)

    # Act
    markdown = render_replay_table(table)

    # Assert
    lines = markdown.splitlines()
    header = next(line for line in lines if "95% CI vs best" in line)
    assert header.index("95% CI vs best") < header.index("paired Δ")
    assert any(line.startswith("| oracle |") for line in lines)
    assert any(line.startswith("| always b |") for line in lines)
    assert f"metric: {METRIC}" in markdown
    assert f"best arm: {table.best_arm}" in markdown
    assert f"invocation: {table.invocation}" in markdown
    assert f"unscored: {table.unscored}" in markdown
