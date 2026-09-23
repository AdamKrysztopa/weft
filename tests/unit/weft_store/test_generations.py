"""Ledger task **43.14** — a store can hold layer generations through one optional Protocol.

A corpus-scoped layer (a RAPTOR tree over every document) is misleading half-built, so it is built
as a **generation**: its nodes are written as members of one generation, invisible to every search
until the generation is published, and published whole. `GenerationHolding` is optional, like
`TargetHolding` before it (`34.3`), so the store contract moves a minor, `2.10.0 → 2.11.0`.
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from weft_store.contract import (
    STORE_CONTRACT_VERSION,
    GenerationHolding,
    GenerationId,
    GenerationRecord,
    GenerationStatus,
    UnknownGenerationError,
)
from weft_store.memory import MemoryStore

_WHEN = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)


def test_the_contract_moved_a_minor_for_the_new_capability() -> None:
    # Assert — `TargetHolding`'s precedent: a new optional Protocol is a minor for both audiences.
    assert STORE_CONTRACT_VERSION == "2.12.0"
    assert GenerationHolding.version == STORE_CONTRACT_VERSION


def test_a_generation_is_building_or_published() -> None:
    # Assert — a stale layer is a fact about sources, derived from their layer records (`43.15`),
    # never a status a store has to be told.
    assert {status.value for status in GenerationStatus} == {"building", "published"}


def test_a_generation_record_round_trips_through_json() -> None:
    # Arrange
    record = GenerationRecord(
        id=GenerationId("g-1"),
        layer="enrich-with-raptor",
        status=GenerationStatus.PUBLISHED,
        opened_at=_WHEN,
        published_at=_WHEN,
    )

    # Act / Assert
    assert GenerationRecord.model_validate_json(record.model_dump_json()) == record


def test_a_generation_record_forbids_an_unknown_field() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        GenerationRecord.model_validate(
            {
                "id": "g-1",
                "layer": "x",
                "status": "building",
                "opened_at": _WHEN.isoformat(),
                "members": 3,
            }
        )


def test_an_unknown_generation_error_carries_the_generations_that_exist() -> None:
    # Act
    refused = UnknownGenerationError("no such generation", valid_options=("g-1", "g-2"))

    # Assert
    assert refused.valid_options == ("g-1", "g-2")


def test_the_in_memory_store_holds_no_generations() -> None:
    # Assert — it has no text search or metadata filter to hide an unpublished member from, so it
    # is not offered the capability rather than offered half of it.
    assert not isinstance(MemoryStore(), GenerationHolding)


def test_a_writer_busy_refusal_names_the_writer_that_holds_the_store() -> None:
    """Ledger **43.18**, the contract half: the refusal carries the holder's claim whole."""
    # Arrange
    from weft_store.contract import SingleWriter, WriterBusyError, WriterClaim

    holder = WriterClaim(host="laptop", pid=4242, started_at=_WHEN, command="weft index corpus")

    # Act
    refused = WriterBusyError(holder)

    # Assert
    assert refused.holder == holder
    for fact in ("'weft index corpus'", "pid 4242", "laptop", "2026-09-23T12:00:00"):
        assert fact in str(refused), fact
    assert SingleWriter.version == "2.12.0"
