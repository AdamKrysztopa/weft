"""`weft eval table <experiment>` — ledger task **38.1**: the table, printed from the wheel.

`weft_eval.evidence` computes and renders it; this is the verb that reads the records under
`runs/` and prints the markdown, so an operator regenerates a committed table with
`weft eval table eval/experiments/<name>.toml > eval/experiments/<name>/table.md`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.weft_eval.test_evidence import complete_records, fixture_experiment
from weft_cli.eval_table import EvalTableArgs, EvalTableCommand
from weft_cli.render import render_outcome
from weft_command.permission import PermissionClass
from weft_eval.evidence import IncompleteExperimentError, evidence_table, render_evidence_table
from weft_eval.run_record import write_run_record
from weft_kernel.context import Context
from weft_kernel.payload import Produced


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


async def test_the_table_prints_exactly_what_the_library_renders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.chdir(tmp_path)
    experiment = fixture_experiment(tmp_path)
    for index, record in enumerate(complete_records(experiment)):
        write_run_record(record, Path("runs") / f"run-{index}.json")

    # Act
    outcome = await EvalTableCommand().run(
        EvalTableArgs(experiment=str(tmp_path / "experiment.toml")), _ctx()
    )
    rendered = render_outcome(outcome)

    # Assert
    assert isinstance(outcome, Produced)
    expected = render_evidence_table(evidence_table(experiment, complete_records(experiment)))
    assert rendered.stdout == expected.rstrip("\n")


async def test_a_named_invocation_and_a_runs_directory_are_honoured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.chdir(tmp_path)
    experiment = fixture_experiment(tmp_path)
    records = complete_records(experiment, "inv-1") + complete_records(experiment, "inv-2")
    for index, record in enumerate(records):
        write_run_record(record, tmp_path / "elsewhere" / f"run-{index}.json")

    # Act
    outcome = await EvalTableCommand().run(
        EvalTableArgs(
            experiment=str(tmp_path / "experiment.toml"),
            runs=str(tmp_path / "elsewhere"),
            invocation="inv-2",
        ),
        _ctx(),
    )

    # Assert
    assert isinstance(outcome, Produced)
    assert "inv-2" in (render_outcome(outcome).stdout or "")


async def test_an_experiment_with_no_complete_invocation_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.chdir(tmp_path)
    fixture_experiment(tmp_path)

    # Act / Assert
    with pytest.raises(IncompleteExperimentError):
        await EvalTableCommand().run(
            EvalTableArgs(experiment=str(tmp_path / "experiment.toml")), _ctx()
        )


def test_the_command_only_reads() -> None:
    # Assert
    assert EvalTableCommand.permission_class is PermissionClass.READ
    assert EvalTableCommand.help
