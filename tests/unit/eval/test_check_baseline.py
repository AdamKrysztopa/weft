"""Unit tests for `eval/check_baseline.py` — the hand-run judge, over the real published baseline.

Since repair `R22.4b` it decides nothing itself: `weft_eval.baseline.judge_reproduction` does, and
this file checks that the script's exit code and output say what that judgement found. The inputs
are the published `v2.6.0` baseline and its 2026-09-14 re-run, which differ in distribution names
and agree in every metric — the pair the previous judge refused.
"""

from pathlib import Path

import pytest
from check_baseline import main

from weft_eval.baseline import BaselineReport, MetricRecord, load_baseline_report

_REPO = Path(__file__).resolve().parents[3]
_PUBLISHED = _REPO / "eval" / "baselines" / "8854c33f71ea-2026-08-25.json"
_RERUN = _REPO / "tests" / "unit" / "weft_eval" / "fixtures" / "baseline-rerun-2026-09-14.json"


def _written(report: BaselineReport, directory: Path) -> Path:
    path = directory / "later.json"
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return path


def test_a_reproduction_exits_zero_and_reports_what_the_installation_changed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Act
    code = main([str(_PUBLISHED), str(_RERUN)])

    # Assert
    out = capsys.readouterr().out
    assert code == 0
    assert "12 metric(s) inside" in out
    assert "weft-qdrant" in out
    assert "weft-rag" in out


def test_a_metric_outside_its_interval_exits_one_naming_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange
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
    later = _written(rerun.model_copy(update={"metrics": shifted}), tmp_path)

    # Act
    code = main([str(_PUBLISHED), str(later)])

    # Assert
    assert code == 1
    assert "document-recall@10" in capsys.readouterr().err


def test_a_different_measurement_exits_two_naming_what_differs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange
    rerun = load_baseline_report(_RERUN)
    later = _written(rerun.model_copy(update={"retrieval_depth": 5}), tmp_path)

    # Act
    code = main([str(_PUBLISHED), str(later)])

    # Assert
    assert code == 2
    assert "retrieval_depth" in capsys.readouterr().err
