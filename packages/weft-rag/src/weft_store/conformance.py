"""The store conformance kit — the assertions a store must satisfy, importable by anyone.

Ledger task **26.4**, argued in `12-roadmap.md` §5e. These twenty-five checks were
`tests/integration/test_store_conformance.py` and ran only inside this repository. A contract with
one implementation is a guess, and the only way to stop guessing is to write the assertions **once**
and make engines that share no code answer them identically — which is worth nothing to a third
party who cannot reach them. Four documents promised a kit an author could install; the tree held
one only this checkout could run.

**How to use it.** Build your store, hand it to the checks its capabilities cover, and run them
however you like — this module imports no test runner, so `pytest`, `unittest` and a plain script
are all fine::

    from weft_store.conformance import (
        check_scan_and_count_see_every_stored_node,
    )

    await check_scan_and_count_see_every_stored_node(my_store)

Each check returns `None` and raises `AssertionError` naming what disagreed. Nothing here
provisions a store, truncates one, or cleans up after itself: the caller owns the store's
lifecycle, because a kit that created its own would only work for stores it already knows how to
create.

**Plain async functions, and that is a measurement rather than a taste.** `pytest` appears in none
of `weft-rag`'s dependency lists, so a pytest base class or plugin here would make it a runtime
dependency of the wheel — or hide the kit behind an extra every user of it has to remember. For the
same reason nothing below imports `qdrant_client`, `psycopg`, `pgvector` or `weft_qdrant`;
`tests/unit/weft_store/test_conformance_is_publishable.py` walks this module's imports and refuses
them by name, the drivers included even though two are runtime dependencies, because a kit that
names a driver has stopped asking the contract's questions.

**The kit imports no capability pack at all, and that is `L21.1` learned twice.** Importing any
module of a pack executes that pack's `__init__`, which is where `register()` lives, so it pulls
every plugin the pack registers and every driver those need. `weft_pdf` is the case that bit:
neither `from weft_pdf import PdfPages` nor `from weft_pdf.document import PdfPages` survives an
install without the `[pdf]` extra, and a probe that tried both in one interpreter reported the
second as fine — a failed package import leaves a partial module in `sys.modules` and the next
attempt sails past it. Running the kit from a real bare venv is what found it. `ConformanceFact`
below is the answer: the kit declares its own extension model rather than borrowing one.

**`_require` rather than `assert`, and that is `python -O`.** The interpreter strips `assert`
statements under `-O`, so a conformance kit written with them would report every store as
conforming the moment a caller ran their suite optimised — the worst failure available to a thing
whose only job is to refuse. A test file may use `assert` because a test never runs under `-O`,
which is why ruff's `S101` is scoped to `tests/` here (`L8.37`); this module ships inside the wheel
and is run by callers this repository will never see.

**The store parameter is typed by what each check calls.** Before this task every assertion carried
`ConformanceStore = PgVectorStore | QdrantStore` — a union of two concrete classes — so a stranger's
store could not satisfy the annotation whatever it implemented. Each check now names the narrowest
protocol it needs, composed below from the capability protocols `weft_store` already publishes.
Which checks a given store should be asked is task `26.5`; this module answers *what* the
assertions are, not *which* apply.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import Final, Protocol, cast, runtime_checkable

from weft_blob.contract import BlobUri
from weft_blob.payload import BlobRef
from weft_extract.payload import BoundingBox, PageSpan, TableGrid
from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.payload import ExtModel, MediaType, Node, SourceId, Vector
from weft_kernel.registry import DuplicateRegistrationError
from weft_store.contract import (
    Filter,
    FilterOp,
    MetadataFilter,
    NodeStore,
    NodeSupersedable,
    Page,
    Reconcilable,
    ReconcileMode,
    SourceRecord,
    SourceStatus,
    SupersedeNarrowsSourcesError,
    VectorSearch,
)
from weft_store.fields import FilterOpMismatchError, UnaddressableFieldError
from weft_store.rehydrate import register_ext_model

__all__ = [
    "OPERATOR_CASES",
    "FilterableSearchableStore",
    "FilterableStore",
    "ReconcilableStore",
    "SearchableStore",
    "SupersedableStore",
    "ConformanceFact",
    "NotAStoreError",
    "checks_for",
    "unsupported_checks",
    "conformance_corpus",
    "register_conformance_ext_models",
]


class ConformanceFact(ExtModel):
    """The `ExtModel` this kit attaches, so the ext round-trip has something to be about.

    **Declared here rather than borrowed from a capability pack, and that is the whole of
    `L21.1`.** These checks first used `weft_pdf`'s `PdfPages`, which is the natural choice —
    it is a real shipped fact and the suite already had it. But importing *any* module of a
    pack executes that pack's `__init__`, which is where `register()` lives, which imports
    every plugin the pack registers and therefore every driver they need. So
    `from weft_pdf.document import PdfPages` raises `ModuleNotFoundError: No module named
    'pdfplumber'` on an install without the `[pdf]` extra — measured against a real bare venv,
    and *not* what a naive probe reports, because a failed `import weft_pdf` leaves a
    partially-initialised module in `sys.modules` that makes the next attempt appear to work.

    The kit needs *an* extension model to prove ext survives a round trip. It does not need
    anybody's in particular, and depending on one couples a contract's conformance suite to a
    capability pack's optional dependency.
    """

    __namespace__ = "weft-store-conformance"
    __schema_version__ = "1.0.0"

    backend: str


class NotAStoreError(WeftError):
    """What was handed to the kit does not satisfy `NodeStore`, so it is not a smaller store.

    **The distinction this class exists for.** A store without `NodeSupersedable` is a *smaller*
    store and gets fewer checks; that is the whole point of `checks_for`. A thing without
    `NodeStore` is not a store at all, and answering it with an empty list would be `01`'s *an
    empty answer is not a fact about the world* — it would read as *you passed everything I have*
    rather than *you handed me the wrong object*.
    """


#: The optional capability each check needs beyond `NodeStore`, derived from the protocol its own
#: `store` parameter is annotated with — so the selector and the checks cannot disagree about what
#: a check requires. `L5.6`: two sides of a comparison that come from one source cannot disagree,
#: and here that is the property wanted rather than the defect, because the annotation **is** the
#: requirement. A check typed against a composed protocol needs that protocol's extra member; one
#: typed `NodeStore` needs nothing more.
_CAPABILITY_OF: Final[Mapping[str, tuple[str, str]]] = {
    "SearchableStore": ("VectorSearch", "search_vector"),
    "FilterableSearchableStore": ("MetadataFilter", "matching"),
    "FilterableStore": ("MetadataFilter", "matching"),
    "SupersedableStore": ("NodeSupersedable", "supersede"),
    "ReconcilableStore": ("Reconcilable", "reconcile"),
}

#: Every method `NodeStore` publishes. A thing missing any of them is refused rather than filtered.
_NODE_STORE_MEMBERS: Final[tuple[str, ...]] = (
    "add",
    "count",
    "delete_source",
    "flush",
    "get",
    "get_source",
    "list_sources",
    "put_source",
    "run",
    "scan",
)


def _published_checks() -> tuple[Callable[..., Awaitable[None]], ...]:
    """Every `check_*` this module publishes, in a stable order.

    Read off the module rather than from a hand-kept list, so a check added here is offered without
    anybody remembering to register it — the producing-side-without-a-consuming-side shape `L5.15`
    names, refused by construction.
    """
    found: list[Callable[..., Awaitable[None]]] = []
    for name, value in sorted(globals().items()):
        if name.startswith("check_") and callable(value):
            found.append(cast("Callable[..., Awaitable[None]]", value))
    return tuple(found)


def _capability_needed(check: Callable[..., Awaitable[None]]) -> tuple[str, str] | None:
    """`(protocol name, the method that proves it)` a check needs beyond `NodeStore`, or `None`."""
    annotation = check.__annotations__.get("store")
    name = getattr(annotation, "__name__", str(annotation))
    return _CAPABILITY_OF.get(name)


def _require_a_store(store: object) -> None:
    missing = [m for m in _NODE_STORE_MEMBERS if not callable(getattr(store, m, None))]
    if missing:
        raise NotAStoreError(
            f"{type(store).__name__} does not satisfy NodeStore — it is missing "
            f"{', '.join(missing)}. Every check in this kit needs the base contract, so this is "
            "not a store with fewer capabilities; it is not a store. `weft_store.contract."
            "NodeStore` names the members it must have."
        )


def checks_for(store: object) -> tuple[Callable[..., Awaitable[None]], ...]:
    """The published checks `store` can answer, in a stable order.

    A store is offered a check when it satisfies the capability that check's own `store` parameter
    is annotated with — capability derived from the methods the object actually has, never
    declared, which is `02` → *Capability is derived, never declared* applied to the kit itself.

    Raises `NotAStoreError` when `store` does not satisfy `NodeStore`. Use `unsupported_checks` to
    see what was left out and why; **nothing is skipped silently**, because a kit that quietly ran
    fewer checks would mean less the smaller the store is, and the author would never learn which
    half they had proved.
    """
    _require_a_store(store)
    return tuple(
        check
        for check in _published_checks()
        if (needed := _capability_needed(check)) is None
        or callable(getattr(store, needed[1], None))
    )


def unsupported_checks(store: object) -> tuple[tuple[Callable[..., Awaitable[None]], str], ...]:
    """`(check, the capability it needs)` for every published check `store` cannot answer.

    The companion to `checks_for`, and the reason that one may filter at all: a caller reports
    these rather than discovering later that a green run proved less than they thought.
    """
    _require_a_store(store)
    return tuple(
        (check, needed[0])
        for check in _published_checks()
        if (needed := _capability_needed(check)) is not None
        and not callable(getattr(store, needed[1], None))
    )


def register_conformance_ext_models() -> None:
    """Make this kit's `ConformanceFact` reconstructable by `rehydrate_ext`, and `BlobRef` too.

    **A function a caller runs, not a side effect of importing.** A store's checks attach ext
    models and read them back, so the models have to be registered before the round-trip checks
    can pass — but registering at module scope would make `import weft_store.conformance` mutate a
    process-wide registry, which is executable code a caller did not ask for (`L9.76`), and
    `register_ext_model` refuses a namespace twice, so a second import in one process would raise.

    Idempotent here rather than at the registry: calling it twice is a no-op, because a caller who
    runs two suites in one process should not have to remember which one registered first.
    """
    for model in (ConformanceFact, BlobRef):
        try:
            register_ext_model(model)
        except DuplicateRegistrationError:
            continue


def _require(condition: bool, message: str) -> None:
    """Raise `AssertionError(message)` when `condition` is false — see this module's docstring."""
    if not condition:
        raise AssertionError(message)


@runtime_checkable
class SearchableStore(NodeStore, VectorSearch, Protocol):
    """A store that holds nodes and ranks them by vector similarity."""


@runtime_checkable
class FilterableStore(NodeStore, MetadataFilter, Protocol):
    """A store that holds nodes and answers a `Filter` over them."""


@runtime_checkable
class FilterableSearchableStore(NodeStore, MetadataFilter, VectorSearch, Protocol):
    """A store that ranks by vector similarity **and** narrows by a `Filter`.

    Its own protocol because one check needs both and neither `SearchableStore` nor
    `FilterableStore` says so. That mattered the moment a store with vectors and no filters
    existed: `checks_for` derives what a check needs from this annotation, so a check typed
    `SearchableStore` while passing a `Filter` was offered to `weft_store.memory.MemoryStore`
    and refused at run time — the selector being exactly as right as the annotation is.
    Found by task `26.6`, which is what `01` → *Runtime shape* says the in-memory store is for.
    """


@runtime_checkable
class SupersedableStore(NodeStore, NodeSupersedable, Protocol):
    """A store that holds nodes and can replace one in place."""


@runtime_checkable
class ReconcilableStore(NodeStore, Reconcilable, Protocol):
    """A store that holds nodes and can converge its own deferred work."""


_SOURCE_A = SourceId("source-a")
_SOURCE_B = SourceId("source-b")


def _node(
    content: str,
    *,
    sources: frozenset[SourceId],
    pages: ConformanceFact | None = None,
    span: PageSpan | None = None,
    embedding: Vector | None = None,
) -> Node:
    node = Node.synthetic(
        content=content, media_type=MediaType.TEXT, reason="conformance kit", sources=sources
    )
    if pages is not None:
        node = node.with_ext(pages)
    if span is not None:
        node = node.with_ext(span)
    return node if embedding is None else node.with_embedding(embedding)


def _conformance_context() -> Context:
    """A `Context` for `reconcile`, which takes one and — for a node store — reads nothing
    from it. A pack that converges by running model calls will; this one has no reason to.
    """
    return Context(tenant_id="conformance", run_id="run-1", trace_id="trace-1", locale="en")


def conformance_corpus() -> tuple[Node, ...]:
    """Three nodes chosen so that every operator in `FilterOp` separates them differently."""
    return (
        _node(
            "alpha",
            sources=frozenset({_SOURCE_A}),
            pages=ConformanceFact(backend="pypdf"),
            span=PageSpan(page=1, ordinal=0),
            embedding=Vector(values=(1.0, 0.0, 0.0)),
        ),
        _node(
            "beta",
            sources=frozenset({_SOURCE_A, _SOURCE_B}),
            pages=ConformanceFact(backend="pdfplumber"),
            span=PageSpan(page=500, ordinal=0),
            embedding=Vector(values=(0.0, 1.0, 0.0)),
        ),
        _node("gamma", sources=frozenset({_SOURCE_B})),
    )


async def _all(page: Page[Node]) -> frozenset[str]:
    return frozenset(node.content for node in page.items)


OPERATOR_CASES: tuple[tuple[str, Filter, frozenset[str]], ...] = (
    ("eq", Filter(op=FilterOp.EQ, field="content", value="alpha"), frozenset({"alpha"})),
    (
        "ne",
        Filter(op=FilterOp.NE, field="content", value="alpha"),
        frozenset({"beta", "gamma"}),
    ),
    (
        "in",
        Filter(
            op=FilterOp.IN, field="ext.weft-store-conformance.backend", value=("pypdf", "poppler")
        ),
        frozenset({"alpha"}),
    ),
    (
        "lt",
        Filter(op=FilterOp.LT, field="ext.weft-extract-page.page", value=2),
        frozenset({"alpha"}),
    ),
    (
        "lte",
        Filter(op=FilterOp.LTE, field="ext.weft-extract-page.page", value=1),
        frozenset({"alpha"}),
    ),
    (
        "gt",
        Filter(op=FilterOp.GT, field="ext.weft-extract-page.page", value=100),
        frozenset({"beta"}),
    ),
    (
        # A fractional bound, which is the case both translators' number handling exists for
        # — `weft_qdrant.store._as_number` casts to `float`, pgvector compares `::numeric` —
        # and the case the AST refused until a reviewer finding against 2.6 was repaired.
        # Every other case here uses an integer bound, which is exactly why nothing caught it.
        "gt-fractional",
        Filter(op=FilterOp.GT, field="ext.weft-extract-page.page", value=99.5),
        frozenset({"beta"}),
    ),
    (
        "gte",
        Filter(op=FilterOp.GTE, field="ext.weft-extract-page.page", value=500),
        frozenset({"beta"}),
    ),
    (
        "exists",
        Filter(op=FilterOp.EXISTS, field="ext.weft-store-conformance.backend"),
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
                Filter(op=FilterOp.EXISTS, field="ext.weft-store-conformance.backend"),
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
            clauses=(Filter(op=FilterOp.EXISTS, field="ext.weft-store-conformance.backend"),),
        ),
        frozenset({"gamma"}),
    ),
)


async def check_a_node_round_trips_through_the_store_with_its_lineage_and_its_ext(
    store: NodeStore,
) -> None:
    # Arrange
    nodes = conformance_corpus()

    # Act
    await store.add(nodes)
    await store.flush()
    found = await store.get([nodes[1].id])

    # Assert
    _require(
        len(found) == 1,
        "the store did not satisfy: len(found) == 1",
    )
    _require(
        found[0].content == "beta",
        'the store did not satisfy: found[0].content == "beta"',
    )
    _require(
        found[0].lineage.sources == frozenset({_SOURCE_A, _SOURCE_B}),
        "the store did not satisfy: found[0].lineage.sources == frozenset({_SOURCE_A, _SOURCE_B})",
    )
    _require(
        found[0].ext_as(ConformanceFact) == ConformanceFact(backend="pdfplumber"),
        "the store did not satisfy: found[0].ext_as(ConformanceFact) == ConformanceFact(backen...",
    )
    _require(
        found[0].embedding is not None,
        "the store did not satisfy: found[0].embedding is not None",
    )


async def check_the_multimodal_facts_round_trip_through_every_store(
    store: NodeStore,
) -> None:
    """Ledger task `9.5`: `BlobRef`, `TableGrid` and `PageSpan` survive a real backend — both.

    The task says *"each survive a round trip through every store"*, and "every store" is what this
    kit is — one suite, two real containers. A unit test over `model_validate(model_dump())` proves
    the model; it cannot prove that a backend's own JSONB or payload encoding carries a nested
    tuple-of-tuples and a float bounding box back unchanged, which is the half that has actually
    broken before.

    All three at once on one node, deliberately: they occupy three namespaces and `ext` is keyed by
    namespace, so a store that dropped or overwrote one would pass a test that stored only the other
    two.
    """
    # Arrange
    grid = TableGrid(
        headers=("Region", "Revenue"),
        rows=(("EMEA", "1,204"), ("APAC", "988")),
        caption="Table 2. Revenue by region.",
        page=7,
        bbox=BoundingBox(x0=72.0, y0=520.5, x1=523.0, y1=610.25),
    )
    span = PageSpan(page=7, ordinal=3)
    ref = BlobRef(uri=BlobUri("file:///blobs/t/9f2c/0.png"), media_type="image/png")
    node = (
        Node.synthetic(
            content="Region | Revenue",
            media_type=MediaType.TABLE,
            reason="9.5's conformance subject",
        )
        .with_ext(grid)
        .with_ext(span)
        .with_ext(ref)
    )

    # Act
    await store.add([node])
    await store.flush()
    found = await store.get([node.id])

    # Assert
    _require(
        len(found) == 1,
        "the store did not satisfy: len(found) == 1",
    )
    _require(
        found[0].ext_as(TableGrid) == grid,
        "the store did not satisfy: found[0].ext_as(TableGrid) == grid",
    )
    _require(
        found[0].ext_as(PageSpan) == span,
        "the store did not satisfy: found[0].ext_as(PageSpan) == span",
    )
    _require(
        found[0].ext_as(BlobRef) == ref,
        "the store did not satisfy: found[0].ext_as(BlobRef) == ref",
    )


async def check_scan_and_count_see_every_stored_node_whatever_order_a_backend_walks_in(
    store: NodeStore,
) -> None:
    # Arrange
    await store.add(conformance_corpus())

    # Act
    page = await store.scan()
    total = await store.count()

    # Assert — a set, not a sequence: the contract promises pages, never an order, and the
    # two backends genuinely differ (Postgres walks the content digest, Qdrant a UUID).
    _require(
        frozenset(node.content for node in page.items) == frozenset({"alpha", "beta", "gamma"}),
        "the store did not satisfy: frozenset(node.content for node in page.items) == frozense...",
    )
    _require(
        page.next_cursor is None,
        "the store did not satisfy: page.next_cursor is None",
    )
    _require(
        total == 3,
        "the store did not satisfy: total == 3",
    )


async def check_delete_source_removes_exactly_the_nodes_carrying_it(store: NodeStore) -> None:
    """Unchanged by G20, and that is the point of the position it settled on.

    `beta` carries `_SOURCE_A` and `_SOURCE_B` because `conformance_corpus()` built it that way in
    **one**
    construction — one production over two documents, which is what a `Node.combine` summary is.
    Deleting either document leaves no production, so the node goes, exactly as `02` §1's cascade
    paragraph has always said. Nothing here moved; the collision cases below are additive.
    """
    # Arrange
    await store.add(conformance_corpus())
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
    _require(
        removed.source_id == _SOURCE_B,
        "the store did not satisfy: removed.source_id == _SOURCE_B",
    )
    _require(
        removed.node_count == 2,
        "the store did not satisfy: removed.node_count == 2",
    )
    _require(
        removed.narrowed_count == 0,
        "the store did not satisfy: removed.narrowed_count == 0",
    )
    _require(
        frozenset(node.content for node in (await store.scan()).items) == frozenset({"alpha"}),
        "the store did not satisfy: frozenset(node.content for node in (await store.scan()).it...",
    )
    _require(
        await store.get_source(_SOURCE_B) is None,
        "the store did not satisfy: await store.get_source(_SOURCE_B) is None",
    )


async def check_add_merges_a_nodes_sources_rather_than_replacing_them(
    store: NodeStore,
) -> None:
    """The write half. Two documents, the same bytes, one node, and it belongs to both."""
    # Arrange — the same content reached from two different documents.
    from_a = _node("shared", sources=frozenset({_SOURCE_A}))
    from_b = _node("shared", sources=frozenset({_SOURCE_B}))
    _require(
        from_a.id == from_b.id,
        "the fixture must exercise the collision, not avoid it",
    )

    # Act
    await store.add((from_a,))
    await store.add((from_b,))

    # Assert
    stored = await store.get((from_a.id,))
    _require(
        len(stored) == 1,
        "the store did not satisfy: len(stored) == 1",
    )
    _require(
        stored[0].lineage.sources == frozenset({_SOURCE_A, _SOURCE_B}),
        "the store did not satisfy: stored[0].lineage.sources == frozenset({_SOURCE_A, _SOURCE_B})",
    )
    _require(
        await store.count() == 1,
        "the store did not satisfy: await store.count() == 1",
    )


async def check_a_node_two_documents_each_produced_whole_is_narrowed_not_deleted(
    store: NodeStore,
) -> None:
    """The delete half, and the case the test above it sets up.

    Two productions of one document each: deleting `_SOURCE_A` drops its production and leaves
    `_SOURCE_B`'s, so the node stays and its `sources` is recomputed from what survives. This is
    the whole difference from the `conformance_corpus()` case above, where one production named
    both.
    """
    # Arrange
    from_a = _node("shared", sources=frozenset({_SOURCE_A}))
    from_b = _node("shared", sources=frozenset({_SOURCE_B}))
    await store.add((from_a,))
    await store.add((from_b,))

    # Act
    removed = await store.delete_source(_SOURCE_A)

    # Assert
    _require(
        (removed.node_count, removed.narrowed_count) == (0, 1),
        "the store did not satisfy: (removed.node_count, removed.narrowed_count) == (0, 1)",
    )
    surviving = await store.get((from_a.id,))
    _require(
        len(surviving) == 1,
        "the store did not satisfy: len(surviving) == 1",
    )
    _require(
        surviving[0].lineage.sources == frozenset({_SOURCE_B}),
        "the store did not satisfy: surviving[0].lineage.sources == frozenset({_SOURCE_B})",
    )


async def check_deleting_the_last_document_that_produced_a_node_deletes_it(
    store: NodeStore,
) -> None:
    """Narrowing is not a way for content to outlive every document that holds it."""
    # Arrange
    from_a = _node("shared", sources=frozenset({_SOURCE_A}))
    from_b = _node("shared", sources=frozenset({_SOURCE_B}))
    await store.add((from_a,))
    await store.add((from_b,))

    # Act
    first = await store.delete_source(_SOURCE_A)
    second = await store.delete_source(_SOURCE_B)

    # Assert
    _require(
        (first.node_count, first.narrowed_count) == (0, 1),
        "the store did not satisfy: (first.node_count, first.narrowed_count) == (0, 1)",
    )
    _require(
        (second.node_count, second.narrowed_count) == (1, 0),
        "the store did not satisfy: (second.node_count, second.narrowed_count) == (1, 0)",
    )
    _require(
        await store.count() == 0,
        "the store did not satisfy: await store.count() == 0",
    )


async def check_a_derived_node_and_a_collided_one_are_told_apart_in_the_same_store(
    store: NodeStore,
) -> None:
    """The two readings of a two-member `sources`, side by side, distinguished by one deletion.

    `L12.6`'s shape: a fixture holding one of a thing cannot show that two are distinguishable.
    Both nodes below end with `sources == {_SOURCE_A, _SOURCE_B}` and the same deletion must do
    opposite things to them, which is the entire property `27.1` adds and the one a store keying
    on `sources` alone cannot have.
    """
    # Arrange — `derived` is built once naming both; `collided` is written twice naming one each.
    derived = _node("derived", sources=frozenset({_SOURCE_A, _SOURCE_B}))
    collided = _node("collided", sources=frozenset({_SOURCE_A}))
    also_collided = _node("collided", sources=frozenset({_SOURCE_B}))
    await store.add((derived, collided))
    await store.add((also_collided,))
    _require(
        derived.lineage.sources == also_collided.lineage.sources | collided.lineage.sources,
        "the store did not satisfy: derived.lineage.sources == also_collided.lineage.sources |...",
    )

    # Act
    removed = await store.delete_source(_SOURCE_A)

    # Assert
    _require(
        (removed.node_count, removed.narrowed_count) == (1, 1),
        "the store did not satisfy: (removed.node_count, removed.narrowed_count) == (1, 1)",
    )
    surviving = {node.content: node for node in (await store.scan()).items}
    _require(
        frozenset(surviving) == frozenset({"collided"}),
        'the store did not satisfy: frozenset(surviving) == frozenset({"collided"})',
    )
    _require(
        surviving["collided"].lineage.sources == frozenset({_SOURCE_B}),
        'the store did not satisfy: surviving["collided"].lineage.sources == frozenset({_SOURC...',
    )


async def check_a_node_written_twice_by_one_document_is_one_production_not_two(
    store: NodeStore,
) -> None:
    """Re-indexing is idempotent, and the production record must not make it otherwise.

    `02` §1: *"Re-indexing unchanged content therefore produces the same ids, which is what makes
    re-index idempotent."* A production keyed on anything but its own source set would accumulate
    one entry per `add`, and the node would then survive the deletion of the only document that
    ever produced it — a hole with no symptom until someone counted.
    """
    # Arrange
    node = _node("written twice", sources=frozenset({_SOURCE_A}))
    await store.add((node,))
    await store.add((node,))

    # Act
    removed = await store.delete_source(_SOURCE_A)

    # Assert
    _require(
        (removed.node_count, removed.narrowed_count) == (1, 0),
        "the store did not satisfy: (removed.node_count, removed.narrowed_count) == (1, 0)",
    )
    _require(
        await store.count() == 0,
        "the store did not satisfy: await store.count() == 0",
    )


async def check_a_deleted_nodes_productions_do_not_outlive_it(
    store: NodeStore,
) -> None:
    """A node's productions die with it, so a recycled id inherits nothing — `27.1`.

    **Asserted through the seam and not by reading a schema** (`L9.39`): a stale production is
    not invisible, it is a *wrong answer* to the next deletion. If deleting `_SOURCE_A` left its
    production behind, the identical node re-added under `_SOURCE_B` would inherit it, and
    deleting `_SOURCE_B` would find a surviving production and narrow a node nothing produces.

    **This passed the first time it was run, and that is worth recording rather than hiding.**
    It was written to catch 1,204 orphaned production rows measured in the development database
    after one gate run, on the theory that `delete_source` was leaking. It was not: the deletion
    path reaps correctly and this test proves it. The orphans came from the seventeen fixtures
    that truncate `weft_nodes` directly and bypass the application entirely — a different
    defect with the same symptom, repaired where it lives. `L12.4`: a symptom is evidence of a
    symptom, and the named cause owes its own measurement.
    """
    # Arrange — one node, produced by A, then deleted.
    node = _node("recycled", sources=frozenset({_SOURCE_A}))
    await store.add((node,))
    first = await store.delete_source(_SOURCE_A)
    _require(
        (first.node_count, first.narrowed_count) == (1, 0),
        "the store did not satisfy: (first.node_count, first.narrowed_count) == (1, 0)",
    )
    _require(
        await store.count() == 0,
        "the store did not satisfy: await store.count() == 0",
    )

    # Act — the same content arrives again, from a different document this time.
    await store.add((_node("recycled", sources=frozenset({_SOURCE_B})),))
    second = await store.delete_source(_SOURCE_B)

    # Assert — B was its only producer, so the node goes. A narrowing here would mean A's
    # production outlived the node it described.
    _require(
        (second.node_count, second.narrowed_count) == (1, 0),
        "the store did not satisfy: (second.node_count, second.narrowed_count) == (1, 0)",
    )
    _require(
        await store.count() == 0,
        "the store did not satisfy: await store.count() == 0",
    )


async def check_supersede_replaces_a_node_and_leaves_its_neighbours_alone(
    store: SupersedableStore,
) -> None:
    """G15's *Remove* face, on both real backends.

    `NodeStore`'s only removal before this was `delete_source`, keyed on a *source*. A summary's
    relationship to a source is many-to-many — `Lineage.sources` is the union of its members' — so
    *"this node is out of date"* had no expression at all, and an incremental tree could not
    replace what it superseded.
    """
    # Arrange
    corpus = conformance_corpus()
    await store.add(corpus)
    old = corpus[1]
    new = _node("beta, revised", sources=old.lineage.sources)

    # Act
    _require(
        callable(getattr(store, "supersede", None)),
        "the capability is derived from the methods a store implements and never declared "
        "(G4), so a real backend must satisfy this Protocol without saying anything",
    )
    await store.supersede(old.id, new)
    await store.flush()

    # Assert
    _require(
        [node.id for node in await store.get([old.id])] == [],
        "the superseded node survived",
    )
    _require(
        [node.content for node in await store.get([new.id])] == ["beta, revised"],
        'the store did not satisfy: [node.content for node in await store.get([new.id])] == ["...',
    )
    _require(
        frozenset(node.content for node in (await store.scan()).items)
        == frozenset({"alpha", "beta, revised", "gamma"}),
        "supersede touched a node it was not given",
    )


async def check_supersede_is_idempotent_so_an_interrupted_one_can_be_retried(
    store: SupersedableStore,
) -> None:
    """The half that makes write-then-delete safe rather than merely ordered.

    `supersede` writes `new` first and deletes `old` second, so a crash between the two leaves a
    **duplicate** — which `reconcile` can find — and never a **hole**, which nothing can find and
    which `04` category A records as staying retrievable forever describing content that is gone.
    That ordering is only useful if the operation can then be *run again*: a retry arrives with
    `old` already gone, and must succeed rather than refuse. The store family already works this
    way — `weft_qdrant.delete_source`'s own docstring calls itself *"`02`'s idempotent, resumable
    deletion"* — and this pins the same property one member over.
    """
    # Arrange
    corpus = conformance_corpus()
    await store.add(corpus)
    old = corpus[1]
    new = _node("beta, revised", sources=old.lineage.sources)
    await store.supersede(old.id, new)
    await store.flush()

    # Act — the retry an interrupted run would make.
    await store.supersede(old.id, new)
    await store.flush()

    # Assert
    _require(
        frozenset(node.content for node in (await store.scan()).items)
        == frozenset({"alpha", "beta, revised", "gamma"}),
        "the retry changed the store, so an interrupted supersede cannot safely be repeated",
    )


async def check_supersede_refuses_a_replacement_that_drops_a_source(
    store: SupersedableStore,
) -> None:
    """The invariant, enforced by the contract rather than remembered by its callers.

    Write-then-delete stops a *crash* leaving a hole. It does nothing about a caller that hands
    over a replacement covering fewer sources than the node it replaces — that removes the last
    node carrying a source while the source's documents remain, which is `04` category A's scar
    approached from the other end: the store keeps content whose provenance is gone, or loses
    content a cascade delete would have been responsible for. `Node.combine` already refuses an
    empty member set by construction for this reason; this is the same refusal one level up.
    """
    # Arrange — `beta` carries both sources; the replacement carries only one.
    corpus = conformance_corpus()
    await store.add(corpus)
    old = corpus[1]
    narrowed = _node("beta, narrowed", sources=frozenset({_SOURCE_A}))

    # Act & Assert
    try:
        await store.supersede(old.id, narrowed)
    except SupersedeNarrowsSourcesError as exc:
        message = str(exc)
    else:
        raise AssertionError(
            "supersede accepted a replacement that drops a source, so a node another document "
            "still produces would silently lose that document's claim"
        )
    _require(
        _SOURCE_B in message,
        f"the refusal must name the source that would be dropped: {message!r}",
    )
    _require(
        frozenset(node.content for node in (await store.scan()).items)
        == frozenset({"alpha", "beta", "gamma"}),
        "a refused supersede must change nothing at all",
    )


async def check_reconcile_finishes_a_deletion_that_was_interrupted(
    store: ReconcilableStore,
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
    await store.add(conformance_corpus())
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
    _require(
        (report.examined, report.removed, report.converged) == (1, 2, True),
        "the store did not satisfy: (report.examined, report.removed, report.converged) == (1,...",
    )
    _require(
        (again.examined, again.removed, again.converged) == (0, 0, True),
        "the store did not satisfy: (again.examined, again.removed, again.converged) == (0, 0,...",
    )
    _require(
        frozenset(node.content for node in (await store.scan()).items) == frozenset({"alpha"}),
        "the store did not satisfy: frozenset(node.content for node in (await store.scan()).it...",
    )
    _require(
        await store.get_source(_SOURCE_B) is None,
        "the store did not satisfy: await store.get_source(_SOURCE_B) is None",
    )


async def check_reconcile_leaves_a_healthy_store_alone_on_either_backend(
    store: ReconcilableStore,
) -> None:
    """The other half, and the one that would have been a corpus-erasing bug: a node store
    holds the primary data, so a source record it has never been given is not evidence that
    its nodes are orphans. Nothing is removed here, and `full` removes no more than `repair`.
    """
    # Arrange — three nodes and no source records at all, which is what `weft index` leaves.
    await store.add(conformance_corpus())

    # Act
    report = await store.reconcile(_conformance_context(), ReconcileMode.FULL)

    # Assert
    _require(
        (report.removed, report.backfilled, report.converged) == (0, 0, True),
        "the store did not satisfy: (report.removed, report.backfilled, report.converged) == (...",
    )
    _require(
        await store.count() == 3,
        "the store did not satisfy: await store.count() == 3",
    )


async def check_estimate_reports_zero_model_calls_on_either_backend(
    store: ReconcilableStore,
) -> None:
    """Task **5.1c**'s own floor, on both real backends: a node store holds the primary data,
    so `full` has nothing to backfill and `estimate` says so honestly rather than guessing at
    a number — see `PgVectorStore.estimate`'s own docstring, which owns the argument for both.
    """
    # Arrange — three nodes, no tombstones: nothing pending either.
    await store.add(conformance_corpus())

    # Act
    estimate = await store.estimate(_conformance_context(), ReconcileMode.FULL)

    # Assert
    _require(
        (estimate.pending, estimate.model_calls) == (0, 0),
        "the store did not satisfy: (estimate.pending, estimate.model_calls) == (0, 0)",
    )


async def check_estimate_counts_the_identical_tombstones_reconcile_itself_examines(
    store: ReconcilableStore,
) -> None:
    """`estimate`'s own `pending` must never disagree with what `reconcile` actually examines —
    both read the same backlog, so a tombstone `estimate` counts is a tombstone `reconcile`
    finishes.
    """
    # Arrange — an interrupted deletion, the same fixture `test_reconcile_finishes_a_deletion_
    # that_was_interrupted` above plants.
    await store.add(conformance_corpus())
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
    _require(
        estimate.pending == 1,
        "the store did not satisfy: estimate.pending == 1",
    )
    _require(
        report.examined == 1,
        "the store did not satisfy: report.examined == 1",
    )


async def check_a_source_record_round_trips_and_is_listed(store: NodeStore) -> None:
    """The whole record, compared with `==` — every field, not the three someone remembered.

    **This test asserted three fields by name until 2026-09-06, and that is why it missed one.**
    Task `9.17` added `SourceRecord.pipeline_identity`; `pgvector`'s `put_source` names its columns
    explicitly and the table had no column for it, so the value was written into a statement with
    nowhere to put it and read back as its own default — silently, and the default *means*
    something, so the feature reported a re-parse that had not happened. Twenty-one unit tests and
    the whole gate passed; the binary found it (`docs/internal/lessons.md` `L9.60`).

    A field-by-field assertion can only check fields its author has heard of, which makes it exactly
    as complete as the day it was written. `==` on a frozen model is complete by construction and
    owes no edit when the model grows.
    """
    # Arrange — every field populated, including the ones with defaults: a default that is never
    # written is a default the store is never asked to carry.
    record = SourceRecord(
        id=_SOURCE_A,
        uri="file:///corpus/a.txt",
        content_hash="hash-a",
        indexed_at=datetime.now(UTC),
        pipeline="conformance",
        pipeline_identity="9f2c1a4e",
    )

    # Act
    await store.put_source(record)
    found = await store.get_source(_SOURCE_A)
    listed = await store.list_sources()

    # Assert
    _require(
        found == record,
        "the store did not satisfy: found == record",
    )
    _require(
        tuple(item.id for item in listed) == (_SOURCE_A,),
        "the store did not satisfy: tuple(item.id for item in listed) == (_SOURCE_A,)",
    )


async def check_search_vector_ranks_by_cosine_similarity_on_either_backend(
    store: SearchableStore,
) -> None:
    # Arrange
    await store.add(conformance_corpus())
    _require(
        callable(getattr(store, "search_vector", None)),
        'the store did not satisfy: callable(getattr(store, "search_vector", None))',
    )

    # Act
    ranked = await store.search_vector(Vector(values=(0.0, 1.0, 0.0)), top_k=2)

    # Assert
    _require(
        [scored.value.content for scored in ranked] == ["beta", "alpha"],
        'the store did not satisfy: [scored.value.content for scored in ranked] == ["beta", "a...',
    )
    _require(abs(ranked[0].score - 1.0) < 1e-3, f"an exact match must score 1.0: {ranked[0].score}")


async def check_every_operator_means_the_same_thing_to_both_backends(
    store: FilterableStore, label: str, filter_: Filter, expected: frozenset[str]
) -> None:
    # Arrange
    await store.add(conformance_corpus())
    _require(
        callable(getattr(store, "matching", None)),
        'the store did not satisfy: callable(getattr(store, "matching", None))',
    )

    # Act
    page = await store.matching(filter_)

    # Assert
    _require(
        await _all(page) == expected,
        f"'{label}' disagrees between backends",
    )


async def check_a_parent_is_one_filter_away_from_its_child_on_either_backend(
    store: FilterableStore,
) -> None:
    """`lineage.parents` selects a node's children — `11` §4 question **G4-c**, ledger `9.14`.

    G4-c asked *"is `lineage.parents` a validated, filterable field path?"* and recommended
    yes, *"and the filter AST gains one operator over it."* **Measured 2026-09-06: the field
    path already exists and the operator already works** — `weft_store.fields.NodeField.PARENTS`
    has been a `TEXT_SET` field since the filter grammar was built, admitting `contains`, and
    both translators derive from that one parse. So the amendment G4-c proposed costs nothing
    to accept, because the code already implements it.

    **What was missing was this test.** Nothing in the tree filtered on `lineage.parents`
    *through a store*: the grammar was checked, the translators were checked, and the round
    trip that a table-to-rows expansion actually performs was checked nowhere. A field path
    that parses and translates but was never asked of a live backend is a capability nobody
    has seen work — and G4-c's own fallback clause (*"a store that cannot filter on it falls
    back to fetching parents by id, which is correct but N+1"*) is unreachable as long as this
    passes on both, which is the fact worth pinning.
    """
    # Arrange
    parent = _node("parent", sources=frozenset({_SOURCE_A}))
    children = tuple(
        parent.derive(content=f"row {ordinal}", ordinal=ordinal) for ordinal in range(2)
    )
    unrelated = _node("unrelated", sources=frozenset({_SOURCE_B}))
    await store.add((parent, *children, unrelated))
    _require(
        callable(getattr(store, "matching", None)),
        'the store did not satisfy: callable(getattr(store, "matching", None))',
    )

    # Act
    page = await store.matching(
        Filter(op=FilterOp.CONTAINS, field="lineage.parents", value=str(parent.id))
    )

    # Assert
    _require(
        await _all(page) == frozenset({"row 0", "row 1"}),
        'the store did not satisfy: await _all(page) == frozenset({"row 0", "row 1"})',
    )


async def check_a_parent_id_nothing_derives_from_selects_nothing_rather_than_everything(
    store: FilterableStore,
) -> None:
    """The negative half, because a filter that silently matched nothing and one that silently
    matched everything look identical from a single positive case — and `weft_store.fields`'
    own `UnaddressableFieldError` docstring is explicit that *"a filter matching nothing looks
    exactly like a corpus that holds nothing"*.
    """
    # Arrange
    await store.add(conformance_corpus())
    _require(
        callable(getattr(store, "matching", None)),
        'the store did not satisfy: callable(getattr(store, "matching", None))',
    )

    # Act
    page = await store.matching(
        Filter(op=FilterOp.CONTAINS, field="lineage.parents", value="no-such-node")
    )

    # Assert
    _require(
        await _all(page) == frozenset(),
        "the store did not satisfy: await _all(page) == frozenset()",
    )


async def check_a_filter_reaches_vector_search_rather_than_being_ignored(
    store: FilterableSearchableStore,
) -> None:
    # Arrange
    await store.add(conformance_corpus())
    _require(
        callable(getattr(store, "search_vector", None)),
        'the store did not satisfy: callable(getattr(store, "search_vector", None))',
    )

    # Act
    ranked = await store.search_vector(
        Vector(values=(0.0, 1.0, 0.0)),
        top_k=5,
        filter=Filter(op=FilterOp.EQ, field="content", value="alpha"),
    )

    # Assert
    _require(
        [scored.value.content for scored in ranked] == ["alpha"],
        'the store did not satisfy: [scored.value.content for scored in ranked] == ["alpha"]',
    )


async def check_a_field_no_node_can_have_is_refused_by_name_on_either_backend(
    store: FilterableStore,
) -> None:
    # Arrange
    _require(
        callable(getattr(store, "matching", None)),
        'the store did not satisfy: callable(getattr(store, "matching", None))',
    )
    nonsense = Filter(op=FilterOp.EQ, field="metadata.author", value="nobody")

    # Act / Assert
    try:
        await store.matching(nonsense)
    except UnaddressableFieldError as exc:
        _require("metadata.author" in str(exc), f"the refusal must name the field: {str(exc)!r}")
    else:
        raise AssertionError("a field no node can carry was accepted; it must be refused by name")


async def check_an_operator_a_field_cannot_carry_is_refused_by_name_on_either_backend(
    store: FilterableStore,
) -> None:
    # Arrange
    _require(
        callable(getattr(store, "matching", None)),
        'the store did not satisfy: callable(getattr(store, "matching", None))',
    )
    wrong = Filter(op=FilterOp.EQ, field="lineage.sources", value=_SOURCE_A)

    # Act / Assert
    try:
        await store.matching(wrong)
    except FilterOpMismatchError as exc:
        _require("contains" in str(exc), f"the refusal must name the operator: {str(exc)!r}")
    else:
        raise AssertionError("an operator the field cannot carry was accepted; refuse it by name")
