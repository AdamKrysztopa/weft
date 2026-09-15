"""What Phase 33's exit prints that no earlier task did — ledger task **33.10**.

Two things the exit names are not printed by 33.1–33.8.
**`weft eval run` prints each role's tokens**,
read off the record 33.7 persisted: a metered role as `in / out`, and a role whose provider reports
nothing as *not reported*, by name, never as zero. **`weft ask --explain`'s stage block accounts for
the call's wall time**: a closing line gives the call's total and the time spent outside every
top-level record, so the records can be checked against the clock rather than trusted.

The constructions are `tests/unit/weft_cli/test_render.py`'s (`L11.17`).
"""

from weft_cli import render
from weft_cli.commands import AskCommandResult
from weft_cli.eval_commands import EvalRunCommandResult
from weft_cli.output import AskFormat
from weft_eval.run_record import CorpusIdentity, RoleTokens, RunRecord
from weft_kernel.payload import Produced
from weft_kernel.resolution import ResolvedPipeline
from weft_kernel.runner import RunSummary
from weft_kernel.seam import OutcomeKind, StageRecord


def _eval_run_stdout(token_usage: dict[str, RoleTokens] | None) -> str:
    record = RunRecord(
        recorded_at="2026-09-15T00:00:00+00:00",
        resolved_pipeline=ResolvedPipeline(name="index"),
        corpus=CorpusIdentity(name="corpus", digest="abcdef123456"),
        token_usage=token_usage,
    )
    result = EvalRunCommandResult(
        run_id="run-1",
        path="corpus",
        summary=RunSummary(produced=1, nothing_to_produce=0, failed=0),
        stored_count=1,
        record=record,
        wall_clock_seconds=0.5,
    )
    return render.render_outcome(Produced(value=result)).stdout or ""


def test_eval_run_prints_a_metered_role_as_tokens_in_and_out() -> None:
    # Act
    stdout = _eval_run_stdout(
        {
            "generate": RoleTokens(
                prompt_tokens=9104, completion_tokens=681, calls=3, calls_not_reporting=0
            )
        }
    )

    # Assert
    assert "generate: 9104 in / 681 out" in stdout


def test_eval_run_names_a_role_whose_provider_reports_nothing() -> None:
    # Act
    stdout = _eval_run_stdout(
        {"grade": RoleTokens(prompt_tokens=0, completion_tokens=0, calls=2, calls_not_reporting=2)}
    )

    # Assert
    assert "grade: not reported (2 calls)" in stdout
    assert "grade: 0 in" not in stdout


def test_eval_run_prints_no_token_line_for_a_record_that_measured_none() -> None:
    # Act
    stdout = _eval_run_stdout(None)

    # Assert
    assert "tokens:" not in stdout


def _record(record_id: int, seconds: float, parent: int | None = None) -> StageRecord:
    return StageRecord(
        id=record_id,
        parent=parent,
        label=f"stage-{record_id}",
        position=None,
        pack="weft-test",
        contract="C",
        plugin="p",
        seconds=seconds,
        outcome=OutcomeKind.PRODUCED,
        items_in=None,
        items_out=None,
    )


def test_the_stage_block_accounts_for_the_calls_wall_time() -> None:
    """The nested record is inside its parent's time, so only top-level records are subtracted —
    counting the child too would make the time outside any stage come out negative."""
    # Arrange
    result = AskCommandResult(
        question="q",
        top_k=5,
        format=AskFormat.TEXT,
        stages=(_record(0, 0.100), _record(1, 0.040, parent=0), _record(2, 0.050)),
        stages_seconds=0.200,
    )

    # Act
    stdout = render.render_outcome(Produced(value=result)).stdout or ""

    # Assert
    (total_line,) = [line for line in stdout.splitlines() if "outside any stage" in line]
    assert "total 200 ms" in total_line
    assert "outside any stage 50 ms" in total_line
