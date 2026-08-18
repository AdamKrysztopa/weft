"""Tests for `weft_qdrant.store`, against a real Qdrant container.

Mirrors `packages/weft-qdrant/src/weft_qdrant/store.py`. Per
`docs/06-phase-0-build.md` step 8, "integration tests must run against the real
container, not a mock, and must be skipped with a clear reason — never silently
passed — when it is absent." `docker compose --profile conformance up -d qdrant`
brings it up; `WEFT_QDRANT_URL` names it. The profile is why it takes an argument:
`compose.yaml`'s opening line promises one container, and this is the second.

**What is here and what is not.** That this store answers the *contract* the same
way pgvector does is `tests/integration/test_store_conformance.py`'s job, and
duplicating it here would be two suites drifting. What belongs here is what is
true of this backend alone: the filter translation as a pure function, the three
Qdrant-shaped facts the contract had to survive (a node with no embedding, a
deterministic point id, a fixed vector width), and the capability set this pack
registers — including the one it deliberately does not have.
"""

import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import MediaType, Node, Produced, SourceId, Vector
from weft_kernel.registry import Registry
from weft_kernel.seam import wrap
from weft_qdrant import NAME, QdrantSettings, QdrantStore, register, to_qdrant_filter
from weft_qdrant.store import VectorWidthMismatchError
from weft_store.contract import (
    Filter,
    FilterOp,
    MetadataFilter,
    NodeStore,
    TextSearch,
    VectorSearch,
)
from weft_store.fields import UnaddressableFieldError

_URL = os.environ.get("WEFT_QDRANT_URL", "http://localhost:6333")


def _node(content: str, *, sources: frozenset[SourceId] = frozenset()) -> Node:
    return Node.synthetic(
        content=content, media_type=MediaType.TEXT, reason="test fixture", sources=sources
    )


async def _unreachable() -> str | None:
    client = AsyncQdrantClient(url=_URL, timeout=2)
    try:
        await client.info()
    except (OSError, ValueError, UnexpectedResponse, ResponseHandlingException) as exc:
        return (
            f"WEFT_QDRANT_URL ({_URL}) is unreachable: {exc}. "
            f"`docker compose --profile conformance up -d qdrant`."
        )
    finally:
        await client.close()
    return None


@pytest.fixture
async def store() -> AsyncIterator[QdrantStore]:
    """A store on collections of its own, deleted afterwards — skipped if Qdrant is absent."""
    reason = await _unreachable()
    if reason is not None:
        pytest.skip(reason)
    settings = QdrantSettings(url=_URL, collection=f"weft_probe_{uuid4().hex[:12]}", vector_size=2)
    instance = QdrantStore(settings)
    yield instance
    await instance.aclose()
    client = AsyncQdrantClient(url=_URL)
    for name in (settings.collection, f"{settings.collection}__sources"):
        if await client.collection_exists(name):
            await client.delete_collection(name)
    await client.close()


async def test_a_node_with_no_embedding_is_an_ordinary_node_here(store: QdrantStore) -> None:
    # Arrange — the property a *named* vector buys. An unnamed vector configuration would
    # require one on every point, and a store that could not hold an unembedded node would
    # fail `NodeStore` outright: nothing says a corpus has been through an embedder.
    plain = _node("never embedded")

    # Act
    await store.add([plain])
    found = await store.get([plain.id])

    # Assert
    assert len(found) == 1
    assert found[0].embedding is None
    assert await store.count() == 1


async def test_the_same_node_written_twice_is_one_point(store: QdrantStore) -> None:
    # Arrange — the point id is a `uuid5` digest of the node id rather than a counter, so a
    # re-index overwrites. A random id would double the corpus on every run, silently.
    node = _node("written twice").with_embedding(Vector(values=(1.0, 0.0)))

    # Act
    await store.add([node])
    await store.add([node])

    # Assert
    assert await store.count() == 1


async def test_an_embedding_of_the_wrong_width_is_refused_naming_both(
    store: QdrantStore,
) -> None:
    # Arrange — Postgres has no such failure: `weft-store` declares its column with no
    # dimension. A Qdrant collection's width is fixed at creation, so this is a decision an
    # operator has to make, and a driver's "expected dim" is not enough to make it from.
    too_wide = _node("too wide").with_embedding(Vector(values=(1.0, 0.0, 0.0)))

    # Act / Assert
    with pytest.raises(VectorWidthMismatchError) as raised:
        await store.add([too_wide])
    message = str(raised.value)
    assert "3-component" in message
    assert "vector_size" in message


async def test_the_registered_plugin_advertises_three_capabilities_and_not_text_search() -> None:
    # Arrange — registered exactly the way the pack registers it, `functools.partial` and
    # all, because that is the object a run assembler's capability check sees.
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-qdrant")
    register(registrar, QdrantSettings())
    registrar.commit()  # `discover()`'s own step: a pack's `register()` never commits itself
    entry = registry.entry(NodeStore, NAME)

    # Act
    instance = entry.factory(None)

    # Assert — derived, never declared: nothing in this pack writes a capability down, and
    # the absent fourth tier is what makes a `needs_store` refusal demonstrable.
    assert isinstance(instance, NodeStore)
    assert isinstance(instance, VectorSearch)
    assert isinstance(instance, MetadataFilter)
    assert not isinstance(instance, TextSearch)


def test_a_filter_tree_translates_into_one_qdrant_filter() -> None:
    # Arrange
    tree = Filter(
        op=FilterOp.AND,
        clauses=(
            Filter(op=FilterOp.CONTAINS, field="lineage.sources", value="doc-1"),
            Filter(op=FilterOp.GT, field="ext.weft-pdf.starts", value=100),
            Filter(
                op=FilterOp.NOT,
                clauses=(Filter(op=FilterOp.EXISTS, field="ext.weft-pdf.backend"),),
            ),
        ),
    )

    # Act
    translated = to_qdrant_filter(tree)

    # Assert — the payload key *is* the filter path, because the payload is the node's own
    # dump; that is what makes this translation a mapping rather than a schema.
    assert translated.must is not None
    membership, ranged, negated = translated.must
    assert isinstance(membership, models.FieldCondition)
    assert membership.key == "lineage.sources"
    assert isinstance(ranged, models.FieldCondition)
    assert isinstance(ranged.range, models.Range)
    assert ranged.range.gt == 100
    assert isinstance(negated, models.Filter)


def test_translating_a_filter_refuses_a_path_no_node_has_before_reaching_qdrant() -> None:
    # Act / Assert — the refusal comes from `weft_store.fields`, so an operator gets the
    # same error whichever backend they are configured against.
    with pytest.raises(UnaddressableFieldError, match="metadata.author"):
        to_qdrant_filter(Filter(op=FilterOp.EQ, field="metadata.author", value="nobody"))


async def test_driving_the_store_through_the_registration_seam_makes_no_blocking_call(
    store: QdrantStore,
) -> None:
    """Fitness function 7(b) against the one path every registered plugin is called through.

    Repair for a reviewer finding against task 2.6. `_connection()` built its
    `AsyncQdrantClient` inline in a coroutine, and that constructor blocks — a synchronous
    version probe, and httpx opening the CA bundle — so the first `NodeStore.run` through
    `weft_kernel.seam.wrap` raised `BlockingCallError` before touching the network. Nothing
    caught it because every other test here calls the store's methods directly, and the
    seam is the only way a registered plugin is ever called.
    """
    # Arrange
    wrapped = wrap(
        store.run, distribution="weft-qdrant", contract="NodeStore", plugin=NAME, stage="store"
    )
    node = _node("through the seam")
    ctx = Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")

    # Act
    outcome = await wrapped([node], ctx)

    # Assert
    assert isinstance(outcome, Produced)
    assert [stored.id for stored in outcome.value] == [node.id]
