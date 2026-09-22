"""The Qdrant store holds targets as collection pairs — ledger task **34.5**, with `34.2`'s half.

`default` is the configured pair, `<collection>` and `<collection>__sources`, exactly as a
collection written before targets existed already has it. Any other target is the pair
`<collection>__t_<name>` and `<collection>__t_<name>__sources`. The live pointer and each target's
recorded embedding identity are points in a third, vector-less collection,
`<collection>__targets`, read when a store opens.

**Why there is no alias, measured rather than assumed** (`34.0`, 2026-09-22, Qdrant v1.12.4): an
alias named like an existing collection is refused (`409 … already exists`), and nothing renames a
collection. So `default` could only have become an alias after a window in which its name
resolved to nothing. Writes through an alias also follow a switch between requests, which would
have split one ingest across two targets. Every name here is a concrete collection.

**A candidate commits to the width of its first vector**, not to `vector_size`. A migration to a
wider embedder is the case this phase exists for, and `vector_size` describes `default`.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from weft_kernel.payload import MediaType, Node, SourceId, Vector
from weft_qdrant import QdrantSettings, QdrantStore
from weft_qdrant.store import TargetCollectionMissingError
from weft_store.contract import DEFAULT_TARGET, Promotion, target_name

_QDRANT_URL = os.environ.get("WEFT_QDRANT_URL", "http://localhost:6333")


def _node(content: str, values: tuple[float, ...]) -> Node:
    node = Node.synthetic(
        content=content,
        media_type=MediaType.TEXT,
        reason="qdrant targets",
        sources=frozenset({SourceId("doc")}),
    )
    return node.with_embedding(Vector(values=values))


def _promotion(target: str) -> Promotion:
    return Promotion(
        target=target, at=datetime.now(UTC), by="test", evidence=(), without_evidence=True
    )


def _collections_of(base: str) -> tuple[str, ...]:
    """Every collection name a test here can create, so the fixture drops each by exact name."""
    names = [base, f"{base}__sources", f"{base}__targets"]
    for target in ("w128", "w256"):
        names += [f"{base}__t_{target}", f"{base}__t_{target}__sources"]
    return tuple(names)


@pytest.fixture
async def settings() -> AsyncIterator[QdrantSettings]:
    client = AsyncQdrantClient(url=_QDRANT_URL, timeout=2)
    try:
        await client.info()
    except (OSError, ValueError, UnexpectedResponse, ResponseHandlingException) as exc:
        await client.close()
        pytest.skip(
            f"WEFT_QDRANT_URL ({_QDRANT_URL}) is unreachable: {exc}. "
            f"`docker compose --profile conformance up -d qdrant`."
        )
    configured = QdrantSettings(
        url=_QDRANT_URL, collection=f"weft_targets_{uuid4().hex[:12]}", vector_size=3
    )
    try:
        yield configured
    finally:
        for name in _collections_of(configured.collection):
            if await client.collection_exists(name):
                await client.delete_collection(name)
        await client.close()


async def test_a_collection_written_before_targets_existed_reads_as_default_live(
    settings: QdrantSettings,
) -> None:
    """`34.2` on Qdrant: the configured pair is `default`, with no operator action."""
    # Arrange — the 2.8.0 shape: the pair holds a point, and there is no catalogue collection.
    written = QdrantStore(settings)
    await written.add([_node("written before targets", (1.0, 0.0, 0.0))])
    await written.aclose()
    client = AsyncQdrantClient(url=_QDRANT_URL)
    if await client.collection_exists(f"{settings.collection}__targets"):
        await client.delete_collection(f"{settings.collection}__targets")
    await client.close()
    upgraded = QdrantStore(settings)

    # Act
    catalogue = await upgraded.target_catalogue()
    count = await upgraded.count()
    await upgraded.aclose()

    # Assert
    assert catalogue.live == DEFAULT_TARGET
    assert catalogue.previous is None
    assert [record.name for record in catalogue.targets] == [DEFAULT_TARGET]
    assert count == 1


async def test_a_candidate_is_its_own_pair_committed_to_its_first_vectors_width(
    settings: QdrantSettings,
) -> None:
    # Arrange
    store = QdrantStore(settings)
    await store.add([_node("live", (1.0, 0.0, 0.0))])
    candidate = await store.bind_target(target_name("w128"))

    # Act — width 5 beside default's 3: `vector_size` describes `default`, not a candidate.
    await candidate.add([_node("candidate", (0.0, 1.0, 0.0, 0.0, 1.0))])
    await candidate.aclose()
    client = AsyncQdrantClient(url=_QDRANT_URL)
    info = await client.get_collection(f"{settings.collection}__t_w128")
    candidate_points = await client.count(f"{settings.collection}__t_w128")
    aliases = await client.get_aliases()
    await client.close()

    # Assert
    vectors = info.config.params.vectors
    assert isinstance(vectors, dict)
    assert next(iter(vectors.values())).size == 5
    assert candidate_points.count == 1
    assert await store.count() == 1
    assert not [
        alias for alias in aliases.aliases if alias.alias_name.startswith(settings.collection)
    ]
    await store.aclose()


async def test_a_catalogued_target_whose_collection_is_gone_is_refused_not_recreated(
    settings: QdrantSettings,
) -> None:
    # Arrange
    store = QdrantStore(settings)
    await store.add([_node("live", (1.0, 0.0, 0.0))])
    candidate = await store.bind_target(target_name("w128"))
    await candidate.add([_node("candidate", (0.0, 1.0, 0.0))])
    await candidate.aclose()
    client = AsyncQdrantClient(url=_QDRANT_URL)
    await client.delete_collection(f"{settings.collection}__t_w128")
    reopened = await QdrantStore(settings).bind_target(target_name("w128"))

    # Act / Assert
    with pytest.raises(TargetCollectionMissingError) as caught:
        await reopened.count()
    message = str(caught.value)
    assert "'w128'" in message
    assert f"{settings.collection}__t_w128" in message
    assert not await client.collection_exists(f"{settings.collection}__t_w128")
    await client.close()
    await reopened.aclose()
    await store.aclose()


async def test_a_store_opened_after_a_promote_reads_the_new_live_target(
    settings: QdrantSettings,
) -> None:
    """Q-C: the live pointer is read when a store opens and held for that store's lifetime."""
    # Arrange
    store = QdrantStore(settings)
    await store.add([_node("live", (1.0, 0.0, 0.0))])
    candidate = await store.bind_target(target_name("w128"))
    await candidate.add([_node("one", (0.0, 1.0, 0.0)), _node("two", (0.0, 0.0, 1.0))])
    await candidate.aclose()

    # Act
    await store.promote(_promotion("w128"))
    opened_after = QdrantStore(settings)
    count_after = await opened_after.count()
    await opened_after.aclose()

    # Assert
    assert await store.count() == 1
    assert count_after == 2
    assert (await store.target_catalogue()).live == "w128"
    await store.aclose()


async def test_reading_a_store_creates_no_catalogue_collection(settings: QdrantSettings) -> None:
    """Found when Qdrant was OOM-killed twice at `34.7`: every store that opened created
    `<collection>__targets`, and every older test fixture drops only the pair it knew of, so each
    gate run leaked hundreds of catalogues — 1,025 of 1,039 collections, 8.3 GiB at start. The
    catalogue is created by the first thing that writes to it, never by opening or reading."""
    # Arrange
    store = QdrantStore(settings)

    # Act
    await store.add([_node("live", (1.0, 0.0, 0.0))])
    catalogue = await store.target_catalogue()
    await store.aclose()
    client = AsyncQdrantClient(url=_QDRANT_URL)
    catalogue_exists = await client.collection_exists(f"{settings.collection}__targets")
    await client.close()

    # Assert
    assert catalogue.live == DEFAULT_TARGET
    assert not catalogue_exists
