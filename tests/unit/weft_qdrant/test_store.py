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
from pydantic import ValidationError
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import MediaType, Node, Produced, SourceId, Vector
from weft_kernel.registry import Registry
from weft_kernel.seam import wrap
from weft_qdrant import (
    NAME,
    QdrantSettings,
    QdrantStore,
    register,
    search_params_for,
    to_qdrant_filter,
)
from weft_qdrant.settings import PayloadIndexType
from weft_qdrant.store import (
    CollectionSchemaMismatchError,
    QuantizationMismatchError,
    UnsupportedIndexKindError,
    UnsupportedPrecisionError,
    VectorWidthMismatchError,
)
from weft_store.contract import (
    Filter,
    FilterOp,
    MetadataFilter,
    NodeStore,
    TextSearch,
    VectorIndexKind,
    VectorPrecision,
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
async def live_qdrant() -> str:
    """The reachable Qdrant URL, or the reason this test cannot run — **the one skip in this file**.

    Factored out of `store` at task **31.2**, which added tests that build their own settings and
    so cannot take `store`. Both take this instead, and the reachability skip stays a single site:
    repeating it per test would be one more `pytest.skip(` for one condition, which is what
    `.claude/hooks/guard_quality_gates.py` refuses and is right to.
    """
    reason = await _unreachable()
    if reason is not None:
        pytest.skip(reason)
    return _URL


@pytest.fixture
async def store(live_qdrant: str) -> AsyncIterator[QdrantStore]:
    """A store on collections of its own, deleted afterwards — skipped if Qdrant is absent."""
    settings = QdrantSettings(
        url=live_qdrant, collection=f"weft_probe_{uuid4().hex[:12]}", vector_size=2
    )
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
    """A pre-upgrade collection, so tests can check how the store treats data it did not lay out.

    A collection missing one of the two named vectors this store writes, the way `v2.4.0` left
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
    """`QdrantStore` satisfies `TextSearch`, so a retriever wanting a text channel can use Qdrant.

    **The headline, and it is one `isinstance`.** Capability is derived, never declared: a
    retriever asking for a text channel gets this store or is refused by name, and until this task
    every such refusal named Qdrant.
    """
    # Assert
    assert isinstance(store, TextSearch)


async def test_search_text_ranks_by_lexical_match_with_higher_meaning_better(
    store: QdrantStore,
) -> None:
    """`Scored.score` means the same thing in both stores or it means nothing.

    The conformance kit compares two backends' rankings.
    """
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
    """**The same assertion `pgvector`'s BM25 arm carries, against the other backend**.

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
    """The review's own words: tenant filters are applied server-side, not afterwards.

    The review's own words: *"do not fetch a global lexical top-k and apply tenant filters
    afterwards."* The stronger match is the excluded one, so a post-filter and a server-side
    filter give different answers here.
    """
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
    """The corpus is bilingual, and an ASCII-only analyzer would fail on it silently.

    **The corpus this project is built against is bilingual, and this is where an ASCII-only
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
    """**The equivalence trap, named so it is not rediscovered**.

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
    """Task `21.1`'s rule reaching the second backend.

    A number is shown only with its meaning, and the meaning comes from whatever produced it.
    """
    # Assert
    assert "bm25" in store.text_score_semantics.lower()
    assert store.text_score_semantics != store.vector_score_semantics


# --- Task 31.2 — the index kind and precision a collection holds, and the two refusals --------


def _probe_settings(
    url: str,
    *,
    index: VectorIndexKind = VectorIndexKind.HNSW,
    precision: VectorPrecision = VectorPrecision.FLOAT32,
    collection: str | None = None,
) -> QdrantSettings:
    """`QdrantSettings` on a collection nothing else touches."""
    return QdrantSettings(
        url=url,
        collection=collection or f"weft_probe_{uuid4().hex[:12]}",
        vector_size=2,
        index=index,
        precision=precision,
    )


async def _drop_collections(url: str, *names: str) -> None:
    client = AsyncQdrantClient(url=url)
    for name in names:
        for collection in (name, f"{name}__sources"):
            if await client.collection_exists(collection):
                await client.delete_collection(collection)
    await client.close()


def test_the_index_kind_defaults_to_hnsw_because_that_is_what_qdrant_builds() -> None:
    # Arrange / Act / Assert — unlike pgvector, Qdrant has always built an HNSW index once a
    # segment passes its own threshold. The default therefore records what this backend already
    # does rather than changing it; `exact` is the opt-in that forces a full scan per search.
    assert QdrantSettings().index is VectorIndexKind.HNSW


def test_the_precision_defaults_to_float32_which_is_what_a_collection_holds_today() -> None:
    # Arrange / Act / Assert — the owner's Q2 rule: float32 stays the default until a persisted
    # `weft eval` run puts a compressed arm inside the baseline's interval. Phase 29 measured
    # compression on pgvector, never on this backend, so nothing has earned the move here.
    assert QdrantSettings().precision is VectorPrecision.FLOAT32


def test_an_index_kind_qdrant_cannot_serve_is_refused_naming_what_it_does() -> None:
    # Arrange / Act / Assert — Qdrant uses HNSW as its only dense vector index, so `diskann` is a
    # real member of the shared vocabulary this backend does not serve. Refused by name at
    # settings validation, exactly as pgvector refuses it — which is what 31.12 asserts of both.
    with pytest.raises(UnsupportedIndexKindError) as raised:
        QdrantSettings(index=VectorIndexKind.DISKANN)

    message = str(raised.value)
    assert "diskann" in message
    assert "exact" in message
    assert "hnsw" in message
    assert raised.value.valid_options == ("exact", "hnsw")


def test_every_precision_the_vocabulary_names_is_one_this_backend_can_hold() -> None:
    # Arrange / Act / Assert — the two backends overlap on `float32` and `binary` only, and this
    # is the side of that asymmetry Qdrant is on: `float16` is a datatype, `int8` is scalar
    # quantization, `binary` is binary quantization. So this backend refuses no precision today.
    # `UnsupportedPrecisionError` exists for the shape rather than for a current member, and
    # asserting the set here is what keeps 31.12's "both refuse alike" honest about which half
    # of it is currently vacuous on this backend.
    assert set(QdrantSettings.served_precisions()) == {
        precision.value for precision in VectorPrecision
    }
    assert issubclass(UnsupportedPrecisionError, Exception)


async def test_a_collection_is_created_holding_the_configured_precision(
    live_qdrant: str,
) -> None:
    # Arrange
    settings = _probe_settings(live_qdrant, precision=VectorPrecision.INT8)
    store = QdrantStore(settings)

    try:
        # Act — the first write provisions the collection.
        await store.add([_node("configured").with_embedding(Vector(values=(1.0, 0.0)))])

        # Assert — read back off the server rather than off the settings that asked for it, so
        # the two sides of the comparison come from different places and can disagree.
        client = AsyncQdrantClient(url=live_qdrant)
        try:
            info = await client.get_collection(settings.collection)
            assert info.config.quantization_config is not None
        finally:
            await client.close()
    finally:
        await store.aclose()
        await _drop_collections(live_qdrant, settings.collection)


async def test_a_collection_quantised_differently_is_refused_with_both_configurations(
    live_qdrant: str,
) -> None:
    """Owner question 2, settled as a split on G22's own two-branch precedent.

    A collection with *no* quantization is the undecided case and is configured in place. One
    already carrying a *different* quantization is the two-widths case: refused with both named,
    never silently reconfigured over a choice an operator already made.
    """
    # Arrange — a collection this store wrote under int8.
    name = f"weft_probe_{uuid4().hex[:12]}"
    first = QdrantStore(
        _probe_settings(live_qdrant, precision=VectorPrecision.INT8, collection=name)
    )
    second = QdrantStore(
        _probe_settings(live_qdrant, precision=VectorPrecision.BINARY, collection=name)
    )
    try:
        await first.add([_node("int8").with_embedding(Vector(values=(1.0, 0.0)))])

        # Act / Assert — the same collection, opened asking for binary.
        with pytest.raises(QuantizationMismatchError) as raised:
            await second.count()

        message = str(raised.value)
        assert "int8" in message
        assert "binary" in message
    finally:
        await first.aclose()
        await second.aclose()
        await _drop_collections(live_qdrant, name)


async def test_an_exact_store_ranks_the_same_as_an_indexed_one(live_qdrant: str) -> None:
    # Arrange — `exact` forces a full scan per search. The ranking must not change: the whole
    # point of the conformance kit comparing two backends is that an index kind is a
    # speed-against-recall trade-off, never a different answer.
    settings = _probe_settings(live_qdrant, index=VectorIndexKind.EXACT)
    store = QdrantStore(settings)
    try:
        near = _node("near").with_embedding(Vector(values=(1.0, 0.0)))
        far = _node("far").with_embedding(Vector(values=(0.0, 1.0)))
        await store.add([near, far])

        # Act
        ranked = await store.search_vector(Vector(values=(1.0, 0.0)), top_k=2)

        # Assert
        assert [scored.value.content for scored in ranked] == ["near", "far"]
    finally:
        await store.aclose()
        await _drop_collections(live_qdrant, settings.collection)


# --- Task 31.1 — payload indexes, created before the first point is written -------------------


def test_lineage_sources_is_indexed_by_default_because_weft_itself_filters_on_it() -> None:
    """`lineage.sources` is the one key this store filters on without being asked.

    Two sites, both unconditional: `delete_source` narrows by it on every delete, and
    `reconcile` narrows by it on every pass. An operator never writes those filters — the store
    issues them — so an index for them is not a tuning choice an operator should have to discover.
    Every *other* key is theirs to declare.
    """
    # Arrange / Act / Assert
    declared = QdrantSettings().payload_indexes
    assert declared["lineage.sources"] is PayloadIndexType.KEYWORD


def test_content_is_not_indexed_by_default_because_no_shipped_filter_needs_it() -> None:
    # Arrange / Act / Assert — `content` *is* an addressable path and admits `eq`, so indexing it
    # would be legal. It is left out on cost: a keyword index over whole chunk text is paid for on
    # every write, and no filter Weft ships asks for it. An operator who wants one declares it.
    assert "content" not in QdrantSettings().payload_indexes


def test_a_key_no_filter_could_ever_address_is_refused_at_settings_validation() -> None:
    """Requirement 5 reaching a settings block rather than a query.

    The same `parse_field_path` the filter translator uses decides this, so a path refused here is
    refused there for the same reason and with the same message — an operator cannot declare an
    index for a key their filters could never name.
    """
    # Arrange / Act / Assert
    with pytest.raises(UnaddressableFieldError) as raised:
        QdrantSettings(payload_indexes={"lineage.parent": PayloadIndexType.KEYWORD})

    assert "lineage.parent" in str(raised.value)


def test_an_extension_path_may_be_declared_with_the_type_its_operators_need() -> None:
    # Arrange / Act / Assert — an `ext.` path admits ordered operators, and Qdrant cannot infer
    # from the path whether it holds a number or a string. So the operator states the type; that
    # is the whole reason this is a map rather than a list of keys.
    declared = QdrantSettings(
        payload_indexes={"ext.weft-pdf.page": PayloadIndexType.INTEGER}
    ).payload_indexes
    assert declared["ext.weft-pdf.page"] is PayloadIndexType.INTEGER
    # And the default is still carried, not replaced by the operator's map.
    assert declared["lineage.sources"] is PayloadIndexType.KEYWORD


async def test_every_declared_payload_index_exists_before_the_first_point_is_written(
    live_qdrant: str,
) -> None:
    """Qdrant's own constraint, and the reason this is not merely an optimisation.

    Filterable-HNSW edges are generated **only for data indexed after the payload index exists**.
    A payload index created later still answers filters, but the graph it needed was already built
    without it — so the index must exist before the first point, which is why creation lives in the
    same `create_collection` branch rather than anywhere later.
    """
    # Arrange
    settings = _probe_settings(live_qdrant).model_copy(
        update={"payload_indexes": {"ext.weft-pdf.page": PayloadIndexType.INTEGER}}
    )
    store = QdrantStore(settings)

    try:
        # Act — the first write provisions the collection.
        await store.add([_node("first").with_embedding(Vector(values=(1.0, 0.0)))])

        # Assert — read the schema back off the server, not off the settings that asked for it.
        client = AsyncQdrantClient(url=live_qdrant)
        try:
            info = await client.get_collection(settings.collection)
            schema = info.payload_schema
            assert "lineage.sources" in schema, f"payload schema holds {sorted(schema)}"
            assert "ext.weft-pdf.page" in schema, f"payload schema holds {sorted(schema)}"
        finally:
            await client.close()
    finally:
        await store.aclose()
        await _drop_collections(live_qdrant, settings.collection)


async def test_the_default_index_serves_the_filter_delete_source_actually_issues(
    live_qdrant: str,
) -> None:
    # Arrange — the point of indexing `lineage.sources` is that this exact call is fast and
    # correct, so the test drives the real path rather than asserting the index in isolation.
    settings = _probe_settings(live_qdrant)
    store = QdrantStore(settings)
    wanted = SourceId("wanted")
    try:
        kept = _node("kept", sources=frozenset({SourceId("other")})).with_embedding(
            Vector(values=(1.0, 0.0))
        )
        doomed = _node("doomed", sources=frozenset({wanted})).with_embedding(
            Vector(values=(0.0, 1.0))
        )
        await store.add([kept, doomed])

        # Act
        removed = await store.delete_source(wanted)

        # Assert — exactly the node carrying it, and the other untouched.
        assert removed.node_count == 1
        assert [node.id for node in await store.get([kept.id])] == [kept.id]
        # `get` returns a tuple on both backends, and `() == []` is `False` in Python whatever
        # the store did — so this compares lengths rather than a bare literal.
        assert len(await store.get([doomed.id])) == 0
    finally:
        await store.aclose()
        await _drop_collections(live_qdrant, settings.collection)


# --- Task 31.3 — a compressed search rescored against the full-precision vectors --------------


def test_rescore_oversampling_has_no_default_because_nothing_measured_one_on_this_backend() -> None:
    """The sixth owner decision of Phase 31, and the reason it is `None` rather than `4`.

    Phase 29 measured **no Qdrant oversampling arm at all** — `run-29.11.json` carries no
    oversampling figure and `g22-table.md`'s only Qdrant arms are payload-index present and
    absent. The `4` the pgvector store carries is `29.8`'s measurement over a `bit` expression
    index rescored by an outer SQL query; this backend rescores server-side against the
    originals Qdrant stored beside the quantized vectors. Different index, different rescore
    path, unmeasured here.

    Unset is therefore not Weft declining to decide — it leaves in force the `1.0` that
    `qdrant-client`'s own `QuantizationSearchParams.oversampling` documents, exactly as
    `timeout_seconds` and `indexing_threshold` in this same class leave the driver's and the
    server's defaults in force.
    """
    # Arrange / Act / Assert
    assert QdrantSettings().rescore_oversampling is None


def test_an_oversampling_factor_below_one_is_refused_because_it_would_fetch_fewer_than_top_k() -> (
    None
):
    # Arrange / Act / Assert — oversampling is a multiplier on `top_k`, so a value under 1 asks
    # the quantized index for fewer candidates than the caller wants results, and the rescore
    # step could not return `top_k` however well it ranked them. Refused at settings validation,
    # where every other bound in this class is checked.
    with pytest.raises(ValidationError):
        QdrantSettings(rescore_oversampling=0.5)


def test_an_uncompressed_collection_is_sent_no_quantization_parameters_at_all() -> None:
    """`float16` is a datatype, not quantization — the distinction `31.3`'s plan clause got wrong.

    `_quantization_config_for` returns `None` for `float16` exactly as it does for `float32`,
    because float16 is set through the vector `datatype` instead. So a float16 collection holds
    nothing quantized to rescore, and sending `rescore`/`oversampling` against it would name a
    step the server has no reason to take. The plan said rescore is set "for every precision
    other than `float32`"; that is false against code this phase already shipped.
    """
    # Arrange / Act / Assert
    for precision in (VectorPrecision.FLOAT32, VectorPrecision.FLOAT16):
        params = search_params_for(
            index=VectorIndexKind.HNSW, precision=precision, rescore_oversampling=4.0
        )

        assert params is None or params.quantization is None


def test_a_compressed_search_rescores_the_configured_oversampling_against_full_precision() -> None:
    # Arrange / Act / Assert — `int8` and `binary` are the two precisions Qdrant holds as
    # quantization, and both are searched by ranking the quantized index and then re-scoring the
    # winners against the stored originals. `ignore` stays False because the quantized index is
    # exactly what makes the first pass cheap; turning it on would discard the compression the
    # collection was built for.
    for precision in (VectorPrecision.INT8, VectorPrecision.BINARY):
        params = search_params_for(
            index=VectorIndexKind.HNSW, precision=precision, rescore_oversampling=4.0
        )

        assert params is not None
        assert params.quantization is not None
        assert params.quantization.rescore is True
        assert params.quantization.ignore is False
        assert params.quantization.oversampling == 4.0


def test_rescore_is_set_explicitly_rather_than_inherited_when_no_oversampling_is_configured() -> (
    None
):
    # Arrange / Act / Assert — the docs enable rescoring by default for binary quantization only,
    # so `int8` would silently rank by the quantized distance if this were left unset. Weft sets
    # it for both and lets `oversampling` stay `None`, which is the one number no measurement
    # here has earned: Qdrant then applies its own documented 1.0.
    for precision in (VectorPrecision.INT8, VectorPrecision.BINARY):
        params = search_params_for(
            index=VectorIndexKind.HNSW, precision=precision, rescore_oversampling=None
        )

        assert params is not None
        assert params.quantization is not None
        assert params.quantization.rescore is True
        assert params.quantization.oversampling is None


def test_an_exact_search_still_forces_a_full_scan_over_a_compressed_collection() -> None:
    # Arrange / Act / Assert — `exact` and `precision` answer different questions, and 31.2's
    # branch must survive 31.3 rather than be replaced by it: a full scan over a compressed
    # collection is still a full scan, and it is still rescored against the originals.
    params = search_params_for(
        index=VectorIndexKind.EXACT,
        precision=VectorPrecision.BINARY,
        rescore_oversampling=4.0,
    )

    assert params is not None
    assert params.exact is True
    assert params.quantization is not None
    assert params.quantization.rescore is True


async def test_a_binary_collection_returns_the_full_precision_ranking(live_qdrant: str) -> None:
    """The behavioural half: the score returned is the full-precision score, not the quantized one.

    Binary quantization of two opposed unit vectors is where the quantized distance is least
    able to separate them, which is exactly why the rescore step has to decide the order. If
    `rescore` were left to Qdrant's own default this would be the arm that shows it.
    """
    # Arrange
    settings = _probe_settings(live_qdrant, precision=VectorPrecision.BINARY)
    store = QdrantStore(settings)
    try:
        near = _node("near").with_embedding(Vector(values=(1.0, 0.0)))
        far = _node("far").with_embedding(Vector(values=(0.0, 1.0)))
        await store.add([near, far])

        # Act
        ranked = await store.search_vector(Vector(values=(1.0, 0.0)), top_k=2)

        # Assert
        assert [scored.value.content for scored in ranked] == ["near", "far"]
        assert ranked[0].score > ranked[1].score
    finally:
        await store.aclose()
        await _drop_collections(live_qdrant, settings.collection)
