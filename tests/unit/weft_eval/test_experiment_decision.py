"""An experiment pre-registers its decision — task 44.8.

A `[decision]` table names the metric that decides, the margin a difference must clear and which
direction is better, before anything runs. The evidence table then prints the verdict that reading
gives, so the verdict is computed from the records and never chosen after they are seen.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.weft_eval.test_evidence import complete_records
from weft_eval.evidence import evidence_table, render_evidence_table
from weft_eval.experiment import (
    EXPERIMENT_SCHEMA_VERSION,
    Decision,
    Direction,
    ExperimentDocumentError,
    load_experiment,
)
from weft_eval.verdict import EffectVerdict

_BODY = (
    f'[experiment]\nschema = {EXPERIMENT_SCHEMA_VERSION}\nname = "fixture"\n'
    'questions = "questions.toml"\ncorpus = "corpus"\nrepeats = 2\ntop_k = 5\n'
    'metrics = ["precision@5"]\nminimum_detectable_effect = 0.05\n\n'
    '[[arm]]\nname = "base"\npipeline = "index"\n\n'
    '[[arm]]\nname = "better"\npipeline = "index"\nquery_pipeline = "rung"\n'
)


def _document(tmp_path: Path, extra: str = "") -> Path:
    path = tmp_path / "experiment.toml"
    path.write_text(_BODY + extra, encoding="utf-8")
    return path


def _decision(
    metric: str = "precision@5", margin: str = "0.05", direction: str = "higher-is-better"
) -> str:
    return f'\n[decision]\nmetric = "{metric}"\nmargin = {margin}\ndirection = "{direction}"\n'


def _cells(line: str) -> list[str]:
    """A table line's cells — the "spread verdict" column also ends in "verdict"."""
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def test_a_declared_decision_is_read(tmp_path: Path) -> None:
    # Act
    experiment = load_experiment(_document(tmp_path, _decision()))

    # Assert
    assert experiment.decision == Decision(
        metric="precision@5", margin=0.05, direction=Direction.HIGHER_IS_BETTER
    )


def test_a_document_without_a_decision_declares_none(tmp_path: Path) -> None:
    # Act
    experiment = load_experiment(_document(tmp_path))

    # Assert
    assert experiment.decision is None


@pytest.mark.parametrize("margin", ["0.0", "-0.05"])
def test_a_margin_that_is_not_positive_is_refused(tmp_path: Path, margin: str) -> None:
    # Act / Assert
    with pytest.raises(ExperimentDocumentError, match="margin"):
        load_experiment(_document(tmp_path, _decision(margin=margin)))


def test_a_decision_on_a_metric_the_experiment_does_not_measure_is_refused(
    tmp_path: Path,
) -> None:
    # Act / Assert
    with pytest.raises(ExperimentDocumentError, match="recall@5"):
        load_experiment(_document(tmp_path, _decision(metric="recall@5")))


def test_an_unknown_direction_is_refused(tmp_path: Path) -> None:
    # Act / Assert
    with pytest.raises(ExperimentDocumentError, match="direction"):
        load_experiment(_document(tmp_path, _decision(direction="upwards")))


def test_an_unknown_top_level_table_is_refused_naming_the_valid_ones(tmp_path: Path) -> None:
    # Arrange — a misspelt `[decision]` would otherwise be skipped, and the verdict with it.
    path = _document(tmp_path, '\n[decison]\nmetric = "precision@5"\n')

    # Act
    with pytest.raises(ExperimentDocumentError, match="decison") as refused:
        load_experiment(path)

    # Assert
    assert "decision" in str(refused.value).replace("decison", "")


def test_the_evidence_table_prints_the_pre_registered_verdict(tmp_path: Path) -> None:
    # Arrange — `better` beats `base` by 0.25 on every question, well past a 0.05 margin.
    experiment = load_experiment(_document(tmp_path, _decision()))

    # Act
    table = evidence_table(experiment, complete_records(experiment))
    markdown = render_evidence_table(table)

    # Assert
    comparison = next(c for c in table.comparisons if c.metric == "precision@5")
    assert comparison.verdict is EffectVerdict.WORTHWHILE
    header = next(line for line in markdown.splitlines() if line.startswith("| arm | metric |"))
    row = next(line for line in markdown.splitlines() if line.startswith("| better |"))
    assert _cells(header)[-2:] == ["spread verdict", "verdict"]
    assert _cells(row)[-1] == EffectVerdict.WORTHWHILE.value


def test_a_lower_is_better_decision_reads_the_same_rise_as_harm(tmp_path: Path) -> None:
    # Arrange
    experiment = load_experiment(_document(tmp_path, _decision(direction="lower-is-better")))

    # Act
    table = evidence_table(experiment, complete_records(experiment))

    # Assert
    comparison = next(c for c in table.comparisons if c.metric == "precision@5")
    assert comparison.verdict is EffectVerdict.HARM


def test_without_a_decision_the_table_carries_no_verdict(tmp_path: Path) -> None:
    # Arrange
    experiment = load_experiment(_document(tmp_path))

    # Act
    table = evidence_table(experiment, complete_records(experiment))
    markdown = render_evidence_table(table)

    # Assert
    assert all(comparison.verdict is None for comparison in table.comparisons)
    header = next(line for line in markdown.splitlines() if line.startswith("| arm | metric |"))
    assert _cells(header)[-1] == "spread verdict"
    assert "verdict" not in _cells(header)


def test_an_unknown_key_in_the_decision_is_refused(tmp_path: Path) -> None:
    # Arrange — a misspelt key would otherwise vanish while the rest of the table still reads.
    path = _document(tmp_path, _decision() + "threshold = 0.1\n")

    # Act / Assert
    with pytest.raises(ExperimentDocumentError, match="threshold"):
        load_experiment(path)
