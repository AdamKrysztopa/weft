"""A target keeps the embedding identity of its first write, and a query that embeds any other
way is refused before a vector is compared — ledger task **34.4**.

`target` names the target a handle was bound to, or `None` for an unbound handle, which serves the
live one; a handle does not say which target it holds, so the caller that bound it does.

A different model at the same width is the case no store refuses on its own: G22 catches a
width mismatch and nothing catches `text-embedding-3-small` queried against a corpus built with
`-large`, which answers with confident nonsense. The identity is recorded per target, never per
node (owner decision Q5), and an embedder that cannot state one is refused where a target is
explicitly asked for (Q-B).
"""

from __future__ import annotations

import pytest

from weft_embed import HashEmbedder, HashEmbedderConfig
from weft_engine.targets import (
    EmbedderStatesNoIdentityError,
    EmbeddingIdentityMismatchError,
    check_embedding_for_query,
    claim_embedding_for_write,
    embedding_identity_of,
)
from weft_kernel.errors import WeftError
from weft_store.contract import EmbeddingIdentity, target_name
from weft_store.memory import MemoryStore


class _Anonymous:
    """An embedder that states nothing about itself — a third party's, before `34.4`."""


def _identity(width: int) -> EmbeddingIdentity:
    return EmbeddingIdentity(plugin="hash", distribution="weft-rag", model="hash", width=width)


class _NoTargets:
    """A store without `TargetHolding`: nothing to record into, so nothing to check."""


async def test_an_identified_embedder_yields_its_whole_identity() -> None:
    # Act
    identity = await embedding_identity_of(
        HashEmbedder(HashEmbedderConfig(dimension=128)), plugin="hash", distribution="weft-rag"
    )

    # Assert
    assert identity == _identity(128)


async def test_an_embedder_that_states_nothing_yields_none() -> None:
    # Act / Assert
    assert await embedding_identity_of(_Anonymous(), plugin="x", distribution="y") is None


async def test_the_first_write_records_the_identity_and_a_second_one_agrees() -> None:
    # Arrange
    store = MemoryStore()

    # Act
    await claim_embedding_for_write(store, _identity(64), plugin="hash", required=False)
    await claim_embedding_for_write(store, _identity(64), plugin="hash", required=False)

    # Assert
    (default,) = (await store.target_catalogue()).targets
    assert default.embedding == _identity(64)


async def test_writing_with_another_identity_into_a_target_is_refused_naming_both() -> None:
    # Arrange
    store = MemoryStore()
    await claim_embedding_for_write(store, _identity(64), plugin="hash", required=False)

    # Act / Assert
    with pytest.raises(EmbeddingIdentityMismatchError) as caught:
        await claim_embedding_for_write(store, _identity(128), plugin="hash", required=False)
    message = str(caught.value)
    assert isinstance(caught.value, WeftError)
    assert "width 64" in message
    assert "width 128" in message
    assert "'default'" in message


async def test_an_anonymous_embedder_is_refused_where_a_target_is_required() -> None:
    # Arrange
    candidate = await MemoryStore().bind_target(target_name("w128"))

    # Act / Assert
    with pytest.raises(EmbedderStatesNoIdentityError) as caught:
        await claim_embedding_for_write(
            candidate, None, plugin="stranger", required=True, target="w128"
        )
    message = str(caught.value)
    assert "'stranger'" in message
    assert "IdentifiedEmbedder" in message


async def test_an_anonymous_embedder_writes_unrecorded_where_no_target_was_asked_for() -> None:
    # Arrange
    store = MemoryStore()

    # Act
    await claim_embedding_for_write(store, None, plugin="stranger", required=False)

    # Assert
    (default,) = (await store.target_catalogue()).targets
    assert default.embedding is None


async def test_a_store_without_targets_is_left_alone() -> None:
    # Act / Assert — neither raises: there is nowhere to record and nothing to compare.
    await claim_embedding_for_write(_NoTargets(), _identity(64), plugin="hash", required=True)
    await check_embedding_for_query(_NoTargets(), _identity(64), plugin="hash")


async def test_a_query_embedding_another_way_than_the_target_was_built_is_refused() -> None:
    # Arrange
    store = MemoryStore()
    candidate = await store.bind_target(target_name("w128"))
    await claim_embedding_for_write(
        candidate, _identity(128), plugin="hash", required=True, target="w128"
    )
    queried = await store.bind_target(target_name("w128"))

    # Act / Assert
    with pytest.raises(EmbeddingIdentityMismatchError) as caught:
        await check_embedding_for_query(queried, _identity(64), plugin="hash", target="w128")
    message = str(caught.value)
    assert "'w128'" in message
    assert "width 64" in message
    assert "width 128" in message


async def test_a_query_agreeing_with_the_target_or_against_an_unrecorded_one_passes() -> None:
    # Arrange
    recorded = MemoryStore()
    await claim_embedding_for_write(recorded, _identity(64), plugin="hash", required=False)

    # Act / Assert
    await check_embedding_for_query(recorded, _identity(64), plugin="hash")
    await check_embedding_for_query(MemoryStore(), _identity(128), plugin="hash")


async def test_an_anonymous_query_against_a_recorded_target_is_refused() -> None:
    """It cannot be confirmed to match, and the silent mismatch is the failure this prevents."""
    # Arrange
    store = MemoryStore()
    await claim_embedding_for_write(store, _identity(64), plugin="hash", required=False)

    # Act / Assert
    with pytest.raises(EmbedderStatesNoIdentityError):
        await check_embedding_for_query(store, None, plugin="stranger")
