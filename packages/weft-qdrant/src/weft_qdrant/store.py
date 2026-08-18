"""`QdrantStore` — the second backend, and the reason the store contract is no longer a guess.

Ledger task **2.6**: "the store contract is satisfied by a second backend of a
genuinely different shape, so it is no longer a guess." `01` → *Runtime shape*
names the pair and why it is that pair: "the contract is proven on **pgvector and
Qdrant**, which have genuinely different shapes, and a store that only Postgres
can satisfy fails that test just as loudly." G4 retired the zero-container target
on the same reasoning — two backends that are obviously different are safer than
two that are subtly alike.

**Three tiers, deliberately not four.** `NodeStore`, `VectorSearch` and
`MetadataFilter`; **no `TextSearch`**, and that is a decision rather than an
omission. Qdrant's text matching is a filter predicate — does this payload
contain this substring — and `TextSearch.search_text` returns `Scored[Node]`, a
*ranking*. There is no honest score to put in it. A shim that returned a constant
score, or a BM25 index this pack maintained beside the collection, would be the
thing task 2.5 exists to forbid: a retriever's own second copy of the corpus,
stale from the first write. So a `hybrid` retriever configured against this store
is refused by name, before any stage runs, and told that `pgvector` provides what
is missing. Two backends with identical capability sets would leave that promise
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
"""

import asyncio
from collections.abc import Mapping, Sequence
from functools import partial
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from qdrant_client import AsyncQdrantClient, models

from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.payload import Node, NodeId, Outcome, Produced, SourceId, Vector
from weft_qdrant.settings import QdrantSettings
from weft_store.contract import (
    Cursor,
    Filter,
    FilterOp,
    FilterValue,
    Page,
    Removed,
    Scored,
    SourceRecord,
    SourceStatus,
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

#: The namespace every point id is derived under. A fixed, arbitrary URL, so the same node
#: lands on the same point in every deployment and a re-index overwrites rather than
#: duplicates — `uuid5` is a digest, not a random id, which is the whole reason to use it.
_ID_NAMESPACE = uuid5(NAMESPACE_URL, "https://weft.invalid/qdrant/point-id")


class VectorWidthMismatchError(WeftError):
    """A node's embedding is not the width this collection was created with.

    Postgres does not have this failure — `weft-store` declares its column with no
    dimension — and that is exactly why it is worth naming rather than letting the
    driver report it. A collection's width cannot be altered, so the remedy is a
    decision (re-index under a different `[packs.weft-qdrant] collection`, or point
    `vector_size` at the embedder actually configured), and an operator cannot make
    it from a driver's "expected dim: 64, got 1536".
    """


class QdrantStore:
    """A `NodeStore`, `VectorSearch` and `MetadataFilter` over a Qdrant deployment.

    Satisfies those three structurally — this class never imports one of the
    Protocols, the same path any third-party store pack takes. It does not satisfy
    `TextSearch`, and the module docstring says why that is a decision.
    """

    def __init__(self, settings: QdrantSettings, config: object = None) -> None:
        del config  # nothing at the stage level this store needs — as with pgvector
        self._settings = settings
        self._nodes = settings.collection
        #: A collection rather than a table, because Qdrant has no second table inside one.
        self._sources = f"{settings.collection}__sources"
        self._client: AsyncQdrantClient | None = None

    async def _connection(self) -> AsyncQdrantClient:
        """The lazily-opened, provisioned client this store reuses for its lifetime.

        Lazy for the reason `weft_store.pgvector_store` gives: creating a collection
        is a coroutine and `__init__` cannot be one. Both collections are created
        idempotently on first use — a store that required a human to have run a
        provisioning step before `weft index` works once is exactly the friction a
        walking skeleton exists to remove.

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
        if not await client.collection_exists(self._nodes):
            await client.create_collection(
                self._nodes,
                vectors_config={
                    _VECTOR: models.VectorParams(
                        size=self._settings.vector_size,
                        # Cosine, not configurable, and matching pgvector's `<=>` on purpose:
                        # `Scored.score` is per-search and comparable to nothing, but the
                        # conformance kit compares two backends' *rankings*, and a distance
                        # metric chosen per deployment would make that comparison meaningless.
                        distance=models.Distance.COSINE,
                    )
                },
            )
        if not await client.collection_exists(self._sources):
            # No vectors at all: a source record has nothing to be similar to, and Qdrant
            # is content to hold a payload-only collection.
            await client.create_collection(self._sources, vectors_config={})
        self._client = client
        return client

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        """Store `payload` and pass it through — the narrowing `NodeStore` records."""
        del ctx
        await self.add(payload)
        return Produced(value=payload)

    async def add(self, nodes: Sequence[Node]) -> None:
        if not nodes:
            return
        client = await self._connection()
        await client.upsert(
            self._nodes,
            points=[self._point(node) for node in nodes],
            # `wait=True` because the contract says durability is a guarantee rather than a
            # call: `flush()` is documented as idempotent and this store has nothing to
            # flush, so the write has to have landed by the time `add` returns.
            wait=True,
        )

    def _point(self, node: Node) -> models.PointStruct:
        vector: dict[str, list[float]] = {}
        if node.embedding is not None:
            values = list(node.embedding.values)
            if len(values) != self._settings.vector_size:
                raise VectorWidthMismatchError(
                    f"node {node.id} carries a {len(values)}-component embedding and "
                    f"collection '{self._nodes}' was created for "
                    f"{self._settings.vector_size}. A Qdrant collection's width is fixed at "
                    f"creation and cannot be altered, so either [packs.weft-qdrant] "
                    f"vector_size names the wrong width for the configured embedder, or "
                    f"this collection was written by a different one — re-index into a new "
                    f"'collection'.",
                    pack="weft-qdrant",
                )
            vector[_VECTOR] = values
        payload = node.model_dump(mode="json")
        payload.pop("embedding", None)  # it is the vector; a second copy could disagree
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
        records = await client.retrieve(
            self._nodes,
            ids=[str(_point_id(node_id)) for node_id in ids],
            with_payload=True,
            with_vectors=True,
        )
        return tuple(_to_node(record) for record in records)

    async def delete_source(self, source_id: SourceId) -> Removed:
        """Tombstone, delete by filter, clear — `02`'s idempotent, resumable deletion.

        The count comes from a `count` before the delete rather than from the
        delete itself, which reports nothing: two calls where Postgres has one, and
        an honest count rather than a number this store would have had to invent.
        """
        client = await self._connection()
        carries = models.Filter(
            must=[
                models.FieldCondition(
                    key="lineage.sources", match=models.MatchValue(value=source_id)
                )
            ]
        )
        counted = await client.count(self._nodes, count_filter=carries, exact=True)
        existing = await self.get_source(source_id)
        if existing is not None:
            await self.put_source(
                SourceRecord(
                    id=existing.id,
                    uri=existing.uri,
                    content_hash=existing.content_hash,
                    indexed_at=existing.indexed_at,
                    pipeline=existing.pipeline,
                    status=SourceStatus.DELETING,
                )
            )
        await client.delete(
            self._nodes, points_selector=models.FilterSelector(filter=carries), wait=True
        )
        await client.delete(
            self._sources,
            points_selector=models.PointIdsList(points=[str(_point_id(source_id))]),
            wait=True,
        )
        return Removed(source_id=source_id, node_count=counted.count)

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
        counted = await client.count(self._nodes, exact=True)
        return counted.count

    async def put_source(self, record: SourceRecord) -> None:
        client = await self._connection()
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
        answered = await client.query_points(
            self._nodes,
            query=list(vector.values),
            using=_VECTOR,
            query_filter=to_qdrant_filter(filter) if filter is not None else None,
            limit=top_k,
            with_payload=True,
            with_vectors=True,
        )
        return [
            Scored(value=_to_node(point), score=point.score or 0.0) for point in answered.points
        ]

    async def aclose(self) -> None:
        """Close the underlying client, if one was ever opened. Not part of any contract."""
        if self._client is not None:
            await self._client.close()
            self._client = None


def to_qdrant_filter(filter: Filter) -> models.Filter:
    """A `Filter` as Qdrant's own filter, with `weft_store.fields`' meanings preserved.

    Public because it is the interesting half of this pack — the evidence that a
    `Filter` is data rather than a SQL fragment with a Pydantic wrapper — and
    because a test that could only reach it through a live deployment would be a
    test of the deployment.

    Every refusal this makes is made for it by `weft_store.fields.field_for`, so
    an operator typing a path no node has, or an operator no field can carry, gets
    the same error from either backend.
    """
    if filter.op is FilterOp.AND:
        return models.Filter(must=[_condition(clause) for clause in filter.clauses])
    if filter.op is FilterOp.OR:
        return models.Filter(should=[_condition(clause) for clause in filter.clauses])
    if filter.op is FilterOp.NOT:
        return models.Filter(must_not=[_condition(filter.clauses[0])])
    return models.Filter(must=[_condition(filter)])


def _condition(filter: Filter) -> models.Condition:
    """One clause as a Qdrant condition — a nested filter where the shape needs one."""
    if filter.clauses:
        return to_qdrant_filter(filter)
    key = filter.field or ""
    field_for(filter.op, key)  # refuses an unaddressable path or an operator it cannot carry
    value = filter.value
    if filter.op is FilterOp.EXISTS:
        # `is_empty` is true for a key that is missing, null, or an empty array — the same
        # three cases `weft_store.pgvector_store` spells out in SQL, which is what makes
        # "this node has that field" one question rather than two.
        return models.Filter(
            must_not=[models.IsEmptyCondition(is_empty=models.PayloadField(key=key))]
        )
    if filter.op in _ORDERED_OPS:
        return models.FieldCondition(key=key, range=_range(filter.op, _as_number(value)))
    if filter.op is FilterOp.IN:
        wanted = value if isinstance(value, tuple) else (value,)
        # The driver types `any` as a list of one strict scalar type; a `FilterValue` tuple
        # is already homogeneous by the time it reaches here, and the cast says so rather
        # than rebuilding the list under a type this module cannot narrow to.
        return models.FieldCondition(
            key=key, match=models.MatchAny(any=cast("models.AnyVariants", list(wanted)))
        )
    matched = models.FieldCondition(key=key, match=models.MatchValue(value=_as_scalar(value)))
    if filter.op is FilterOp.NE:
        return models.Filter(must_not=[matched])
    # `eq` and `contains` are one condition here, and deliberately: Qdrant matches a payload
    # array element-wise, which is the rule `weft_store.fields` states for every store.
    return matched


#: The four operators Qdrant answers with a `Range` rather than a match.
_ORDERED_OPS = frozenset({FilterOp.LT, FilterOp.LTE, FilterOp.GT, FilterOp.GTE})


def _range(op: FilterOp, bound: float) -> models.Range:
    """One bound of a Qdrant `Range`, the other three left open.

    Four branches rather than a keyword table: `Range`'s four fields are separately
    typed, and building it by unpacking a `{name: value}` mapping types the value
    as whatever the first field happens to be.
    """
    if op is FilterOp.LT:
        return models.Range(lt=bound)
    if op is FilterOp.LTE:
        return models.Range(lte=bound)
    if op is FilterOp.GT:
        return models.Range(gt=bound)
    return models.Range(gte=bound)


def _as_number(value: FilterValue | None) -> float:
    """The number an ordered comparison carries. `Filter` has already refused anything else."""
    return float(cast(float, value))


def _as_scalar(value: FilterValue | None) -> str | int | bool:
    """The scalar an identity comparison carries. `Filter` has already refused a tuple."""
    return cast(str | int | bool, value)


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
    return SourceRecord.model_validate(record.payload or {})
