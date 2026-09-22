"""`QdrantStore` — the second backend, and the reason the store contract is no longer a guess.

Ledger task **2.6**: "the store contract is satisfied by a second backend of a
genuinely different shape, so it is no longer a guess." `01` → *Runtime shape*
names the pair and why it is that pair: "the contract is proven on **pgvector and
Qdrant**, which have genuinely different shapes, and a store that only Postgres
can satisfy fails that test just as loudly." G4 retired the zero-container target
on the same reasoning — two backends that are obviously different are safer than
two that are subtly alike.

**Four tiers, since ledger task 21.8.** `NodeStore`, `VectorSearch`,
`MetadataFilter` and `TextSearch`.

*This module said "three tiers, deliberately not four" until 2026-09-13, and the
refusal rested on a premise that has expired.* It read: "Qdrant's text matching is
a filter predicate — does this payload contain this substring — and
`TextSearch.search_text` returns `Scored[Node]`, a *ranking*. There is no honest
score to put in it." A **named sparse vector** is a scored ranking, and it is one
this server already serves: measured on the pinned `v1.12.4`, a collection created
with `sparse_vectors: {lexical: {modifier: idf}}` answers a sparse query with
collection IDF applied and returns positive, descending scores. The second half of
the refusal does not apply either — the sparse vector rides **the same point** as
the dense one, written by the same `add()`, so there is no second copy of the
corpus for a write to leave stale, which is the thing task 2.5 actually forbids.
What the refusal *did* buy — a `needs_store` refusal demonstrable against a real
backend rather than a mock — now falls to `weft_store.memory.MemoryStore`, which
satisfies `NodeStore` and `VectorSearch` and nothing else. `docs/02-extension-model.md`
§1 carries the withdrawal. Two backends with identical capability sets would leave that promise
with nothing to demonstrate.

**What is genuinely different, and therefore what the contract had to survive.**
Each of these is a place a Postgres-shaped assumption would have broken:

* **Point identity is a UUID or an integer, never a string.** A `NodeId` is a
  sha256 hex digest, which Qdrant will not accept as a point id. Every point is
  keyed by a UUID derived deterministically from the node id (`_point_id`), and
  the real id rides in the payload — so `get` still answers by `NodeId` and
  nothing above the store learns that a translation happened.
* **A collection fixes its vector width at creation.** See
  `QdrantSettings.vector_size`, and `VectorWidthMismatchError` for what happens
  when a node disagrees with it.
* **A point may hold no vector at all**, which is what a node embedded by no
  stage is — expressible only because the vector is *named*. An unnamed vector
  configuration would require one on every point, and a store that could not hold
  an unembedded node would fail `NodeStore` outright.
* **There is no second table.** `SourceRecord`s live in a collection of their own,
  created with no vector configuration whatsoever, because a source record has
  nothing to be similar to.
* **Nothing is ordered by the node id.** `scan` and `matching` walk Qdrant's own
  point order, which is the UUID above; `Page` promises pages and never an order,
  and this is the store that makes that promise load-bearing rather than
  theoretical.

**The payload is the node's own dump**, minus the embedding, which is why this
module needs no field-name mapping at all: `weft_store.fields` says a filter path
is the path you would write to reach the value on a `Node`, and here that is
literally the payload key Qdrant matches on. The filter *semantics* — which
operator each kind of field admits, and that an array is compared element-wise —
come from that same module, so this translator and pgvector's cannot drift into
disagreeing about what one `Filter` means.

**Capability is derived, never declared.** This class implements the methods of
three Protocols and imports none of them; `isinstance(store, VectorSearch)` at
registration is what makes the capability true, per `docs/02-extension-model.md`
→ *The store contract family*. Nothing here writes a flag, which is exactly why
the missing fourth tier cannot be faked.

**`TargetHolding` arrives at task 34.5, with 34.2's Qdrant half.** `default` is exactly the
pair this store has always written, `self._nodes`/`self._sources` — a collection pair
written before targets existed reads as `default`, live, with no operator action. Any other
target `<name>` is its own pair, `<collection>__t_<name>` and `<collection>__t_<name>__sources`;
the live pointer and each target's claimed embedding identity are points in a third,
vector-less collection, `<collection>__targets`, read once when an unbound handle opens and
held for that handle's lifetime (owner decision Q-C) — `bind_target` gives a handle onto one
target by name instead. **No alias is ever used, measured rather than assumed** (`34.0`,
2026-09-22, Qdrant v1.12.4): creating an alias named like an existing collection is refused
(`409 … already exists`) and nothing renames a collection, so `default` could only have become
an alias after a window where its name resolved to nothing; and a write through an alias
follows a mid-request switch, which would split one ingest across two targets. Every name here
is a concrete collection instead. A bound, uncatalogued target creates nothing at open — its
first `add()` or `put_source()` creates the pair, sized to the width of the first embedded
vector that call carries rather than to `[packs.qdrant] vector_size`, which describes `default`
alone; a read against it before that first write answers empty rather than touching Qdrant. A
catalogued target whose collection has gone missing is refused by name
(`TargetCollectionMissingError`) rather than silently recreated empty. Qdrant has no session
lock, so `drop_target`'s refusal that another handle is bound to a target comes from an
expiring lease instead (**R34.10**): a handle that writes to a non-`default` target holds a
lease point in the catalogue, written on its first write and renewed on every later one,
released by `aclose`, and left to expire after `[packs.qdrant] target_lease_seconds` if the
writer never closes — so a crashed writer blocks a drop for at most that long, and a handle
that only reads takes no lease at all.
"""

import asyncio
import time
from collections.abc import Mapping, Sequence
from functools import partial
from typing import Any, ClassVar, Final, Self, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from qdrant_client import AsyncQdrantClient, models

from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.payload import Node, NodeId, Outcome, Produced, SourceId, Vector
from weft_qdrant.lexical import analyze, document_weights, query_weights
from weft_qdrant.settings import DEFAULT_PAYLOAD_INDEXES, PayloadIndexType, QdrantSettings
from weft_store.contract import (
    DEFAULT_TARGET,
    Cursor,
    EmbeddingIdentity,
    Filter,
    FilterOp,
    FilterValue,
    NoPreviousTargetError,
    Page,
    Promotion,
    ReconcileEstimate,
    ReconcileMode,
    ReconcileReport,
    Removed,
    Scored,
    SourceRecord,
    SourceStatus,
    SupersedeNarrowsSourcesError,
    TargetCatalogue,
    TargetInUseError,
    TargetName,
    TargetRecord,
    UnhandledFilterOpError,
    UnknownTargetError,
    VectorIndexKind,
    VectorPrecision,
    source_failure,
    source_layers,
    source_status,
)
from weft_store.contract import (
    # Re-exported deliberately, `X as X`: these two moved to `weft_store.contract` at task
    # **31.12** so one class serves both backends, and a caller that reached them here before
    # the move still resolves them here. Nothing in this module raises them — the refusals are
    # in `weft_qdrant.settings`'s validators, which import them from the contract directly.
    UnsupportedIndexKindError as UnsupportedIndexKindError,
)
from weft_store.contract import (
    UnsupportedPrecisionError as UnsupportedPrecisionError,
)
from weft_store.fields import field_for
from weft_store.rehydrate import rehydrate_ext

#: Matches `weft_store.pgvector_store`'s page size. Not imported from it — that constant is
#: private to a store's own paging, and two stores agreeing on a number is a coincidence a
#: reader should be able to see rather than an import that implies a shared rule.
_PAGE_SIZE = 100

#: The name of the one vector a node carries. Named rather than anonymous for the reason the
#: module docstring gives: only a named vector may be absent from a point, and a node with no
#: embedding is an ordinary node.
_VECTOR = "content"

#: The name of the sparse lexical vector — named for the same reason `_VECTOR` is, and so a
#: point with no analysable content (see `_point`) can carry an empty one rather than none.
_LEXICAL = "lexical"

#: The namespace every point id is derived under. A fixed, arbitrary URL, so the same node
#: lands on the same point in every deployment and a re-index overwrites rather than
#: duplicates — `uuid5` is a digest, not a random id, which is the whole reason to use it.
_ID_NAMESPACE = uuid5(NAMESPACE_URL, "https://weft.invalid/qdrant/point-id")

#: The namespace a target's catalogue point id is derived under — its own, distinct from
#: `_ID_NAMESPACE`, because a target's name and a node's id are two different alphabets that
#: happen to collide in nothing but the collection they would collide in if they shared one.
_TARGET_ID_NAMESPACE = uuid5(NAMESPACE_URL, "https://weft.invalid/qdrant/target-id")

#: The live pointer's own point id — fixed, because there is exactly one pointer per catalogue
#: collection, never one per target.
_POINTER_POINT_ID: Final[str] = str(uuid5(_TARGET_ID_NAMESPACE, "__pointer__"))


def _target_point_id(name: str) -> str:
    """A target's catalogue point id, deterministic like `_point_id` — `uuid5` under
    `_TARGET_ID_NAMESPACE` so re-claiming or re-promoting a target finds the same point rather
    than accumulating a second one.
    """
    return str(uuid5(_TARGET_ID_NAMESPACE, name))


def _lease_point_id(collection: str, target: str, holder: str) -> str:
    """A handle's own write-lease point id on `target` — **R34.10**, deterministic per
    `(collection, target, holder)` like `_target_point_id` is per `(catalogue, name)`, so a
    renewal upserts the same point rather than accumulating one per write.
    """
    return str(uuid5(_TARGET_ID_NAMESPACE, f"lease:{collection}:{target}:{holder}"))


#: Weft's own payload-index vocabulary, mapped onto the driver's — task **31.1**. A Weft-side
#: enum rather than the client's `PayloadSchemaType` re-exported, per `QdrantSettings.
#: payload_indexes`'s docstring, so this is where the two meet.
_PAYLOAD_SCHEMA_TYPE: dict[PayloadIndexType, models.PayloadSchemaType] = {
    PayloadIndexType.KEYWORD: models.PayloadSchemaType.KEYWORD,
    PayloadIndexType.INTEGER: models.PayloadSchemaType.INTEGER,
    PayloadIndexType.FLOAT: models.PayloadSchemaType.FLOAT,
}


def _datatype_for(precision: VectorPrecision) -> models.Datatype | None:
    """`float16` is a vector `datatype`; every other precision leaves Qdrant's own default."""
    return models.Datatype.FLOAT16 if precision is VectorPrecision.FLOAT16 else None


def _quantization_config_for(
    precision: VectorPrecision,
) -> models.ScalarQuantization | models.BinaryQuantization | None:
    """The quantization Qdrant is asked to hold `precision` under, or `None` for no compression.

    `float32` and `float16` need no `quantization_config` at all — the first is Qdrant's own
    default and the second is a vector `datatype`, set by `_datatype_for` instead.
    """
    match precision:
        case VectorPrecision.INT8:
            return models.ScalarQuantization(
                scalar=models.ScalarQuantizationConfig(type=models.ScalarType.INT8)
            )
        case VectorPrecision.BINARY:
            return models.BinaryQuantization(binary=models.BinaryQuantizationConfig())
        case _:
            return None


def _quantization_kind_for(precision: VectorPrecision) -> str | None:
    """The `VectorPrecision` value a quantised collection reads back as, or `None` for neither
    quantization this backend applies — see `_quantization_config_for`, which this mirrors.
    """
    config = _quantization_config_for(precision)
    return _quantization_kind(config)


def _quantization_kind(config: models.QuantizationConfig | None) -> str | None:
    """The precision name a collection's own `quantization_config` reads back as.

    `None` for a collection with no quantization applied — the undecided case
    `QuantizationMismatchError`'s docstring names, distinct from either quantised kind.
    """
    if isinstance(config, models.ScalarQuantization):
        return VectorPrecision.INT8.value
    if isinstance(config, models.BinaryQuantization):
        return VectorPrecision.BINARY.value
    return None


def search_params_for(
    *,
    index: VectorIndexKind,
    precision: VectorPrecision,
    rescore_oversampling: float | None,
) -> models.SearchParams | None:
    """The `SearchParams` a search sends — task **31.3**, the one construction site for them.

    Rescoring is requested **explicitly** for `int8` and `binary`, the two precisions
    `_quantization_config_for` compresses: Qdrant's documented default enables it for binary
    quantization only, so leaving `int8` unset would silently rank by the lossy quantized
    distance. `float16` and `float32` carry no quantized vectors at all — `float16` is a vector
    *datatype*, set through `_datatype_for` instead — so neither gets a `quantization` component.

    `exact` and quantization answer different questions and both can hold at once: a full scan
    over a compressed collection is still a full scan, and it is still rescored against the
    originals. `None` only when there is nothing to say — not exact, not compressed.
    """
    quantization = (
        models.QuantizationSearchParams(
            ignore=False, rescore=True, oversampling=rescore_oversampling
        )
        if precision in (VectorPrecision.INT8, VectorPrecision.BINARY)
        else None
    )
    exact = index is VectorIndexKind.EXACT
    if not exact and quantization is None:
        return None
    return models.SearchParams(exact=exact, quantization=quantization)


class VectorWidthMismatchError(WeftError):
    """A node's embedding is not the width this collection was created with.

    **Both backends have this failure, and that is newer than this class.** Until G22 was
    settled (2026-09-16) `weft-store` declared its column with no dimension and could not
    refuse a width at all; it now commits to one at first write and raises its own sibling of
    this error, which `weft_store.conformance` asserts says the same things this one does. The
    two never share a class — the packs do not import each other — so the contract is the
    message: the node, both widths, and a remedy. A collection's width cannot be altered, so
    that remedy is a decision (re-index under a different `[packs.qdrant] collection`, or point
    `vector_size` at the embedder actually configured), and an operator cannot make it from a
    driver's "expected dim: 64, got 1536".
    """


class CollectionSchemaMismatchError(WeftError):
    """An existing collection lacks a named vector this store writes.

    Unlike `VectorWidthMismatchError`, this is not something a node triggers — it is
    read off the collection itself, once, in `_connection`, before any point is
    written or queried. Named rather than left to the driver for the same reason:
    Qdrant answers with a 400 naming the missing vector inside an upsert, which is a
    write-path detail, not a schema fact an operator can act on. A collection's
    vector set cannot be widened in place, so the remedy — a new `collection`, or a
    delete-and-re-index — is the operator's decision, exactly as it is for
    `VectorWidthMismatchError`.
    """


class QuantizationMismatchError(WeftError):
    """An existing collection is already quantised differently from what `precision` asks for.

    Owner question 2, settled as a split on grilling session G22's own two-branch precedent for
    vector width: a collection with **no** quantization has never had this question answered, so
    `_connection` applies the configured one in place — both are online operations in Qdrant, and
    nothing an operator chose is being overwritten. A collection already quantised
    **differently** carries somebody's settings' own choice, and re-quantising it in place would
    silently change what every stored vector compares as with no error to notice it by — refused
    here rather than reconfigured, naming both the collection's current quantization and the one
    `precision` asks for.
    """


class TargetCollectionMissingError(WeftError):
    """A catalogued target's own point exists, but one of its two collections does not.

    Qdrant's sibling of `weft_store.pgvector_store.TargetTableMissingError` — the identical
    measured hazard, on a backend with no `search_path` to fall through: something outside Weft
    deleted the collection, or a `drop_target` was interrupted after removing one of the pair
    and before the other. This store refuses by name rather than silently recreating an empty
    collection, which would answer every later query "nothing found" instead of reporting the
    corpus is gone.
    """


class QdrantStore:
    """Every tier of the store family over a Qdrant deployment, since ledger task 21.8.

    Satisfies all four structurally — this class never imports one of the
    Protocols, the same path any third-party store pack takes.
    """

    #: What `search_vector`'s number means — ledger task **21.1**, read off this class by
    #: `weft_cli.explain.ScoreExplanation.of`. One per capability, not one per class: this
    #: object satisfies `VectorSearch` and `TextSearch` and they return incommensurable
    #: numbers, matching the register `PgVectorStore`'s own pair of these uses.
    vector_score_semantics: ClassVar[str] = (
        "cosine similarity, computed by the server; higher is nearer, and it is unbounded "
        "below — a hash embedder routinely produces negative values, which rank correctly "
        "and mean nothing"
    )

    #: What `search_text`'s number means. A `ClassVar` rather than an instance attribute,
    #: unlike `PgVectorStore`'s: this store has no `text_mode` setting to vary it by, since
    #: `weft_qdrant.lexical`'s BM25 is the only lexical ranking this backend offers.
    text_score_semantics: ClassVar[str] = (
        "Okapi BM25 relevance score, with an IDF over this collection applied by Qdrant's "
        "own sparse-vector modifier and saturating term frequency computed by this store; "
        "higher is a better lexical match, with no fixed range, and it is not comparable "
        "with this store's own cosine similarity"
    )

    def __init__(
        self, settings: QdrantSettings, config: object = None, *, _bound: TargetName | None = None
    ) -> None:
        del config  # nothing at the stage level this store needs — as with pgvector
        self._settings = settings
        self._nodes = settings.collection
        #: A collection rather than a table, because Qdrant has no second table inside one.
        self._sources = f"{settings.collection}__sources"
        #: The catalogue — every target this store has ever written to, the live pointer, and
        #: the embedding identity claimed against each. Its name never varies with the active
        #: target: `target_catalogue` must read the same collection whichever pair a handle is
        #: currently bound to.
        self._catalogue = f"{settings.collection}__targets"
        self._client: AsyncQdrantClient | None = None
        #: `None` on an unbound handle — see `_connection`, which reads the live target once and
        #: holds it here for this handle's lifetime (owner decision Q-C, ledger task 34.3).
        self._bound = _bound
        #: This handle's own resolved target — `self._bound`, or the live target read at connect.
        self._active_target: TargetName | None = None
        #: Whether `self._nodes`/`self._sources` are known to exist. Always true for `default`
        #: and for a catalogued target (refused by `TargetCollectionMissingError` otherwise);
        #: false for a bound, uncatalogued target until its first `add`/`put_source` provisions
        #: the pair — a read against it before that must not create anything (`34.5`, point 3).
        self._provisioned = False
        #: The width `self._nodes`' vector is committed to — `self._settings.vector_size` for
        #: `default`, or a candidate's own first-write width once `_ensure_pair_provisioned` or
        #: `_open_candidate` has read it. `None` only before either has run.
        self._vector_width: int | None = None
        self._holder: str = uuid4().hex
        #: A handle that only reads never touches the catalogue, on close included (`L28.27`).
        self._lease_written = False

    @property
    def vector_index_kind(self) -> VectorIndexKind:
        """The configured index kind, read by `weft_cli.estimate.store_index_kind` —
        ledger task **31.8**. This class keeps `self._settings` whole rather than
        unpacking it into per-field attributes the way `PgVectorStore` does, so the
        public name reads straight through it instead of duplicating a stored copy that
        could drift from `self._settings.index`.
        """
        return self._settings.index

    @property
    def vector_precision(self) -> VectorPrecision:
        """The configured vector precision — `vector_index_kind`'s own reasoning, one
        setting over.
        """
        return self._settings.precision

    @property
    def payload_index_fields(self) -> tuple[str, ...]:
        """Every payload index field path this store ensures — ledger task **31.14**.

        Read from the same mapping `_reconcile_payload_indexes` writes from, so the report and
        the write cannot disagree: `DEFAULT_PAYLOAD_INDEXES` folded under whatever
        `[packs.qdrant] payload_indexes` declares. Sorted, so a run's output is stable rather
        than dict-ordered.

        Declared, never required — `weft_cli.ingest` reaches it through `getattr` exactly as
        `31.8` reaches `vector_index_kind`, so a store that does not define it reports a stated
        absence instead of being refused over a question about reporting.
        """
        return tuple(sorted({**DEFAULT_PAYLOAD_INDEXES, **self._settings.payload_indexes}))

    async def _connection(self) -> AsyncQdrantClient:
        """The lazily-opened, provisioned client this store reuses for its lifetime.

        Lazy for the reason `weft_store.pgvector_store` gives: creating a collection
        is a coroutine and `__init__` cannot be one. `default`'s pair, like a candidate
        target's, is created by its first `add`/`put_source` rather than by opening it
        (**R43.2**) — a store that required a human to have run a provisioning step
        before `weft index` works once is exactly the friction a walking skeleton
        exists to remove, and one nothing ever wrote to must not leave a collection
        behind either.

        **The client is built off the loop, and that is not caution.** `AsyncQdrantClient`
        is async everywhere except its own constructor: `AsyncQdrantRemote.__init__` runs a
        *synchronous* HTTP version probe, and httpx's client construction opens the CA
        bundle from disk. Both are blocking calls on the event loop thread, so building it
        inline made every contract method fail fitness function 7(b) the moment it was
        driven through `weft_kernel.seam.wrap` — which is the only way a registered plugin
        is ever called. `asyncio.to_thread` is `01` → *Colour*'s sanctioned escape hatch and
        the one the guard's own message names; `check_compatibility=False` is not a fix,
        because the CA-bundle read fires regardless. Repair for a reviewer finding against
        task 2.6, pinned by a test that drives this store through the seam.
        """
        if self._client is not None:
            return self._client
        api_key = self._settings.api_key.get_secret_value()
        client = await asyncio.to_thread(
            partial(
                AsyncQdrantClient,
                url=self._settings.url,
                api_key=api_key or None,
                timeout=self._settings.timeout_seconds,
            )
        )
        target = self._bound if self._bound is not None else await self._read_live_target(client)
        self._active_target = target
        if target == DEFAULT_TARGET:
            self._provisioned = await self._open_default(client)
        else:
            self._nodes = f"{self._settings.collection}__t_{target}"
            self._sources = f"{self._settings.collection}__t_{target}__sources"
            self._provisioned = await self._open_candidate(client, target)
        self._client = client
        return client

    async def _open_default(self, client: AsyncQdrantClient) -> bool:
        """`default`'s own pair, verified and reconciled here when it already exists.

        `self._nodes`/`self._sources` are already `self._settings.collection` and its
        `__sources` sibling from `__init__`; this is the identical verify-or-reconcile body
        `_connection` ran unconditionally before ledger task **34.5** — minus the *creation*
        half, which moved to `_ensure_pair_provisioned` at **R43.2** so a `default` nothing
        has written to is opened without creating either collection. Returns whether the
        pair is known to exist, exactly as `_open_candidate` does for a non-default target.
        """
        if not await client.collection_exists(self._nodes):
            return False
        await self._refuse_if_schema_mismatch(client)
        await self._reconcile_quantization(client)
        await self._reconcile_payload_indexes(client)
        if not await client.collection_exists(self._sources):
            # No vectors at all: a source record has nothing to be similar to, and Qdrant
            # is content to hold a payload-only collection. Guarded rather than assumed
            # alongside `self._nodes`, in case an earlier provisioning was interrupted
            # between the two creates.
            await client.create_collection(self._sources, vectors_config={})
        self._vector_width = self._settings.vector_size
        return True

    async def _open_candidate(self, client: AsyncQdrantClient, target: TargetName) -> bool:
        """Resolve a non-default target at open: refuse by name if it is catalogued and one of
        its collections is gone, verify and reconcile if both are there, or leave it alone —
        `self._nodes`/`self._sources` are already set — for an uncatalogued target's first
        write to provision.

        Returns whether the pair is known to exist, which is exactly `self._provisioned`.
        """
        point = await self._catalogue_point(client, target)
        if point is None:
            return False
        nodes_exists = await client.collection_exists(self._nodes)
        sources_exists = await client.collection_exists(self._sources)
        if not nodes_exists or not sources_exists:
            missing = self._nodes if not nodes_exists else self._sources
            raise TargetCollectionMissingError(
                f"target {target!r} is catalogued, but its collection {missing} does not "
                f"exist — something outside Weft deleted it, or a drop was interrupted. "
                f"Weft will not recreate it empty. Drop the target and index it again.",
                pack="weft-qdrant",
            )
        await self._refuse_if_schema_mismatch(client)
        await self._reconcile_quantization(client)
        await self._reconcile_payload_indexes(client)
        self._vector_width = await self._read_committed_width(client)
        return True

    async def _ensure_pair_provisioned(
        self, client: AsyncQdrantClient, width_hint: int | None
    ) -> None:
        """The pair's first write: create `self._nodes`/`self._sources`, and, for a non-default
        target, its catalogue point.

        A no-op once `self._provisioned` is true — every later `add`/`put_source` on this
        handle reaches this and returns immediately. `width_hint` is the width of the first
        embedded node `add` carries, when it carries one, for a non-default target; `put_source`,
        an `add` with no embedded node, and every `default` write (**R43.2** — `default`'s width
        is `[packs.qdrant] vector_size` alone, never a written node's, so the collection a first
        write creates for it is identical to what `_open_default` created eagerly before) pass
        `None`, which falls back to that same setting — the only width an uncatalogued target has
        to go on when its first write carries nothing to measure.

        The two collections created here are the identical pair `_open_default` used to create
        unconditionally at open, moved here at **R43.2**: same vector configuration, same sparse
        vector, same quantization, same optimizer setting, same payload indexes, same vector-less
        `self._sources`.
        """
        if self._provisioned:
            return
        width = width_hint if width_hint is not None else self._settings.vector_size
        if not await client.collection_exists(self._nodes):
            await client.create_collection(
                self._nodes,
                vectors_config={
                    _VECTOR: models.VectorParams(
                        size=width,
                        # Cosine, not configurable, and matching pgvector's `<=>` on purpose:
                        # `Scored.score` is per-search and comparable to nothing, but the
                        # conformance kit compares two backends' *rankings*, and a distance
                        # metric chosen per deployment would make that comparison meaningless.
                        distance=models.Distance.COSINE,
                        datatype=_datatype_for(self._settings.precision),
                    )
                },
                sparse_vectors_config={
                    # `modifier=IDF` is the load-bearing part: it is what applies collection
                    # inverse document frequency at query time, over a sparse dot product that
                    # would otherwise be plain term-frequency matching wearing BM25's name.
                    # Measured working on the pinned `v1.12.4`.
                    _LEXICAL: models.SparseVectorParams(modifier=models.Modifier.IDF)
                },
                quantization_config=_quantization_config_for(self._settings.precision),
                optimizers_config=(
                    models.OptimizersConfigDiff(
                        indexing_threshold=self._settings.indexing_threshold
                    )
                    if self._settings.indexing_threshold is not None
                    else None
                ),
            )
            # Before the first point — task **31.1**: Qdrant generates filterable-HNSW edges
            # only for data indexed after the payload index exists, so an index created later
            # still answers filters but the graph it needed was already built without it.
        await self._reconcile_payload_indexes(client)
        if not await client.collection_exists(self._sources):
            # No vectors at all: a source record has nothing to be similar to, and Qdrant
            # is content to hold a payload-only collection.
            await client.create_collection(self._sources, vectors_config={})
        await self._register_target_if_needed(client)
        self._vector_width = width
        self._provisioned = True

    async def _read_committed_width(self, client: AsyncQdrantClient) -> int:
        """The width `self._nodes`' vector is actually configured for, read off the collection
        itself rather than assumed — a catalogued candidate's width is whatever its first write
        committed to, which `[packs.qdrant] vector_size` does not necessarily name.
        """
        info = await client.get_collection(self._nodes)
        vectors = cast("dict[str, models.VectorParams]", info.config.params.vectors)
        return vectors[_VECTOR].size

    def _committed_width(self) -> int:
        """The width `self._nodes`' vector is committed to — `self._vector_width` once
        `_connection` (and, for a candidate, its first write) has set it, or `vector_size` when
        neither has: a store whose `_connection` a test double replaced entirely never sets
        `self._vector_width` at all, and that is `default`'s own configured width regardless.
        """
        return self._vector_width if self._vector_width is not None else self._settings.vector_size

    def _candidate_unprovisioned(self) -> bool:
        """Whether this handle is bound to a non-default target whose pair does not exist yet —
        the state `claim_embedding` alone still asks about by that narrower name, since a claim
        provisions a candidate sized to the claimed identity's own width and must never do the
        same to `default`, whose width is `[packs.qdrant] vector_size` and nothing else
        (`34.5`, point 3; scope kept narrow at **R43.2**).

        `self._active_target is None` only when `_connection` was never really run — a test
        double replacing it wholesale, as `tests/unit/weft_qdrant/test_store_batches_large_writes
        .py` does — and that case must behave exactly as it always has: an ordinary, already
        writable `default` handle, never a candidate awaiting its first write.
        """
        return (
            self._active_target is not None
            and self._active_target != DEFAULT_TARGET
            and not self._provisioned
        )

    def _pair_unprovisioned(self) -> bool:
        """Whether this handle's node/source pair does not exist yet — the general form of
        `_candidate_unprovisioned`, widened at **R43.2** to include `default` before its first
        write: every read reaching this must answer empty rather than touch Qdrant, and every
        write reaching it must provision first. See `_candidate_unprovisioned` for why
        `claim_embedding` keeps asking the narrower question instead.
        """
        return self._active_target is not None and not self._provisioned

    def _require_active_target(self) -> TargetName:
        """`self._active_target`, narrowed — same guarantee and the same reason as
        `_require_vector_width` above.
        """
        if self._active_target is None:
            raise AssertionError("_connection() must run before _active_target is read")
        return self._active_target

    async def _read_live_target(self, client: AsyncQdrantClient) -> TargetName:
        """The live target the pointer point names, or `DEFAULT_TARGET` when there is none yet
        — `34.2`'s upgrade clause, held for this handle's lifetime by its one caller.
        """
        if not await client.collection_exists(self._catalogue):
            return DEFAULT_TARGET
        records = await client.retrieve(self._catalogue, ids=[_POINTER_POINT_ID], with_payload=True)
        if not records or records[0].payload is None:
            return DEFAULT_TARGET
        return TargetName(cast(str, records[0].payload["live"]))

    async def _catalogue_point(self, client: AsyncQdrantClient, name: str) -> models.Record | None:
        """The one catalogue point recording `name`, or `None` if it has never been written —
        the fact `_open_candidate` reads to decide "catalogued" and `claim_embedding` reads to
        decide whether an identity is already held.
        """
        if not await client.collection_exists(self._catalogue):
            return None
        records = await client.retrieve(
            self._catalogue, ids=[_target_point_id(name)], with_payload=True
        )
        return records[0] if records else None

    async def _ensure_catalogue(self, client: AsyncQdrantClient) -> None:
        """Create `<collection>__targets` before the first write to it, and never on open or on a
        read: a store that only ever serves `default` keeps the two collections it always had.
        Vector-less, like `self._sources`.
        """
        if not await client.collection_exists(self._catalogue):
            await client.create_collection(self._catalogue, vectors_config={})

    async def _register_target_if_needed(self, client: AsyncQdrantClient) -> None:
        """The catalogue point a non-default target earns on its first write — never on a bind,
        never on a read, and never overwriting an identity `claim_embedding` already recorded.
        `default` needs none: the catalogue lists it regardless (`target_catalogue` below).
        """
        target = self._active_target
        if target is None or target == DEFAULT_TARGET:
            return
        if await self._catalogue_point(client, target) is not None:
            return
        await self._ensure_catalogue(client)
        await client.upsert(
            self._catalogue,
            points=[
                models.PointStruct(
                    id=_target_point_id(target),
                    vector={},
                    payload={"kind": "target", "name": target, "embedding": None},
                )
            ],
            wait=True,
        )

    async def _touch_lease(self, client: AsyncQdrantClient) -> None:
        """Write or renew this handle's lease on its non-`default` target — **R34.10**. Renewed
        per write batch, so one long `add` cannot outlive its own lease."""
        target = self._active_target
        if target is None or target == DEFAULT_TARGET:
            return
        await self._ensure_catalogue(client)
        await client.upsert(
            self._catalogue,
            points=[
                models.PointStruct(
                    id=_lease_point_id(self._settings.collection, target, self._holder),
                    vector={},
                    payload={
                        "kind": "lease",
                        "target": target,
                        "holder": self._holder,
                        "expires_at": time.time() + self._settings.target_lease_seconds,
                    },
                )
            ],
            wait=True,
        )
        self._lease_written = True

    async def _leases_for(self, client: AsyncQdrantClient, target: str) -> list[models.Record]:
        """Every lease point recorded against `target`, any holder, expired or not — what
        `drop_target` reads to decide whether another handle still holds it, and what it
        clears once a drop goes ahead.
        """
        if not await client.collection_exists(self._catalogue):
            return []
        found: list[models.Record] = []
        offset: models.ExtendedPointId | None = None
        while True:
            records, next_offset = await client.scroll(
                self._catalogue,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(key="kind", match=models.MatchValue(value="lease")),
                        models.FieldCondition(key="target", match=models.MatchValue(value=target)),
                    ]
                ),
                limit=_PAGE_SIZE,
                with_payload=True,
                offset=offset,
            )
            found.extend(records)
            if next_offset is None:
                return found
            offset = cast("models.ExtendedPointId", next_offset)

    async def _catalogue_names(self, client: AsyncQdrantClient) -> tuple[str, ...]:
        """Every target name the catalogue holds, `default` included — what a refusal naming
        "the targets that exist" offers.
        """
        names: set[str] = {DEFAULT_TARGET}
        if not await client.collection_exists(self._catalogue):
            return tuple(sorted(names))
        offset: models.ExtendedPointId | None = None
        while True:
            records, next_offset = await client.scroll(
                self._catalogue,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(key="kind", match=models.MatchValue(value="target"))
                    ]
                ),
                limit=_PAGE_SIZE,
                with_payload=True,
                offset=offset,
            )
            for record in records:
                if record.payload is not None:
                    names.add(cast(str, record.payload["name"]))
            if next_offset is None:
                return tuple(sorted(names))
            offset = cast("models.ExtendedPointId", next_offset)

    async def _refuse_if_schema_mismatch(self, client: AsyncQdrantClient) -> None:
        """Read the nodes collection's own layout and refuse before any point is touched.

        Run once per `_connection` call, before `self._client` is set — every method goes
        through `_connection`, so a refusal here reaches `add`, `search_text` and the rest
        alike, and none of them ever asks the backend to upsert or query against a vector
        it does not have.
        """
        info = await client.get_collection(self._nodes)
        params = info.config.params
        missing: list[str] = []
        if not isinstance(params.vectors, dict) or _VECTOR not in params.vectors:
            missing.append(_VECTOR)
        if params.sparse_vectors is None or _LEXICAL not in params.sparse_vectors:
            missing.append(_LEXICAL)
        if not missing:
            return
        await client.close()
        named = " ".join(
            f"collection '{self._nodes}' has no vector named '{name}'." for name in missing
        )
        raise CollectionSchemaMismatchError(
            f"{named} It was written by an earlier release of this store, or by "
            f"something else, before this store wrote that vector. Point "
            f"[packs.qdrant] collection at a new name, or delete the collection and "
            f"re-index.",
            pack="weft-qdrant",
        )

    async def _reconcile_quantization(self, client: AsyncQdrantClient) -> None:
        """Apply the configured precision to an unquantised collection, or refuse a mismatch.

        Run once per `_connection` call, after `_refuse_if_schema_mismatch` and before
        `self._client` is set — every method goes through `_connection`, so the refusal reaches
        `add`, `count`, `search_vector` and the rest alike. See `QuantizationMismatchError` for
        the two-branch reasoning this implements.
        """
        info = await client.get_collection(self._nodes)
        current = _quantization_kind(info.config.quantization_config)
        desired = _quantization_kind_for(self._settings.precision)
        if current == desired:
            return
        if current is None:
            config = _quantization_config_for(self._settings.precision)
            if config is not None:
                await client.update_collection(self._nodes, quantization_config=config)
            return
        await client.close()
        raise QuantizationMismatchError(
            f"collection '{self._nodes}' is quantised as '{current}', and [packs.qdrant] "
            f"precision asks for '{self._settings.precision.value}'. Re-quantising in place "
            f"would silently change what every stored vector compares as, so this store "
            f"refuses rather than reconfiguring a collection somebody else's settings built. "
            f"Point [packs.qdrant] collection at a new name and re-index, or set precision "
            f"back to '{current}'.",
            pack="weft-qdrant",
        )

    async def _reconcile_payload_indexes(self, client: AsyncQdrantClient) -> None:
        """Create whatever declared payload index this collection is still missing.

        A payload index is present or absent, never conflicting the way quantization can, so
        there is no refusal to write here — a key declared after the collection already exists
        is simply created. Run for a freshly created collection (every declared key is missing)
        and for an existing one (only the newly declared ones are); the filterable-HNSW benefit
        `_connection` names only reaches points written after an index exists, so creating one
        against an existing collection still answers every filter but does not retroactively
        gain that graph for points already there.

        `DEFAULT_PAYLOAD_INDEXES` is folded in again here, not only trusted from `self._settings`
        — `QdrantSettings.model_copy` does not re-run the validator that merges it in, and the
        guarantee that `lineage.sources` is indexed is the store's, not a property of how its
        settings object happened to be built.
        """
        wanted = {**DEFAULT_PAYLOAD_INDEXES, **self._settings.payload_indexes}
        info = await client.get_collection(self._nodes)
        existing = set(info.payload_schema)
        for field, kind in wanted.items():
            if field in existing:
                continue
            await client.create_payload_index(
                self._nodes, field_name=field, field_schema=_PAYLOAD_SCHEMA_TYPE[kind]
            )

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        """Store `payload` and pass it through — the narrowing `NodeStore` records."""
        del ctx
        await self.add(payload)
        return Produced(value=payload)

    #: How many nodes one request carries. **Not a tuned number and not a measurement.**
    #: `weft index` hands this store the whole corpus as a single batch — `weft_cli/ingest.py`
    #: says "every `SourceDoc` `discover_source_docs` finds is handed to `Runner.run` as the
    #: single element of its batch iterator" — so `add` is routinely called with every node in
    #: the corpus at once. On 2026-09-16 that was 169,223 nodes, and `31.6`'s measurement died
    #: inside this method twice: once on the client's default timeout and again with
    #: `timeout_seconds` raised to 900, both times reaching the operator as `'store' failed: `
    #: with no message (`R31.9`). Any bound far below a corpus makes the request sendable, and
    #: this value is chosen for that alone — it carries no throughput claim, because none was
    #: measured.
    _WRITE_BATCH: ClassVar[int] = 256

    async def add(self, nodes: Sequence[Node]) -> None:
        """Store `nodes` in requests small enough to send — carried repair **R31.10**.

        **Both calls are bounded, and the read is the one that mattered.** `_add_batch` issues a
        `retrieve` before its `upsert`, carrying one id per node, so an unbounded read is reached
        *first* and is as unsendable as an unbounded write — a repair that chunked only the write
        would have fixed nothing. Batching here also bounds peak memory, since the points for a
        slice are built and discarded rather than the whole corpus being materialised at once.

        Splitting is safe because each slice is independently correct: the merge below reads the
        prior payload for the ids in *that* slice, and node ids are content-derived, so no slice
        depends on another. What it gives up is all-or-nothing atomicity across the whole call —
        an interrupted `add` can leave earlier slices written. That is already true of this store
        across separate `add` calls, and `weft index`'s own source records are what make a
        partial index detectable and re-runnable.
        """
        if not nodes:
            return
        client = await self._connection()
        if self._pair_unprovisioned():
            # A `default` or a bound, uncatalogued target's first write (`34.5`, point 3;
            # `default`'s case added at **R43.2**). A candidate is sized to the first embedded
            # node this call carries, or `vector_size` when none of them are embedded; `default`
            # is always sized to `vector_size` alone, exactly as `_open_default` created it.
            width_hint = (
                next(
                    (len(node.embedding.values) for node in nodes if node.embedding is not None),
                    None,
                )
                if self._active_target != DEFAULT_TARGET
                else None
            )
            await self._ensure_pair_provisioned(client, width_hint)
        for start in range(0, len(nodes), self._WRITE_BATCH):
            await self._touch_lease(client)
            await self._add_batch(client, nodes[start : start + self._WRITE_BATCH])

    async def _add_batch(self, client: AsyncQdrantClient, nodes: Sequence[Node]) -> None:
        """One bounded slice of `add`: read the prior payloads, merge, write."""
        # Qdrant has no upsert-merge: an `upsert` replaces the whole payload, so the
        # union of `sources` has to be read back and computed here rather than left to
        # the write itself, the way `pgvector`'s `ON CONFLICT ... DO UPDATE` can.
        point_ids = [str(_point_id(node.id)) for node in nodes]
        existing = await client.retrieve(
            self._nodes, ids=point_ids, with_payload=True, with_vectors=False
        )
        stored: dict[str, Mapping[str, Any]] = {
            str(record.id): cast("Mapping[str, Any]", record.payload)
            for record in existing
            if record.payload is not None
        }
        points: list[models.PointStruct] = []
        for node, point_id in zip(nodes, point_ids, strict=True):
            prior_payload = stored.get(point_id)
            prior_productions = _productions_of(prior_payload) if prior_payload is not None else []
            incoming = node.lineage.sources
            productions = (
                prior_productions
                if incoming in prior_productions
                else [*prior_productions, incoming]
            )
            sources = frozenset[SourceId]().union(*productions) if productions else incoming
            points.append(self._point(node, sources=sources, productions=productions))
        await client.upsert(
            self._nodes,
            points=points,
            # `wait=True` because the contract says durability is a guarantee rather than a
            # call: `flush()` is documented as idempotent and this store has nothing to
            # flush, so the write has to have landed by the time `add` returns.
            wait=True,
        )

    def _point(
        self,
        node: Node,
        *,
        sources: frozenset[SourceId] | None = None,
        productions: Sequence[frozenset[SourceId]] | None = None,
    ) -> models.PointStruct:
        vector: dict[str, list[float] | models.SparseVector] = {}
        if node.embedding is not None:
            values = list(node.embedding.values)
            committed = self._committed_width()
            if len(values) != committed:
                raise VectorWidthMismatchError(
                    f"node {node.id} carries a {len(values)}-component embedding and "
                    f"collection '{self._nodes}' was created for "
                    f"{committed}. A Qdrant collection's width is fixed at "
                    f"creation and cannot be altered, so either [packs.qdrant] "
                    f"vector_size names the wrong width for the configured embedder, or "
                    f"this collection was written by a different one — re-index into a new "
                    f"'collection'.",
                    pack="weft-qdrant",
                )
            vector[_VECTOR] = values
        tokens = analyze(node.content)
        weights = document_weights(tokens, avg_doc_len=self._settings.bm25_avg_doc_len)
        # An empty sparse vector, not a missing entry: `node.content` analysing to no tokens is
        # a legitimate node here, and `SparseVector` has no notion of "absent" the way a named
        # dense vector does.
        vector[_LEXICAL] = models.SparseVector(
            indices=list(weights.keys()), values=list(weights.values())
        )
        payload = node.model_dump(mode="json")
        payload.pop("embedding", None)  # it is the vector; a second copy could disagree
        if sources is not None:
            payload["lineage"]["sources"] = sorted(sources)
        if productions is not None:
            # Ledger **27.1** — a top-level payload key, sibling to `lineage` rather than
            # inside it: `Node` carries no notion of a production (decision 3, "a store fact,
            # never a payload one"), and `_to_node` below reconstructs a node from exactly the
            # keys it names, so this key never reaches `Node.model_validate`.
            payload["productions"] = [sorted(group) for group in productions]
        return models.PointStruct(
            id=str(_point_id(node.id)),
            # The driver types a named-vector map as `dict[str, Vector]`, where `Vector` is
            # its own union; a `dict[str, list[float]]` is the same thing to Qdrant and a
            # different thing to an invariant `dict`, so the cast is about variance and not
            # about the value.
            vector=cast("models.VectorStruct", vector),
            payload=payload,
        )

    async def flush(self) -> None:
        """A true no-op: `add()` waits for the write — see `add`."""
        return

    async def get(self, ids: Sequence[NodeId]) -> Sequence[Node]:
        if not ids:
            return ()
        client = await self._connection()
        if self._pair_unprovisioned():
            # `default` or a bound, uncatalogued target — `34.5`, point 3, widened to `default`
            # at **R43.2**: a read here must not create the pair, and the honest answer is that
            # it holds nothing yet.
            return ()
        records = await client.retrieve(
            self._nodes,
            ids=[str(_point_id(node_id)) for node_id in ids],
            with_payload=True,
            with_vectors=True,
        )
        return tuple(_to_node(record) for record in records)

    async def delete_source(self, source_id: SourceId) -> Removed:
        """Tombstone, delete-and-narrow by filter, clear — `02`'s idempotent, resumable deletion.

        **Ledger `27.1`.** Qdrant has no `array_remove` and no upsert-merge, so a node this
        source shares with a live document cannot be narrowed by the delete itself the way
        `pgvector`'s `cardinality(array_remove(...))` clause is: `_delete_and_narrow` reads
        every point the filter selects and decides, per point, whether removing `source_id`
        empties `lineage.sources` (deleted, counted in `node_count`) or leaves it non-empty
        (narrowed in place, counted in `narrowed_count`).
        """
        client = await self._connection()
        carries = models.Filter(
            must=[
                models.FieldCondition(
                    key="lineage.sources", match=models.MatchValue(value=source_id)
                )
            ]
        )
        existing = await self.get_source(source_id)
        if existing is not None:
            await self.put_source(existing.model_copy(update={"status": SourceStatus.DELETING}))
        node_count, narrowed_count = await self._delete_and_narrow(client, carries, source_id)
        await client.delete(
            self._sources,
            points_selector=models.PointIdsList(points=[str(_point_id(source_id))]),
            wait=True,
        )
        return Removed(source_id=source_id, node_count=node_count, narrowed_count=narrowed_count)

    async def _delete_and_narrow(
        self, client: AsyncQdrantClient, carries: models.Filter, source_id: SourceId
    ) -> tuple[int, int]:
        """Read-modify-write against every point `carries` selects, and the two counts that
        come out of it — shared by `delete_source` and `reconcile`'s own finishing pass, so
        the two can never narrow differently for the identical deletion.

        **Ledger `27.1`.** A point is doomed when every production it carries names
        `source_id` — removing it would leave none. A point is narrowed when at least one
        production does not — that production survives untouched, and `lineage.sources` is
        recomputed as the union of the *surviving* productions rather than merely having
        `source_id` stripped out of it, because two surviving productions can still overlap in
        a source neither alone would justify keeping. `_productions_of` is what makes a point
        written before this feature answer honestly: no stored `productions` key reads as one
        production equal to whatever `lineage.sources` already says (decision 5).
        """
        to_delete: list[models.ExtendedPointId] = []
        narrowed = 0
        offset: Any = None
        while True:
            records, offset = await client.scroll(
                self._nodes,
                scroll_filter=carries,
                limit=_PAGE_SIZE,
                with_payload=True,
                offset=offset,
            )
            for record in records:
                payload = cast("Mapping[str, Any]", record.payload or {})
                surviving = [group for group in _productions_of(payload) if source_id not in group]
                if surviving:
                    sources = frozenset[SourceId]().union(*surviving)
                    await client.set_payload(
                        self._nodes,
                        payload={"sources": sorted(sources)},
                        points=[record.id],
                        key="lineage",
                        wait=True,
                    )
                    await client.set_payload(
                        self._nodes,
                        payload={"productions": [sorted(group) for group in surviving]},
                        points=[record.id],
                        wait=True,
                    )
                    narrowed += 1
                else:
                    to_delete.append(str(record.id))
            if offset is None:
                break
        if to_delete:
            await client.delete(
                self._nodes, points_selector=models.PointIdsList(points=to_delete), wait=True
            )
        return len(to_delete), narrowed

    async def supersede(self, old: NodeId, new: Node) -> None:
        """Replace `old` with `new` — `NodeStore.supersede`, ledger task **10.24**.

        The same design `weft_store.pgvector_store.PgVectorStore.supersede` implements,
        over this backend's own points rather than rows — see that method's docstring,
        which owns the reasoning for both: write `new` first, delete `old` second, so an
        interruption leaves a duplicate rather than a hole; refuse first, changing
        nothing, when `new` covers fewer sources than `old` does; and guard
        `old == new.id` so superseding a node with itself never deletes the point this
        call just wrote to. No transaction spans the write and the delete — Qdrant has
        none to open, and this store keeps the identical, honest ordering-only guarantee
        pgvector does rather than a stronger one only it could keep.
        """
        existing = await self.get([old])
        if existing:
            missing = existing[0].lineage.sources - new.lineage.sources
            if missing:
                dropped = ", ".join(f"'{source}'" for source in sorted(missing))
                raise SupersedeNarrowsSourcesError(
                    f"cannot supersede node {old} with a replacement that drops "
                    f"source(s) {dropped}. A superseding node must carry at least the "
                    f"sources of the node it replaces, or the last node carrying a "
                    f"source disappears while that source's documents remain.",
                    pack="weft-qdrant",
                )
        await self.add([new])
        if old == new.id:
            return
        client = await self._connection()
        await client.delete(
            self._nodes,
            points_selector=models.PointIdsList(points=[str(_point_id(old))]),
            wait=True,
        )

    async def reconcile(self, ctx: Context, mode: ReconcileMode) -> ReconcileReport:
        """Finish every deletion that was interrupted — `Reconcilable`, task **5.1b**.

        The same convergence `weft_store.pgvector_store.PgVectorStore.reconcile` performs, and
        the same argument for why a *node* store converges tombstones rather than orphans; see
        that method's docstring, which owns the reasoning for both. What differs is only what
        this backend's tombstones are: a source record in the second, vector-less collection
        whose `status` is `deleting`, left behind by a `delete_source` that got as far as
        writing it and no further.

        `list_sources` already walks that collection in id order, so the backlog is read with
        the method this store publishes rather than a second traversal that could disagree
        with it.
        """
        del ctx
        client = await self._connection()
        examined = 0
        removed = 0
        for record in await self._tombstoned():
            carries = models.Filter(
                must=[
                    models.FieldCondition(
                        key="lineage.sources", match=models.MatchValue(value=record.id)
                    )
                ]
            )
            node_count, _ = await self._delete_and_narrow(client, carries, record.id)
            await client.delete(
                self._sources,
                points_selector=models.PointIdsList(points=[str(_point_id(record.id))]),
                wait=True,
            )
            examined += 1
            removed += node_count
        return ReconcileReport(
            mode=mode,
            examined=examined,
            removed=removed,
            remaining=len(await self._tombstoned()),
        )

    async def estimate(self, ctx: Context, mode: ReconcileMode) -> ReconcileEstimate:
        """What converging would cost — `Reconcilable`, task **5.1c**.

        The same convergence `weft_store.pgvector_store.PgVectorStore.estimate` reports, and
        the same argument for why: a node store holds the primary data, so `model_calls` is
        honestly `0` for either mode, and `pending` is the identical tombstone count
        `reconcile` itself would examine — see that method's own docstring, which owns the
        reasoning for both backends.
        """
        del ctx
        pending = len(await self._tombstoned())
        description = (
            f"{pending} source(s) have an unfinished deletion to finish"
            if pending
            else "no unfinished deletions; nothing to converge"
        )
        return ReconcileEstimate(mode=mode, pending=pending, description=description)

    async def _tombstoned(self) -> tuple[SourceRecord, ...]:
        """Every source record whose deletion started and did not finish, in id order."""
        return tuple(
            record for record in await self.list_sources() if record.status is SourceStatus.DELETING
        )

    async def scan(self, cursor: Cursor | None = None) -> Page[Node]:
        return await self._walk(None, cursor)

    async def matching(self, filter: Filter, cursor: Cursor | None = None) -> Page[Node]:
        """Every node `filter` selects, paged — `MetadataFilter`, task 2.6."""
        return await self._walk(to_qdrant_filter(filter), cursor)

    async def _walk(self, selector: models.Filter | None, cursor: Cursor | None) -> Page[Node]:
        """One page of Qdrant's own point order, with the driver's offset as the cursor.

        `scan` and `matching` are the same walk with and without a predicate, which
        is what keeps the paging behaviour one implementation: a filtered walk that
        reported "no more pages" differently from an unfiltered one would be a bug
        only a corpus larger than a page could reveal.
        """
        client = await self._connection()
        if self._pair_unprovisioned():
            return Page(items=(), next_cursor=None)
        records, offset = await client.scroll(
            self._nodes,
            scroll_filter=selector,
            offset=cursor,
            limit=_PAGE_SIZE,
            with_payload=True,
            with_vectors=True,
        )
        return Page(
            items=tuple(_to_node(record) for record in records),
            next_cursor=Cursor(str(offset)) if offset is not None else None,
        )

    async def count(self) -> int:
        client = await self._connection()
        if self._pair_unprovisioned():
            return 0
        counted = await client.count(self._nodes, exact=True)
        return counted.count

    async def put_source(self, record: SourceRecord) -> None:
        client = await self._connection()
        if self._pair_unprovisioned():
            # `default`'s first write, or a bound, uncatalogued target's (`34.5`, point 3;
            # `default`'s case at **R43.2**): `put_source` alone, with no embedded node to
            # measure, always falls back to `vector_size` — which is `default`'s own width too.
            await self._ensure_pair_provisioned(client, None)
        await self._touch_lease(client)
        await client.upsert(
            self._sources,
            points=[
                models.PointStruct(
                    id=str(_point_id(record.id)), vector={}, payload=record.model_dump(mode="json")
                )
            ],
            wait=True,
        )

    async def get_source(self, source_id: SourceId) -> SourceRecord | None:
        client = await self._connection()
        if self._pair_unprovisioned():
            return None
        records = await client.retrieve(
            self._sources, ids=[str(_point_id(source_id))], with_payload=True
        )
        return _to_source_record(records[0]) if records else None

    async def list_sources(self) -> Sequence[SourceRecord]:
        """Every source record, ordered by id — the order pgvector's `ORDER BY id` gives.

        Sorted here rather than by the engine because Qdrant orders by point id,
        which is a digest of the source id and therefore an order nobody asked for.
        A caller comparing two backends' output should not have to know which one
        it is talking to.
        """
        client = await self._connection()
        if self._pair_unprovisioned():
            return ()
        found: list[SourceRecord] = []
        offset: models.ExtendedPointId | None = None
        while True:
            records, next_offset = await client.scroll(
                self._sources, offset=offset, limit=_PAGE_SIZE, with_payload=True
            )
            found.extend(_to_source_record(record) for record in records)
            if next_offset is None:
                return tuple(sorted(found, key=lambda record: record.id))
            offset = cast("models.ExtendedPointId", next_offset)

    async def search_vector(
        self, vector: Vector, top_k: int, filter: Filter | None = None
    ) -> Sequence[Scored[Node]]:
        """Rank stored nodes by cosine similarity — `VectorSearch`.

        Never embeds and never asks who embedded: it is handed a vector. The score
        is Qdrant's own cosine similarity, which is the same quantity pgvector's
        `1 - (embedding <=> query)` is, so a ranking from either backend means the
        same thing.
        """
        client = await self._connection()
        if self._pair_unprovisioned():
            return []
        answered = await client.query_points(
            self._nodes,
            query=list(vector.values),
            using=_VECTOR,
            query_filter=to_qdrant_filter(filter) if filter is not None else None,
            search_params=search_params_for(
                index=self._settings.index,
                precision=self._settings.precision,
                rescore_oversampling=self._settings.rescore_oversampling,
            ),
            limit=top_k,
            with_payload=True,
            with_vectors=True,
        )
        return [
            Scored(value=_to_node(point), score=point.score or 0.0) for point in answered.points
        ]

    async def search_text(
        self, text: str, top_k: int, filter: Filter | None = None
    ) -> Sequence[Scored[Node]]:
        """Rank stored nodes by BM25 over the sparse `_LEXICAL` vector — `TextSearch`, task 21.8.

        Term frequency and length normalisation are `weft_qdrant.lexical.query_weights`' own
        arithmetic; the collection's inverse document frequency is applied by the server, from
        the `modifier=IDF` the collection was created with. `filter` narrows what may be
        ranked at the server, exactly as `search_vector` does — passed through to the same
        `to_qdrant_filter`, so a stronger match outside the filter can never win the way it
        would if the filter were applied to an already-decided top-k. A filtered query returns
        the filter's non-matching points at score zero, and they are dropped because a node
        sharing no term with the query is not a match.

        No match, including a query that analyses to no tokens at all, is an empty sequence —
        `TextSearch`'s own emptiness rule — and a query with nothing to ask requires no round
        trip to find that out.
        """
        weights = query_weights(analyze(text))
        if not weights:
            return []
        client = await self._connection()
        if self._pair_unprovisioned():
            return []
        query = models.SparseVector(indices=list(weights.keys()), values=list(weights.values()))
        answered = await client.query_points(
            self._nodes,
            query=query,
            using=_LEXICAL,
            query_filter=to_qdrant_filter(filter) if filter is not None else None,
            limit=top_k,
            with_payload=True,
            with_vectors=True,
        )
        # Descending from the server, non-negative — the other backend's sign-crossing
        # problem is `pg_textsearch`'s `<@>` alone, not this store's.
        return [
            Scored(value=_to_node(point), score=point.score)
            for point in answered.points
            if point.score > 0
        ]

    async def aclose(self) -> None:
        """Release this handle's lease, if it wrote one, and close the client. Not part of any
        contract."""
        if self._client is not None:
            if self._lease_written and self._active_target is not None:
                await self._client.delete(
                    self._catalogue,
                    points_selector=models.PointIdsList(
                        points=[
                            _lease_point_id(
                                self._settings.collection, self._active_target, self._holder
                            )
                        ]
                    ),
                    wait=True,
                )
            await self._client.close()
            self._client = None

    # -- TargetHolding — ledger task **34.5**, with `34.2`'s Qdrant half ---------------------

    async def target_catalogue(self) -> TargetCatalogue:
        client = await self._connection()
        if not await client.collection_exists(self._catalogue):
            return TargetCatalogue(
                live=DEFAULT_TARGET,
                previous=None,
                targets=(TargetRecord(name=DEFAULT_TARGET),),
                promotion=None,
            )
        pointer = await client.retrieve(self._catalogue, ids=[_POINTER_POINT_ID], with_payload=True)
        payload = pointer[0].payload if pointer and pointer[0].payload is not None else None
        live = TargetName(cast(str, payload["live"])) if payload is not None else DEFAULT_TARGET
        previous = cast("str | None", payload.get("previous")) if payload is not None else None
        promotion_json = payload.get("promotion") if payload is not None else None
        promotion = Promotion.model_validate(promotion_json) if promotion_json is not None else None
        embeddings: dict[str, EmbeddingIdentity | None] = {DEFAULT_TARGET: None}
        offset: models.ExtendedPointId | None = None
        while True:
            records, next_offset = await client.scroll(
                self._catalogue,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(key="kind", match=models.MatchValue(value="target"))
                    ]
                ),
                limit=_PAGE_SIZE,
                with_payload=True,
                offset=offset,
            )
            for record in records:
                if record.payload is None:
                    continue
                name = cast(str, record.payload["name"])
                identity_json = record.payload.get("embedding")
                embeddings[name] = (
                    EmbeddingIdentity.model_validate(identity_json)
                    if identity_json is not None
                    else None
                )
            if next_offset is None:
                break
            offset = cast("models.ExtendedPointId", next_offset)
        records_out = tuple(
            TargetRecord(name=name, embedding=embeddings[name]) for name in sorted(embeddings)
        )
        return TargetCatalogue(
            live=live, previous=previous, targets=records_out, promotion=promotion
        )

    async def bind_target(self, target: TargetName) -> Self:
        """A second handle onto the same deployment, bound to `target` — its own client,
        opened lazily on first use exactly as an unbound handle's is.
        """
        return type(self)(self._settings, _bound=target)

    async def claim_embedding(self, identity: EmbeddingIdentity) -> EmbeddingIdentity:
        """Record `identity` against this handle's target, provisioning it first if this is
        its first write — ledger task **34.4**, point 6: a bound, uncatalogued target creates
        its pair exactly as `add`'s first write does (`width_hint` above), sized to
        `identity.width` rather than to a node's vector, so a target opened only to claim an
        identity is not left half-created for the next handle to trip over.
        """
        client = await self._connection()
        target = self._require_active_target()
        if self._candidate_unprovisioned():
            await self._ensure_pair_provisioned(client, identity.width)
        point = await self._catalogue_point(client, target)
        held = point.payload.get("embedding") if point is not None and point.payload else None
        if held is not None:
            return EmbeddingIdentity.model_validate(held)
        await self._ensure_catalogue(client)
        await client.upsert(
            self._catalogue,
            points=[
                models.PointStruct(
                    id=_target_point_id(target),
                    vector={},
                    payload={
                        "kind": "target",
                        "name": target,
                        "embedding": identity.model_dump(mode="json"),
                    },
                )
            ],
            wait=True,
        )
        return identity

    async def promote(self, promotion: Promotion) -> TargetCatalogue:
        """Promoting the target that is already live is a no-op: `previous` is never rewritten to
        the already-live target, so a converging re-run after a crash leaves the rollback an
        operator needs intact.
        """
        client = await self._connection()
        if promotion.target != DEFAULT_TARGET and (
            await self._catalogue_point(client, promotion.target) is None
        ):
            raise UnknownTargetError(
                promotion.target, valid_options=await self._catalogue_names(client)
            )
        old_live = await self._read_live_target(client)
        if old_live == promotion.target:
            return await self.target_catalogue()
        await self._ensure_catalogue(client)
        await client.upsert(
            self._catalogue,
            points=[
                models.PointStruct(
                    id=_POINTER_POINT_ID,
                    vector={},
                    payload={
                        "kind": "pointer",
                        "live": promotion.target,
                        "previous": old_live,
                        "promotion": promotion.model_dump(mode="json"),
                    },
                )
            ],
            wait=True,
        )
        return await self.target_catalogue()

    async def rollback(self) -> TargetCatalogue:
        client = await self._connection()
        if not await client.collection_exists(self._catalogue):
            raise NoPreviousTargetError(DEFAULT_TARGET)
        pointer = await client.retrieve(self._catalogue, ids=[_POINTER_POINT_ID], with_payload=True)
        payload = pointer[0].payload if pointer and pointer[0].payload is not None else None
        live = TargetName(cast(str, payload["live"])) if payload is not None else DEFAULT_TARGET
        previous = cast("str | None", payload.get("previous")) if payload is not None else None
        if previous is None:
            raise NoPreviousTargetError(live)
        # `promotion` is carried over unchanged — the record of the last `promote` call, not
        # reset by a `rollback`, matching `weft_store.pgvector_store.PgVectorStore.rollback`.
        promotion_json = payload.get("promotion") if payload is not None else None
        await self._ensure_catalogue(client)
        await client.upsert(
            self._catalogue,
            points=[
                models.PointStruct(
                    id=_POINTER_POINT_ID,
                    vector={},
                    payload={
                        "kind": "pointer",
                        "live": previous,
                        "previous": live,
                        "promotion": promotion_json,
                    },
                )
            ],
            wait=True,
        )
        return await self.target_catalogue()

    async def drop_target(self, target: TargetName) -> None:
        client = await self._connection()
        catalogue = await self.target_catalogue()
        known = {record.name for record in catalogue.targets}
        if target != DEFAULT_TARGET and target not in known:
            raise UnknownTargetError(target, valid_options=tuple(sorted(known)))
        if target == catalogue.live or target == catalogue.previous:
            raise TargetInUseError(target)
        now = time.time()
        leases = await self._leases_for(client, target)
        blocking = [
            lease
            for lease in leases
            if lease.payload is not None
            and lease.payload.get("holder") != self._holder
            and cast(float, lease.payload.get("expires_at", 0.0)) > now
        ]
        if blocking:
            raise TargetInUseError(target, reason="another handle is bound to it")
        base = self._settings.collection
        if target == DEFAULT_TARGET:
            nodes, sources = base, f"{base}__sources"
        else:
            nodes, sources = f"{base}__t_{target}", f"{base}__t_{target}__sources"
        for name in (nodes, sources):
            if await client.collection_exists(name):
                await client.delete_collection(name)
        # A no-op if `target` never earned a catalogue point — `default` usually has none.
        await self._ensure_catalogue(client)
        await client.delete(
            self._catalogue,
            points_selector=models.PointIdsList(
                points=[_target_point_id(target), *(str(lease.id) for lease in leases)]
            ),
            wait=True,
        )


#: The nine operators that reach a single leaf condition rather than combining others —
#: `_COMPARISON_OPS | {EXISTS}` in `weft_store.contract`'s own naming, restated here by hand
#: rather than imported, because that constant is private to the module that owns the whole
#: vocabulary and this pack only needs to know which nine are *its* leaves.
_LEAF_OPS = frozenset(
    {
        FilterOp.EQ,
        FilterOp.NE,
        FilterOp.IN,
        FilterOp.LT,
        FilterOp.LTE,
        FilterOp.GT,
        FilterOp.GTE,
        FilterOp.EXISTS,
        FilterOp.CONTAINS,
    }
)


def to_qdrant_filter(filter: Filter) -> models.Filter:
    """A `Filter` as Qdrant's own filter, with `weft_store.fields`' meanings preserved.

    Public because it is the interesting half of this pack — the evidence that a
    `Filter` is data rather than a SQL fragment with a Pydantic wrapper — and
    because a test that could only reach it through a live deployment would be a
    test of the deployment.

    Every refusal this makes is made for it by `weft_store.fields.field_for`, so
    an operator typing a path no node has, or an operator no field can carry, gets
    the same error from either backend.

    **`match`/`case _: raise`, not `if`/`elif`/bare fallthrough — task 5.2b.** The final
    line used to be `return models.Filter(must=[_condition(filter)])` with no guard at
    all: any operator that was not `and`/`or`/`not` fell there, leaf or not. A 13th
    `FilterOp` member that turned out to be a *second* combinator would have been routed
    into `_condition` as if it were a leaf, which reads `filter.clauses` and, seeing it
    non-empty, calls back into this function — a mutual-recursion loop neither function's
    tests could have shown, because it does not exist for any operator this enum has
    today. `case op if op in _LEAF_OPS` names exactly the nine operators this branch is
    correct for; `case _: raise` is what makes "not `and`/`or`/`not`" and "is a leaf" stop
    being treated as the same fact.
    """
    match filter.op:
        case FilterOp.AND:
            return models.Filter(must=[_condition(clause) for clause in filter.clauses])
        case FilterOp.OR:
            return models.Filter(should=[_condition(clause) for clause in filter.clauses])
        case FilterOp.NOT:
            return models.Filter(must_not=[_condition(filter.clauses[0])])
        case op if op in _LEAF_OPS:
            return models.Filter(must=[_condition(filter)])
        case _:
            raise UnhandledFilterOpError(
                f"weft-qdrant's filter translator has no top-level case for '{filter.op}'. "
                f"It translates the combinators 'and', 'or', 'not' and the leaf operators "
                f"{', '.join(sorted(member.value for member in _LEAF_OPS))}.",
                valid_options=("and", "or", "not", *sorted(member.value for member in _LEAF_OPS)),
                pack="weft-qdrant",
            )


def _condition(filter: Filter) -> models.Condition:
    """One clause as a Qdrant condition — a nested filter where the shape needs one.

    **`match`/`case _: raise` — task 5.2b.** The final arm used to be an unconditional
    `return matched` reached by anything that was not `exists`, an ordered op or `in` —
    which is correct only because today's remaining two leaf operators, `eq` and
    `contains`, both want an unadorned `MatchValue` and `ne` is peeled off one line above
    it. An operator added to this leaf set tomorrow that wanted a third shape would
    silently be answered as `eq` instead, which is `docs/09-release.md` §2.3's own worked
    example: "`weft_qdrant.store` reinterprets an unknown `FilterOp` as `eq` in
    `_condition`."
    """
    if filter.clauses:
        return to_qdrant_filter(filter)
    key = filter.field or ""
    field_for(filter.op, key)  # refuses an unaddressable path or an operator it cannot carry
    value = filter.value
    match filter.op:
        case FilterOp.EXISTS:
            # `is_empty` is true for a key that is missing, null, or an empty array — the
            # same three cases `weft_store.pgvector_store` spells out in SQL, which is what
            # makes "this node has that field" one question rather than two.
            return models.Filter(
                must_not=[models.IsEmptyCondition(is_empty=models.PayloadField(key=key))]
            )
        case op if op in _ORDERED_OPS:
            return models.FieldCondition(key=key, range=_range(filter.op, _as_number(value)))
        case FilterOp.IN:
            wanted = value if isinstance(value, tuple) else (value,)
            # The driver types `any` as a list of one strict scalar type; a `FilterValue`
            # tuple is already homogeneous by the time it reaches here, and the cast says
            # so rather than rebuilding the list under a type this module cannot narrow to.
            return models.FieldCondition(
                key=key, match=models.MatchAny(any=cast("models.AnyVariants", list(wanted)))
            )
        case FilterOp.NE:
            matched = models.FieldCondition(
                key=key, match=models.MatchValue(value=_as_scalar(value))
            )
            return models.Filter(must_not=[matched])
        case FilterOp.EQ | FilterOp.CONTAINS:
            # `eq` and `contains` are one condition here, and deliberately: Qdrant matches
            # a payload array element-wise, which is the rule `weft_store.fields` states
            # for every store.
            return models.FieldCondition(key=key, match=models.MatchValue(value=_as_scalar(value)))
        case _:
            raise UnhandledFilterOpError(
                f"weft-qdrant's leaf-condition translator has no case for '{filter.op}'. It "
                f"knows: {', '.join(sorted(member.value for member in _LEAF_OPS))}.",
                valid_options=tuple(sorted(member.value for member in _LEAF_OPS)),
                pack="weft-qdrant",
            )


#: The four operators Qdrant answers with a `Range` rather than a match.
_ORDERED_OPS = frozenset({FilterOp.LT, FilterOp.LTE, FilterOp.GT, FilterOp.GTE})


def _range(op: FilterOp, bound: float) -> models.Range:
    """One bound of a Qdrant `Range`, the other three left open.

    Four branches rather than a keyword table: `Range`'s four fields are separately
    typed, and building it by unpacking a `{name: value}` mapping types the value
    as whatever the first field happens to be.

    **`match`/`case _: raise` — task 5.2b.** The final branch used to be a bare
    `return models.Range(gte=bound)`, so any operator besides `lt`/`lte`/`gt` — reachable
    only through `_ORDERED_OPS`, whose own membership check is what made "the other
    three" mean exactly `gte` and nothing else — answered as `gte` instead of refusing.
    `docs/09-release.md` §2.3's own words for this: "as `gte` in `_range`."
    """
    match op:
        case FilterOp.LT:
            return models.Range(lt=bound)
        case FilterOp.LTE:
            return models.Range(lte=bound)
        case FilterOp.GT:
            return models.Range(gt=bound)
        case FilterOp.GTE:
            return models.Range(gte=bound)
        case _:
            raise UnhandledFilterOpError(
                f"weft-qdrant's range translator has no case for '{op}'. It knows: gt, gte, "
                f"lt, lte.",
                valid_options=("gt", "gte", "lt", "lte"),
                pack="weft-qdrant",
            )


def _as_number(value: FilterValue | None) -> float:
    """The number an ordered comparison carries. `Filter` has already refused anything else."""
    return float(cast(float, value))


def _as_scalar(value: FilterValue | None) -> str | int | bool:
    """The scalar an identity comparison carries. `Filter` has already refused a tuple."""
    return cast(str | int | bool, value)


def _productions_of(payload: Mapping[str, Any]) -> list[frozenset[SourceId]]:
    """Every production a stored point carries — ledger **27.1**.

    `payload["productions"]` is written by `QdrantStore._point` and read back nowhere but here
    and `_delete_and_narrow`; a point this store wrote before the feature existed has no such
    key, and decision 5's answer for a point whose history was never kept applies identically to
    this backend as it does to `weft_store.pgvector_store`'s migration: one production, equal to
    whatever `lineage.sources` already says.
    """
    raw = payload.get("productions")
    if raw is None:
        lineage = cast("Mapping[str, Any]", payload["lineage"])
        return [frozenset(cast("list[SourceId]", lineage["sources"]))]
    return [frozenset(cast("list[SourceId]", group)) for group in cast("list[list[str]]", raw)]


def _point_id(identifier: str) -> UUID:
    """The point id for a `NodeId` or a `SourceId` — deterministic, so a re-index overwrites.

    Qdrant accepts an unsigned integer or a UUID and nothing else, and both of
    Weft's identifiers are strings: a `NodeId` is a sha256 hex digest, a `SourceId`
    is whatever named the document. `uuid5` maps either into the space Qdrant will
    take without inventing a counter that would have to be stored somewhere.
    """
    return uuid5(_ID_NAMESPACE, identifier)


def _to_node(record: models.Record | models.ScoredPoint) -> Node:
    """A stored point back into a `Node`, with its `ext` rehydrated by the owning classes."""
    payload = cast(Mapping[str, Any], record.payload or {})
    vectors = record.vector if isinstance(record.vector, dict) else {}
    values = cast("dict[str, Any]", vectors).get(_VECTOR)
    return Node.model_validate(
        {
            "id": payload["id"],
            "lineage": payload["lineage"],
            "content": payload["content"],
            "media_type": payload["media_type"],
            "embedding": {"values": list(cast("Sequence[float]", values))}
            if values is not None
            else None,
            "ext": rehydrate_ext(cast("Mapping[str, object]", payload.get("ext", {}))),
        },
        context={"derived": True},
    )


def _to_source_record(record: models.Record) -> SourceRecord:
    payload = dict(record.payload or {})
    status = payload.get("status")
    if isinstance(status, str):
        payload["status"] = source_status(status)
    failure = payload.get("failure")
    if isinstance(failure, Mapping):
        payload["failure"] = source_failure(cast("Mapping[str, object]", failure))
    if "layers" in payload:
        payload["layers"] = source_layers(cast("Sequence[Mapping[str, object]]", payload["layers"]))
    return SourceRecord.model_validate(payload)
