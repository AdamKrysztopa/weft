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

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, SourceId, Vector
from weft_qdrant import QdrantSettings, QdrantStore
from weft_qdrant.store import TargetCollectionMissingError
from weft_store.contract import (
    DEFAULT_TARGET,
    Promotion,
    ReconcileMode,
    TargetInUseError,
    WriterBusyError,
    WriterClaim,
    target_name,
)

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
    """The targets catalogue is created by its first write, never by opening or reading.

    Found when Qdrant was OOM-killed twice at `34.7`: every store that opened created
    `<collection>__targets`, and every older test fixture drops only the pair it knew of, so each
    gate run leaked hundreds of catalogues — 1,025 of 1,039 collections, 8.3 GiB at start. The
    catalogue is created by the first thing that writes to it, never by opening or reading.
    """
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


async def test_a_target_another_open_store_has_written_to_cannot_be_dropped(
    settings: QdrantSettings,
) -> None:
    """A drop is refused while another handle's write lease on the target is live.

    Carried repair **R34.10**: Qdrant has no session lock, so a handle that has written to a
    target holds an expiring lease on it, and a drop is refused while that lease is live —
    the refusal pgvector and the graph store make through an advisory lock.
    """
    # Arrange
    store = QdrantStore(settings)
    await store.add([_node("live", (1.0, 0.0, 0.0))])
    writer = await QdrantStore(settings).bind_target(target_name("w256"))
    await writer.add([_node("candidate", (0.0, 1.0, 0.0))])

    # Act / Assert
    with pytest.raises(TargetInUseError) as caught:
        await store.drop_target(target_name("w256"))
    assert "'w256'" in str(caught.value)
    await writer.aclose()
    await store.drop_target(target_name("w256"))
    assert "w256" not in {record.name for record in (await store.target_catalogue()).targets}
    await store.aclose()


async def test_a_lease_left_by_a_writer_that_never_closed_expires(
    settings: QdrantSettings,
) -> None:
    """A crashed writer's lease expires rather than blocking a drop forever.

    A writer that crashed never releases its lease, so the lease carries its own expiry
    (`[packs.qdrant] target_lease_seconds`) rather than blocking a drop forever.
    """
    # Arrange
    short = settings.model_copy(update={"target_lease_seconds": 1})
    store = QdrantStore(short)
    await store.add([_node("live", (1.0, 0.0, 0.0))])
    abandoned = await QdrantStore(short).bind_target(target_name("w128"))
    await abandoned.add([_node("candidate", (0.0, 1.0, 0.0))])

    # Act
    await asyncio.sleep(1.5)
    await store.drop_target(target_name("w128"))

    # Assert
    assert "w128" not in {record.name for record in (await store.target_catalogue()).targets}
    await store.aclose()


async def test_reading_a_store_nothing_wrote_to_creates_no_collection(
    settings: QdrantSettings,
) -> None:
    """Carried repair R43.2, found at `43.0`.

    A project whose `pipelines/` held a Qdrant document and whose index wrote to pgvector left
    `<collection>` and `<collection>__sources` behind. `weft index` reaches every store a project
    names, through the participants check and the automatic reconcile, and opening the default
    target created the pair. `R34.3` made the catalogue lazy and left the pair eager. A read of a
    store nothing wrote to answers empty.
    """
    # Arrange
    store = QdrantStore(settings)
    ctx = Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")

    # Act
    catalogue = await store.target_catalogue()
    sources = await store.list_sources()
    counted = await store.count()
    hits = await store.search_vector(Vector(values=(1.0, 0.0, 0.0)), top_k=3)
    report = await store.reconcile(ctx, ReconcileMode.REPAIR)
    await store.aclose()
    client = AsyncQdrantClient(url=_QDRANT_URL)
    created = [
        name
        for name in (settings.collection, f"{settings.collection}__sources")
        if await client.collection_exists(name)
    ]
    await client.close()

    # Assert
    assert catalogue.live == DEFAULT_TARGET
    assert list(sources) == []
    assert counted == 0
    assert list(hits) == []
    assert report.removed == 0
    assert created == []


async def test_the_first_write_still_creates_the_pair(settings: QdrantSettings) -> None:
    """The collections a read no longer creates are created by the first write.

    R43.2's control: the collections a read no longer creates are created by the first write,
    and a read after it sees what was written.
    """
    # Arrange
    store = QdrantStore(settings)

    # Act
    await store.add([_node("live", (1.0, 0.0, 0.0))])
    counted = await store.count()
    await store.aclose()
    client = AsyncQdrantClient(url=_QDRANT_URL)
    nodes_exist = await client.collection_exists(settings.collection)
    await client.close()

    # Assert
    assert nodes_exist
    assert counted == 1


def _writer(pid: int, command: str) -> WriterClaim:
    return WriterClaim(host="test-host", pid=pid, started_at=datetime.now(UTC), command=command)


async def test_a_writer_claim_holds_past_its_lease_while_its_holder_never_writes(
    settings: QdrantSettings,
) -> None:
    """Holding a target renews its claim even through a handle that never writes.

    Carried repair R43.18, measured before the red: the claim was renewed only by `add`, so a
    `weft delete` or `weft reconcile` holding it through a handle that never writes lost it at
    `target_lease_seconds`, and a second writer was admitted beside it.
    """
    # Arrange
    short = settings.model_copy(update={"target_lease_seconds": 1})
    holder, other = QdrantStore(short), QdrantStore(short)
    await holder.claim_writer(_writer(1001, "weft reconcile"))

    # Act
    await asyncio.sleep(2.5)

    # Assert — still held; then released, and the next writer gets in.
    with pytest.raises(WriterBusyError, match="weft reconcile"):
        await other.claim_writer(_writer(1002, "weft index"))
    await holder.release_writer()
    await other.claim_writer(_writer(1002, "weft index"))
    await other.release_writer()
    await holder.aclose()
    await other.aclose()


async def test_a_writer_claim_whose_holder_stopped_without_releasing_still_expires(
    settings: QdrantSettings,
) -> None:
    """Renewing the lease stops when its holder does.

    The lease is what frees a store a crashed writer held, so renewing it must stop when
    the holder does.
    """
    # Arrange
    short = settings.model_copy(update={"target_lease_seconds": 1})
    holder, other = QdrantStore(short), QdrantStore(short)
    await holder.claim_writer(_writer(1001, "weft index"))
    await holder.aclose()

    # Act
    await asyncio.sleep(1.5)
    await other.claim_writer(_writer(1002, "weft index"))

    # Assert
    await other.release_writer()
    await other.aclose()
