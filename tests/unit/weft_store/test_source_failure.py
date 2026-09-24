"""Ledger task **36.0** — a source that failed says so, in the record every store already keeps.

Phase 36, settled at its opening (2026-09-21): a failed source is recorded `FAILED` and carries one
frozen `SourceFailure` — never five loose optional fields, so "no failure" is one fact. A status
this release does not know is a stored value a newer `weft-rag` wrote, and reading it is refused by
name rather than surfacing as `ValueError: 'x' is not a valid SourceStatus`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from weft_kernel.payload import SourceId
from weft_store.contract import (
    SourceFailure,
    SourceRecord,
    SourceStatus,
    UnknownSourceFailureError,
    UnknownSourceStatusError,
    source_failure,
    source_status,
)

_WHEN = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


def _failure(**overrides: object) -> SourceFailure:
    fields: dict[str, object] = {
        "error_type": "Failed",
        "stage": "extract",
        "message": "not valid UTF-8",
        "attempts": 1,
        "last_attempt_at": _WHEN,
    }
    fields.update(overrides)
    return SourceFailure.model_validate(fields)


def test_a_failed_source_carries_its_failure_whole() -> None:
    # Act
    record = SourceRecord(
        id=SourceId("doc-1"),
        uri="file:///corpus/bad.txt",
        content_hash="hash",
        indexed_at=_WHEN,
        pipeline="index-text",
        status=SourceStatus.FAILED,
        failure=_failure(),
    )

    # Assert
    assert record.status is SourceStatus.FAILED
    assert record.failure == _failure()


def test_a_record_that_did_not_fail_carries_no_failure() -> None:
    # Act
    record = SourceRecord(
        id=SourceId("doc-1"),
        uri="file:///corpus/a.txt",
        content_hash="hash",
        indexed_at=_WHEN,
        pipeline="index-text",
    )

    # Assert
    assert record.failure is None


def test_an_unknown_stage_is_stated_rather_than_guessed() -> None:
    # Act
    failure = _failure(stage=None)

    # Assert
    assert failure.stage is None


@pytest.mark.parametrize(
    ("field", "bad"), [("attempts", 0), ("error_type", ""), ("unexpected", "x")]
)
def test_a_failure_record_refuses_what_it_cannot_mean(field: str, bad: object) -> None:
    with pytest.raises(ValidationError):
        _failure(**{field: bad})


def test_a_failure_record_is_frozen() -> None:
    # Arrange
    failure = _failure()

    # Act / Assert
    with pytest.raises(ValidationError):
        failure.attempts = 2  # type: ignore[misc]


def test_every_status_this_release_knows_reads_back() -> None:
    # Act / Assert
    for status in SourceStatus:
        assert source_status(status.value) is status


def test_a_status_written_by_a_newer_release_is_refused_by_name() -> None:
    # Act
    with pytest.raises(UnknownSourceStatusError) as refused:
        source_status("quarantined")

    # Assert — the value it met, and why a store can hold it.
    message = str(refused.value)
    assert "'quarantined'" in message
    assert "newer weft-rag" in message


def test_a_stored_failure_reads_back_through_the_named_reader() -> None:
    # Act
    failure = source_failure(_failure().model_dump(mode="json"))

    # Assert
    assert failure == _failure()


def test_a_failure_a_newer_release_wrote_is_refused_by_name() -> None:
    """`R36.3`: a stored failure with a field this release lacks is refused as a newer release's.

    `R36.3`: `SourceFailure` forbids unknown fields, so a failure a newer `weft-rag` wrote
    reached the operator as pydantic's own error with a documentation URL (`L28.13`'s shape).
    """
    # Arrange
    written = {**_failure().model_dump(mode="json"), "retry_after": "2026-09-22T00:00:00Z"}

    # Act
    with pytest.raises(UnknownSourceFailureError) as refused:
        source_failure(written)

    # Assert
    message = str(refused.value)
    assert "retry_after" in message
    assert "newer weft-rag" in message
