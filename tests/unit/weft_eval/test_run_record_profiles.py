"""A run record carries each question's profile — task 44.17.

An evidence claim's regime is written in the profile's feature names, so a record has to say what
each question's profile was, under which profiler version, for the claim to be recomputed from it.
A record written before this task reads both as not recorded.
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


def test_profiles_survive_a_write_and_a_read(tmp_path: Path) -> None:
    # Arrange
    record = build_run_record(
        recorded_at="2026-09-28T00:00:00+00:00",
        resolved_pipeline=ResolvedPipeline(name="index"),
        corpus=CorpusIdentity(name="corpus", digest="c" * 64),
        question_profiles={"q-1": {"query.word_count": 5, "query.cue.comparison": True}},
        profiler_version="1",
    )

    # Act
    write_run_record(record, tmp_path / "run.json")
    loaded = load_run_record(tmp_path / "run.json")

    # Assert
    assert loaded == record
    assert loaded.question_profiles is not None
    assert loaded.question_profiles["q-1"]["query.cue.comparison"] is True


def test_a_record_written_before_this_task_carries_no_profiles() -> None:
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
    assert record.question_profiles is None
    assert record.profiler_version is None
