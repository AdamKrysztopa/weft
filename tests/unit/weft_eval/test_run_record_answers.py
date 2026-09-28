"""A run record keeps each question's answer text — task 44.43a.

A head-to-head judge compares two arms' answers after the experiment, so the answers have to be in
the records rather than regenerated. A record written before this reads them as not recorded.
"""

from __future__ import annotations

from pathlib import Path

from weft_eval.run_record import (
    CorpusIdentity,
    build_run_record,
    load_run_record,
    write_run_record,
)
from weft_kernel.resolution import ResolvedPipeline

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_answers_survive_a_write_and_a_read(tmp_path: Path) -> None:
    # Arrange
    record = build_run_record(
        recorded_at="2026-09-28T00:00:00+00:00",
        resolved_pipeline=ResolvedPipeline(name="index"),
        corpus=CorpusIdentity(name="corpus", digest="c" * 64),
        question_answers={"q-1": "The warp is held taut."},
    )

    # Act
    write_run_record(record, tmp_path / "run.json")
    loaded = load_run_record(tmp_path / "run.json")

    # Assert
    assert loaded == record
    assert loaded.question_answers == {"q-1": "The warp is held taut."}


def test_a_record_written_before_this_task_carries_no_answers() -> None:
    # Act
    record = load_run_record(
        REPO_ROOT
        / "eval"
        / "experiments"
        / "whole-corpus-en"
        / "runs"
        / "2f9667c5-1cfa-4b51-b67b-9e69a0bf2cfb.json"
    )

    # Assert
    assert record.question_answers is None
