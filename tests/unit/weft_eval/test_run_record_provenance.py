"""A run record says which code, which judge wording and what each question cost — task 44.4.

`source_revision` is the commit of the checkout the installed `weft_eval` was loaded from, and says
so when it came from a wheel instead; a record written in the repository's working directory by an
installed wheel must not borrow that directory's commit. `judge_prompts` digests each judge's
wording. `question_tokens` is what answering each question spent. A record written before this
task reads each as not recorded.
"""

from __future__ import annotations

from pathlib import Path

from weft_eval.run_record import (
    CorpusIdentity,
    RoleTokens,
    SourceRevision,
    build_run_record,
    load_run_record,
    write_run_record,
)
from weft_kernel.resolution import ResolvedPipeline

REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMITTED = (
    REPO_ROOT
    / "eval"
    / "experiments"
    / "whole-corpus-en"
    / "runs"
    / "2f9667c5-1cfa-4b51-b67b-9e69a0bf2cfb.json"
)


def test_a_record_written_before_this_task_reads_each_field_as_not_recorded() -> None:
    # Act
    record = load_run_record(_COMMITTED)

    # Assert
    assert record.source_revision is None
    assert record.judge_prompts is None
    assert record.question_tokens is None


def test_the_three_fields_survive_a_write_and_a_read(tmp_path: Path) -> None:
    # Arrange
    record = build_run_record(
        recorded_at="2026-09-28T00:00:00+00:00",
        resolved_pipeline=ResolvedPipeline(name="index"),
        corpus=CorpusIdentity(name="corpus", digest="c" * 64),
        source_revision=SourceRevision(commit="a" * 40, dirty=True),
        judge_prompts={"answer_correctness": "b" * 64},
        question_tokens={
            "q-1": {
                "generate": RoleTokens(
                    prompt_tokens=120, completion_tokens=12, calls=1, calls_not_reporting=0
                )
            }
        },
    )

    # Act
    write_run_record(record, tmp_path / "run.json")
    loaded = load_run_record(tmp_path / "run.json")

    # Assert
    assert loaded == record
    assert loaded.source_revision is not None
    assert loaded.source_revision.dirty is True
    assert loaded.question_tokens is not None
    assert loaded.question_tokens["q-1"]["generate"].prompt_tokens == 120
