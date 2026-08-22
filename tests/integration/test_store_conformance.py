"""The store conformance kit — one suite, two backends, run against both real containers.

Ledger task **2.6**: "the store contract is satisfied by a second backend of a
genuinely different shape, so it is no longer a guess." A guess is what a
contract with one implementation is, and the only way to stop guessing is to
write the assertions *once* and make two engines that share no code answer them
identically. So every test below takes a `store` fixture it cannot identify:
parameterised over `pgvector` and `qdrant`, it asks the contract's questions and
never the backend's.

`01` → *Runtime shape* is what this discharges — "the contract is proven on
**pgvector and Qdrant**, which have genuinely different shapes, and a store that
only Postgres can satisfy fails that test just as loudly."

**The shapes really are different, and the suite is where that shows.** Postgres
stores a row per node, keyed by the node's own content digest, and can be asked
for text ranking. Qdrant stores a point keyed by a UUID (its ids are integers or
UUIDs, never a sha256 string), fixes a collection's vector width at creation,
holds source records in a second, vector-less collection, and offers no scored
lexical ranking at all. The one test below that names a backend is the one whose
subject *is* that asymmetry.

**Recorded rather than hidden: this is a repository asset, not a published one.** A third
party writing a store cannot import these assertions — they live under `tests/`, so they
are in no distribution, and adding a third backend means an entry in the `store` fixture's
parameters here rather than a factory of their own. `01` → *Runtime shape* names a
conformance kit and pack authors' unit tests as two consumers of the same **in-memory
store**; it does not settle whether the assertions themselves ship, and neither
`.phase2-design.md` nor any ledger task does. Publishing them would mean deciding what a
`weft_store.conformance` module may depend on — `weft_pdf`'s `ExtModel`, `weft_cli`'s run
assembler and `weft_retrieve`'s payload types are all imported below and none of them may
become a `weft-store` dependency — and what its own version means while **G9 is Open**.
That is a design decision, and it is left as one.

**Against the real containers, skipped with a reason when they are absent** —
`docs/06-phase-0-build.md` step 8's discipline, applied per backend rather than
per module, so an operator with only Postgres up still gets the pgvector half.
`docker compose up -d` brings Postgres; `docker compose --profile conformance up
-d qdrant` brings the other, which sits behind a profile because `compose.yaml`'s
opening line promises one container.
"""

import os
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from functools import partial
from typing import cast
from uuid import uuid4

import psycopg
import pytest
from pydantic import SecretStr
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from weft_cli.run_services import StoreCapabilityMissingError, check_store_capabilities
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, Outcome, Produced, SourceId, Vector
from weft_kernel.registry import Registry
from weft_kernel.runner import StageSpec
from weft_pdf import PdfPages
from weft_qdrant import QdrantSettings, QdrantStore
from weft_retrieve.contract import Retriever
from weft_retrieve.payload import Candidates, QuerySet
from weft_store import register_ext_model
from weft_store.contract import (
    Filter,
    FilterOp,
    MetadataFilter,
    NodeStore,
    Page,
    ReconcileMode,
    SourceRecord,
    SourceStatus,
    TextSearch,
    VectorSearch,
)
from weft_store.fields import FilterOpMismatchError, UnaddressableFieldError
from weft_store.pgvector_store import PgVectorSettings, PgVectorStore

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")
_QDRANT_URL = os.environ.get("WEFT_QDRANT_URL", "http://localhost:6333")

#: `weft-pdf` ships a real `ExtModel` with a string field and a field of numbers, which is
#: exactly the pair the operator set needs to be exercised over — and it belongs to a
#: distribution neither store depends on, so the round trip proves the documented extension
#: point rather than a store's own type. `docs/02-extension-model.md` names this call as the
#: one a pack makes so its nodes survive a store; nothing registers it implicitly.
register_ext_model(PdfPages)

_SOURCE_A = SourceId("source-a")
_SOURCE_B = SourceId("source-b")

#: What the `store` fixture yields. The union rather than `NodeStore` itself, and the reason
#: is the contract family's own documented quirk: `version` is declared under
#: `if TYPE_CHECKING:` so that it never joins `__protocol_attrs__`, which means a store class
#: satisfies `NodeStore` at runtime and not to a static checker. Nothing below branches on
#: which of the two it has — that is the property this suite exists to demonstrate — and
#: `isinstance` against a capability Protocol is still what every capability claim rests on.
type ConformanceStore = PgVectorStore | QdrantStore


def _node(
    content: str,
    *,
    sources: frozenset[SourceId],
    pages: PdfPages | None = None,
    embedding: Vector | None = None,
) -> Node:
    node = Node.synthetic(
        content=content, media_type=MediaType.TEXT, reason="conformance kit", sources=sources
    )
    if pages is not None:
        node = node.with_ext(pages)
    return node if embedding is None else node.with_embedding(embedding)


def _conformance_context() -> Context:
    """A `Context` for `reconcile`, which takes one and — for a node store — reads nothing
    from it. A pack that converges by running model calls will; this one has no reason to.
    """
    return Context(tenant_id="conformance", run_id="run-1", trace_id="trace-1", locale="en")


def _corpus() -> tuple[Node, ...]:
    """Three nodes chosen so that every operator in `FilterOp` separates them differently."""
    return (
        _node(
            "alpha",
            sources=frozenset({_SOURCE_A}),
            pages=PdfPages(backend="pypdf", starts=(0,)),
            embedding=Vector(values=(1.0, 0.0, 0.0)),
        ),
        _node(
            "beta",
            sources=frozenset({_SOURCE_A, _SOURCE_B}),
            pages=PdfPages(backend="pdfplumber", starts=(0, 500)),
            embedding=Vector(values=(0.0, 1.0, 0.0)),
        ),
        _node("gamma", sources=frozenset({_SOURCE_B})),
    )


async def _postgres_unreachable() -> str | None:
    try:
        conn = await psycopg.AsyncConnection.connect(_DSN, connect_timeout=2)
    except psycopg.OperationalError as exc:
        return f"WEFT_DATABASE_URL ({_DSN}) is unreachable: {exc}. `docker compose up -d`."
    await conn.close()
    return None


async def _pgvector_store() -> PgVectorStore:
    instance = PgVectorStore(PgVectorSettings(dsn=SecretStr(_DSN)))
    await instance.count()  # provisions the schema through the public API
    conn = await psycopg.AsyncConnection.connect(_DSN, autocommit=True)
    async with conn.cursor() as cur:
        await cur.execute("TRUNCATE weft_nodes, weft_sources")
    await conn.close()
    return instance


async def _qdrant_unreachable() -> str | None:
    client = AsyncQdrantClient(url=_QDRANT_URL, timeout=2)
    try:
        await client.info()
    except (OSError, ValueError, UnexpectedResponse, ResponseHandlingException) as exc:
        return (
            f"WEFT_QDRANT_URL ({_QDRANT_URL}) is unreachable: {exc}. "
            f"`docker compose --profile conformance up -d qdrant`."
        )
    finally:
        await client.close()
    return None


def _qdrant_settings() -> QdrantSettings:
    """A collection of its own per test, so two runs of this suite never share one."""
    return QdrantSettings(
        url=_QDRANT_URL, collection=f"weft_conformance_{uuid4().hex[:12]}", vector_size=3
    )


async def _drop(settings: QdrantSettings) -> None:
    """Delete both collections the store provisioned — the fixture's own cleanup.

    The test owns this rather than the store, exactly as
    `tests/unit/weft_store/test_pgvector_store.py` opens its own connection to
    truncate: a `drop()` on the store would be a destructive method that exists
    only because a test wanted one, and it would be reachable from a pipeline.
    """
    client = AsyncQdrantClient(url=settings.url)
    for name in (settings.collection, f"{settings.collection}__sources"):
        if await client.collection_exists(name):
            await client.delete_collection(name)
    await client.close()


@pytest.fixture(params=("pgvector", "qdrant"))
async def store(request: pytest.FixtureRequest) -> AsyncIterator[ConformanceStore]:
    """A provisioned, empty store of whichever backend this parameter names."""
    backend = cast(str, request.param)
    if backend == "pgvector":
        reason = await _postgres_unreachable()
        if reason is not None:
            pytest.skip(reason)
        pg = await _pgvector_store()
        yield pg
        await pg.aclose()
        return
    reason = await _qdrant_unreachable()
    if reason is not None:
        pytest.skip(reason)
    settings = _qdrant_settings()
    qdrant = QdrantStore(settings)
    yield qdrant
    await qdrant.aclose()
    await _drop(settings)


async def _all(page: Page[Node]) -> frozenset[str]:
    return frozenset(node.content for node in page.items)


async def test_a_node_round_trips_through_the_store_with_its_lineage_and_its_ext(
    store: ConformanceStore,
) -> None:
    # Arrange
    nodes = _corpus()

    # Act
    await store.add(nodes)
    await store.flush()
    found = await store.get([nodes[1].id])

    # Assert
    assert len(found) == 1
    assert found[0].content == "beta"
    assert found[0].lineage.sources == frozenset({_SOURCE_A, _SOURCE_B})
    assert found[0].ext_as(PdfPages) == PdfPages(backend="pdfplumber", starts=(0, 500))
    assert found[0].embedding is not None


async def test_scan_and_count_see_every_stored_node_whatever_order_a_backend_walks_in(
    store: ConformanceStore,
) -> None:
    # Arrange
    await store.add(_corpus())

    # Act
    page = await store.scan()
    total = await store.count()

    # Assert — a set, not a sequence: the contract promises pages, never an order, and the
    # two backends genuinely differ (Postgres walks the content digest, Qdrant a UUID).
    assert frozenset(node.content for node in page.items) == frozenset({"alpha", "beta", "gamma"})
    assert page.next_cursor is None
    assert total == 3


async def test_delete_source_removes_exactly_the_nodes_carrying_it(store: ConformanceStore) -> None:
    # Arrange
    await store.add(_corpus())
    await store.put_source(
        SourceRecord(
            id=_SOURCE_B,
            uri="file:///corpus/b.txt",
            content_hash="hash-b",
            indexed_at=datetime.now(UTC),
            pipeline="conformance",
        )
    )

    # Act
    removed = await store.delete_source(_SOURCE_B)

    # Assert
    assert removed.source_id == _SOURCE_B
    assert removed.node_count == 2
    assert frozenset(node.content for node in (await store.scan()).items) == frozenset({"alpha"})
    assert await store.get_source(_SOURCE_B) is None


async def test_reconcile_finishes_a_deletion_that_was_interrupted(
    store: ConformanceStore,
) -> None:
    """Task **5.1b**'s property, on both real backends: a deletion that started and did not
    end is finished by the *next* pass, not restarted from nothing.

    The interruption is constructed rather than raced: a `DELETING` tombstone plus the nodes
    it should have taken with it is exactly the state a `delete_source` killed between its two
    statements leaves behind, and it is the state `SourceRecord.status` was given a
    `DELETING` member for. That the backlog is a *row* rather than a cursor is the whole of
    why `02` §1 can promise a pass resumes rather than restarts — see
    `PgVectorStore.reconcile`'s own docstring.
    """
    # Arrange — two nodes carrying _SOURCE_B, and a tombstone saying its deletion began.
    await store.add(_corpus())
    await store.put_source(
        SourceRecord(
            id=_SOURCE_B,
            uri="file:///corpus/b.txt",
            content_hash="hash-b",
            indexed_at=datetime.now(UTC),
            pipeline="conformance",
            status=SourceStatus.DELETING,
        )
    )

    # Act
    report = await store.reconcile(_conformance_context(), ReconcileMode.REPAIR)
    again = await store.reconcile(_conformance_context(), ReconcileMode.REPAIR)

    # Assert — the first pass finished the job; the second found nothing and is a no-op.
    assert (report.examined, report.removed, report.converged) == (1, 2, True)
    assert (again.examined, again.removed, again.converged) == (0, 0, True)
    assert frozenset(node.content for node in (await store.scan()).items) == frozenset({"alpha"})
    assert await store.get_source(_SOURCE_B) is None


async def test_reconcile_leaves_a_healthy_store_alone_on_either_backend(
    store: ConformanceStore,
) -> None:
    """The other half, and the one that would have been a corpus-erasing bug: a node store
    holds the primary data, so a source record it has never been given is not evidence that
    its nodes are orphans. Nothing is removed here, and `full` removes no more than `repair`.
    """
    # Arrange — three nodes and no source records at all, which is what `weft index` leaves.
    await store.add(_corpus())

    # Act
    report = await store.reconcile(_conformance_context(), ReconcileMode.FULL)

    # Assert
    assert (report.removed, report.backfilled, report.converged) == (0, 0, True)
    assert await store.count() == 3


async def test_estimate_reports_zero_model_calls_on_either_backend(
    store: ConformanceStore,
) -> None:
    """Task **5.1c**'s own floor, on both real backends: a node store holds the primary data,
    so `full` has nothing to backfill and `estimate` says so honestly rather than guessing at
    a number — see `PgVectorStore.estimate`'s own docstring, which owns the argument for both.
    """
    # Arrange — three nodes, no tombstones: nothing pending either.
    await store.add(_corpus())

    # Act
    estimate = await store.estimate(_conformance_context(), ReconcileMode.FULL)

    # Assert
    assert (estimate.pending, estimate.model_calls) == (0, 0)


async def test_estimate_counts_the_identical_tombstones_reconcile_itself_examines(
    store: ConformanceStore,
) -> None:
    """`estimate`'s own `pending` must never disagree with what `reconcile` actually examines —
    both read the same backlog, so a tombstone `estimate` counts is a tombstone `reconcile`
    finishes.
    """
    # Arrange — an interrupted deletion, the same fixture `test_reconcile_finishes_a_deletion_
    # that_was_interrupted` above plants.
    await store.add(_corpus())
    await store.put_source(
        SourceRecord(
            id=_SOURCE_B,
            uri="file:///corpus/b.txt",
            content_hash="hash-b",
            indexed_at=datetime.now(UTC),
            pipeline="conformance",
            status=SourceStatus.DELETING,
        )
    )

    # Act
    estimate = await store.estimate(_conformance_context(), ReconcileMode.REPAIR)
    report = await store.reconcile(_conformance_context(), ReconcileMode.REPAIR)

    # Assert
    assert estimate.pending == 1
    assert report.examined == 1


async def test_a_source_record_round_trips_and_is_listed(store: ConformanceStore) -> None:
    # Arrange
    record = SourceRecord(
        id=_SOURCE_A,
        uri="file:///corpus/a.txt",
        content_hash="hash-a",
        indexed_at=datetime.now(UTC),
        pipeline="conformance",
    )

    # Act
    await store.put_source(record)
    found = await store.get_source(_SOURCE_A)
    listed = await store.list_sources()

    # Assert
    assert found is not None
    assert found.uri == "file:///corpus/a.txt"
    assert found.content_hash == "hash-a"
    assert tuple(item.id for item in listed) == (_SOURCE_A,)


async def test_search_vector_ranks_by_cosine_similarity_on_either_backend(
    store: ConformanceStore,
) -> None:
    # Arrange
    await store.add(_corpus())
    assert isinstance(store, VectorSearch)

    # Act
    ranked = await store.search_vector(Vector(values=(0.0, 1.0, 0.0)), top_k=2)

    # Assert
    assert [scored.value.content for scored in ranked] == ["beta", "alpha"]
    assert ranked[0].score == pytest.approx(1.0, abs=1e-3)


#: One case per member of `FilterOp`, as `(filter, the contents that must match)`. The point
#: is not the individual answers but that two engines sharing no code produce the same ones:
#: a `Filter` is data, and data that means two things is not data.
_OPERATOR_CASES: tuple[tuple[str, Filter, frozenset[str]], ...] = (
    ("eq", Filter(op=FilterOp.EQ, field="content", value="alpha"), frozenset({"alpha"})),
    (
        "ne",
        Filter(op=FilterOp.NE, field="content", value="alpha"),
        frozenset({"beta", "gamma"}),
    ),
    (
        "in",
        Filter(op=FilterOp.IN, field="ext.weft-pdf.backend", value=("pypdf", "poppler")),
        frozenset({"alpha"}),
    ),
    (
        "lt",
        Filter(op=FilterOp.LT, field="ext.weft-pdf.starts", value=1),
        frozenset({"alpha", "beta"}),
    ),
    (
        "lte",
        Filter(op=FilterOp.LTE, field="ext.weft-pdf.starts", value=0),
        frozenset({"alpha", "beta"}),
    ),
    ("gt", Filter(op=FilterOp.GT, field="ext.weft-pdf.starts", value=100), frozenset({"beta"})),
    (
        # A fractional bound, which is the case both translators' number handling exists for
        # — `weft_qdrant.store._as_number` casts to `float`, pgvector compares `::numeric` —
        # and the case the AST refused until a reviewer finding against 2.6 was repaired.
        # Every other case here uses an integer bound, which is exactly why nothing caught it.
        "gt-fractional",
        Filter(op=FilterOp.GT, field="ext.weft-pdf.starts", value=99.5),
        frozenset({"beta"}),
    ),
    (
        "gte",
        Filter(op=FilterOp.GTE, field="ext.weft-pdf.starts", value=500),
        frozenset({"beta"}),
    ),
    (
        "exists",
        Filter(op=FilterOp.EXISTS, field="ext.weft-pdf.backend"),
        frozenset({"alpha", "beta"}),
    ),
    (
        "contains",
        Filter(op=FilterOp.CONTAINS, field="lineage.sources", value=_SOURCE_B),
        frozenset({"beta", "gamma"}),
    ),
    (
        "and",
        Filter(
            op=FilterOp.AND,
            clauses=(
                Filter(op=FilterOp.CONTAINS, field="lineage.sources", value=_SOURCE_A),
                Filter(op=FilterOp.EXISTS, field="ext.weft-pdf.backend"),
                Filter(op=FilterOp.NE, field="content", value="alpha"),
            ),
        ),
        frozenset({"beta"}),
    ),
    (
        "or",
        Filter(
            op=FilterOp.OR,
            clauses=(
                Filter(op=FilterOp.EQ, field="content", value="alpha"),
                Filter(op=FilterOp.EQ, field="content", value="gamma"),
            ),
        ),
        frozenset({"alpha", "gamma"}),
    ),
    (
        "not",
        Filter(
            op=FilterOp.NOT,
            clauses=(Filter(op=FilterOp.EXISTS, field="ext.weft-pdf.backend"),),
        ),
        frozenset({"gamma"}),
    ),
)


@pytest.mark.parametrize(
    ("label", "filter_", "expected"),
    _OPERATOR_CASES,
    ids=[case[0] for case in _OPERATOR_CASES],
)
async def test_every_operator_means_the_same_thing_to_both_backends(
    store: ConformanceStore, label: str, filter_: Filter, expected: frozenset[str]
) -> None:
    # Arrange
    await store.add(_corpus())
    assert isinstance(store, MetadataFilter)

    # Act
    page = await store.matching(filter_)

    # Assert
    assert await _all(page) == expected, f"'{label}' disagrees between backends"


async def test_a_filter_reaches_vector_search_rather_than_being_ignored(
    store: ConformanceStore,
) -> None:
    # Arrange
    await store.add(_corpus())
    assert isinstance(store, VectorSearch)

    # Act
    ranked = await store.search_vector(
        Vector(values=(0.0, 1.0, 0.0)),
        top_k=5,
        filter=Filter(op=FilterOp.EQ, field="content", value="alpha"),
    )

    # Assert
    assert [scored.value.content for scored in ranked] == ["alpha"]


async def test_a_field_no_node_can_have_is_refused_by_name_on_either_backend(
    store: ConformanceStore,
) -> None:
    # Arrange
    assert isinstance(store, MetadataFilter)
    nonsense = Filter(op=FilterOp.EQ, field="metadata.author", value="nobody")

    # Act / Assert
    with pytest.raises(UnaddressableFieldError, match="metadata.author"):
        await store.matching(nonsense)


async def test_an_operator_a_field_cannot_carry_is_refused_by_name_on_either_backend(
    store: ConformanceStore,
) -> None:
    # Arrange
    assert isinstance(store, MetadataFilter)
    wrong = Filter(op=FilterOp.EQ, field="lineage.sources", value=_SOURCE_A)

    # Act / Assert
    with pytest.raises(FilterOpMismatchError, match="contains"):
        await store.matching(wrong)


class _HybridRetriever:
    """The `hybrid` shape: a retriever that will call both search arms, so it says so."""

    needs_store: tuple[type, ...] = (VectorSearch, TextSearch)

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[Candidates]:
        del ctx
        return Produced(value=Candidates(origin=payload.origin))


async def test_the_two_backends_advertise_different_capabilities_and_nobody_declared_them() -> None:
    # Arrange
    reason = await _postgres_unreachable()
    if reason is not None:
        pytest.skip(reason)
    pg = await _pgvector_store()
    qdrant = QdrantStore(_qdrant_settings())

    # Act — `isinstance`, which is the whole mechanism: no store writes a capability down.
    # Neither instance is ever connected: a capability is a fact about a class, and asking a
    # deployment would make this test about whether a container was up.
    try:
        pg_capabilities = frozenset(
            name
            for name, protocol in (
                ("VectorSearch", VectorSearch),
                ("TextSearch", TextSearch),
                ("MetadataFilter", MetadataFilter),
            )
            if isinstance(pg, protocol)
        )
        qdrant_capabilities = frozenset(
            name
            for name, protocol in (
                ("VectorSearch", VectorSearch),
                ("TextSearch", TextSearch),
                ("MetadataFilter", MetadataFilter),
            )
            if isinstance(qdrant, protocol)
        )
    finally:
        await pg.aclose()
        await qdrant.aclose()

    # Assert — the asymmetry is the point: Qdrant's text matching is a filter predicate, not
    # a scored ranking, so it satisfies three tiers and not the fourth.
    assert pg_capabilities == frozenset({"VectorSearch", "TextSearch", "MetadataFilter"})
    assert qdrant_capabilities == frozenset({"VectorSearch", "MetadataFilter"})


async def test_a_hybrid_run_against_qdrant_is_refused_before_any_stage_runs() -> None:
    # Arrange — a real `QdrantStore`, never connected: the refusal happens at run assembly,
    # before any stage runs, which is exactly before anything would have opened a connection.
    qdrant = QdrantStore(_qdrant_settings())
    registry = Registry()
    registry.add(Retriever, "hybrid", _HybridRetriever, distribution="weft-retrieve")
    registry.add(
        NodeStore,
        "pgvector",
        partial(PgVectorStore, PgVectorSettings(dsn=SecretStr(_DSN))),
        distribution="weft-store",
    )
    registry.add(
        NodeStore, "qdrant", partial(QdrantStore, QdrantSettings()), distribution="weft-qdrant"
    )
    specs: Sequence[StageSpec] = (StageSpec(id="retrieve", contract=Retriever, name="hybrid"),)

    # Act / Assert — named, with where to get what is missing, and no degradation offered.
    with pytest.raises(StoreCapabilityMissingError) as raised:
        check_store_capabilities(
            specs,
            registry=registry,
            store=qdrant,
            store_contract=NodeStore,
            store_name="qdrant",
        )
    message = str(raised.value)
    assert "TextSearch" in message
    assert "'pgvector' (weft-store)" in message
