"""The ephemeral in-memory store — a dict with brute-force cosine, and not a backend.

Ledger task **26.6**. `docs/01-high-level-plan.md` → *Runtime shape* has required this since
Phase 0 and no ledger task ever owned it:

> An ephemeral in-memory store exists, and is not a backend. A dict with brute-force cosine, never
> persisted, used by the conformance kit and by pack authors' unit tests so writing a plugin does
> not require Docker. It forgets everything on exit, deliberately, so nobody deploys on it and
> there is no migration path to fight.

`docs/07-extension-cost.md` §2's canonical-four table promises it too — file 4 is *"the pack's own
tests, against the conformance kit and the ephemeral in-memory store"* — and carried repair
`R19.5` recorded that neither half existed. Task `26.4` published the kit; this is the other half.
Without it, the kit a stranger can now import still needs two containers before it says anything.

**What it satisfies, and what it deliberately does not.** `NodeStore`, `VectorSearch` and, since
ledger task **34.3**, `TargetHolding`. Not `MetadataFilter`: no in-Python evaluator for the filter
AST exists anywhere in this tree — `pgvector_store` translates a `Filter` into SQL and
`weft_qdrant` into Qdrant's own filter language — so answering `matching` here would mean writing
a third evaluator from scratch and keeping it correct against two others that a real query engine
already checks. `01` asks this store for a dict and brute-force cosine, which is exactly these two
capabilities; `TargetHolding` costs nothing beyond a second dict, keyed by target name, because the
store was already one instance's own state. `weft_store.conformance.checks_for` is what makes that
a first-class store rather than a failing one: it is offered the checks it can answer and told
which it cannot, with the capability each needs.

**Not a backend, and that is a property rather than a limitation.** It opens no connection, writes
no file and registers under no `[services] store` name, so nothing can select it from `weft.toml`
and nobody can deploy on it by accident. Forgetting everything when the process ends is the point:
there is no persisted shape, so there is no migration path to fight.

**Per-instance state, never module-level.** Two `MemoryStore()` objects share nothing. A module
dict would pass every test that examines one store and then quietly join two test cases together,
which is worse than no double at all — it fails intermittently, in somebody else's suite, for a
reason that is not in their code.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import ClassVar, Self

from weft_kernel.context import Context
from weft_kernel.payload import Node, NodeId, Outcome, Produced, SourceId, Vector
from weft_store.contract import (
    DEFAULT_TARGET,
    STORE_CONTRACT_VERSION,
    Cursor,
    EmbeddingIdentity,
    Filter,
    NoPreviousTargetError,
    Page,
    Promotion,
    Removed,
    Scored,
    SourceRecord,
    TargetCatalogue,
    TargetInUseError,
    TargetName,
    TargetRecord,
    UnknownTargetError,
)


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    """Cosine similarity, brute force, with a zero vector scoring `0.0` rather than dividing.

    A zero-magnitude vector has no direction, so *similar to what?* has no answer; returning `0.0`
    is the honest one and raising would make an empty embedding a crash on a path a caller cannot
    see into. `1.0` for the identical vector is what the kit's own ranking check asserts.
    """
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    magnitude = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return 0.0 if magnitude == 0.0 else dot / magnitude


class _TargetData:
    """One target's own nodes, source records, productions and claimed embedding identity.

    Never shared across targets — a `MemoryStore` handle bound to one target must see none of
    another's, exactly as two `MemoryStore()` instances share nothing.
    """

    def __init__(self) -> None:
        self.nodes: dict[NodeId, Node] = {}
        self.sources: dict[SourceId, SourceRecord] = {}
        #: One entry per *arrival* of a node, holding the sources that arrival carried — never a
        #: flattened set. **G20 turns on exactly this distinction and a set cannot express it**: a
        #: node built by one `Node.combine` over two documents has a single production naming both,
        #: and deleting either document leaves no production, so the node goes. A node two
        #: documents each produced *whole* has two productions, and deleting one leaves the other,
        #: so the node stays and its `sources` is recomputed. Both shapes have
        #: `lineage.sources == {A, B}`, which is why storing only that answers the two cases
        #: identically and wrongly.
        self.productions: dict[NodeId, list[frozenset[SourceId]]] = {}
        self.embedding: EmbeddingIdentity | None = None


class _StoreState:
    """What every handle onto one `MemoryStore()` shares — task **34.3**.

    `MemoryStore()` builds one of these; `bind_target` hands out another `MemoryStore` sharing
    the same instance, which is the whole of how two handles onto one store see the same
    catalogue. `default` exists from construction — `check_a_fresh_store_has_one_live_target_
    named_default` — because a store nothing has targeted yet still has to answer `target_
    catalogue()` with something live.
    """

    def __init__(self) -> None:
        self.data: dict[TargetName, _TargetData] = {DEFAULT_TARGET: _TargetData()}
        self.live: TargetName = DEFAULT_TARGET
        self.previous: TargetName | None = None
        self.promotion: Promotion | None = None


class MemoryStore:
    """An in-memory `NodeStore`, `VectorSearch` and `TargetHolding`.

    A `NodeStore`, `VectorSearch` and `TargetHolding` that keeps everything in one store's
    own dicts.

    Satisfies all three structurally, with nothing declared — `02` → *Capability is derived,
    never declared*. Construct one per test; it is cheap and sharing one is the defect this
    class's module docstring describes. `bind_target` returns a second `MemoryStore` sharing the
    first's state rather than a different kind of object, so every capability this class has
    stays reachable through a bound handle too.
    """

    version: ClassVar[str] = STORE_CONTRACT_VERSION

    def __init__(
        self, *, _state: _StoreState | None = None, _bound: TargetName | None = None
    ) -> None:
        self._state = _state if _state is not None else _StoreState()
        #: `None` on an unbound handle — see `_active_target`. Set once explicit targets are
        #: bound through `bind_target`, and never changes after that: the name was given by name.
        self._bound = _bound
        #: An unbound handle's own resolution of "live", read once and held — Q-C, ledger 34.3.
        self._resolved: TargetName | None = None

    def _active_target(self) -> TargetName:
        """The target this handle's storage operations read and write.

        Explicit for a bound handle. For an unbound one, `self._state.live` is read the first
        time any storage operation reaches this method and cached from then on, so a promote
        that happens after this handle has already touched storage does not retarget it —
        `test_an_unbound_handle_holds_the_target_that_was_live_when_it_first_read`.
        """
        if self._bound is not None:
            return self._bound
        if self._resolved is None:
            self._resolved = self._state.live
        return self._resolved

    def _writable(self) -> _TargetData:
        return self._state.data.setdefault(self._active_target(), _TargetData())

    def _readable(self) -> _TargetData:
        return self._state.data.get(self._active_target()) or _TargetData()

    # -- NodeStore ---------------------------------------------------------------------------

    async def add(self, nodes: Sequence[Node]) -> None:
        """Store each node, **merging** `lineage.sources` when the id is already present.

        A node id is a content digest, so two documents producing byte-identical content produce
        one id. Replacing rather than merging would drop the first document's claim on it, and
        `delete_source` would then take a node another document still produces — which is the
        defect `02` → *Deletion is idempotent and resumable* and the kit's own merge check exist
        for.
        """
        target = self._writable()
        for node in nodes:
            arrival = node.lineage.sources
            existing = target.nodes.get(node.id)
            productions = target.productions.setdefault(node.id, [])
            if arrival not in productions:
                productions.append(arrival)
            if existing is None:
                target.nodes[node.id] = node
                continue
            merged = existing.lineage.sources | arrival
            target.nodes[node.id] = existing.model_copy(
                update={"lineage": existing.lineage.model_copy(update={"sources": merged})}
            )

    async def flush(self) -> None:
        """Nothing is buffered, so this is a real no-op rather than an unimplemented one.

        `02` → *Durability is a guarantee, not a call*: the runner flushes every stage that has the
        method, and `flush` is documented as idempotent, so a store with nothing to flush answers
        honestly by doing nothing.
        """
        return

    async def count(self) -> int:
        """Count the nodes stored.

        Returns:
            How many nodes this store holds.
        """
        return len(self._readable().nodes)

    async def get(self, ids: Sequence[NodeId]) -> Sequence[Node]:
        """The nodes that exist, in the order asked for.

        An id this store does not hold is absent from the answer rather than `None` in it, so a
        caller's `len()` means what it looks like.
        """
        nodes = self._readable().nodes
        return tuple(nodes[node_id] for node_id in ids if node_id in nodes)

    async def scan(self, cursor: Cursor | None = None) -> Page[Node]:
        """Every node in one page.

        Paging exists for stores that cannot hold a corpus in memory, and this one is defined by
        being unable to hold one that large in the first place.
        """
        del cursor
        return Page[Node](items=tuple(self._readable().nodes.values()), next_cursor=None)

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        """The pipeline position: store what arrives and pass it through unchanged."""
        del ctx
        await self.add(payload)
        return Produced(value=payload)

    async def put_source(self, record: SourceRecord) -> None:
        """Write or replace one source's record.

        Args:
            record: The record to store under its own id.
        """
        self._writable().sources[record.id] = record

    async def get_source(self, source_id: SourceId) -> SourceRecord | None:
        """Read one source's record.

        Args:
            source_id: The source to read.

        Returns:
            The record, or `None` when none is stored.
        """
        return self._readable().sources.get(source_id)

    async def list_sources(self) -> Sequence[SourceRecord]:
        """Read every source record this store holds.

        Returns:
            Every source record.
        """
        return tuple(self._readable().sources.values())

    async def delete_source(self, source_id: SourceId) -> Removed:
        """Remove this document's claim, and the node only when no document still produces it.

        **Narrowing rather than deleting is the whole of G20**, and getting it wrong here would
        make this store disagree with both real backends on the one behaviour the conformance kit
        spends five checks on: a node two documents each produced whole survives the deletion of
        either, with its `sources` recomputed from what is left.
        """
        target = self._writable()
        narrowed = 0
        removed: list[NodeId] = []
        for node_id, node in list(target.nodes.items()):
            productions = target.productions.get(node_id, [node.lineage.sources])
            surviving = [p for p in productions if source_id not in p]
            if len(surviving) == len(productions):
                continue
            if not surviving:
                removed.append(node_id)
                continue
            target.productions[node_id] = surviving
            remaining: frozenset[SourceId] = frozenset[SourceId]().union(*surviving)
            target.nodes[node_id] = node.model_copy(
                update={"lineage": node.lineage.model_copy(update={"sources": remaining})}
            )
            narrowed += 1
        for node_id in removed:
            del target.nodes[node_id]
            target.productions.pop(node_id, None)
        target.sources.pop(source_id, None)
        return Removed(source_id=source_id, node_count=len(removed), narrowed_count=narrowed)

    # -- VectorSearch ------------------------------------------------------------------------

    async def search_vector(
        self, vector: Vector, top_k: int, filter: Filter | None = None
    ) -> Sequence[Scored[Node]]:
        """The `top_k` nearest nodes by cosine, computed over every stored vector.

        **A filter is refused rather than ignored.** This store satisfies no `MetadataFilter`, so
        it cannot narrow — and silently returning unfiltered results would be the plausible answer
        against the wrong data that `CLAUDE.md` puts above a crash. A caller reaches this only by
        passing one deliberately: `weft_store.conformance.checks_for` never offers a filter check
        to a store without the capability.

        **A query of the wrong width is refused too.** `zip(strict=True)` would raise on its own,
        but with a message about iterables rather than about vectors, and a store that answered
        anyway by truncating would rank confidently on a comparison it never made.
        """
        if filter is not None:
            raise ValueError(
                "MemoryStore satisfies no MetadataFilter, so it cannot narrow a vector search — "
                "it would have to ignore the filter and return results that look filtered and are "
                "not. Use a store that implements `matching`, or drop the filter."
            )
        stored = [node for node in self._readable().nodes.values() if node.embedding is not None]
        for node in stored:
            embedding = node.embedding
            if embedding is not None and len(embedding.values) != len(vector.values):
                raise ValueError(
                    f"the query vector's width is {len(vector.values)} and a stored node's is "
                    f"{len(embedding.values)}; cosine over two widths is not a similarity"
                )
        scored = [
            Scored(value=node, score=_cosine(vector.values, node.embedding.values))
            for node in stored
            if node.embedding is not None
        ]
        scored.sort(key=lambda hit: (-hit.score, hit.value.id))
        return tuple(scored[:top_k])

    # -- TargetHolding -------------------------------------------------------------------------

    async def target_catalogue(self) -> TargetCatalogue:
        """Read every target this store holds.

        Returns:
            The targets, which one is live, which was live before, and the last promotion.
        """
        records = tuple(
            sorted(
                (
                    TargetRecord(name=name, embedding=data.embedding)
                    for name, data in self._state.data.items()
                ),
                key=lambda record: record.name,
            )
        )
        return TargetCatalogue(
            live=self._state.live,
            previous=self._state.previous,
            targets=records,
            promotion=self._state.promotion,
        )

    async def bind_target(self, target: TargetName) -> Self:
        """A second handle onto this store's own state, bound to `target` — never `self`.

        Binding creates nothing in the catalogue; the target is created by the handle's first
        write (`add` or `put_source`), through `_writable`'s own `setdefault`.
        """
        return type(self)(_state=self._state, _bound=target)

    async def claim_embedding(self, identity: EmbeddingIdentity) -> EmbeddingIdentity:
        """Record `identity` against this handle's target, unless one is recorded.

        Args:
            identity: What embedded the vectors about to be written.

        Returns:
            The identity the target holds, which is the earlier one if already claimed.
        """
        target = self._writable()
        if target.embedding is None:
            target.embedding = identity
        return target.embedding

    async def promote(self, promotion: Promotion) -> TargetCatalogue:
        """Make the promoted target live, recording the previous one for rollback.

        Promoting the target that is already live is a no-op: `previous` stays what it was
        (never rewritten to the already-live target), so a converging re-run after a crash leaves
        the rollback an operator needs intact.
        """
        state = self._state
        if promotion.target not in state.data:
            raise UnknownTargetError(promotion.target, valid_options=tuple(sorted(state.data)))
        if promotion.target == state.live:
            return await self.target_catalogue()
        state.previous = state.live
        state.live = TargetName(promotion.target)
        state.promotion = promotion
        return await self.target_catalogue()

    async def rollback(self) -> TargetCatalogue:
        """Swap the live target with the previous one.

        Returns:
            The catalogue after the rollback.

        Raises:
            NoPreviousTargetError: No target was live before this one.
        """
        state = self._state
        if state.previous is None:
            raise NoPreviousTargetError(state.live)
        state.live, state.previous = state.previous, state.live
        return await self.target_catalogue()

    async def drop_target(self, target: TargetName) -> None:
        """Delete `target` and everything stored in it.

        Args:
            target: The target to drop.

        Raises:
            TargetInUseError: The target is live or previous.
            UnknownTargetError: The target is not in the catalogue.
        """
        state = self._state
        if target == state.live or target == state.previous:
            raise TargetInUseError(target)
        if target not in state.data:
            raise UnknownTargetError(target, valid_options=tuple(sorted(state.data)))
        del state.data[target]
