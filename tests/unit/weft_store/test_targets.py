"""A store holds named targets, one live — ledger task **34.3**, Phase 34's contract.

The published kit's target checks run against the in-memory store in `test_memory_store.py`,
through `checks_for`. This file holds what the kit cannot say: the contract's own types, and the
two facts about the in-memory store that only a second handle onto it can show.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_kernel.payload import MediaType, Node
from weft_store.contract import (
    DEFAULT_TARGET,
    STORE_CONTRACT_VERSION,
    EmbeddingIdentity,
    Promotion,
    TargetHolding,
    UnknownTargetError,
    target_name,
)
from weft_store.memory import MemoryStore


def _node(content: str) -> Node:
    return Node.synthetic(content=content, media_type=MediaType.TEXT, reason="targets test")


def _promotion(target: str) -> Promotion:
    return Promotion(
        target=target, at=datetime.now(UTC), by="test", evidence=(), without_evidence=True
    )


def test_the_contract_moved_a_minor_for_the_new_capability() -> None:
    # Assert — `NodeSupersedable`'s precedent: an optional Protocol is a minor for both audiences.
    assert STORE_CONTRACT_VERSION == "3.0.0"
    assert TargetHolding.version == STORE_CONTRACT_VERSION


def test_the_in_memory_store_satisfies_the_capability_structurally() -> None:
    # Assert
    assert isinstance(MemoryStore(), TargetHolding)


def test_an_embedding_identity_is_a_frozen_value() -> None:
    # Arrange
    identity = EmbeddingIdentity(plugin="hash", distribution="weft-rag", model="hash", width=64)

    # Act / Assert
    with pytest.raises(ValidationError):
        identity.width = 128  # type: ignore[misc]
    assert (
        EmbeddingIdentity(
            plugin="openai", distribution="weft-rag", model="text-embedding-3-small", width=None
        ).width
        is None
    )


def test_a_valid_target_name_passes_through_unchanged() -> None:
    # Act / Assert
    assert target_name("w128") == "w128"
    assert target_name("default") == DEFAULT_TARGET


def test_an_unknown_target_carries_the_valid_names_as_a_typed_field() -> None:
    # Act
    error = UnknownTargetError("w256", valid_options=("default", "w128"))

    # Assert — FF12's family: the options are a field, not only prose.
    assert isinstance(error, WeftError)
    assert isinstance(error, UnresolvedNameError)
    assert error.valid_options == ("default", "w128")
    assert "w256" in str(error)


async def test_an_unbound_handle_holds_the_target_that_was_live_when_it_first_read() -> None:
    """Q-C: the live pointer is read once per operation and held for it.

    A handle constructed before a promote and already used keeps serving the target it read,
    so one operation never reads two targets; a handle bound afterwards reads the new live one.
    """
    # Arrange
    store = MemoryStore()
    candidate = await store.bind_target(target_name("w128"))
    await store.add([_node("in default")])
    await candidate.add([_node("in w128"), _node("also in w128")])
    assert await store.count() == 1

    # Act
    await store.promote(_promotion("w128"))

    # Assert
    assert await store.count() == 1
    assert (await store.target_catalogue()).live == "w128"
    fresh = await store.bind_target(target_name("w128"))
    assert await fresh.count() == 2


async def test_two_handles_onto_one_store_share_its_catalogue() -> None:
    # Arrange
    store = MemoryStore()
    candidate = await store.bind_target(target_name("w128"))

    # Act
    await candidate.add([_node("x")])

    # Assert
    assert "w128" in {record.name for record in (await store.target_catalogue()).targets}
    assert (await candidate.target_catalogue()) == (await store.target_catalogue())
