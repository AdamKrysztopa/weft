"""`InMemoryNodeStore` — a stranger's whole store family: `NodeStore`, `VectorSearch`,
`TextSearch`, `MetadataFilter`, `SourceDeletable` and `Reconcilable`, all six, over one
process-lifetime Python dict.

**`Lifetime.PROCESS`, stated as the deliberate choice it is.** A plugin defaults to
`Lifetime.RUN` — a fresh instance per pipeline run — which is exactly right for
`weft_store.pgvector_store.PgVectorStore`: the durable state lives in Postgres, not in the
Python object, so a fresh instance still talks to the same database. An in-memory store has
no database behind it — the dict *is* the durable state — so `Lifetime.RUN` here would mean
every run started from an empty corpus. Declaring `PROCESS` is what makes "in-memory" mean
"durable for this process" rather than "durable for one call".

**No container, on purpose.** `docs/07-extension-cost.md` §9's own note for the query-path
example applies here too: a stranger's own test suite must run with nothing behind it but
this file, and a real store contract is provable without a database standing behind it —
this is the "ephemeral in-memory store" `docs/build-ledger.md` task 2.6 names as still open
and unclaimed by any ledger task; this pack is not that store (it lives outside the
workspace, on purpose — see the module's own `pyproject.toml`), but it is a genuine,
independently-arrived-at instance of the same shape.

**`matching` reuses `weft_store.fields`, never re-derives its own field vocabulary.** `02`
§1's own argument for that module — "two translators start from one parse" — applies to a
third translator exactly as it does to a second: `field_for` is the one call that decides
what a `Filter.field` reaches on a `Node` and which operators it admits, so this store
disagrees with pgvector and Qdrant about a filter's meaning in no more ways than they
already disagree with each other, which is none.
"""

from collections.abc import Sequence
from typing import ClassVar

from weft_kernel.context import Context
from weft_kernel.payload import Node, NodeId, Outcome, Produced, SourceId, Vector
from weft_kernel.runner import Lifetime
from weft_store.contract import (
    Cursor,
    Filter,
    FilterOp,
    Page,
    ReconcileEstimate,
    ReconcileMode,
    ReconcileReport,
    Removed,
    Scored,
    SourceRecord,
    SourceStatus,
)
from weft_store.fields import FieldKind, FieldPath, field_for


class InMemoryNodeStore:
    """The whole store family over a plain `dict`. Satisfies `weft_store.contract.NodeStore`,
    `VectorSearch`, `TextSearch`, `MetadataFilter`, `SourceDeletable` and `Reconcilable`
    structurally — this class never imports any of them. The last two arrived with G7 at tasks
    5.1a and 5.1b, and `SourceDeletable` needed no code at all: `delete_source` was already
    here, which is what "capability is derived, never declared" buys a pack author.
    `Reconcilable` grew `estimate` at task 5.1c, a major bump for every implementer per G9 —
    this stranger's own update is one small, honest method, not a rewrite.
    """

    lifetime: ClassVar[Lifetime] = Lifetime.PROCESS

    def __init__(self, config: object = None) -> None:
        del config
        self._nodes: dict[NodeId, Node] = {}
        self._sources: dict[SourceId, SourceRecord] = {}

    # -- NodeStore -----------------------------------------------------------------------

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        await self.add(payload)
        return Produced(value=payload)

    async def add(self, nodes: Sequence[Node]) -> None:
        for node in nodes:
            self._nodes[node.id] = node

    async def flush(self) -> None:
        # Every write above is already durable within this process — nothing buffered.
        return

    async def get(self, ids: Sequence[NodeId]) -> Sequence[Node]:
        return tuple(self._nodes[node_id] for node_id in ids if node_id in self._nodes)

    async def delete_source(self, source_id: SourceId) -> Removed:
        record = self._sources.get(source_id)
        if record is not None:
            self._sources[source_id] = record.model_copy(update={"status": SourceStatus.DELETING})
        removed = tuple(
            node_id for node_id, node in self._nodes.items() if source_id in node.lineage.sources
        )
        for node_id in removed:
            del self._nodes[node_id]
        self._sources.pop(source_id, None)
        return Removed(source_id=source_id, node_count=len(removed))

    async def reconcile(self, ctx: Context, mode: ReconcileMode) -> ReconcileReport:
        """`Reconcilable` — finish every deletion this store started and did not end.

        A stranger's whole convergence, and it is short for the reason the contract is worth
        having: the backlog is *state this store already keeps*, the `DELETING` tombstones
        `delete_source` above writes, so a pass that stops early loses nothing and the next
        one finds exactly what is left. Nothing here is derived from a cursor, which is what
        `02` §1 means by "resumes rather than restarting".

        `full` backfills nothing, and that is honest rather than lazy: this store holds the
        primary nodes, so it has no derived state that was never built.
        """
        del ctx
        removed = 0
        examined = 0
        for source_id in tuple(self._tombstoned()):
            gone = tuple(
                node_id
                for node_id, node in self._nodes.items()
                if source_id in node.lineage.sources
            )
            for node_id in gone:
                del self._nodes[node_id]
            self._sources.pop(source_id, None)
            examined += 1
            removed += len(gone)
        return ReconcileReport(
            mode=mode, examined=examined, removed=removed, remaining=len(tuple(self._tombstoned()))
        )

    async def estimate(self, ctx: Context, mode: ReconcileMode) -> ReconcileEstimate:
        """`Reconcilable.estimate` — what converging would cost, task **5.1c**.

        Honest for the same reason `reconcile` above is: this store holds the primary nodes,
        never derived state, so `model_calls` is `0` whichever mode is asked about. `pending`
        is the identical tombstone count `reconcile` itself would examine.
        """
        del ctx
        pending = len(self._tombstoned())
        description = (
            f"{pending} source(s) have an unfinished deletion to finish"
            if pending
            else "no unfinished deletions; nothing to converge"
        )
        return ReconcileEstimate(mode=mode, pending=pending, description=description)

    def _tombstoned(self) -> tuple[SourceId, ...]:
        return tuple(
            source_id
            for source_id, record in self._sources.items()
            if record.status is SourceStatus.DELETING
        )

    async def scan(self, cursor: Cursor | None = None) -> Page[Node]:
        del cursor  # a single in-memory page holds the whole corpus — no real pagination
        return Page(items=tuple(self._nodes.values()))

    async def count(self) -> int:
        return len(self._nodes)

    async def put_source(self, record: SourceRecord) -> None:
        self._sources[record.id] = record

    async def get_source(self, source_id: SourceId) -> SourceRecord | None:
        return self._sources.get(source_id)

    async def list_sources(self) -> Sequence[SourceRecord]:
        return tuple(self._sources.values())

    # -- VectorSearch ----------------------------------------------------------------------

    async def search_vector(
        self, vector: Vector, top_k: int, filter: Filter | None = None
    ) -> Sequence[Scored[Node]]:
        candidates = (node for node in self._nodes.values() if node.embedding is not None)
        if filter is not None:
            candidates = (node for node in candidates if _matches(node, filter))
        scored = [
            Scored(value=node, score=_cosine(vector, node.embedding))
            for node in candidates
            if node.embedding is not None
        ]
        scored.sort(key=lambda item: item.score, reverse=True)
        return tuple(scored[:top_k])

    # -- TextSearch ------------------------------------------------------------------------

    async def search_text(
        self, text: str, top_k: int, filter: Filter | None = None
    ) -> Sequence[Scored[Node]]:
        query_words = _words(text)
        if not query_words:
            return ()
        candidates = self._nodes.values()
        if filter is not None:
            candidates = [node for node in candidates if _matches(node, filter)]
        scored: list[Scored[Node]] = []
        for node in candidates:
            overlap = query_words & _words(node.content)
            if overlap:
                scored.append(Scored(value=node, score=len(overlap) / len(query_words)))
        scored.sort(key=lambda item: item.score, reverse=True)
        return tuple(scored[:top_k])

    # -- MetadataFilter ----------------------------------------------------------------------

    async def matching(self, filter: Filter, cursor: Cursor | None = None) -> Page[Node]:
        del cursor  # see `scan` — no real pagination in this example store
        return Page(items=tuple(node for node in self._nodes.values() if _matches(node, filter)))


def _cosine(left: Vector, right: Vector) -> float:
    """Cosine similarity, `0.0` when either vector has no magnitude — never a division error."""
    dot = sum(a * b for a, b in zip(left.values, right.values, strict=False))
    left_norm = sum(a * a for a in left.values) ** 0.5
    right_norm = sum(b * b for b in right.values) ** 0.5
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _words(text: str) -> frozenset[str]:
    return frozenset(text.lower().split())


def _matches(node: Node, filter: Filter) -> bool:
    """Evaluate `filter`'s AST against `node` — the whole of `MetadataFilter`'s promise."""
    if filter.op is FilterOp.AND:
        return all(_matches(node, clause) for clause in filter.clauses)
    if filter.op is FilterOp.OR:
        return any(_matches(node, clause) for clause in filter.clauses)
    if filter.op is FilterOp.NOT:
        return not _matches(node, filter.clauses[0])
    path = field_for(filter.op, filter.field or "")
    value = _value_at(node, path)
    if filter.op is FilterOp.EXISTS:
        return value is not None
    return _compare(filter.op, value, filter.value)


def _value_at(node: Node, path: FieldPath) -> object:
    """The value `path` reaches on `node`, or `None` when an extension path is absent."""
    if path.kind is FieldKind.EXTENSION:
        model = node.ext.get(path.namespace)
        for key in path.keys:
            if model is None:
                return None
            model = getattr(model, key, None)
        return model
    if path.core is None:  # pragma: no cover — `field_for` never returns this combination
        return None
    return {
        "id": node.id,
        "content": node.content,
        "media_type": node.media_type,
        "lineage.parents": frozenset(node.lineage.parents),
        "lineage.sources": frozenset(node.lineage.sources),
    }[path.core.value]


def _compare(op: FilterOp, value: object, target: object) -> bool:
    """Every comparison `MetadataFilter` promises, once the field and its target are in hand."""
    if value is None:
        return False
    if op is FilterOp.EQ:
        return value == target
    if op is FilterOp.NE:
        return value != target
    if op is FilterOp.IN:
        return isinstance(target, tuple) and value in target
    if op is FilterOp.CONTAINS:
        return isinstance(value, frozenset | tuple | list) and target in value
    if op in (FilterOp.LT, FilterOp.LTE, FilterOp.GT, FilterOp.GTE):
        if not isinstance(value, int | float) or not isinstance(target, int | float):
            return False
        return {
            FilterOp.LT: value < target,
            FilterOp.LTE: value <= target,
            FilterOp.GT: value > target,
            FilterOp.GTE: value >= target,
        }[op]
    return False  # pragma: no cover — every operator field_for admits is handled above
