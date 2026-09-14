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
from weft_qdrant.store import CollectionSchemaMismatchError, VectorWidthMismatchError
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


@pytest.fixture(params=["lexical", "content"])
async def legacy_collection(
    request: pytest.FixtureRequest, store: QdrantStore
) -> AsyncIterator[tuple[str, QdrantSettings]]:
    """A collection missing one of the two named vectors this store writes, the way `v2.4.0` left
    one before the lexical vector existed — skipped with `store` when Qdrant is absent. Yields
    the missing vector's name and settings pointing at that collection.
    """
    del store
    missing = str(request.param)
    settings = QdrantSettings(url=_URL, collection=f"weft_legacy_{uuid4().hex[:12]}", vector_size=2)
    dense = {"content": models.VectorParams(size=2, distance=models.Distance.COSINE)}
    sparse = {"lexical": models.SparseVectorParams(modifier=models.Modifier.IDF)}
    client = AsyncQdrantClient(url=_URL)
    await client.create_collection(
        settings.collection,
        vectors_config={} if missing == "content" else dense,
        sparse_vectors_config=None if missing == "lexical" else sparse,
    )
    yield missing, settings
    for name in (settings.collection, f"{settings.collection}__sources"):
        if await client.collection_exists(name):
            await client.delete_collection(name)
    await client.close()


async def test_a_collection_missing_a_vector_this_store_writes_is_refused_naming_the_remedy(
    legacy_collection: tuple[str, QdrantSettings],
) -> None:
    """`R22.7`: writing to such a collection failed with the backend's raw 400."""
    # Arrange
    missing, settings = legacy_collection
    legacy = QdrantStore(settings)
    node = _node("the kestrel hovers").with_embedding(Vector(values=(1.0, 0.0)))

    # Act
    with pytest.raises(CollectionSchemaMismatchError) as raised:
        await legacy.add([node])
    await legacy.aclose()

    # Assert
    message = str(raised.value)
    assert f"collection '{settings.collection}' has no vector named '{missing}'" in message
    assert "[packs.qdrant] collection" in message
    assert "re-index" in message


async def test_a_search_on_such_a_collection_is_refused_before_the_backend_answers(
    legacy_collection: tuple[str, QdrantSettings],
) -> None:
    # Arrange
    missing, settings = legacy_collection
    legacy = QdrantStore(settings)

    # Act
    with pytest.raises(CollectionSchemaMismatchError) as raised:
        await legacy.search_text("kestrel", top_k=1)
    await legacy.aclose()

    # Assert
    assert f"has no vector named '{missing}'" in str(raised.value)


async def test_the_registered_plugin_advertises_all_four_capabilities() -> None:
    # Arrange — registered exactly the way the pack registers it, `functools.partial` and
    # all, because that is the object a run assembler's capability check sees.
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-qdrant")
    register(registrar, QdrantSettings())
    registrar.commit()  # `discover()`'s own step: a pack's `register()` never commits itself
    entry = registry.entry(NodeStore, NAME)

    # Act
    instance = entry.factory(None)

    # Assert — derived, never declared: nothing in this pack writes a capability down.
    #
    # **This asserted `not isinstance(instance, TextSearch)` until ledger 21.8**, and the sentence
    # under it said the absent fourth tier was what made a `needs_store` refusal demonstrable.
    # `weft_store.memory.MemoryStore` carries that now — `NodeStore` and `VectorSearch` and
    # nothing else — and `docs/02-extension-model.md` §1 records which premises of the refusal
    # expired and which one merely moved.
    assert isinstance(instance, NodeStore)
    assert isinstance(instance, VectorSearch)
    assert isinstance(instance, MetadataFilter)
    assert isinstance(instance, TextSearch)


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


# --- task 21.8: the second backend satisfies TextSearch ---------------------------------------
#
# **`02` §1: "a contract with one implementation is a guess."** `TextSearch` has had exactly one
# since task 2.5, and `01`'s own over-fitting guard names the pair it is proven on — *"pgvector and
# Qdrant, which have genuinely different shapes, and a store that only Postgres can satisfy fails
# that test just as loudly."* This is where that stops being an aspiration for the text arm.
#
# **Nothing here downloads a model.** The lexical encoding is statistical: an analyzer that folds
# case and splits on word boundaries, document-side BM25 term weights computed by this adapter, and
# collection IDF applied by Qdrant's own `modifier: idf`. `02`'s *stores never embed* holds — a
# store that reached for a transformer to satisfy `TextSearch` would be the coupling that rule
# exists to forbid.


async def test_the_store_advertises_text_search_at_all(store: QdrantStore) -> None:
    """**The headline, and it is one `isinstance`.** Capability is derived, never declared: a
    retriever asking for a text channel gets this store or is refused by name, and until this task
    every such refusal named Qdrant."""
    # Assert
    assert isinstance(store, TextSearch)


async def test_search_text_ranks_by_lexical_match_with_higher_meaning_better(
    store: QdrantStore,
) -> None:
    """`Scored.score` means the same thing in both stores or it means nothing — the conformance
    kit compares two backends' rankings."""
    # Arrange
    await store.add(
        [
            _node("the microkernel knows nothing about pdfs chunking embeddings or graphs"),
            _node("every capability is a plugin discovered through python entry points"),
            _node("pipelines are data derivable from other pipelines"),
        ]
    )

    # Act
    results = await store.search_text("plugin capability", top_k=3)

    # Assert
    assert results, "a matching corpus returns matches"
    assert results[0].value.content.startswith("every capability")
    scores = [hit.score for hit in results]
    assert scores == sorted(scores, reverse=True)
    assert all(score > 0.0 for score in scores)


async def test_qdrant_weighs_a_rare_term_above_one_every_document_carries(
    store: QdrantStore,
) -> None:
    """**The same assertion `pgvector`'s BM25 arm carries, against the other backend.**

    It is the one that says *BM25* rather than *some lexical ranking*: the weight of a term has to
    depend on how many documents hold it. Here that comes from Qdrant's `modifier: idf` applied to
    the sparse dot product, not from anything this adapter computes — which is the point, because
    a collection statistic is the one thing a per-document encoder cannot know.
    """
    # Arrange — 'shared' is in all three; 'sporadic' is in exactly one.
    await store.add(
        [
            _node("shared shared sporadic vocabulary"),
            _node("shared shared shared ordinary vocabulary"),
            _node("shared shared shared other vocabulary"),
        ]
    )

    # Act
    ubiquitous = await store.search_text("shared", top_k=3)
    rare = await store.search_text("sporadic", top_k=3)

    # Assert
    assert ubiquitous and rare
    assert rare[0].score > ubiquitous[0].score


async def test_search_text_narrows_by_a_filter_the_server_evaluates(store: QdrantStore) -> None:
    """The review's own words: *"do not fetch a global lexical top-k and apply tenant filters
    afterwards."* The stronger match is the excluded one, so a post-filter and a server-side
    filter give different answers here."""
    # Arrange
    wanted = _node("plugin capability", sources=frozenset({SourceId("keep")}))
    louder = _node(
        "plugin plugin plugin capability capability", sources=frozenset({SourceId("drop")})
    )
    await store.add([wanted, louder])

    # Act
    unfiltered = await store.search_text("plugin capability", top_k=5)
    narrowed = await store.search_text(
        "plugin capability",
        top_k=5,
        filter=Filter(op=FilterOp.CONTAINS, field="lineage.sources", value="keep"),
    )

    # Assert
    assert len(unfiltered) == 2
    assert unfiltered[0].value.content == louder.content, "unfiltered, the louder one wins"
    assert [scored.value.content for scored in narrowed] == [wanted.content]


async def test_nothing_matching_is_an_empty_ranking_rather_than_a_failure(
    store: QdrantStore,
) -> None:
    """`TextSearch`'s own emptiness rule, which both backends owe identically."""
    # Arrange
    await store.add([_node("pipelines are data")])

    # Act
    results = await store.search_text("xenopsychology", top_k=5)

    # Assert
    assert results == []


async def test_the_analyzer_keeps_a_polish_word_whole(store: QdrantStore) -> None:
    """**The corpus this project is built against is bilingual, and this is where an ASCII-only
    analyzer would fail silently.** `09` §4's V1 body is not English; `pgvector`'s text arm uses
    Postgres's `simple` configuration precisely because it folds case and splits on word boundaries
    and stems nothing, which is the one behaviour that is equally honest in both languages. A
    tokenizer splitting on `[a-z]+` would cut `zażółć` into three fragments matching nothing a
    reader wrote, and would raise nothing at all.
    """
    # Arrange
    await store.add([_node("zażółć gęślą jaźń"), _node("entirely unrelated content")])

    # Act
    results = await store.search_text("gęślą", top_k=2)

    # Assert
    assert len(results) == 1
    assert results[0].value.content == "zażółć gęślą jaźń"


async def test_the_average_document_length_is_a_disclosed_approximation_that_reaches_the_score(
    store: QdrantStore,
) -> None:
    """**The equivalence trap, named so it is not rediscovered.**

    Qdrant's own BM25 defaults `avg_doc_len` to **256**, and that is an *encoding* parameter — not
    the mean length of anybody's corpus. Collection IDF updates as documents arrive; document-side
    length weights do **not**, because they were computed when each point was written. So the value
    is either measured against the real corpus or explicitly disclosed, and this project discloses
    it: a setting, with its approximation stated where an operator reads it.

    Asserted by `L9.79`'s rule — a value whose whole job is to travel from `[packs.qdrant]` to a
    weight must be read off the far end, or the wire is untested along its length.
    """
    # Arrange — two stores over one corpus, differing only in the declared mean length.
    short_mean = QdrantSettings(
        url=_URL,
        collection=f"weft_probe_{uuid4().hex[:12]}",
        vector_size=2,
        bm25_avg_doc_len=4.0,
    )
    other = QdrantStore(short_mean)
    corpus = [_node("alpha beta gamma delta epsilon zeta eta theta"), _node("alpha")]
    await store.add(corpus)
    await other.add(corpus)

    # Act
    try:
        default_mean = await store.search_text("alpha", top_k=2)
        declared = await other.search_text("alpha", top_k=2)
    finally:
        await other.aclose()
        client = AsyncQdrantClient(url=_URL)
        for name in (short_mean.collection, f"{short_mean.collection}__sources"):
            if await client.collection_exists(name):
                await client.delete_collection(name)
        await client.close()

    # Assert — the long document is penalised harder when the declared mean is short.
    assert len(default_mean) == 2 and len(declared) == 2
    long_under_default = next(h.score for h in default_mean if h.value.content.startswith("alpha "))
    long_under_declared = next(h.score for h in declared if h.value.content.startswith("alpha "))
    assert long_under_declared < long_under_default, (
        "b-weighted length normalisation must actually read the configured mean"
    )


async def test_the_store_says_what_its_text_score_means(store: QdrantStore) -> None:
    """Task `21.1`'s rule reaching the second backend: a number is shown only with its meaning,
    and the meaning comes from whatever produced it."""
    # Assert
    assert "bm25" in store.text_score_semantics.lower()
    assert store.text_score_semantics != store.vector_score_semantics
