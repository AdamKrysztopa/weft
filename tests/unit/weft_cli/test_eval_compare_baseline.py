"""`weft eval compare <published> <later>` over baseline report files — ledger repair **R22.4d**.

`01` → Phase 6's Exit names this command: "`weft eval compare` against the published baseline run
reports every metric inside the interval that baseline recorded across its own repetitions".
Until this repair `weft eval compare` took two run ids and nothing else, and its comparability
check counts the active distribution set, which G19 renamed — so it could not answer that question
for any published baseline. Given two report files it asks `weft_eval.baseline.judge_reproduction`
instead, the judge `R22.4b` built for exactly this. Each verdict is asserted through
`weft_cli.render`, the text and exit code a user meets (`L22.14`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from weft_cli import render
from weft_cli.eval_commands import (
    BaselineNotReproducedError,
    EvalCompareArgs,
    EvalCompareCommand,
    EvalCompareCommandResult,
    IncomparableRunsError,
    NotABaselineReportError,
)
from weft_cli.exit_codes import ExitCode
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_eval.baseline import IncomparableBaselinesError, MetricRecord, load_baseline_report
from weft_kernel.context import Context
from weft_kernel.payload import Produced
from weft_kernel.registry import Registry

_REPO = Path(__file__).resolve().parents[3]
_PUBLISHED = _REPO / "eval" / "baselines" / "8854c33f71ea-2026-08-25.json"
_RERUN = _REPO / "tests" / "unit" / "weft_eval" / "fixtures" / "baseline-rerun-2026-09-14.json"


def _ctx() -> Context:
    ctx = Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")
    ctx.services.add(
        Dependencies, Dependencies(registry=Registry(), reports=(), services=ServiceSelection())
    )
    return ctx


def _shifted_rerun(directory: Path) -> Path:
    """The re-run with `document-recall@10` moved outside its zero-width published interval."""
    rerun = load_baseline_report(_RERUN)
    shifted = tuple(
        record
        if record.metric != "document-recall@10"
        else MetricRecord(
            metric=record.metric,
            depth=record.depth,
            values=(0.5, 0.5, 0.5),
            mean=0.5,
            low=0.5,
            high=0.5,
            n_scored=record.n_scored,
            n_excluded=record.n_excluded,
        )
        for record in rerun.metrics
    )
    later = directory / "later.json"
    later.write_text(
        rerun.model_copy(update={"metrics": shifted}).model_dump_json(), encoding="utf-8"
    )
    return later


async def test_a_published_baseline_and_its_rerun_compare_as_a_reproduction() -> None:
    # Act
    outcome = await EvalCompareCommand().run(
        EvalCompareArgs(a=str(_PUBLISHED), b=str(_RERUN)), _ctx()
    )

    # Assert
    assert isinstance(outcome, Produced)
    assert isinstance(outcome.value, EvalCompareCommandResult)
    reproduction = outcome.value.reproduction
    assert reproduction is not None
    assert reproduction.reproduced
    assert len(reproduction.verdicts) == 12
    assert len(reproduction.provenance) == 6
    rendered = render.render_outcome(outcome)
    assert rendered.exit_code is ExitCode.SUCCESS
    stdout = rendered.stdout or ""
    assert "12 of 12 metric(s) inside" in stdout
    assert "installation differs at stage 'store': distribution weft-qdrant -> weft-rag" in stdout
    assert any(
        line.strip().startswith("document-recall@10:") and "inside" in line
        for line in stdout.splitlines()
    )


async def test_a_rerun_outside_an_interval_is_refused_naming_the_metric(tmp_path: Path) -> None:
    # Arrange
    later = _shifted_rerun(tmp_path)

    # Act
    with pytest.raises(BaselineNotReproducedError) as caught:
        await EvalCompareCommand().run(EvalCompareArgs(a=str(_PUBLISHED), b=str(later)), _ctx())

    # Assert
    rendered = render.render_refusal(caught.value)
    assert rendered.exit_code is ExitCode.OPERATION_FAILED
    stderr = rendered.stderr or ""
    assert "document-recall@10: 0.5 is outside" in stderr
    assert "quote-recall@10" not in stderr


async def test_a_baseline_report_against_a_different_measurement_is_refused(
    tmp_path: Path,
) -> None:
    # Arrange
    later = tmp_path / "later.json"
    rerun = load_baseline_report(_RERUN)
    later.write_text(
        rerun.model_copy(update={"retrieval_depth": 5}).model_dump_json(), encoding="utf-8"
    )

    # Act
    with pytest.raises(IncomparableBaselinesError) as caught:
        await EvalCompareCommand().run(EvalCompareArgs(a=str(_PUBLISHED), b=str(later)), _ctx())

    # Assert
    assert render.render_refusal(caught.value).exit_code is ExitCode.OPERATION_FAILED
    assert "retrieval_depth differs" in str(caught.value)


async def test_a_baseline_report_against_a_run_id_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.chdir(tmp_path)

    # Act
    with pytest.raises(IncomparableRunsError) as caught:
        await EvalCompareCommand().run(EvalCompareArgs(a=str(_PUBLISHED), b="some-run-id"), _ctx())

    # Assert
    assert "baseline report" in str(caught.value)
    assert "some-run-id" in str(caught.value)


async def test_a_file_that_is_not_a_baseline_report_is_refused_naming_it(tmp_path: Path) -> None:
    # Arrange
    other = tmp_path / "notes.json"
    other.write_text('{"hello": "world"}', encoding="utf-8")

    # Act
    with pytest.raises(NotABaselineReportError) as caught:
        await EvalCompareCommand().run(EvalCompareArgs(a=str(_PUBLISHED), b=str(other)), _ctx())

    # Assert
    assert str(other) in str(caught.value)
    assert render.render_refusal(caught.value).exit_code is ExitCode.OPERATION_FAILED


@pytest.mark.parametrize(("flag", "value"), [("baseline", "baseline"), ("kind", "definitional")])
async def test_a_run_only_option_given_with_two_baseline_reports_is_refused(
    flag: str, value: str
) -> None:
    # Arrange
    args = EvalCompareArgs.model_validate({"a": str(_PUBLISHED), "b": str(_RERUN), flag: value})

    # Act
    with pytest.raises(IncomparableRunsError) as caught:
        await EvalCompareCommand().run(args, _ctx())

    # Assert
    assert f"--{flag}" in str(caught.value)
