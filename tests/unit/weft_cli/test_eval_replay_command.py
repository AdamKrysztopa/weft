"""`weft eval replay <experiment>` — task 44.6a: the route replay table, printed from the wheel.

Not `test_eval_replay.py`, which is 40.2's pool replay through rerankers. `weft_eval.replay`
computes and renders the table; this is the verb that reads an experiment document and the records
beside it. The runs directory defaults to the one beside the document, never the working directory:
`R44.3` is `weft eval table` getting that wrong.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from weft_cli.eval_replay import EvalReplayArgs, EvalReplayCommand
from weft_eval.replay import UnscoredMetricError, render_replay_table, replay

from tests.unit.weft_eval.replay_records import METRIC, experiment_of, records_of
from weft_cli.exit_codes import ExitCode, exit_code_for
from weft_cli.render import render_outcome
from weft_command.permission import PermissionClass
from weft_eval.run_record import write_run_record
from weft_kernel.context import Context
from weft_kernel.payload import Produced

_SCORES = {"a": {"q1": 1.0, "q2": 0.0}, "b": {"q1": 0.0, "q2": 1.0}}


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _document(tmp_path: Path) -> Path:
    return tmp_path / "replay-fixture.toml"


async def test_the_runs_beside_the_document_are_read_from_any_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    experiment = experiment_of(tmp_path, ("a", "b"))
    records = records_of(experiment, _SCORES)
    for index, record in enumerate(records):
        write_run_record(record, tmp_path / "replay-fixture" / "runs" / f"run-{index}.json")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    # Act
    outcome = await EvalReplayCommand().run(
        EvalReplayArgs(experiment=str(_document(tmp_path))), _ctx()
    )
    rendered = render_outcome(outcome)

    # Assert — the metric defaults to the first the document declares.
    assert isinstance(outcome, Produced)
    expected = render_replay_table(replay(experiment, records, metric=METRIC))
    assert rendered.stdout == expected.rstrip("\n")
    assert rendered.exit_code is ExitCode.SUCCESS


async def test_a_runs_directory_a_metric_and_an_invocation_are_honoured(
    tmp_path: Path,
) -> None:
    # Arrange
    experiment = experiment_of(tmp_path, ("a", "b"))
    records = records_of(experiment, _SCORES, invocation="inv-1") + records_of(
        experiment, _SCORES, invocation="inv-2"
    )
    for index, record in enumerate(records):
        write_run_record(record, tmp_path / "kept" / f"run-{index}.json")

    # Act
    outcome = await EvalReplayCommand().run(
        EvalReplayArgs(
            experiment=str(_document(tmp_path)),
            runs=str(tmp_path / "kept"),
            metric=METRIC,
            invocation="inv-2",
        ),
        _ctx(),
    )

    # Assert
    assert isinstance(outcome, Produced)
    stdout = render_outcome(outcome).stdout or ""
    assert "invocation: inv-2" in stdout
    assert any(line.startswith("| oracle |") for line in stdout.splitlines())


async def test_a_metric_no_record_scored_is_a_resolution_failure(tmp_path: Path) -> None:
    # Arrange
    experiment = experiment_of(tmp_path, ("a", "b"))
    for index, record in enumerate(records_of(experiment, _SCORES)):
        write_run_record(record, tmp_path / "replay-fixture" / "runs" / f"run-{index}.json")

    # Act
    with pytest.raises(UnscoredMetricError) as refused:
        await EvalReplayCommand().run(
            EvalReplayArgs(experiment=str(_document(tmp_path)), metric="token_recall"), _ctx()
        )

    # Assert
    assert exit_code_for(refused.value) is ExitCode.RESOLUTION_FAILED


def test_the_command_only_reads() -> None:
    # Assert
    assert EvalReplayCommand.permission_class is PermissionClass.READ
    assert EvalReplayCommand.help
