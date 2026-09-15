"""A run record carries per-question latency and per-role tokens — ledger task **33.7**.

The one `RunRecord` schema change Phase 33 makes, absorbing Phase 30's task 30.4. Both fields
default to `None`, which means *not recorded*: every record written before this task measured
neither, and a default of `{}` or `0.0` would be mistakable for a run that measured and found
nothing — task 10.22's rule for `durations`, one field over.
"""

import json
from collections.abc import Mapping
from pathlib import Path

from weft_eval.run_record import (
    PerQuestionSeconds,
    QuestionKey,
    RoleTokens,
    RunRecord,
    build_run_record,
    corpus_identity,
    load_run_record,
)
from weft_kernel.resolution import ResolvedPipeline


def _record(
    *,
    question_seconds: PerQuestionSeconds | None = None,
    token_usage: Mapping[str, RoleTokens] | None = None,
) -> RunRecord:
    return build_run_record(
        recorded_at="2026-09-15T12:00:00Z",
        resolved_pipeline=ResolvedPipeline(name="index", stages=()),
        corpus=corpus_identity("corpus", ("doc-a",)),
        question_seconds=question_seconds,
        token_usage=token_usage,
    )


def test_a_record_with_latency_and_tokens_round_trips(tmp_path: Path) -> None:
    # Arrange
    record = _record(
        question_seconds=PerQuestionSeconds(
            keyed_by=QuestionKey.QUESTION_ID, seconds={"fetch-001": 0.25, "fetch-002": 1.5}
        ),
        token_usage={
            "generate": RoleTokens(
                prompt_tokens=150, completion_tokens=25, calls=2, calls_not_reporting=0
            )
        },
    )
    path = tmp_path / "run.json"

    # Act
    path.write_text(record.model_dump_json(), encoding="utf-8")
    loaded = load_run_record(path)

    # Assert
    assert loaded == record


def test_a_record_written_before_the_fields_existed_still_loads_as_not_recorded(
    tmp_path: Path,
) -> None:
    # Arrange
    older = json.loads(_record().model_dump_json())
    older.pop("question_seconds", None)
    older.pop("token_usage", None)
    path = tmp_path / "older.json"
    path.write_text(json.dumps(older), encoding="utf-8")

    # Act
    loaded = load_run_record(path)

    # Assert
    assert loaded.question_seconds is None
    assert loaded.token_usage is None
