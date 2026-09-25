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

import asyncio
import math
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import Final, Protocol, cast, runtime_checkable

from weft_blob.contract import BlobUri
from weft_blob.payload import BlobRef
from weft_chunk.payload import ChunkPosition
from weft_extract.payload import BoundingBox, PageSpan, TableGrid
from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.payload import ExtModel, MediaType, Node, SourceId, Vector
from weft_kernel.registry import DuplicateRegistrationError
from weft_store.contract import (
    DEFAULT_TARGET,
    EmbeddingIdentity,
    Filter,
    FilterOp,
    GenerationCarrying,
    GenerationHolding,
    GenerationId,
    GenerationStatus,
    GenerationWithdrawing,
    InvalidTargetNameError,
    LayerRecord,
    LayerStatus,
    MetadataFilter,
    NodeStore,
    NodeSupersedable,
    NoPreviousTargetError,
    NotAPublishedGenerationError,
    NotAPublishedMemberError,
    Page,
    Promotion,
    Reconcilable,
    ReconcileMode,
    SingleWriter,
    SourceFailure,
    SourceRecord,
    SourceStatus,
    SupersedeNarrowsSourcesError,
    TargetHolding,
    TargetInUseError,
    TextSearch,
    UnknownGenerationError,
    UnknownTargetError,
    VectorSearch,
    WriterBusyError,
    WriterClaim,
    target_name,
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


#: Every capability each check needs beyond `NodeStore`, derived from the protocol its own `store`
#: parameter is annotated with — so the selector and the checks cannot disagree about what a check
#: requires. `L5.6`: two sides of a comparison that come from one source cannot disagree, and here
#: that is the property wanted rather than the defect, because the annotation **is** the
#: requirement. Each value is an *ordered* tuple of `(protocol name, proving method)` pairs — a
#: check typed against a protocol composed of several capabilities needs every one of them, never
#: just the first its selector happened to check (ledger `43.39`: a store with `open_generation`
#: and no search arm was offered a check keyed on `open_generation` alone and failed with
#: `AttributeError`). A check typed `NodeStore` needs nothing more, so its tuple is empty.
_CAPABILITY_OF: Final[Mapping[str, tuple[tuple[str, str], ...]]] = {
    "SearchableStore": (("VectorSearch", "search_vector"),),
    "TextSearchableStore": (("TextSearch", "search_text"),),
    "FilterableTextStore": (("TextSearch", "search_text"), ("MetadataFilter", "matching")),
    "FilterableSearchableStore": (
        ("MetadataFilter", "matching"),
        ("VectorSearch", "search_vector"),
    ),
    "FilterableStore": (("MetadataFilter", "matching"),),
    "SupersedableStore": (("NodeSupersedable", "supersede"),),
    "ReconcilableStore": (("Reconcilable", "reconcile"),),
    "TargetHoldingStore": (("TargetHolding", "target_catalogue"),),
    "GenerationHoldingStore": (
        ("GenerationHolding", "open_generation"),
        ("VectorSearch", "search_vector"),
        ("TextSearch", "search_text"),
        ("MetadataFilter", "matching"),
    ),
    "GenerationHoldingNodeStore": (("GenerationHolding", "open_generation"),),
    "GenerationCarryingStore": (
        ("GenerationCarrying", "carry_forward"),
        ("GenerationHolding", "open_generation"),
        ("VectorSearch", "search_vector"),
        ("TextSearch", "search_text"),
        ("MetadataFilter", "matching"),
    ),
    "GenerationWithdrawingStore": (
        ("GenerationWithdrawing", "withdraw_generation"),
        ("GenerationHolding", "open_generation"),
        ("VectorSearch", "search_vector"),
        ("TextSearch", "search_text"),
        ("MetadataFilter", "matching"),
    ),
    "GenerationWithdrawingNodeStore": (
        ("GenerationWithdrawing", "withdraw_generation"),
        ("GenerationHolding", "open_generation"),
    ),
    "SingleWriterStore": (("SingleWriter", "claim_writer"),),
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


def _capabilities_needed(check: Callable[..., Awaitable[None]]) -> tuple[tuple[str, str], ...]:
    """Every `(protocol name, the method that proves it)` pair a check needs beyond `NodeStore`.

    Ordered with the annotated shape's defining capability first, as `_CAPABILITY_OF` is built.
    Empty for a check typed `NodeStore` — nothing more is required.
    """
    annotation = check.__annotations__.get("store")
    name = getattr(annotation, "__name__", str(annotation))
    return _CAPABILITY_OF.get(name, ())


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
        if all(
            callable(getattr(store, method, None))
            for _protocol, method in _capabilities_needed(check)
        )
    )


def unsupported_checks(store: object) -> tuple[tuple[Callable[..., Awaitable[None]], str], ...]:
    """`(check, the capability it needs)` for every published check `store` cannot answer.

    The companion to `checks_for`, and the reason that one may filter at all: a caller reports
    these rather than discovering later that a green run proved less than they thought. When a
    check needs several capabilities, the **first missing one**, in `_CAPABILITY_OF`'s order, is
    what is reported — the shape's defining capability, so a store missing that is told about it
    rather than about an arm it may never grow.
    """
    _require_a_store(store)
    reported: list[tuple[Callable[..., Awaitable[None]], str]] = []
    for check in _published_checks():
        for protocol, method in _capabilities_needed(check):
            if not callable(getattr(store, method, None)):
                reported.append((check, protocol))
                break
    return tuple(reported)


def register_conformance_ext_models() -> None:
    """Make every `ExtModel` this kit's own checks attach reconstructable by `rehydrate_ext`.

    `PageSpan` and `TableGrid` are attached by the multimodal round-trip checks, and were missing
    until repair `R22.10`: the kit passed only in a process where discovery had already registered
    them, so a store author running it alone met 44 failures.

    **A function a caller runs, not a side effect of importing.** A store's checks attach ext
    models and read them back, so the models have to be registered before the round-trip checks
    can pass — but registering at module scope would make `import weft_store.conformance` mutate a
    process-wide registry, which is executable code a caller did not ask for (`L9.76`), and
    `register_ext_model` refuses a namespace twice, so a second import in one process would raise.

    Idempotent here rather than at the registry: calling it twice is a no-op, because a caller who
    runs two suites in one process should not have to remember which one registered first.
    """
    for model in (ConformanceFact, BlobRef, ChunkPosition, PageSpan, TableGrid):
        try:
            register_ext_model(model)
        except DuplicateRegistrationError:
            continue


def _require(*, condition: bool, message: str) -> None:
    """Raise `AssertionError(message)` when `condition` is false — see this module's docstring."""
    if not condition:
        raise AssertionError(message)


@runtime_checkable
class SearchableStore(NodeStore, VectorSearch, Protocol):
    """A store that holds nodes and ranks them by vector similarity."""


@runtime_checkable
class TextSearchableStore(NodeStore, TextSearch, Protocol):
    """A store that holds nodes and ranks them by lexical match on their own text.

    **Published at `R21.3`, and late.** The kit shipped 25 checks covering three of the store
    contract family's four capability tiers and **none** for `search_text`, so a third party
    writing a store could prove three quarters of it. That was defensible while `TextSearch` had
    one implementation — a check for a capability only one backend satisfies has nothing to hold
    it to, which is `02` §1's own *a contract with one implementation is a guess* — and ledger task
    `21.8` made it two.
    """


@runtime_checkable
class FilterableTextStore(NodeStore, MetadataFilter, TextSearch, Protocol):
    """A store that ranks by lexical match **and** narrows by a `Filter`.

    Its own protocol for `FilterableSearchableStore`'s stated reason, one capability over: the
    selector derives what a check needs from this annotation, so a check that passes a `Filter`
    while typed `TextSearchableStore` would be offered to a store that cannot evaluate one and
    refused at run time.
    """


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


@runtime_checkable
class TargetHoldingStore(NodeStore, TargetHolding, Protocol):
    """A store that holds nodes in named targets, one of them live — ledger task **34.3**."""


@runtime_checkable
class GenerationHoldingStore(
    NodeStore, GenerationHolding, VectorSearch, TextSearch, MetadataFilter, Protocol
):
    """A store that holds layer generations and searches them — ledger task **43.14**."""


@runtime_checkable
class GenerationHoldingNodeStore(NodeStore, GenerationHolding, Protocol):
    """A store that holds layer generations without searching them — ledger task **43.39**.

    The graph pack's store is this shape: it derives graph rows from a generation's nodes at
    publish rather than answering `search_vector`, `search_text` or `matching`, so the checks that
    read a generation only through `NodeStore` and the catalogue — never through a search arm —
    are typed against this narrower shape rather than `GenerationHoldingStore`, and are offered to
    it.
    """


@runtime_checkable
class GenerationCarryingStore(GenerationHoldingStore, GenerationCarrying, Protocol):
    """A store that carries a published generation's members into a new one — ledger **43.22**."""


@runtime_checkable
class GenerationWithdrawingStore(GenerationHoldingStore, GenerationWithdrawing, Protocol):
    """The store shape the withdrawal checks need: generation holding and withdrawing at once.

    A store that withdraws a published generation now and reclaims its nodes later — repair
    **R43.29**.
    """


@runtime_checkable
class GenerationWithdrawingNodeStore(NodeStore, GenerationHolding, GenerationWithdrawing, Protocol):
    """A store that withdraws a published generation without searching it — ledger **43.40**.

    The graph store's shape: it derives graph rows from a generation's nodes at publish and
    retracts them at withdraw, rather than answering `search_vector`, `search_text` or
    `matching`, so the one withdrawal check that reads only through `NodeStore` and the
    catalogue — never through a search arm — is typed against this narrower shape rather than
    `GenerationWithdrawingStore`, and is offered to it.
    """


@runtime_checkable
class SingleWriterStore(NodeStore, SingleWriter, TargetHolding, Protocol):
    """A store that admits one writer at a time — ledger task **43.18**.

    `TargetHolding` is how a check reaches a second handle onto the same storage.
    """


#: How many callers overlap on one handle in the concurrency checks: raptor's shipped
#: `max_concurrent_summaries`.
_CONCURRENT_CALLERS: Final = 8
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


def _conformance_context(store: NodeStore) -> Context:
    """A `Context` for `reconcile`, carrying `store` as the run's corpus `NodeStore`.

    A store checked alone is its own corpus, as it is when it is `[services] store`. A secondary
    store reads the corpus from the passport (G13) and refuses a run without one (R43.54).
    """
    ctx = Context(tenant_id="conformance", run_id="run-1", trace_id="trace-1", locale="en")
    ctx.services.add(NodeStore, store)
    return ctx


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
        condition=len(found) == 1,
        message="the store did not satisfy: len(found) == 1",
    )
    _require(
        condition=found[0].content == "beta",
        message='the store did not satisfy: found[0].content == "beta"',
    )
    _require(
        condition=found[0].lineage.sources == frozenset({_SOURCE_A, _SOURCE_B}),
        message="the store did not satisfy: found[0].lineage.sources == frozenset({_SOURCE_A, "
        "_SOURCE_B})",
    )
    _require(
        condition=found[0].ext_as(ConformanceFact) == ConformanceFact(backend="pdfplumber"),
        message="the store did not satisfy: found[0].ext_as(ConformanceFact) == "
        "ConformanceFact(backen...",
    )
    _require(
        condition=found[0].embedding is not None,
        message="the store did not satisfy: found[0].embedding is not None",
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
        condition=len(found) == 1,
        message="the store did not satisfy: len(found) == 1",
    )
    _require(
        condition=found[0].ext_as(TableGrid) == grid,
        message="the store did not satisfy: found[0].ext_as(TableGrid) == grid",
    )
    _require(
        condition=found[0].ext_as(PageSpan) == span,
        message="the store did not satisfy: found[0].ext_as(PageSpan) == span",
    )
    _require(
        condition=found[0].ext_as(BlobRef) == ref,
        message="the store did not satisfy: found[0].ext_as(BlobRef) == ref",
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
        condition=frozenset(node.content for node in page.items)
        == frozenset({"alpha", "beta", "gamma"}),
        message="the store did not satisfy: frozenset(node.content for node in page.items) == "
        "frozense...",
    )
    _require(
        condition=page.next_cursor is None,
        message="the store did not satisfy: page.next_cursor is None",
    )
    _require(
        condition=total == 3,
        message="the store did not satisfy: total == 3",
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
        condition=removed.source_id == _SOURCE_B,
        message="the store did not satisfy: removed.source_id == _SOURCE_B",
    )
    _require(
        condition=removed.node_count == 2,
        message="the store did not satisfy: removed.node_count == 2",
    )
    _require(
        condition=removed.narrowed_count == 0,
        message="the store did not satisfy: removed.narrowed_count == 0",
    )
    _require(
        condition=frozenset(node.content for node in (await store.scan()).items)
        == frozenset({"alpha"}),
        message="the store did not satisfy: frozenset(node.content for node in (await "
        "store.scan()).it...",
    )
    _require(
        condition=await store.get_source(_SOURCE_B) is None,
        message="the store did not satisfy: await store.get_source(_SOURCE_B) is None",
    )


async def check_concurrent_writes_on_one_handle_all_land(store: NodeStore) -> None:
    """One handle owes callers that overlap exactly what a serial run gives them.

    Phase 43e's first owner answer. `raptor`, `hypothetical-questions` and `llm-facts` fan out
    under `asyncio.gather` through one handle, and the first calls on a handle that has not yet
    touched storage race to open it. Two interleaved transactions on one pgvector connection
    were `R43.40`. One event loop only: this asks nothing of threads.
    """
    # Arrange — a handle that has not touched storage, so these calls are also its first.
    nodes = tuple(
        _node(f"concurrent write {i}", sources=frozenset({_SOURCE_A}))
        for i in range(_CONCURRENT_CALLERS)
    )

    # Act
    await asyncio.gather(*(store.add([node]) for node in nodes))
    stored = await store.get([node.id for node in nodes])
    count = await store.count()

    # Assert
    _require(
        condition={node.content for node in stored} == {node.content for node in nodes}
        and count == len(nodes),
        message=f"{len(nodes)} overlapping writes on one handle left {len(stored)} readable "
        f"and a count of {count}; a serial run leaves {len(nodes)}",
    )


async def check_reads_overlapping_writes_on_one_handle_answer_as_a_serial_run_would(
    store: FilterableStore,
) -> None:
    """A read that overlaps writes on the same handle answers what it would answer alone.

    Phase 43e's first owner answer, on its read side: a layer reads its leaves and keeps its
    summaries through one handle while other callers write, and neither may see the other's
    half-finished transaction.
    """
    # Arrange
    stored = tuple(
        _node(f"already stored {i}", sources=frozenset({_SOURCE_A}))
        for i in range(_CONCURRENT_CALLERS)
    )
    arriving = tuple(
        _node(f"arriving {i}", sources=frozenset({_SOURCE_B})) for i in range(_CONCURRENT_CALLERS)
    )
    await store.add(stored)
    of_a = Filter(op=FilterOp.IN, field="lineage.sources", value=(str(_SOURCE_A),))

    # Act
    _, gets, pages = await asyncio.gather(
        asyncio.gather(*(store.add([node]) for node in arriving)),
        asyncio.gather(*(store.get([n.id for n in stored]) for _ in arriving)),
        asyncio.gather(*(store.matching(of_a) for _ in arriving)),
    )
    count = await store.count()

    # Assert
    wanted = {node.content for node in stored}
    _require(
        condition=all({node.content for node in got} == wanted for got in gets)
        and all({node.content for node in page.items} == wanted for page in pages),
        message="a read overlapping writes on its handle answered other than a serial read: "
        f"gets {[len(got) for got in gets]}, filters {[len(p.items) for p in pages]}, of "
        f"{len(wanted)}",
    )
    _require(
        condition=count == len(stored) + len(arriving),
        message=f"after overlapping reads and writes the store counts {count}, not "
        f"{len(stored) + len(arriving)}",
    )


async def check_add_merges_a_nodes_sources_rather_than_replacing_them(
    store: NodeStore,
) -> None:
    """The write half. Two documents, the same bytes, one node, and it belongs to both."""
    # Arrange — the same content reached from two different documents.
    from_a = _node("shared", sources=frozenset({_SOURCE_A}))
    from_b = _node("shared", sources=frozenset({_SOURCE_B}))
    _require(
        condition=from_a.id == from_b.id,
        message="the fixture must exercise the collision, not avoid it",
    )

    # Act
    await store.add((from_a,))
    await store.add((from_b,))

    # Assert
    stored = await store.get((from_a.id,))
    _require(
        condition=len(stored) == 1,
        message="the store did not satisfy: len(stored) == 1",
    )
    _require(
        condition=stored[0].lineage.sources == frozenset({_SOURCE_A, _SOURCE_B}),
        message="the store did not satisfy: stored[0].lineage.sources == frozenset({_SOURCE_A, "
        "_SOURCE_B})",
    )
    _require(
        condition=await store.count() == 1,
        message="the store did not satisfy: await store.count() == 1",
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
        condition=(removed.node_count, removed.narrowed_count) == (0, 1),
        message="the store did not satisfy: (removed.node_count, removed.narrowed_count) == (0, 1)",
    )
    surviving = await store.get((from_a.id,))
    _require(
        condition=len(surviving) == 1,
        message="the store did not satisfy: len(surviving) == 1",
    )
    _require(
        condition=surviving[0].lineage.sources == frozenset({_SOURCE_B}),
        message="the store did not satisfy: surviving[0].lineage.sources == frozenset({_SOURCE_B})",
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
        condition=(first.node_count, first.narrowed_count) == (0, 1),
        message="the store did not satisfy: (first.node_count, first.narrowed_count) == (0, 1)",
    )
    _require(
        condition=(second.node_count, second.narrowed_count) == (1, 0),
        message="the store did not satisfy: (second.node_count, second.narrowed_count) == (1, 0)",
    )
    _require(
        condition=await store.count() == 0,
        message="the store did not satisfy: await store.count() == 0",
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
        condition=derived.lineage.sources
        == also_collided.lineage.sources | collided.lineage.sources,
        message="the store did not satisfy: derived.lineage.sources == "
        "also_collided.lineage.sources |...",
    )

    # Act
    removed = await store.delete_source(_SOURCE_A)

    # Assert
    _require(
        condition=(removed.node_count, removed.narrowed_count) == (1, 1),
        message="the store did not satisfy: (removed.node_count, removed.narrowed_count) == (1, 1)",
    )
    surviving = {node.content: node for node in (await store.scan()).items}
    _require(
        condition=frozenset(surviving) == frozenset({"collided"}),
        message='the store did not satisfy: frozenset(surviving) == frozenset({"collided"})',
    )
    _require(
        condition=surviving["collided"].lineage.sources == frozenset({_SOURCE_B}),
        message='the store did not satisfy: surviving["collided"].lineage.sources == '
        "frozenset({_SOURC...",
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
        condition=(removed.node_count, removed.narrowed_count) == (1, 0),
        message="the store did not satisfy: (removed.node_count, removed.narrowed_count) == (1, 0)",
    )
    _require(
        condition=await store.count() == 0,
        message="the store did not satisfy: await store.count() == 0",
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
        condition=(first.node_count, first.narrowed_count) == (1, 0),
        message="the store did not satisfy: (first.node_count, first.narrowed_count) == (1, 0)",
    )
    _require(
        condition=await store.count() == 0,
        message="the store did not satisfy: await store.count() == 0",
    )

    # Act — the same content arrives again, from a different document this time.
    await store.add((_node("recycled", sources=frozenset({_SOURCE_B})),))
    second = await store.delete_source(_SOURCE_B)

    # Assert — B was its only producer, so the node goes. A narrowing here would mean A's
    # production outlived the node it described.
    _require(
        condition=(second.node_count, second.narrowed_count) == (1, 0),
        message="the store did not satisfy: (second.node_count, second.narrowed_count) == (1, 0)",
    )
    _require(
        condition=await store.count() == 0,
        message="the store did not satisfy: await store.count() == 0",
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
        condition=callable(getattr(store, "supersede", None)),
        message="the capability is derived from the methods a store implements and never declared "
        "(G4), so a real backend must satisfy this Protocol without saying anything",
    )
    await store.supersede(old.id, new)
    await store.flush()

    # Assert
    _require(
        condition=[node.id for node in await store.get([old.id])] == [],
        message="the superseded node survived",
    )
    _require(
        condition=[node.content for node in await store.get([new.id])] == ["beta, revised"],
        message="the store did not satisfy: [node.content for node in await store.get([new.id])] "
        '== ["...',
    )
    _require(
        condition=frozenset(node.content for node in (await store.scan()).items)
        == frozenset({"alpha", "beta, revised", "gamma"}),
        message="supersede touched a node it was not given",
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
        condition=frozenset(node.content for node in (await store.scan()).items)
        == frozenset({"alpha", "beta, revised", "gamma"}),
        message="the retry changed the store, so an interrupted supersede cannot safely be "
        "repeated",
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
        condition=_SOURCE_B in message,
        message=f"the refusal must name the source that would be dropped: {message!r}",
    )
    _require(
        condition=frozenset(node.content for node in (await store.scan()).items)
        == frozenset({"alpha", "beta", "gamma"}),
        message="a refused supersede must change nothing at all",
    )


async def check_reconcile_finishes_a_deletion_that_was_interrupted(
    store: ReconcilableStore,
) -> None:
    """An interrupted deletion is finished by the next pass, not restarted.

    Task **5.1b**'s property, on both real backends: a deletion that started and did not
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
    report = await store.reconcile(_conformance_context(store), ReconcileMode.REPAIR)
    again = await store.reconcile(_conformance_context(store), ReconcileMode.REPAIR)

    # Assert — the first pass finished the job; the second found nothing and is a no-op.
    _require(
        condition=(report.examined, report.removed, report.converged) == (1, 2, True),
        message="the store did not satisfy: (report.examined, report.removed, report.converged) == "
        "(1,...",
    )
    _require(
        condition=(again.examined, again.removed, again.converged) == (0, 0, True),
        message="the store did not satisfy: (again.examined, again.removed, again.converged) == "
        "(0, 0,...",
    )
    _require(
        condition=frozenset(node.content for node in (await store.scan()).items)
        == frozenset({"alpha"}),
        message="the store did not satisfy: frozenset(node.content for node in (await "
        "store.scan()).it...",
    )
    _require(
        condition=await store.get_source(_SOURCE_B) is None,
        message="the store did not satisfy: await store.get_source(_SOURCE_B) is None",
    )


async def check_reconcile_leaves_a_healthy_store_alone_on_either_backend(
    store: ReconcilableStore,
) -> None:
    """Reconcile leaves a store alone whose nodes have no source records.

    The other half, and the one that would have been a corpus-erasing bug: a node store
    holds the primary data, so a source record it has never been given is not evidence that
    its nodes are orphans. Nothing is removed here, and `full` removes no more than `repair`.
    """
    # Arrange — three nodes and no source records at all, which is what `weft index` leaves.
    await store.add(conformance_corpus())

    # Act
    report = await store.reconcile(_conformance_context(store), ReconcileMode.FULL)

    # Assert
    _require(
        condition=(report.removed, report.backfilled, report.converged) == (0, 0, True),
        message="the store did not satisfy: (report.removed, report.backfilled, report.converged) "
        "== (...",
    )
    _require(
        condition=await store.count() == 3,
        message="the store did not satisfy: await store.count() == 3",
    )


async def check_estimate_reports_zero_model_calls_on_either_backend(
    store: ReconcilableStore,
) -> None:
    """Keeps a store's reconcile estimate from inventing model cost it would never spend.

    Task **5.1c**'s own floor, on both real backends: a node store holds the primary data,
    so `full` has nothing to backfill and `estimate` says so honestly rather than guessing at
    a number — see `PgVectorStore.estimate`'s own docstring, which owns the argument for both.
    """
    # Arrange — three nodes, no tombstones: nothing pending either.
    await store.add(conformance_corpus())

    # Act
    estimate = await store.estimate(_conformance_context(store), ReconcileMode.FULL)

    # Assert
    _require(
        condition=(estimate.pending, estimate.model_calls) == (0, 0),
        message="the store did not satisfy: (estimate.pending, estimate.model_calls) == (0, 0)",
    )


async def check_estimate_counts_the_identical_tombstones_reconcile_itself_examines(
    store: ReconcilableStore,
) -> None:
    """`estimate`'s `pending` agrees with what `reconcile` examines.

    `estimate`'s own `pending` must never disagree with what `reconcile` actually examines —
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
    estimate = await store.estimate(_conformance_context(store), ReconcileMode.REPAIR)
    report = await store.reconcile(_conformance_context(store), ReconcileMode.REPAIR)

    # Assert
    _require(
        condition=estimate.pending == 1,
        message="the store did not satisfy: estimate.pending == 1",
    )
    _require(
        condition=report.examined == 1,
        message="the store did not satisfy: report.examined == 1",
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
        status=SourceStatus.FAILED,
        failure=SourceFailure(
            error_type="Failed",
            stage="extract",
            message="not valid UTF-8",
            attempts=2,
            last_attempt_at=datetime.now(UTC),
        ),
    )

    # Act
    await store.put_source(record)
    found = await store.get_source(_SOURCE_A)
    listed = await store.list_sources()

    # Assert
    _require(
        condition=found == record,
        message="the store did not satisfy: found == record",
    )
    _require(
        condition=tuple(item.id for item in listed) == (_SOURCE_A,),
        message="the store did not satisfy: tuple(item.id for item in listed) == (_SOURCE_A,)",
    )


async def check_a_source_records_layers_round_trip_whole_and_are_listed(store: NodeStore) -> None:
    """Layer records in three statuses round-trip whole and are listed.

    Ledger **43.6**, widened at **43.21**: three layers in three statuses on one record,
    none on another — each read back whole, by `get_source` and by `list_sources`. `==` on the
    frozen record, for the reason `check_a_source_record_round_trips_and_is_listed` gives: a
    store that names its columns keeps only the fields its author had heard of. `STALE` joins
    `ACTIVE`/`FAILED` here so a third-party store is held to round-tripping it too, the same
    way `test_a_stale_layer_record_round_trips_whole_and_is_listed` holds the two first-party
    ones.
    """
    # Arrange
    when = datetime.now(UTC)
    layered = SourceRecord(
        id=_SOURCE_A,
        uri="file:///corpus/a.txt",
        content_hash="hash-a",
        indexed_at=when,
        pipeline="conformance",
        pipeline_identity="base-a",
        layers=(
            LayerRecord(
                name="enrich-with-questions",
                pipeline_identity="layer-q",
                status=LayerStatus.ACTIVE,
                attempts=1,
                at=when,
            ),
            LayerRecord(
                name="enrich-with-facts",
                pipeline_identity="layer-f",
                status=LayerStatus.FAILED,
                failure=SourceFailure(
                    error_type="Failed",
                    stage="facts",
                    message="the model refused",
                    attempts=2,
                    last_attempt_at=when,
                ),
                attempts=2,
                at=when,
            ),
            LayerRecord(
                name="enrich-with-summary",
                pipeline_identity="layer-s",
                status=LayerStatus.STALE,
                attempts=1,
                at=when,
            ),
        ),
    )
    bare = SourceRecord(
        id=_SOURCE_B,
        uri="file:///corpus/b.txt",
        content_hash="hash-b",
        indexed_at=when,
        pipeline="conformance",
    )

    # Act
    await store.put_source(layered)
    await store.put_source(bare)
    found = await store.get_source(_SOURCE_A)
    listed = {record.id: record for record in await store.list_sources()}

    # Assert
    _require(condition=found == layered, message="the store did not satisfy: found == layered")
    _require(
        condition=listed == {_SOURCE_A: layered, _SOURCE_B: bare},
        message="the store did not satisfy: listed == {_SOURCE_A: layered, _SOURCE_B: bare}",
    )


def _failed_record(source_id: SourceId, name: str) -> SourceRecord:
    return SourceRecord(
        id=source_id,
        uri=f"file:///corpus/{name}",
        content_hash=f"hash-{name}",
        indexed_at=datetime.now(UTC),
        pipeline="conformance",
        status=SourceStatus.FAILED,
        failure=SourceFailure(
            error_type="Failed",
            stage="extract",
            message="not valid UTF-8",
            attempts=1,
            last_attempt_at=datetime.now(UTC),
        ),
    )


async def check_deleting_a_failed_source_removes_it_like_any_other(store: NodeStore) -> None:
    """Deleting a failed source removes its record and every node it left.

    Ledger **36.5**: an operator abandoning a document that failed has one command that works —
    its record goes, and so does every node it left behind.
    """
    # Arrange
    await store.add(conformance_corpus())
    await store.put_source(_failed_record(_SOURCE_B, "b.txt"))

    # Act
    removed = await store.delete_source(_SOURCE_B)

    # Assert
    _require(
        condition=removed.node_count == 2,
        message="the store did not satisfy: removed.node_count == 2",
    )
    _require(
        condition=await store.get_source(_SOURCE_B) is None,
        message="the store did not satisfy: await store.get_source(_SOURCE_B) is None",
    )


async def check_reconcile_neither_deletes_nor_clears_a_failed_source(
    store: ReconcilableStore,
) -> None:
    """Reconcile leaves a failed source's record in place.

    Ledger **36.5**: reconcile finishes interrupted deletions; a failed source is not one, and
    its record is the only place an operator can find what went wrong.
    """
    # Arrange
    await store.add(conformance_corpus())
    record = _failed_record(_SOURCE_A, "a.txt")
    await store.put_source(record)

    # Act
    await store.reconcile(_conformance_context(store), ReconcileMode.REPAIR)
    await store.reconcile(_conformance_context(store), ReconcileMode.FULL)

    # Assert
    _require(
        condition=await store.get_source(_SOURCE_A) == record,
        message="the store did not satisfy: await store.get_source(_SOURCE_A) == record",
    )
    _require(
        condition=await store.count() == 3,
        message="the store did not satisfy: await store.count() == 3",
    )


async def check_search_vector_ranks_by_cosine_similarity_on_either_backend(
    store: SearchableStore,
) -> None:
    # Arrange
    await store.add(conformance_corpus())
    _require(
        condition=callable(getattr(store, "search_vector", None)),
        message='the store did not satisfy: callable(getattr(store, "search_vector", None))',
    )

    # Act
    ranked = await store.search_vector(Vector(values=(0.0, 1.0, 0.0)), top_k=2)

    # Assert
    _require(
        condition=[scored.value.content for scored in ranked] == ["beta", "alpha"],
        message="the store did not satisfy: [scored.value.content for scored in ranked] == "
        '["beta", "a...',
    )
    _require(
        condition=abs(ranked[0].score - 1.0) < 1e-3,
        message=f"an exact match must score 1.0: {ranked[0].score}",
    )


async def check_search_text_finds_the_node_that_carries_the_words(
    store: TextSearchableStore,
) -> None:
    """`TextSearch` promises a *ranked* result, and this is the floor of that promise.

    **What this deliberately does not check, stated rather than left to be discovered.** The
    shared corpus is `alpha`, `beta`, `gamma` — no two nodes carry a term in common — so nothing
    here can compare two matching nodes and therefore nothing here checks *ordering*, which is the
    property a sign error in an adapter breaks. Weft's own backends cover that in their unit
    suites, and widening this corpus is not free: it is the shared subject of every filter check,
    and `docs/internal/lessons.md` `L15.3` records a field being removed from it taking five of
    them red. A kit check that pretended otherwise would be worse than one that says so.
    """
    # Arrange
    await store.add(conformance_corpus())
    _require(
        condition=callable(getattr(store, "search_text", None)),
        message='the store did not satisfy: callable(getattr(store, "search_text", None))',
    )

    # Act
    ranked = await store.search_text("beta", top_k=3)

    # Assert
    _require(
        condition=[scored.value.content for scored in ranked] == ["beta"],
        message=f"a lexical search for a word one node carries must return that node: "
        f"{[scored.value.content for scored in ranked]}",
    )


async def check_search_text_answers_nothing_matching_with_an_empty_ranking(
    store: TextSearchableStore,
) -> None:
    """A text search that matches nothing returns an empty sequence.

    `TextSearch`'s own emptiness rule, in its own words: *"a store whose index holds nothing
    matching returns an empty sequence; that is the honest answer to 'what matches these words',
    and it is a different fact from a store that could not look, which raises."*

    The failure this refuses is the one with no symptom — a backend that answers an unmatched query
    with every node it holds, at whatever score its operator gives a non-match, looks like a
    working text arm until somebody reads the results.
    """
    # Arrange
    await store.add(conformance_corpus())

    # Act
    ranked = await store.search_text("nonesuch-lexeme-no-corpus-carries", top_k=3)

    # Assert
    _require(
        condition=list(ranked) == [],
        message=f"nothing matching is an empty ranking, not a ranking of everything: "
        f"{[scored.value.content for scored in ranked]}",
    )


async def check_search_text_narrows_by_a_filter_rather_than_ignoring_it(
    store: FilterableTextStore,
) -> None:
    """A `Filter` reaches *inside* the lexical ranking, never around it.

    `MetadataFilter`'s own promise is that a store which can evaluate a filter honours one on
    whichever search capabilities it has — so a store with both owes this. The failure it refuses
    is the one the review this repair came from names outright: *"do not fetch a global lexical
    top-k and apply tenant filters afterwards."* Post-filtering returns fewer than `top_k` for a
    reason the caller cannot see, and on a large corpus returns nothing at all while matching rows
    exist.
    """
    # Arrange
    await store.add(conformance_corpus())

    # Act — `beta` carries both sources; the filter keeps the one it does not have.
    excluded = await store.search_text(
        "beta",
        top_k=3,
        filter=Filter(op=FilterOp.CONTAINS, field="lineage.sources", value=_SOURCE_B),
    )
    kept = await store.search_text(
        "gamma",
        top_k=3,
        filter=Filter(op=FilterOp.CONTAINS, field="lineage.sources", value=_SOURCE_A),
    )

    # Assert
    _require(
        condition=[scored.value.content for scored in excluded] == ["beta"],
        message=f"a filter the match satisfies must keep it: "
        f"{[scored.value.content for scored in excluded]}",
    )
    _require(
        condition=list(kept) == [],
        message=f"a filter the match does not satisfy must drop it, not return it anyway: "
        f"{[scored.value.content for scored in kept]}",
    )


async def check_every_operator_means_the_same_thing_to_both_backends(
    store: FilterableStore, label: str, filter_: Filter, expected: frozenset[str]
) -> None:
    # Arrange
    await store.add(conformance_corpus())
    _require(
        condition=callable(getattr(store, "matching", None)),
        message='the store did not satisfy: callable(getattr(store, "matching", None))',
    )

    # Act
    page = await store.matching(filter_)

    # Assert
    _require(
        condition=await _all(page) == expected,
        message=f"'{label}' disagrees between backends",
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
        condition=callable(getattr(store, "matching", None)),
        message='the store did not satisfy: callable(getattr(store, "matching", None))',
    )

    # Act
    page = await store.matching(
        Filter(op=FilterOp.CONTAINS, field="lineage.parents", value=str(parent.id))
    )

    # Assert
    _require(
        condition=await _all(page) == frozenset({"row 0", "row 1"}),
        message='the store did not satisfy: await _all(page) == frozenset({"row 0", "row 1"})',
    )


async def check_a_parent_id_nothing_derives_from_selects_nothing_rather_than_everything(
    store: FilterableStore,
) -> None:
    """A filter on a parent id nothing derives from selects nothing.

    The negative half, because a filter that silently matched nothing and one that silently
    matched everything look identical from a single positive case — and `weft_store.fields`'
    own `UnaddressableFieldError` docstring is explicit that *"a filter matching nothing looks
    exactly like a corpus that holds nothing"*.
    """
    # Arrange
    await store.add(conformance_corpus())
    _require(
        condition=callable(getattr(store, "matching", None)),
        message='the store did not satisfy: callable(getattr(store, "matching", None))',
    )

    # Act
    page = await store.matching(
        Filter(op=FilterOp.CONTAINS, field="lineage.parents", value="no-such-node")
    )

    # Assert
    _require(
        condition=await _all(page) == frozenset(),
        message="the store did not satisfy: await _all(page) == frozenset()",
    )


async def check_a_parents_children_within_an_ordinal_range_are_one_filter_away(
    store: FilterableStore,
) -> None:
    """A hit's siblings, by position — ledger `32.2`, what `adjacent-chunks` (`32.3`) asks.

    `lineage.parents` alone was checked above; this is that predicate **and** an integer `in`
    over `ext.weft-chunk.ordinal` (`weft_chunk.payload.ChunkPosition`, `32.1`), the one
    combination reading the two translators cannot settle. A second parent whose children
    carry the same ordinals is stored beside it, so a store that dropped either clause
    answers visibly wrong rather than accidentally right.
    """
    # Arrange
    wanted = _node("wanted parent", sources=frozenset({_SOURCE_A}))
    other = _node("other parent", sources=frozenset({_SOURCE_B}))
    children = tuple(
        parent.derive(content=f"{label} {ordinal}", ordinal=ordinal).with_ext(
            ChunkPosition(ordinal=ordinal, start=ordinal * 10)
        )
        for parent, label in ((wanted, "wanted"), (other, "other"))
        for ordinal in range(5)
    )
    await store.add((wanted, other, *children))
    _require(
        condition=callable(getattr(store, "matching", None)),
        message='the store did not satisfy: callable(getattr(store, "matching", None))',
    )

    # Act
    page = await store.matching(
        Filter(
            op=FilterOp.AND,
            clauses=(
                Filter(op=FilterOp.CONTAINS, field="lineage.parents", value=str(wanted.id)),
                Filter(op=FilterOp.IN, field="ext.weft-chunk.ordinal", value=(1, 2, 3)),
            ),
        )
    )

    # Assert
    _require(
        condition=await _all(page) == frozenset({"wanted 1", "wanted 2", "wanted 3"}),
        message='the store did not satisfy: await _all(page) == frozenset({"wanted 1", "wanted 2", '
        '"wanted 3"})',
    )


async def check_in_over_a_set_field_matches_a_node_holding_any_listed_value(
    store: FilterableStore,
) -> None:
    """`in` over `lineage.sources` is overlap: any listed source, among any others, matches.

    Carried repair `R43.50`. `weft_store.fields` admits `in` on a set field, both shipped
    backends answer it as overlap, and every layer reads its leaves through exactly this
    (`weft_cli.layers.layer_leaf_filter`). A store comparing the whole set against the list
    answers nothing, and a corpus layer built over it publishes an empty tree.
    """
    # Arrange
    await store.add(
        (
            _node("holds a among others", sources=frozenset({_SOURCE_A, _SOURCE_B})),
            _node("holds only a", sources=frozenset({_SOURCE_A})),
            _node("holds only b", sources=frozenset({_SOURCE_B})),
        )
    )

    # Act
    page = await store.matching(
        Filter(op=FilterOp.IN, field="lineage.sources", value=(str(_SOURCE_A), "source-unheld"))
    )

    # Assert
    _require(
        condition=await _all(page) == frozenset({"holds a among others", "holds only a"}),
        message="in over lineage.sources must match every node holding a listed source, "
        f"among others or alone, and no other; got {sorted(await _all(page))}",
    )


async def check_writing_a_node_again_under_its_id_replaces_its_ext(
    store: FilterableStore,
) -> None:
    """Guards the upsert against keeping stale extension data when a node is rewritten.

    `weft index --reprocess` is how a corpus indexed before `32.1` gains positions — Phase
    32's owner question 5, settled on measurement — and it works only if writing a node again
    under an unchanged id replaces its `ext` rather than keeping the first write's. A chunk's id
    does not move when `ChunkPosition` is added (`32.1` pins that), so this is exactly the write
    a re-index performs.
    """
    # Arrange
    parent = _node("reprocessed parent", sources=frozenset({_SOURCE_A}))
    before = parent.derive(content="indexed before positions existed", ordinal=0)
    after = before.with_ext(ChunkPosition(ordinal=0, start=0))
    await store.add((parent, before))

    # Act
    await store.add((after,))
    page = await store.matching(Filter(op=FilterOp.EXISTS, field="ext.weft-chunk.ordinal"))

    # Assert
    _require(
        condition=await _all(page) == frozenset({"indexed before positions existed"}),
        message='the store did not satisfy: await _all(page) == frozenset({"indexed before '
        "positions "
        'existed"})',
    )


async def check_a_filter_reaches_vector_search_rather_than_being_ignored(
    store: FilterableSearchableStore,
) -> None:
    # Arrange
    await store.add(conformance_corpus())
    _require(
        condition=callable(getattr(store, "search_vector", None)),
        message='the store did not satisfy: callable(getattr(store, "search_vector", None))',
    )

    # Act
    ranked = await store.search_vector(
        Vector(values=(0.0, 1.0, 0.0)),
        top_k=5,
        filter=Filter(op=FilterOp.EQ, field="content", value="alpha"),
    )

    # Assert
    _require(
        condition=[scored.value.content for scored in ranked] == ["alpha"],
        message="the store did not satisfy: [scored.value.content for scored in ranked] == "
        '["alpha"]',
    )


async def check_a_filtered_search_returns_top_k_in_the_approximate_regime(
    store: FilterableSearchableStore,
) -> None:
    """A filtered vector search must not go short under an approximate index — task **31.5**.

    `check_a_filter_reaches_vector_search_rather_than_being_ignored` asks `top_k=5` of three nodes,
    where a post-filter shortfall and a correct answer are indistinguishable — three nodes can
    never answer more than three. Phase 29 measured the real failure on a real corpus: pgvector
    under `hnsw.iterative_scan = off` returned a mean of **0.03 rows out of 10** at 0.1%
    selectivity, silently, with no error to notice it by. No check built before this task could
    have seen that, because none of them ever built an index.

    **The corpus is shaped to force a pre-filter candidate cut, not merely a small one.** 185
    nodes sit almost exactly where the query vector points; 15 carry the filter and sit well away
    from it. A search that fetches its nearest neighbours *before* the filter is applied fills its
    whole candidate list with the 185 near-duplicates and finds none of the 15 that matter; a
    search where the filter reaches inside the index keeps looking until it is satisfied, finds
    all fifteen, and this check asks for ten of them.
    """
    # Arrange
    top_k = 10
    target_count = 15
    noise_count = 185
    query = Vector(values=(1.0, 0.0, 0.0))
    noise = tuple(
        _node(
            f"noise-{i}",
            sources=frozenset({_SOURCE_A}),
            embedding=Vector(values=(1.0, (i % 7) * 1e-6, (i % 5) * 1e-6)),
        )
        for i in range(noise_count)
    )
    targets = tuple(
        _node(
            f"target-{i}",
            sources=frozenset({_SOURCE_A}),
            pages=ConformanceFact(backend="target"),
            embedding=Vector(
                values=(
                    math.cos(2 * math.pi * i / target_count),
                    math.sin(2 * math.pi * i / target_count),
                    0.5,
                )
            ),
        )
        for i in range(target_count)
    )
    await store.add(noise + targets)
    await store.flush()
    _require(
        condition=callable(getattr(store, "search_vector", None)),
        message='the store did not satisfy: callable(getattr(store, "search_vector", None))',
    )

    # Act
    ranked = await store.search_vector(
        query,
        top_k=top_k,
        filter=Filter(op=FilterOp.EQ, field="ext.weft-store-conformance.backend", value="target"),
    )

    # Assert — the count first: a store returning fewer than the caller asked for is the failure
    # this check exists to catch, and a predicate alone cannot see it.
    _require(
        condition=len(ranked) == top_k,
        message=f"{target_count} nodes matched the filter and top_k={top_k} was asked for, but the "
        f"approximate regime returned {len(ranked)}",
    )
    _require(
        condition=all(
            scored.value.ext_as(ConformanceFact) == ConformanceFact(backend="target")
            for scored in ranked
        ),
        message="every result must satisfy the filter: "
        f"{[scored.value.content for scored in ranked]}",
    )


async def check_a_field_no_node_can_have_is_refused_by_name_on_either_backend(
    store: FilterableStore,
) -> None:
    # Arrange
    _require(
        condition=callable(getattr(store, "matching", None)),
        message='the store did not satisfy: callable(getattr(store, "matching", None))',
    )
    nonsense = Filter(op=FilterOp.EQ, field="metadata.author", value="nobody")

    # Act / Assert
    try:
        await store.matching(nonsense)
    except UnaddressableFieldError as exc:
        _require(
            condition="metadata.author" in str(exc),
            message=f"the refusal must name the field: {str(exc)!r}",
        )
    else:
        raise AssertionError("a field no node can carry was accepted; it must be refused by name")


async def check_an_operator_a_field_cannot_carry_is_refused_by_name_on_either_backend(
    store: FilterableStore,
) -> None:
    # Arrange
    _require(
        condition=callable(getattr(store, "matching", None)),
        message='the store did not satisfy: callable(getattr(store, "matching", None))',
    )
    wrong = Filter(op=FilterOp.EQ, field="lineage.sources", value=_SOURCE_A)

    # Act / Assert
    try:
        await store.matching(wrong)
    except FilterOpMismatchError as exc:
        _require(
            condition="contains" in str(exc),
            message=f"the refusal must name the operator: {str(exc)!r}",
        )
    else:
        raise AssertionError("an operator the field cannot carry was accepted; refuse it by name")


#: The targets the checks create. The kit owns no lifecycle (`26.4`): a caller hands each check a
#: fresh store, and a persistent backend's own suite removes what a check left behind.
_CANDIDATE = "conformance_candidate"
_OTHER = "conformance_other"


def _promotion(target: str) -> Promotion:
    return Promotion(
        target=target,
        at=datetime.now(UTC),
        by="conformance",
        evidence=("run-live", "run-candidate"),
        without_evidence=False,
    )


async def check_a_fresh_store_has_one_live_target_named_default(
    store: TargetHoldingStore,
) -> None:
    """Ledger **34.2**'s contract half: a store nothing has targeted reads as `default`, live."""
    # Act
    catalogue = await store.target_catalogue()

    # Assert
    _require(
        condition=catalogue.live == DEFAULT_TARGET,
        message=f"live must be 'default': {catalogue.live!r}",
    )
    _require(
        condition=catalogue.previous is None,
        message=f"previous must be None: {catalogue.previous!r}",
    )
    _require(
        condition=DEFAULT_TARGET in {record.name for record in catalogue.targets},
        message="the catalogue must list 'default' even before anything named a target",
    )
    _require(
        condition=catalogue.promotion is None,
        message="nothing was promoted, so no promotion is recorded",
    )


async def check_a_target_is_created_by_its_first_write_and_isolated_from_every_other(
    store: TargetHoldingStore,
) -> None:
    """A node written into a candidate is invisible to the live target, and the reverse."""
    # Arrange
    candidate = await store.bind_target(target_name(_CANDIDATE))
    before = await store.target_catalogue()
    _require(
        condition=_CANDIDATE not in {record.name for record in before.targets},
        message="binding a target must not create it; its first write does",
    )
    live_node, candidate_node = conformance_corpus()[:2]

    # Act
    await store.add((live_node,))
    await candidate.add((candidate_node,))
    after = await store.target_catalogue()

    # Assert
    _require(
        condition=_CANDIDATE in {record.name for record in after.targets},
        message="a target's first write must add it to the catalogue",
    )
    _require(
        condition=after.live == DEFAULT_TARGET, message="writing a candidate must not make it live"
    )
    _require(
        condition=tuple(node.id for node in await store.get((candidate_node.id,))) == (),
        message="the live target returned a node written only into the candidate",
    )
    _require(
        condition=tuple(node.id for node in await candidate.get((live_node.id,))) == (),
        message="the candidate returned a node written only into the live target",
    )
    _require(
        condition=await candidate.count() == 1, message="the candidate must count only its own node"
    )


async def check_a_source_record_belongs_to_the_target_it_was_written_into(
    store: TargetHoldingStore,
) -> None:
    """Source records are per target too: a target's sources are listed from that target alone."""
    # Arrange
    candidate = await store.bind_target(target_name(_CANDIDATE))
    record = SourceRecord(
        id=_SOURCE_A,
        uri="file:///corpus/a.txt",
        content_hash="hash-a",
        indexed_at=datetime.now(UTC),
        pipeline="conformance",
    )

    # Act
    await candidate.put_source(record)

    # Assert
    _require(
        condition=await store.get_source(_SOURCE_A) is None,
        message="the live target saw a candidate's source",
    )
    _require(
        condition=await candidate.get_source(_SOURCE_A) == record,
        message="the candidate lost its source",
    )


async def check_promote_makes_a_target_live_and_rollback_restores_the_previous_one(
    store: TargetHoldingStore,
) -> None:
    """One pointer, switched whole: live and previous move together, and the promotion is kept."""
    # Arrange
    candidate = await store.bind_target(target_name(_CANDIDATE))
    await candidate.add(conformance_corpus()[:1])
    promotion = _promotion(_CANDIDATE)

    # Act
    promoted = await store.promote(promotion)
    rolled_back = await store.rollback()

    # Assert
    _require(
        condition=promoted.live == _CANDIDATE,
        message=f"promote must make the target live: {promoted.live!r}",
    )
    _require(
        condition=promoted.previous == DEFAULT_TARGET, message="promote must record what was live"
    )
    _require(
        condition=promoted.promotion == promotion, message="the promotion must be recorded whole"
    )
    _require(
        condition=rolled_back.live == DEFAULT_TARGET,
        message="rollback must restore the previous target",
    )
    _require(
        condition=rolled_back.previous == _CANDIDATE,
        message="rollback must remember what it replaced",
    )
    _require(
        condition=await store.target_catalogue() == rolled_back,
        message="the catalogue read back must be the one rollback returned",
    )


async def check_promote_refuses_a_target_that_does_not_exist_naming_those_that_do(
    store: TargetHoldingStore,
) -> None:
    # Act / Assert
    try:
        await store.promote(_promotion("conformance_absent"))
    except UnknownTargetError as exc:
        _require(
            condition=DEFAULT_TARGET in exc.valid_options,
            message=f"the refusal must offer the targets that exist: {exc.valid_options!r}",
        )
        _require(
            condition="conformance_absent" in str(exc),
            message=f"the refusal must name the target: {exc}",
        )
    else:
        raise AssertionError("a promote to a target that does not exist was accepted")
    _require(
        condition=(await store.target_catalogue()).live == DEFAULT_TARGET,
        message="a refused promote must change nothing",
    )


async def check_rollback_with_nothing_to_roll_back_to_is_refused(
    store: TargetHoldingStore,
) -> None:
    # Act / Assert
    try:
        await store.rollback()
    except NoPreviousTargetError as exc:
        _require(
            condition=DEFAULT_TARGET in str(exc),
            message=f"the refusal must name the live target: {exc}",
        )
    else:
        raise AssertionError("a rollback with no previous target was accepted")


async def check_drop_refuses_the_live_and_previous_targets_and_removes_another(
    store: TargetHoldingStore,
) -> None:
    """`drop` is the one destructive verb, so the two targets a rollback needs are refused."""
    # Arrange — `_CANDIDATE` live, `default` previous, `_OTHER` neither.
    candidate = await store.bind_target(target_name(_CANDIDATE))
    other = await store.bind_target(target_name(_OTHER))
    await candidate.add(conformance_corpus()[:1])
    await other.add(conformance_corpus()[1:2])
    await store.promote(_promotion(_CANDIDATE))
    # A store may refuse to drop a target an open handle still holds — pgvector does, because the
    # handle's next statement would reach `default`'s tables — so the writer lets go first.
    # `aclose` is read off the handle, never a contract member, as `weft_kernel.seam.aclose` does.
    close = getattr(other, "aclose", None)
    if close is not None:
        await close()

    # Act / Assert
    for protected in (_CANDIDATE, DEFAULT_TARGET):
        try:
            await store.drop_target(target_name(protected))
        except TargetInUseError as exc:
            _require(
                condition=protected in str(exc), message=f"the refusal must name the target: {exc}"
            )
        else:
            raise AssertionError(f"dropping {protected!r}, which a rollback needs, was accepted")
    await store.drop_target(target_name(_OTHER))
    names = {record.name for record in (await store.target_catalogue()).targets}
    _require(condition=_OTHER not in names, message="a dropped target must leave the catalogue")


async def check_drop_refuses_a_target_that_does_not_exist_naming_those_that_do(
    store: TargetHoldingStore,
) -> None:
    # Act / Assert
    try:
        await store.drop_target(target_name("conformance_absent"))
    except UnknownTargetError as exc:
        _require(
            condition=DEFAULT_TARGET in exc.valid_options,
            message=f"offer what exists: {exc.valid_options!r}",
        )
    else:
        raise AssertionError("dropping a target that does not exist was accepted")


async def check_the_first_embedding_identity_claimed_is_the_one_a_target_keeps(
    store: TargetHoldingStore,
) -> None:
    """Ledger **34.4**'s storage half: recorded once, per target, never per node, never replaced.

    `claim_embedding` answers with what the target holds, so the caller compares; the store does
    not decide what counts as a mismatch.
    """
    # Arrange
    candidate = await store.bind_target(target_name(_CANDIDATE))
    first = EmbeddingIdentity(plugin="hash", distribution="weft-rag", model="hash", width=64)
    second = EmbeddingIdentity(plugin="hash", distribution="weft-rag", model="hash", width=128)
    await candidate.add(conformance_corpus()[:1])

    # Act
    recorded = await candidate.claim_embedding(first)
    again = await candidate.claim_embedding(second)
    catalogue = await store.target_catalogue()

    # Assert
    _require(condition=recorded == first, message="the first claim must be recorded and returned")
    _require(
        condition=again == first,
        message="a second, different claim must return the recorded identity",
    )
    by_name = {record.name: record for record in catalogue.targets}
    _require(
        condition=by_name[_CANDIDATE].embedding == first,
        message="the catalogue must carry the identity",
    )
    _require(
        condition=by_name[DEFAULT_TARGET].embedding is None,
        message="a claim on one target must not reach another",
    )


async def check_a_target_name_outside_the_grammar_is_refused_by_name(
    store: TargetHoldingStore,
) -> None:
    """A target becomes a schema, a collection and a directory, so its alphabet is closed."""
    del store
    for bad in ("", "Default", "w-128", "1st", "a" * 41, "x;drop"):
        try:
            target_name(bad)
        except InvalidTargetNameError as exc:
            _require(
                condition=repr(bad) in str(exc), message=f"the refusal must quote the name: {exc}"
            )
        else:
            raise AssertionError(f"the target name {bad!r} was accepted")


async def check_claiming_an_identity_creates_the_target_as_a_first_write_does(
    store: TargetHoldingStore,
) -> None:
    """Lets ingest pin an embedder to a new target before any node is written to it.

    Ingest records a target's identity before its first write, so a claim on a target that
    does not exist yet creates it — catalogued and holding its storage, empty and readable.
    """
    # Arrange
    identity = EmbeddingIdentity(plugin="hash", distribution="weft-rag", model="hash", width=3)
    candidate = await store.bind_target(target_name(_CANDIDATE))

    # Act
    held = await candidate.claim_embedding(identity)
    reopened = await store.bind_target(target_name(_CANDIDATE))

    # Assert
    _require(condition=held == identity, message="the claim must be recorded and returned")
    _require(
        condition=_CANDIDATE
        in {record.name for record in (await store.target_catalogue()).targets},
        message="a claimed target must be in the catalogue",
    )
    _require(
        condition=await reopened.count() == 0,
        message="a claimed target must open, empty, on a new handle",
    )


async def check_a_target_whose_first_write_is_a_source_record_is_catalogued(
    store: TargetHoldingStore,
) -> None:
    """A target holding sources and no nodes exists.

    Ingest writes a document's source record (`INDEXING`) before its nodes, so a run
    interrupted between the two leaves a target holding sources and no nodes. That target exists:
    it is in the catalogue, and every command naming it answers about it rather than calling it
    unknown. Found at `34.8`: pgvector catalogued a target on its first node write only.
    """
    # Arrange
    candidate = await store.bind_target(target_name(_CANDIDATE))

    # Act
    await candidate.put_source(
        SourceRecord(
            id=_SOURCE_A,
            uri="file:///corpus/a.txt",
            content_hash="hash-a",
            indexed_at=datetime.now(UTC),
            pipeline="conformance",
            status=SourceStatus.INDEXING,
        )
    )

    # Assert
    _require(
        condition=_CANDIDATE
        in {record.name for record in (await store.target_catalogue()).targets},
        message="a target whose first write was a source record must be in the catalogue",
    )


async def check_promoting_the_live_target_again_changes_nothing(store: TargetHoldingStore) -> None:
    """Keeps a converging re-promote idempotent, so a rollback still has somewhere to go.

    A promote that converges participants after a crash is re-run on the ones that already
    moved, so promoting the live target keeps both pointers as they are. Were it to set `previous`
    to the live target itself, the rollback the operator needs next would go nowhere.
    """
    # Arrange
    candidate = await store.bind_target(target_name(_CANDIDATE))
    await candidate.add(conformance_corpus()[:1])
    first = await store.promote(_promotion(_CANDIDATE))

    # Act
    again = await store.promote(_promotion(_CANDIDATE))

    # Assert
    _require(
        condition=again.live == _CANDIDATE, message="promoting the live target must leave it live"
    )
    _require(
        condition=again.previous == first.previous == DEFAULT_TARGET,
        message=f"promoting the live target must keep previous: {again.previous!r}",
    )


def _member(content: str, values: tuple[float, float, float]) -> Node:
    return _node(content, sources=frozenset({_SOURCE_A}), embedding=Vector(values=values))


async def _visible(
    store: GenerationHoldingStore, content: str, values: tuple[float, float, float]
) -> tuple[bool, bool, bool]:
    """Whether `content` is found by vector search, text search and a metadata filter."""
    by_vector = any(
        s.value.content == content
        for s in await store.search_vector(Vector(values=values), top_k=10)
    )
    by_text = any(s.value.content == content for s in await store.search_text(content, top_k=10))
    page = await store.matching(Filter(op=FilterOp.EQ, field="content", value=content))
    return by_vector, by_text, any(node.content == content for node in page.items)


async def _next_operation[T: GenerationHoldingNodeStore](store: T) -> T:
    """A handle bound to a fresh, empty generation, as the next operation reads.

    A handle reading as the next operation would: bound to a fresh, empty generation, so its
    manifest is whatever is published when it first touches storage, plus nothing of its own.

    Generic over the store's own shape — bound to `GenerationHoldingNodeStore` rather than
    `GenerationHoldingStore` — so a caller with a search-capable handle gets one back, and the two
    checks that read only through `NodeStore` and the catalogue (ledger `43.39`) get one typed no
    wider than what they call.
    """
    probe = await store.open_generation("conformance-probe")
    return await store.bind_generation(probe.id)


async def check_overlapping_writes_into_one_generation_are_published_whole(
    store: GenerationHoldingStore,
) -> None:
    """Every member written through one bound handle by overlapping callers is published.

    Phase 43e's first owner answer, where it was paid for: a corpus build keeps each summary into
    its open generation as it finishes, `max_concurrent_summaries` of them at a time (`R43.40`).
    """
    # Arrange
    generation = await store.open_generation("summaries")
    writer = await store.bind_generation(generation.id)
    members = tuple(
        _member(f"concurrent member {i}", (1.0, 0.0, 0.0)) for i in range(_CONCURRENT_CALLERS)
    )

    # Act
    await asyncio.gather(*(writer.add([member]) for member in members))
    await store.publish_generation(generation.id)
    reader = await _next_operation(store)
    page = await reader.matching(
        Filter(op=FilterOp.IN, field="lineage.sources", value=(str(_SOURCE_A),))
    )

    # Assert
    _require(
        condition={node.content for node in page.items} == {m.content for m in members},
        message=f"{len(members)} overlapping writes into one generation published "
        f"{len(page.items)} members",
    )


async def check_an_unpublished_generation_is_invisible_until_it_is_published(
    store: GenerationHoldingStore,
) -> None:
    """A half-built layer is never searchable, and all of it is once published.

    Ledger **43.14**: a half-built corpus-scoped layer is never searchable — its members are
    absent from vector search, text search and metadata filters, before top-k — and all of it
    becomes searchable at once when it is published.
    """
    # Arrange
    await store.add(conformance_corpus())
    generation = await store.open_generation("summaries")
    writer = await store.bind_generation(generation.id)
    await writer.add([_member("delta", (0.0, 0.0, 1.0))])

    # Act
    before = await _visible(await _next_operation(store), "delta", (0.0, 0.0, 1.0))
    await store.publish_generation(generation.id)
    after = await _visible(await _next_operation(store), "delta", (0.0, 0.0, 1.0))

    # Assert
    _require(
        condition=before == (False, False, False),
        message=f"an unpublished member was found: {before}",
    )
    _require(
        condition=after == (True, True, True), message=f"a published member was not found: {after}"
    )


async def check_a_handle_keeps_the_generations_it_read_when_it_opened(
    store: GenerationHoldingStore,
) -> None:
    """Snapshot isolation for generations: a publish mid-operation stays invisible to it.

    One operation sees one set of generations: a handle that touched storage before a publish
    keeps what it read, so a multi-arm ask never mixes two trees.
    """
    # Arrange
    await store.add(conformance_corpus())
    generation = await store.open_generation("summaries")
    writer = await store.bind_generation(generation.id)
    await writer.add([_member("delta", (0.0, 0.0, 1.0))])
    reader = await _next_operation(store)
    await reader.count()

    # Act
    await store.publish_generation(generation.id)
    seen = await _visible(reader, "delta", (0.0, 0.0, 1.0))

    # Assert
    _require(
        condition=seen == (False, False, False),
        message=f"a handle saw a publish made after it opened: {seen}",
    )


async def check_base_nodes_are_visible_under_every_set_of_generations(
    store: GenerationHoldingStore,
) -> None:
    """A node no generation wrote — the base — is visible to every handle, published or not."""
    # Arrange
    await store.add(conformance_corpus())
    building = await store.open_generation("summaries")
    writer = await store.bind_generation(building.id)

    # Act
    unbound = await _visible(store, "alpha", (1.0, 0.0, 0.0))
    bound = await _visible(writer, "alpha", (1.0, 0.0, 0.0))

    # Assert
    _require(
        condition=unbound == (True, True, True),
        message=f"a base node was hidden from an unbound handle: {unbound}",
    )
    _require(
        condition=bound == (True, True, True),
        message=f"a base node was hidden from a bound handle: {bound}",
    )


async def check_a_node_shared_with_a_published_generation_stays_visible(
    store: GenerationHoldingStore,
) -> None:
    """Guards against a build in progress hiding a node that a published tree serves.

    A node two generations both wrote belongs to both: the unpublished one cannot hide what
    the published one made visible.
    """
    # Arrange
    shared = _member("delta", (0.0, 0.0, 1.0))
    published = await store.open_generation("summaries")
    await (await store.bind_generation(published.id)).add([shared])
    await store.publish_generation(published.id)
    building = await store.open_generation("summaries")

    # Act
    await (await store.bind_generation(building.id)).add([shared])
    seen = await _visible(await _next_operation(store), "delta", (0.0, 0.0, 1.0))

    # Assert
    _require(
        condition=seen == (True, True, True),
        message=f"a node a published generation holds was hidden: {seen}",
    )


async def check_retracting_a_generation_removes_its_own_nodes_and_keeps_shared_ones(
    store: GenerationHoldingNodeStore,
) -> None:
    """Protects shared and base nodes from the cleanup of an abandoned build.

    `retract_generation` removes the nodes only that generation made, keeps a node another
    generation also holds and every base node, and forgets the generation.
    """
    # Arrange
    await store.add(conformance_corpus())
    kept = await store.open_generation("summaries")
    await (await store.bind_generation(kept.id)).add([_member("delta", (0.0, 0.0, 1.0))])
    await store.publish_generation(kept.id)
    doomed = await store.open_generation("summaries")
    await (await store.bind_generation(doomed.id)).add(
        [_member("delta", (0.0, 0.0, 1.0)), _member("epsilon", (0.0, 0.5, 0.5))]
    )

    # Act
    removed = await store.retract_generation(doomed.id)

    # Assert
    _require(
        condition=removed.node_count == 1,
        message=f"retract must remove exactly the sole member: {removed.node_count}",
    )
    _require(
        condition=await store.count() == 4,
        message=f"base and shared nodes must survive: {await store.count()}",
    )
    _require(
        condition=doomed.id not in {record.id for record in await store.generations()},
        message="a retracted generation must be forgotten",
    )


async def check_a_generation_bound_again_sees_and_extends_what_was_written(
    store: GenerationHoldingStore,
) -> None:
    """Protects resume: an interrupted corpus build's work is kept, not rebuilt or orphaned.

    Ledger **43.20**: a resumed corpus build binds a new handle to the generation an
    interrupted one left `building`. That handle sees what the first wrote, what it writes joins
    the same generation, and publishing makes both visible.
    """
    # Arrange
    generation = await store.open_generation("summaries")
    first = await store.bind_generation(generation.id)
    await first.add([_member("delta", (0.0, 0.0, 1.0))])
    await first.flush()
    # `aclose` is read off the handle, never a contract member, as `weft_kernel.seam.aclose` does.
    close = getattr(first, "aclose", None)
    if close is not None:
        await close()

    # Act
    again = await store.bind_generation(generation.id)
    seen = await again.matching(Filter(op=FilterOp.EQ, field="content", value="delta"))
    await again.add([_member("epsilon", (0.0, 0.5, 0.5))])
    await again.flush()
    await store.publish_generation(generation.id)
    reader = await _next_operation(store)
    delta = await _visible(reader, "delta", (0.0, 0.0, 1.0))
    epsilon = await _visible(reader, "epsilon", (0.0, 0.5, 0.5))

    # Assert
    _require(
        condition=[node.content for node in seen.items] == ["delta"],
        message=f"a handle bound again must see what the first handle wrote: {seen.items}",
    )
    _require(
        condition=delta == (True, True, True),
        message=f"the first handle's node was not published: {delta}",
    )
    _require(
        condition=epsilon == (True, True, True),
        message=f"the second handle's node was not published: {epsilon}",
    )


async def check_a_generation_record_round_trips_and_an_unknown_one_is_refused_by_name(
    store: GenerationHoldingNodeStore,
) -> None:
    """Generation records carry their status, and an unknown one is refused.

    `open_generation` records `building`, `publish_generation` records `published` with its
    time, `generations()` returns both whole, and a generation nobody opened is refused naming
    the ones that exist.
    """
    # Arrange
    opened = await store.open_generation("summaries")

    # Act
    published = await store.publish_generation(opened.id)
    listed = await store.generations()
    try:
        await store.publish_generation(GenerationId("no-such-generation"))
    except UnknownGenerationError as refused:
        refusal: UnknownGenerationError | None = refused
    else:
        refusal = None

    # Assert
    _require(
        condition=opened.status is GenerationStatus.BUILDING, message=f"opened as {opened.status}"
    )
    _require(
        condition=opened.layer == "summaries",
        message=f"the layer must be recorded: {opened.layer!r}",
    )
    _require(
        condition=published.status is GenerationStatus.PUBLISHED,
        message=f"published as {published.status}",
    )
    _require(condition=published.published_at is not None, message="a publish must record when")
    _require(
        condition=listed == (published,),
        message=f"the catalogue must hold the record whole: {listed}",
    )
    _require(condition=refusal is not None, message="an unknown generation must be refused")
    _require(
        condition=refusal is not None and opened.id in refusal.valid_options,
        message="the refusal must name the generations that exist",
    )


async def check_a_reader_sees_only_the_newest_published_generation_of_each_layer(
    store: GenerationHoldingStore,
) -> None:
    """A reader opened between a publish and a retract sees one tree per layer.

    Repair **R43.25**: the layer loop publishes a layer's new generation before it retracts
    the old one, so a reader opened between the two must see one tree per layer — the newest
    published generation of each — never both.
    """
    # Arrange
    older = await store.open_generation("summaries")
    await (await store.bind_generation(older.id)).add([_member("amber", (1.0, 0.0, 0.0))])
    await store.publish_generation(older.id)
    newer = await store.open_generation("summaries")
    await (await store.bind_generation(newer.id)).add([_member("birch", (0.0, 1.0, 0.0))])
    await store.publish_generation(newer.id)
    other = await store.open_generation("facts")
    await (await store.bind_generation(other.id)).add([_member("cedar", (0.0, 0.0, 1.0))])
    await store.publish_generation(other.id)

    # Act
    reader = await _next_operation(store)
    replaced = await _visible(reader, "amber", (1.0, 0.0, 0.0))
    newest = await _visible(reader, "birch", (0.0, 1.0, 0.0))
    other_layer = await _visible(reader, "cedar", (0.0, 0.0, 1.0))

    # Assert
    _require(
        condition=replaced == (False, False, False),
        message=f"a reader saw an older published generation of the same layer: {replaced}",
    )
    _require(
        condition=newest == (True, True, True),
        message=f"the newest published generation was hidden: {newest}",
    )
    _require(
        condition=other_layer == (True, True, True),
        message=f"another layer's published generation was hidden: {other_layer}",
    )


_OLD_TREE: Final[tuple[tuple[str, tuple[float, float, float]], ...]] = (
    ("amber", (1.0, 0.0, 0.0)),
    ("birch", (0.0, 1.0, 0.0)),
    ("cedar", (0.0, 0.0, 1.0)),
    ("dune", (0.5, 0.5, 0.0)),
    ("ember", (0.0, 0.5, 0.5)),
)
_NEW_TREE: Final[tuple[tuple[str, tuple[float, float, float]], ...]] = (
    ("fjord", (0.5, 0.0, 0.5)),
    ("grove", (0.3, 0.3, 0.4)),
)


async def _seen(
    store: GenerationHoldingStore, tree: tuple[tuple[str, tuple[float, float, float]], ...]
) -> dict[str, tuple[bool, bool, bool]]:
    return {word: await _visible(store, word, values) for word, values in tree}


async def check_a_carried_generation_keeps_what_it_carries_and_drops_what_it_replaces(
    store: GenerationCarryingStore,
) -> None:
    """Carried members stay visible and replaced ones vanish once published.

    Ledger **43.22**: a new generation carries three of the published generation's five
    members and replaces the other two. Once it is published and the old one retracted, the three
    carried and the two new are found by every read path and the two replaced by none; a handle
    opened before the publish still sees the old five and nothing new; a carried node is the node
    it was, never rewritten.
    """
    # Arrange
    old_members = [_member(word, values) for word, values in _OLD_TREE]
    carried, replaced = _OLD_TREE[:3], _OLD_TREE[3:]
    old = await store.open_generation("summaries")
    await (await store.bind_generation(old.id)).add(old_members)
    await store.publish_generation(old.id)
    new = await store.open_generation("summaries")
    await (await store.bind_generation(new.id)).add(
        [_member(word, values) for word, values in _NEW_TREE]
    )
    before = await _next_operation(store)
    await before.count()

    # Act
    moved = await store.carry_forward(new.id, [node.id for node in old_members[:3]])
    await store.publish_generation(new.id)
    seen_before = await _seen(before, _OLD_TREE + _NEW_TREE)
    await store.retract_generation(old.id)
    after = await _next_operation(store)
    seen_after = await _seen(after, _OLD_TREE + _NEW_TREE)
    kept = await after.get([node.id for node in old_members[:3]])

    # Assert
    everywhere, nowhere = (True, True, True), (False, False, False)
    _require(
        condition=moved == 3, message=f"carry_forward must report the 3 nodes it carried: {moved}"
    )
    _require(
        condition=all(seen_before[word] == everywhere for word, _ in _OLD_TREE)
        and all(seen_before[word] == nowhere for word, _ in _NEW_TREE),
        message="a handle opened before the publish must see the old five and nothing new: "
        f"{seen_before}",
    )
    _require(
        condition=all(seen_after[word] == everywhere for word, _ in carried + _NEW_TREE),
        message="every carried and every new member must be found by every read path: "
        f"{seen_after}",
    )
    _require(
        condition=all(seen_after[word] == nowhere for word, _ in replaced),
        message="a replaced member must be gone once the old generation is retracted: "
        f"{seen_after}",
    )
    _require(
        condition=sorted(kept, key=lambda node: node.id)
        == sorted(old_members[:3], key=lambda node: node.id),
        message=f"a carried node must be the node it was: {kept}",
    )


async def check_carrying_a_node_no_published_generation_holds_is_refused_by_name(
    store: GenerationCarryingStore,
) -> None:
    """Ledger **43.22**: only a member of a published generation can be carried.

    A base node and a member of an unpublished generation are refused together, named, and nothing
    in the call is carried; a generation nobody opened is refused naming the ones that exist.
    """
    # Arrange
    published = _member("amber", (1.0, 0.0, 0.0))
    unpublished = _member("birch", (0.0, 1.0, 0.0))
    base = _member("cedar", (0.0, 0.0, 1.0))
    await store.add([base])
    old = await store.open_generation("summaries")
    await (await store.bind_generation(old.id)).add([published])
    await store.publish_generation(old.id)
    stray = await store.open_generation("summaries")
    await (await store.bind_generation(stray.id)).add([unpublished])
    new = await store.open_generation("summaries")

    # Act
    try:
        await store.carry_forward(new.id, [published.id, unpublished.id, base.id])
    except NotAPublishedMemberError as refused:
        refusal: NotAPublishedMemberError | None = refused
    else:
        refusal = None
    try:
        await store.carry_forward(GenerationId("no-such-generation"), [published.id])
    except UnknownGenerationError as refused:
        unknown: UnknownGenerationError | None = refused
    else:
        unknown = None
    await store.publish_generation(new.id)
    await store.retract_generation(old.id)
    seen = await _visible(await _next_operation(store), "amber", (1.0, 0.0, 0.0))

    # Assert
    _require(
        condition=refusal is not None,
        message="carrying a node no published generation holds must be refused",
    )
    _require(
        condition=refusal is not None
        and refusal.generation == new.id
        and refusal.node_ids == tuple(sorted((unpublished.id, base.id))),
        message="the refusal must name the generation and exactly the nodes it refused: "
        f"{refusal!r}",
    )
    _require(
        condition=seen == (False, False, False),
        message=f"a refused carry must carry nothing: {seen}",
    )
    _require(
        condition=unknown is not None, message="carrying into an unknown generation must be refused"
    )
    _require(
        condition=unknown is not None and new.id in unknown.valid_options,
        message="the refusal must name the generations that exist",
    )


async def _scanned(store: GenerationHoldingStore) -> frozenset[str]:
    """Every node `scan` walks, across every page."""
    page = await store.scan()
    seen = set(await _all(page))
    while page.next_cursor is not None:
        page = await store.scan(page.next_cursor)
        seen |= await _all(page)
    return frozenset(seen)


async def _a_published_tree_and_its_rebuild(
    store: GenerationWithdrawingStore,
) -> tuple[GenerationId, GenerationId, list[Node]]:
    """Set up a published `old` generation and a building `new` one sharing members.

    `old` published with `_OLD_TREE`; `new` sharing its first three members, replacing the
    other two with `_NEW_TREE`, still building. Returns `old`, `new` and `old`'s members.
    """
    old_members = [_member(word, values) for word, values in _OLD_TREE]
    old = await store.open_generation("summaries")
    await (await store.bind_generation(old.id)).add(old_members)
    await store.publish_generation(old.id)
    new = await store.open_generation("summaries")
    await (await store.bind_generation(new.id)).add(
        [*old_members[:3], *(_member(word, values) for word, values in _NEW_TREE)]
    )
    return old.id, new.id, old_members


async def check_a_handle_opened_before_a_withdraw_keeps_reading_the_tree_it_opened_on(
    store: GenerationWithdrawingStore,
) -> None:
    """A reader of a withdrawn generation keeps reading all of it.

    Repair **R43.29**: a reader that opened while the old generation was published keeps
    reading all of it after the new one is published and the old one withdrawn — the members the
    new generation shares and the ones it replaced, through `count`, `scan` and every search —
    and none of the new generation. Retracting in place of withdrawing strips the old id from the
    shared members and deletes the replaced ones, which left that reader with neither tree.
    """
    # Arrange
    old, new, _ = await _a_published_tree_and_its_rebuild(store)
    reader = await _next_operation(store)
    counted_before = await reader.count()
    scanned_before = await _scanned(reader)

    # Act
    await store.publish_generation(new)
    withdrawn = await store.withdraw_generation(old)
    counted_after = await reader.count()
    scanned_after = await _scanned(reader)
    searched = await _seen(reader, _OLD_TREE + _NEW_TREE)

    # Assert
    everywhere, nowhere = (True, True, True), (False, False, False)
    _require(
        condition=(withdrawn.id, withdrawn.status) == (old, GenerationStatus.WITHDRAWN),
        message=f"withdraw must record the generation withdrawn: {withdrawn}",
    )
    _require(
        condition=counted_after == counted_before,
        message=f"a withdraw removed nodes under an open reader: {counted_before} -> "
        f"{counted_after}",
    )
    _require(
        condition={word for word, _ in _OLD_TREE} <= scanned_after
        and scanned_after == scanned_before,
        message=f"a withdraw changed what an open reader scans: {scanned_before} -> "
        f"{scanned_after}",
    )
    _require(
        condition=all(searched[word] == everywhere for word, _ in _OLD_TREE),
        message="an open reader lost the tree it opened on, shared or replaced members: "
        f"{searched}",
    )
    _require(
        condition=all(searched[word] == nowhere for word, _ in _NEW_TREE),
        message=f"an open reader saw a generation published after it opened: {searched}",
    )


async def check_a_handle_opened_after_a_withdraw_sees_only_the_generation_that_replaced_it(
    store: GenerationWithdrawingStore,
) -> None:
    """Repair **R43.29**: once withdrawn, a generation is in no new handle's manifest.

    A reader opened after the withdraw finds the shared and the new members and none of the replaced
    ones; a layer whose only published generation is withdrawn shows that reader nothing of it. The
    catalogue still lists the withdrawn generation until it is reclaimed.
    """
    # Arrange
    old, new, _ = await _a_published_tree_and_its_rebuild(store)
    await store.publish_generation(new)
    sole = await store.open_generation("facts")
    await (await store.bind_generation(sole.id)).add([_member("heath", (0.2, 0.2, 0.6))])
    await store.publish_generation(sole.id)

    # Act
    await store.withdraw_generation(old)
    await store.withdraw_generation(sole.id)
    reader = await _next_operation(store)
    searched = await _seen(reader, _OLD_TREE + _NEW_TREE)
    sole_seen = await _visible(reader, "heath", (0.2, 0.2, 0.6))
    listed = {record.id: record.status for record in await store.generations()}

    # Assert
    everywhere, nowhere = (True, True, True), (False, False, False)
    _require(
        condition=all(searched[word] == everywhere for word, _ in _OLD_TREE[:3] + _NEW_TREE),
        message=f"a reader opened after the withdraw must find the new tree whole: {searched}",
    )
    _require(
        condition=all(searched[word] == nowhere for word, _ in _OLD_TREE[3:]),
        message=f"a reader opened after the withdraw found a replaced member: {searched}",
    )
    _require(
        condition=sole_seen == nowhere,
        message=f"a withdrawn layer's only generation was in a new reader's manifest: {sole_seen}",
    )
    _require(
        condition=(listed.get(old), listed.get(sole.id), listed.get(new))
        == (GenerationStatus.WITHDRAWN, GenerationStatus.WITHDRAWN, GenerationStatus.PUBLISHED),
        message=f"the catalogue must list a withdrawn generation until it is reclaimed: {listed}",
    )


async def check_reclaiming_a_layer_removes_the_nodes_only_its_withdrawn_generations_held(
    store: GenerationWithdrawingStore,
) -> None:
    """`reclaim_withdrawn` retracts each withdrawn generation of one layer.

    Repair **R43.29**: `reclaim_withdrawn(layer)` does, per withdrawn generation of `layer`,
    what `retract_generation` does — deletes the nodes only it held, keeps the ones a published
    generation shares, and forgets it. Another layer's withdrawn generation is left alone. Counted
    raw, so the manifest cannot hide a node still stored.
    """
    # Arrange
    old, new, old_members = await _a_published_tree_and_its_rebuild(store)
    await store.publish_generation(new)
    await store.withdraw_generation(old)
    other = await store.open_generation("facts")
    await (await store.bind_generation(other.id)).add([_member("heath", (0.2, 0.2, 0.6))])
    await store.publish_generation(other.id)
    await store.withdraw_generation(other.id)
    stored_before = await (await _next_operation(store)).count()

    # Act
    removed = await store.reclaim_withdrawn("summaries")
    fresh = await _next_operation(store)
    stored_after = await fresh.count()
    kept = await fresh.get([node.id for node in old_members])
    listed = {record.id: record.status for record in await store.generations()}
    searched = await _seen(fresh, _OLD_TREE[:3] + _NEW_TREE)

    # Assert
    _require(
        condition=removed.node_count == 2,
        message=f"reclaim must remove exactly the 2 members only the withdrawn generation held: "
        f"{removed.node_count}",
    )
    _require(
        condition=stored_before - stored_after == 2,
        message=f"a fresh raw count must drop by 2: {stored_before} -> {stored_after}",
    )
    _require(
        condition=sorted(node.id for node in kept) == sorted(node.id for node in old_members[:3]),
        message=f"reclaim must keep every member a published generation shares: {kept}",
    )
    _require(
        condition=old not in listed, message=f"a reclaimed generation must be forgotten: {listed}"
    )
    _require(
        condition=(listed.get(new), listed.get(other.id))
        == (GenerationStatus.PUBLISHED, GenerationStatus.WITHDRAWN),
        message=f"reclaim touched a generation outside its layer's withdrawn ones: {listed}",
    )
    _require(
        condition=all(seen == (True, True, True) for seen in searched.values()),
        message=f"reclaim hid a member of the published generation: {searched}",
    )


async def check_a_layer_rebuilt_twice_reads_as_one_tree_at_every_step(
    store: GenerationWithdrawingStore,
) -> None:
    """A layer's generation lifecycle, whole: every read sees exactly one tree, at every step.

    Ledger **43.28**. A layer is built, rebuilt sharing three of its nodes, and rebuilt again
    sharing none; each superseded tree is withdrawn and then reclaimed. At every step a fresh
    handle reads exactly the newest published tree, a handle opened before a withdraw keeps the
    tree it opened on, and a node two trees share survives the reclaim of either while one of
    them still holds it.
    """
    # Arrange
    first, second, third = _OLD_TREE, _OLD_TREE[:3] + _NEW_TREE, _NEW_TREE
    everything = _OLD_TREE + _NEW_TREE
    g1 = await _published_tree(store, first)
    early = await _next_operation(store)
    await early.count()

    # Act
    g2 = await _published_tree(store, second)
    await store.withdraw_generation(g1)
    after_rebuild = await _seen(await _next_operation(store), everything)
    kept_by_early = await _seen(early, everything)
    first_reclaim = await store.reclaim_withdrawn("summaries")
    after_reclaim = await _seen(await _next_operation(store), everything)
    await _published_tree(store, third)
    await store.withdraw_generation(g2)
    second_reclaim = await store.reclaim_withdrawn("summaries")
    after_second_rebuild = await _seen(await _next_operation(store), everything)

    # Assert
    for label, seen, tree in (
        ("after the first rebuild", after_rebuild, second),
        ("after the first reclaim", after_reclaim, second),
        ("after the second rebuild and reclaim", after_second_rebuild, third),
    ):
        wanted = {word for word, _ in tree}
        _require(
            condition=all(
                seen[word] == ((True, True, True) if word in wanted else (False, False, False))
                for word, _ in everything
            ),
            message=f"{label}, a fresh handle must read exactly {sorted(wanted)}: {seen}",
        )
    _require(
        condition=all(kept_by_early[word] == (True, True, True) for word, _ in first)
        and all(kept_by_early[word] == (False, False, False) for word, _ in _NEW_TREE),
        message=f"a handle opened before the withdraw must keep the first tree: {kept_by_early}",
    )
    _require(
        condition=(first_reclaim.node_count, second_reclaim.node_count) == (2, 3),
        message="a reclaim removes only what its withdrawn trees alone held (2, then 3): "
        f"{first_reclaim.node_count}, {second_reclaim.node_count}",
    )


async def _published_tree(
    store: GenerationWithdrawingStore, tree: tuple[tuple[str, tuple[float, float, float]], ...]
) -> GenerationId:
    """Open a generation of `summaries`, write `tree` into it, publish it, return its id."""
    record = await store.open_generation("summaries")
    await (await store.bind_generation(record.id)).add(
        [_member(word, values) for word, values in tree]
    )
    await store.publish_generation(record.id)
    return record.id


async def check_withdrawing_an_unknown_or_unpublished_generation_is_refused_by_name(
    store: GenerationWithdrawingNodeStore,
) -> None:
    """A mistaken withdraw must fail loudly with the valid choices, never pass as a silent no-op.

    Repair **R43.29**: a generation nobody opened is refused with `UnknownGenerationError`
    naming the ones that exist; a `building` one — an abandoned build is retracted, never
    withdrawn — and one already withdrawn are refused with `NotAPublishedGenerationError` naming
    it, its status and the published ones. A refusal changes no generation's status.
    """
    # Arrange
    published = await store.open_generation("summaries")
    await store.publish_generation(published.id)
    building = await store.open_generation("summaries")
    gone = await store.open_generation("facts")
    await store.publish_generation(gone.id)
    await store.withdraw_generation(gone.id)

    # Act
    refusals: list[BaseException | None] = []
    for asked in (GenerationId("no-such-generation"), building.id, gone.id):
        try:
            await store.withdraw_generation(asked)
        except (UnknownGenerationError, NotAPublishedGenerationError) as refused:
            refusals.append(refused)
        else:
            refusals.append(None)
    unknown, unbuilt, again = refusals
    listed = {record.id: record.status for record in await store.generations()}

    # Assert
    _require(
        condition=isinstance(unknown, UnknownGenerationError)
        and published.id in unknown.valid_options,
        message=f"an unknown generation must be refused naming the ones that exist: {unknown!r}",
    )
    for asked, status, refusal in (
        (building.id, GenerationStatus.BUILDING, unbuilt),
        (gone.id, GenerationStatus.WITHDRAWN, again),
    ):
        _require(
            condition=isinstance(refusal, NotAPublishedGenerationError)
            and (refusal.generation, refusal.status) == (asked, status)
            and refusal.valid_options == (published.id,),
            message=f"a {status.value} generation must be refused naming it, its status and the "
            f"published ones: {refusal!r}",
        )
    _require(
        condition=listed
        == {
            published.id: GenerationStatus.PUBLISHED,
            building.id: GenerationStatus.BUILDING,
            gone.id: GenerationStatus.WITHDRAWN,
        },
        message=f"a refused withdraw changed a generation's status: {listed}",
    )


async def check_a_handle_opened_before_any_node_was_stored_retracts_a_generations_nodes(
    store: GenerationHoldingNodeStore,
) -> None:
    """An early reader's handle still retracts a generation's nodes.

    Repair **R43.26**: a handle that read storage before anything was stored, while a handle
    bound to a generation then stores that generation's members, retracts the generation's nodes
    along with its record — counted raw, so the manifest cannot hide nodes still held.
    """
    # Arrange
    await store.count()
    generation = await store.open_generation("summaries")
    writer = await store.bind_generation(generation.id)
    await writer.add([_member("delta", (0.0, 0.0, 1.0)), _member("epsilon", (0.0, 0.5, 0.5))])
    await writer.flush()
    await store.publish_generation(generation.id)

    # Act
    removed = await store.retract_generation(generation.id)
    stored = await (await _next_operation(store)).count()

    # Assert
    _require(
        condition=stored == 0,
        message=f"a retracted generation's nodes must be gone: {stored} still stored",
    )
    _require(
        condition=removed.node_count == 2,
        message=f"retract must report the 2 nodes it removed: {removed.node_count}",
    )


async def check_a_handle_opened_before_any_node_was_stored_reads_what_a_fresh_handle_reads(
    store: GenerationHoldingNodeStore,
) -> None:
    """An early reader sees what a bound handle later stored.

    Repair **R43.26**: a handle that read storage before anything was stored reads what a
    bound handle then stored exactly as a fresh handle does, through every read the manifest
    does not gate — `count`, `scan`, `get`, `get_source` and `list_sources`.
    """
    # Arrange
    await store.count()
    generation = await store.open_generation("summaries")
    writer = await store.bind_generation(generation.id)
    member = _member("delta", (0.0, 0.0, 1.0))
    record = SourceRecord(
        id=_SOURCE_A,
        uri="file:///corpus/a.txt",
        content_hash="hash-a",
        indexed_at=datetime.now(UTC),
        pipeline="conformance",
    )
    await writer.add([member])
    await writer.put_source(record)
    await writer.flush()
    fresh = await _next_operation(store)

    # Act
    first_reads = (
        await store.count(),
        await _all(await store.scan()),
        [node.id for node in await store.get([member.id])],
        await store.get_source(_SOURCE_A),
        tuple(await store.list_sources()),
    )
    fresh_reads = (
        await fresh.count(),
        await _all(await fresh.scan()),
        [node.id for node in await fresh.get([member.id])],
        await fresh.get_source(_SOURCE_A),
        tuple(await fresh.list_sources()),
    )

    # Assert
    _require(
        condition=fresh_reads == (1, frozenset({"delta"}), [member.id], record, (record,)),
        message=f"a fresh handle must read the stored node and record: {fresh_reads}",
    )
    _require(
        condition=first_reads == fresh_reads,
        message=f"a handle opened before the first store read {first_reads}, a fresh one "
        f"{fresh_reads}",
    )


def _claim(command: str, pid: int) -> WriterClaim:
    return WriterClaim(
        host="conformance-host", pid=pid, started_at=datetime.now(UTC), command=command
    )


async def check_a_second_writer_is_refused_naming_the_first(store: SingleWriterStore) -> None:
    """A second writer on a claimed store is refused, naming the holder.

    Ledger **43.18**: two `weft index` runs interleaving their batch records into one store is
    refused before the second writes, and the refusal names the writer that holds it.
    """
    # Arrange
    other = await store.bind_target(DEFAULT_TARGET)
    first = _claim("weft index corpus", 101)
    await store.claim_writer(first)

    # Act
    try:
        await other.claim_writer(_claim("weft index elsewhere", 202))
    except WriterBusyError as busy:
        refusal: WriterBusyError | None = busy
    else:
        refusal = None
    await store.release_writer()

    # Assert
    _require(
        condition=refusal is not None,
        message="a second writer was admitted while the first held the store",
    )
    _require(
        condition=refusal is not None and refusal.holder == first,
        message="the refusal must name the writer that holds the store: "
        f"{refusal and refusal.holder}",
    )


async def check_a_released_claim_lets_the_next_writer_in(store: SingleWriterStore) -> None:
    """Ledger **43.18**: `release_writer` ends the claim, so the next writer is admitted."""
    # Arrange
    other = await store.bind_target(DEFAULT_TARGET)
    await store.claim_writer(_claim("weft index corpus", 101))

    # Act / Assert — the second claim raising `WriterBusyError` is the failure.
    await store.release_writer()
    await other.claim_writer(_claim("weft index corpus", 202))
    await other.release_writer()
