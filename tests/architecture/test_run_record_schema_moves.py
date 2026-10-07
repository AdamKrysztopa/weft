"""A field added to `RunRecord` moves its record schema — carried repair **R20.4**.

`44.4`, `44.17`, `44.43a` and `20.12` each added a `RunRecord` field with no version move, and an
older weft then refused the newer records by pydantic's `extra_forbidden` rather than by name. The
owner's rule (2026-10-07): every field addition moves `RUN_RECORD_SCHEMA_VERSION`. This pins the
field set each schema number means, so a field added without a move fails here, and the move is a
visible line in the diff.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel

from weft_eval.run_record import RUN_RECORD_SCHEMA_VERSION, RunRecord

_SCHEMA_2: Final[frozenset[str]] = frozenset(
    {
        "schema_version",
        "recorded_at",
        "resolved_pipeline",
        "corpus",
        "model_versions",
        "active_distributions",
        "distribution_versions",
        "durations",
        "corpus_digest_basis",
        "query_rung",
        "metrics",
        "question_set_digest",
        "question_set_digest_basis",
        "question_scores",
        "question_axes",
        "question_contributors",
        "question_seconds",
        "token_usage",
        "experiment",
        "target",
        "target_embedding",
        "query_embedding",
        "source_revision",
        "judge_prompts",
        "question_tokens",
        "question_routes",
        "question_profiles",
        "profiler_version",
        "question_answers",
    }
)

#: Each record schema number and the fields a record of it may carry. A new number is a new entry.
FIELDS_BY_SCHEMA: Final[dict[int, frozenset[str]]] = {2: _SCHEMA_2}


def _schema_moved_with_fields(model: type[BaseModel], version: int) -> bool:
    return FIELDS_BY_SCHEMA.get(version) == frozenset(model.model_fields)


def test_the_run_record_fields_are_the_ones_its_schema_number_names() -> None:
    # Arrange
    fields = frozenset(RunRecord.model_fields)

    # Act
    pinned = FIELDS_BY_SCHEMA.get(RUN_RECORD_SCHEMA_VERSION)

    # Assert
    assert pinned is not None, (
        f"RUN_RECORD_SCHEMA_VERSION is {RUN_RECORD_SCHEMA_VERSION}, and nothing here says which "
        "fields that schema carries; add its entry to FIELDS_BY_SCHEMA."
    )
    assert fields == pinned, (
        f"RunRecord's fields differ from schema {RUN_RECORD_SCHEMA_VERSION}'s: added "
        f"{sorted(fields - pinned)}, removed {sorted(pinned - fields)}. A field addition moves "
        "RUN_RECORD_SCHEMA_VERSION, so an older weft refuses the newer record by name."
    )


def test_the_check_can_actually_fail() -> None:
    # Arrange
    class _Grown(RunRecord):
        from_the_future: bool = False

    # Act
    verdict = _schema_moved_with_fields(_Grown, RUN_RECORD_SCHEMA_VERSION)

    # Assert
    assert verdict is False
    assert _schema_moved_with_fields(RunRecord, RUN_RECORD_SCHEMA_VERSION + 1) is False
