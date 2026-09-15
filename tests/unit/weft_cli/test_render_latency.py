"""`weft eval run` and `weft eval compare` print query latency percentiles — ledger task **33.8**.

The percentiles are read off a record's per-question seconds (task 33.7), never recomputed from a
wall clock. A record written before 33.7 carries none, and compare says *not recorded* for it
rather than refusing: latency depends on the machine and is not identity, so it is reported beside a
comparison the way packaging is (repair `R22.11`), never a reason to refuse one.

The constructions are `tests/unit/weft_cli/test_render.py`'s (`L11.17`).
"""

from weft_cli import render
from weft_cli.eval_commands import EvalCompareCommandResult, EvalRunCommandResult
from weft_cli.pipeline_diff import PipelineDiff
from weft_eval.latency import latency_summary
from weft_eval.run_record import CorpusIdentity, PerQuestionSeconds, QuestionKey, RunRecord
from weft_kernel.payload import Produced
from weft_kernel.resolution import ResolvedPipeline
from weft_kernel.runner import RunSummary


def _seconds(count: int) -> PerQuestionSeconds:
    return PerQuestionSeconds(
        keyed_by=QuestionKey.POSITION,
        seconds={str(index): (index + 1) / 100 for index in range(count)},
    )


def _record(question_seconds: PerQuestionSeconds | None) -> RunRecord:
    return RunRecord(
        recorded_at="2026-09-15T00:00:00+00:00",
        resolved_pipeline=ResolvedPipeline(name="index"),
        corpus=CorpusIdentity(name="corpus", digest="abcdef123456"),
        question_seconds=question_seconds,
    )


def _eval_run_stdout(record: RunRecord) -> str:
    result = EvalRunCommandResult(
        run_id="run-1",
        path="corpus",
        summary=RunSummary(produced=1, nothing_to_produce=0, failed=0),
        stored_count=1,
        record=record,
        wall_clock_seconds=0.5,
    )
    return render.render_outcome(Produced(value=result)).stdout or ""


def test_eval_run_prints_each_percentile_with_its_label() -> None:
    # Act
    stdout = _eval_run_stdout(_record(_seconds(200)))

    # Assert
    assert "p50: 1.00s" in stdout
    assert "p95: 1.90s" in stdout
    assert "p99: 1.98s" in stdout


def test_eval_run_withholds_a_percentile_its_samples_cannot_support() -> None:
    # Act
    stdout = _eval_run_stdout(_record(_seconds(66)))

    # Assert
    assert "p99: not aggregated (66 samples)" in stdout
    assert "p95: 0.63s" in stdout


def test_eval_run_prints_no_latency_line_for_a_record_that_measured_none() -> None:
    # Act
    stdout = _eval_run_stdout(_record(None))

    # Assert
    assert "p50:" not in stdout


def _diff() -> PipelineDiff:
    return PipelineDiff(
        a_name="base",
        b_name="specific",
        identical=False,
        added_stages=(),
        removed_stages=(),
        changed_stages=(),
        var_changes=(),
        unapplied_operators_changed=False,
        unplaced_contributions_changed=False,
    )


def test_eval_compare_prints_each_runs_latency_and_says_when_one_was_not_recorded() -> None:
    # Arrange
    result = EvalCompareCommandResult(
        run_a="run-a",
        run_b="run-b",
        corpus_matches=True,
        model_versions_match=True,
        active_distributions_match=True,
        pipeline_diff=_diff(),
        metrics_comparison={},
        latency_a=None,
        latency_b=latency_summary(_seconds(200)),
    )

    # Act
    rendered = render.render_outcome(Produced(value=result))

    # Assert
    stdout = rendered.stdout or ""
    (line_a,) = [line for line in stdout.splitlines() if "latency" in line and "'run-a'" in line]
    (line_b,) = [line for line in stdout.splitlines() if "latency" in line and "'run-b'" in line]
    assert "not recorded" in line_a
    assert "p95: 1.90s" in line_b
    assert rendered.exit_code.value == 0
