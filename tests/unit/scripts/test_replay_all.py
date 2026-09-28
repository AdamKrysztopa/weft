"""`scripts/replay_all.py` — task 44.50a, E0a: the replay of every committed multi-arm experiment.

Each experiment document is replayed on its first declared metric over whichever records under the
root match its digest, wherever they sit: the pool-promotion experiments keep theirs in one shared
directory, not beside the document. An experiment that cannot be replayed is named with the refusal,
never dropped. An arm whose query pipeline reads labels at query time is a control, not a choice a
router could make, so it is left out of the oracle and named.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from replay_all import LABEL_READING_PLUGINS, replay_report

from tests.unit.weft_eval.replay_records import experiment_of, record_of, records_of
from weft_cli.pipeline_catalogue import load_pipeline_catalogue
from weft_eval.run_record import RunRecord, write_run_record

REPO_ROOT = Path(__file__).resolve().parents[3]


def _write(records: list[RunRecord], directory: Path) -> None:
    for index, record in enumerate(records):
        write_run_record(
            record,
            directory / f"{record.experiment.name if record.experiment else 'x'}-{index}.json",
        )


def _section(report: str, name: str) -> str:
    start = report.index(f"## {name}\n")
    following = report.find("\n## ", start + 1)
    return report[start:] if following == -1 else report[start:following]


def test_an_eligible_experiment_gets_its_replay_table_and_a_headline_row(tmp_path: Path) -> None:
    # Arrange — the records sit in a shared runs directory, not beside the document.
    experiments = tmp_path / "experiments"
    experiments.mkdir()
    experiment = experiment_of(experiments, ("a", "b"), name="pair")
    _write(
        records_of(experiment, {"a": {"q1": 1.0, "q2": 0.0}, "b": {"q1": 0.0, "q2": 1.0}}),
        tmp_path / "shared" / "runs",
    )

    # Act
    report = replay_report(experiments, tmp_path)

    # Assert
    section = _section(report, "pair")
    assert any(line.startswith("| oracle |") for line in section.splitlines())
    assert any(line.startswith("| pair |") for line in report.splitlines())


def test_an_experiment_over_different_question_sets_is_named_with_the_refusal(
    tmp_path: Path,
) -> None:
    # Arrange
    experiments = tmp_path / "experiments"
    experiments.mkdir()
    experiment = experiment_of(experiments, ("a", "b"), name="apart")
    _write(
        [
            record_of(experiment, "a", {"q1": 1.0}, question_set_digest="1" * 64),
            record_of(experiment, "a", {"q1": 1.0}, repetition=2, question_set_digest="1" * 64),
            record_of(experiment, "b", {"q1": 1.0}, question_set_digest="2" * 64),
            record_of(experiment, "b", {"q1": 1.0}, repetition=2, question_set_digest="2" * 64),
        ],
        tmp_path / "experiments" / "apart" / "runs",
    )

    # Act
    report = replay_report(experiments, tmp_path)

    # Assert
    section = _section(report, "apart")
    assert "skipped: " in section
    assert "question set differs" in section
    assert "| oracle |" not in section


def test_an_experiment_with_no_records_is_named_not_dropped(tmp_path: Path) -> None:
    # Arrange
    experiments = tmp_path / "experiments"
    experiments.mkdir()
    experiment_of(experiments, ("a", "b"), name="unrun")

    # Act
    report = replay_report(experiments, tmp_path)

    # Assert
    section = _section(report, "unrun")
    assert "skipped: " in section
    assert "no records" in section


def test_an_arm_reading_labels_at_query_time_is_left_out_of_the_oracle_and_named(
    tmp_path: Path,
) -> None:
    # Arrange — the label-reading arm scores 1.0 everywhere; a router could never choose it.
    experiments = tmp_path / "experiments"
    (experiments / "pipelines").mkdir(parents=True)
    plugin = sorted(LABEL_READING_PLUGINS)[0]
    (experiments / "pipelines" / "rung-labelled.yaml").write_text(
        "name: rung-labelled\nstages:\n"
        f"  - {{id: promote, use: {plugin}, with: {{labels: labels.jsonl}}}}\n"
        "  - {id: pack, use: repack, with: {method: reverse}}\n",
        encoding="utf-8",
    )
    experiment = experiment_of(experiments, ("a", "b", "labelled"), name="controlled")
    _write(
        records_of(
            experiment,
            {
                "a": {"q1": 0.5, "q2": 0.0},
                "b": {"q1": 0.0, "q2": 0.5},
                "labelled": {"q1": 1.0, "q2": 1.0},
            },
        ),
        tmp_path / "runs",
    )

    # Act
    report = replay_report(experiments, tmp_path)

    # Assert
    section = _section(report, "controlled")
    assert "labelled" in section.split("|", 1)[0]
    oracle = next(line for line in section.splitlines() if line.startswith("| oracle |"))
    assert oracle.split("|")[2].strip() == "0.500"
    assert "| always labelled |" not in section


def test_every_label_reading_plugin_is_one_a_committed_experiment_pipeline_uses() -> None:
    # Arrange
    catalogue = load_pipeline_catalogue(REPO_ROOT / "eval" / "experiments" / "pipelines")

    # Act
    used = {stage.use for pipeline in catalogue.values() for stage in pipeline.stages}

    # Assert
    assert LABEL_READING_PLUGINS
    assert used >= LABEL_READING_PLUGINS


@pytest.mark.parametrize("order", [("first", "second"), ("second", "first")])
def test_every_multi_arm_document_gets_one_section_in_filename_order(
    tmp_path: Path, order: tuple[str, str]
) -> None:
    # Arrange
    experiments = tmp_path / "experiments"
    experiments.mkdir()
    for name in order:
        experiment_of(experiments, ("a", "b"), name=name)

    # Act
    report = replay_report(experiments, tmp_path)

    # Assert
    assert report.index("## first\n") < report.index("## second\n")
    assert report.count("## first\n") == 1


def test_a_missing_experiments_directory_is_refused_not_reported_empty(tmp_path: Path) -> None:
    # Act / Assert — an empty report would read as "no experiment has headroom".
    with pytest.raises(FileNotFoundError, match="missing"):
        replay_report(tmp_path / "missing", tmp_path)
