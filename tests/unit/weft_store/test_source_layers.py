"""Ledger task **43.6** — a source records each layer built over it, in the record stores keep.

Phase 43, settled at its opening (2026-09-22): a layer is a pipeline document whose first stage
consumes stored nodes, and a per-source layer publishes per source. So `SourceRecord` carries one
frozen `LayerRecord` per layer — its name, the identity of the document that built it, its status,
its failure, its attempts and when — defaulting to none. A record written by `2.9.0` has no layers,
and a layer field or status this release does not know is a value a newer `weft-rag` wrote, refused
by name the way `R36.3` refuses a failure field.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from weft_kernel.payload import SourceId
from weft_store.contract import (
    LayerRecord,
    LayerStatus,
    SourceFailure,
    SourceRecord,
    UnknownSourceLayerError,
    source_layers,
)
from weft_store.memory import MemoryStore

_WHEN = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


def _record(*layers: LayerRecord) -> SourceRecord:
    return SourceRecord(
        id=SourceId("doc-1"),
        uri="file:///corpus/a.pdf",
        content_hash="hash",
        indexed_at=_WHEN,
        pipeline="index-pdf-text",
        pipeline_identity="base-identity",
        layers=layers,
    )


def _active() -> LayerRecord:
    return LayerRecord(
        name="enrich-with-questions",
        pipeline_identity="layer-identity",
        status=LayerStatus.ACTIVE,
        attempts=1,
        at=_WHEN,
    )


def _failed() -> LayerRecord:
    return LayerRecord(
        name="enrich-with-facts",
        pipeline_identity="facts-identity",
        status=LayerStatus.FAILED,
        failure=SourceFailure(
            error_type="Failed",
            stage="questions",
            message="the model refused",
            attempts=2,
            last_attempt_at=_WHEN,
        ),
        attempts=2,
        at=_WHEN,
    )


def test_a_record_carries_no_layers_unless_given_them() -> None:
    # Act
    record = _record()

    # Assert
    assert record.layers == ()


def test_two_layers_in_two_statuses_round_trip_whole_through_json() -> None:
    # Arrange
    record = _record(_active(), _failed())

    # Act
    back = SourceRecord.model_validate_json(record.model_dump_json())

    # Assert
    assert back == record
    assert [layer.status for layer in back.layers] == [LayerStatus.ACTIVE, LayerStatus.FAILED]


def test_a_layer_status_is_one_of_four() -> None:
    # Assert — no `PENDING`: a layer never run over a source has no record at all. `STALE`
    # (43.21): built, then a source its corpus-scoped tree covered was deleted.
    assert {status.value for status in LayerStatus} == {"indexing", "active", "failed", "stale"}


def test_one_layer_named_twice_on_a_record_is_refused() -> None:
    # Act
    with pytest.raises(ValidationError) as refused:
        _record(_active(), _active())

    # Assert
    assert "enrich-with-questions" in str(refused.value)


def test_stored_layers_read_back_through_the_named_reader() -> None:
    # Arrange
    stored = [_active().model_dump(mode="json"), _failed().model_dump(mode="json")]

    # Act
    layers = source_layers(stored)

    # Assert
    assert layers == (_active(), _failed())


def test_a_layer_field_a_newer_release_wrote_is_refused_by_name() -> None:
    # Arrange
    stored = [{**_active().model_dump(mode="json"), "generation": 3}]

    # Act
    with pytest.raises(UnknownSourceLayerError) as refused:
        source_layers(stored)

    # Assert
    message = str(refused.value)
    assert "'generation'" in message
    assert "newer weft-rag" in message


def test_a_layer_status_a_newer_release_wrote_is_refused_by_name() -> None:
    # Arrange
    stored = [{**_active().model_dump(mode="json"), "status": "retired"}]

    # Act
    with pytest.raises(UnknownSourceLayerError) as refused:
        source_layers(stored)

    # Assert
    message = str(refused.value)
    assert "'retired'" in message
    assert "newer weft-rag" in message


def test_a_stored_layer_failure_is_read_through_the_failure_reader() -> None:
    # Arrange
    written = _failed().model_dump(mode="json")
    written["failure"] = {**written["failure"], "retry_after": "x"}

    # Act
    with pytest.raises(Exception) as refused:
        source_layers([written])

    # Assert — `R36.3`'s refusal, not pydantic's own `extra_forbidden`.
    assert type(refused.value).__name__ == "UnknownSourceFailureError"


def _stale() -> LayerRecord:
    return LayerRecord(
        name="enrich-with-summary",
        pipeline_identity="summary-identity",
        status=LayerStatus.STALE,
        attempts=1,
        at=_WHEN,
    )


def test_a_stale_layer_round_trips_whole_through_json() -> None:
    # Arrange — 43.21, fitness function 19's own property for the new member.
    record = _record(_active(), _stale())

    # Act
    back = SourceRecord.model_validate(record.model_dump(mode="json"))

    # Assert
    assert back == record
    assert back.layers[1].status is LayerStatus.STALE


def test_a_stored_stale_layer_reads_back_through_the_named_reader() -> None:
    # Act
    layers = source_layers([_stale().model_dump(mode="json")])

    # Assert
    assert layers == (_stale(),)


async def test_the_memory_store_keeps_a_stale_layer_whole() -> None:
    # Arrange
    store = MemoryStore()
    record = _record(_active(), _stale())

    # Act
    await store.put_source(record)
    found = await store.get_source(record.id)

    # Assert
    assert found == record


def test_a_layer_written_before_stale_existed_still_reads_back() -> None:
    # Arrange — the literal a `2.11.0` store wrote: every field it knew, and no `stale`.
    written_by_2_11: list[dict[str, object]] = [
        {
            "name": "enrich-with-questions",
            "pipeline_identity": "layer-identity",
            "status": "active",
            "failure": None,
            "attempts": 1,
            "at": "2026-09-22T12:00:00Z",
        }
    ]

    # Act
    layers = source_layers(written_by_2_11)

    # Assert
    assert layers == (_active(),)
    record = _record(*layers)
    assert SourceRecord.model_validate(record.model_dump(mode="json")) == record
