"""`InMemoryNodeStore`: a stranger's whole store family over one process-lifetime dict.

`InMemoryNodeStore` — a stranger's whole store family: `NodeStore`, `VectorSearch`,
`TextSearch`, `MetadataFilter`, `SourceDeletable`, `Reconcilable`, `TargetHolding` (ledger
task **34.3**), `GenerationHolding` (ledger task **43.14**), `SingleWriter` (ledger task
**43.18**) and, since ledger task **43.22**, `GenerationCarrying`, all ten, over one
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
this is the "ephemeral in-memory store" `docs/internal/build-ledger.md` task 2.6 names as still open
and unclaimed by any ledger task; this pack is not that store (it lives outside the
workspace, on purpose — see the module's own `pyproject.toml`), but it is a genuine,
independently-arrived-at instance of the same shape.

**`matching` reuses `weft_store.fields`, never re-derives its own field vocabulary.** `02`
§1's own argument for that module — "two translators start from one parse" — applies to a
third translator exactly as it does to a second: `field_for` is the one call that decides
what a `Filter.field` reaches on a `Node` and which operators it admits, so this store
disagrees with pgvector and Qdrant about a filter's meaning in no more ways than they
already disagree with each other, which is none.

**`GenerationHolding`, task 43.14, is `TargetHolding`'s shape run again one layer down.**
Every target already keeps its own nodes; here it also keeps its own generation catalogue
and, per node, the set of generation ids that wrote it — `""` standing for a write made
through an unbound handle, the base marker `pgvector` and Qdrant both use so a legacy or
never-generationed node reads as "no generation wrote this" rather than "wrote by nothing
visible". A handle resolves which generations it can see at the same moment it resolves its
target — first storage touch, cached for its lifetime, so a publish that happens afterwards
is invisible to work already in flight, exactly as a promote already is under `TargetHolding`.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import ClassVar, Self
from uuid import uuid4

from weft_kernel.context import Context
from weft_kernel.payload import Node, NodeId, Outcome, Produced, SourceId, Vector
from weft_kernel.runner import Lifetime
from weft_store.contract import (
    DEFAULT_TARGET,
    Cursor,
    EmbeddingIdentity,
    Filter,
    FilterOp,
    GenerationId,
    GenerationRecord,
    GenerationStatus,
    NoPreviousTargetError,
    NotAPublishedGenerationError,
    NotAPublishedMemberError,
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
    UnknownGenerationError,
    UnknownTargetError,
    WriterBusyError,
    WriterClaim,
)
from weft_store.fields import FieldKind, FieldPath, field_for

#: The base marker — a node written through an unbound handle carries this in its own
#: generation set, and it is always in a handle's visible set, so a base write is visible to
#: everyone whatever generations they can or cannot see.
_BASE = ""


class _Target:
    """One target's own nodes, source records and generation catalogue.

    One target's own nodes, source records and generation catalogue — never shared
    across targets, on the same footing as a pgvector schema or a Qdrant collection prefix.
    """

    def __init__(self) -> None:
        self.nodes: dict[NodeId, Node] = {}
        self.sources: dict[SourceId, SourceRecord] = {}
        self.embedding: EmbeddingIdentity | None = None
        self.generations: dict[GenerationId, GenerationRecord] = {}
        #: The generation ids that wrote each node — `_BASE` for an unbound write, merged by
        #: union on every further write, exactly as `sources` is merged on `add`.
        self.node_generations: dict[NodeId, frozenset[str]] = {}
        #: `SingleWriter`, ledger task **43.18** — this target's own claim, or `None`. Held
        #: on the target so every handle `bind_target` hands back onto it sees the same claim.
        self.writer: WriterClaim | None = None


class _Catalogue:
    """What every handle onto one `InMemoryNodeStore()` shares — task **34.3**.

    `default` exists from construction, live, with nothing previous and nothing promoted —
    `check_a_fresh_store_has_one_live_target_named_default`.
    """

    def __init__(self) -> None:
        self.targets: dict[TargetName, _Target] = {DEFAULT_TARGET: _Target()}
        self.live: TargetName = DEFAULT_TARGET
        self.previous: TargetName | None = None
        self.promotion: Promotion | None = None


class InMemoryNodeStore:
    """The whole store family over a plain `dict`.

    Satisfies `weft_store.contract.NodeStore`, `VectorSearch`, `TextSearch`, `MetadataFilter`,
    `SourceDeletable`, `Reconcilable` and `TargetHolding` structurally — this class never imports
    any of them. `SourceDeletable` needed no code at all: `delete_source` was already here, which is
    what "capability is derived, never declared" buys a pack author. `Reconcilable` grew `estimate`
    at task 5.1c, a major bump for every implementer per G9 — this stranger's own update is one
    small, honest method, not a rewrite.

    **`TargetHolding`, task 34.3, costs one more dict, keyed by target name.** Every other
    method above already worked against one process's own state; here that state is split
    per target, and `bind_target` hands back a second `InMemoryNodeStore` sharing the same
    catalogue rather than a different kind of object, so every other capability stays
    reachable through a bound handle too. An unbound handle reads `live` the first time any
    storage method touches it and holds that answer for its own lifetime, so a promote that
    happens afterwards does not retarget a handle already in use.

    **`GenerationHolding`, task 43.14, follows the identical shape one level down**, inside
    whichever target a handle resolves to: `bind_generation` hands back a third kind of bound
    handle, sharing the same catalogue and the same target settings as the handle it was
    asked from, and a handle's visible generation set is read once, at the same moment its
    target is, and held for its own lifetime.
    """

    lifetime: ClassVar[Lifetime] = Lifetime.PROCESS

    def __init__(
        self,
        config: object = None,
        *,
        _catalogue: _Catalogue | None = None,
        _bound: TargetName | None = None,
        _bound_generation: GenerationId | None = None,
    ) -> None:
        del config
        self._catalogue = _catalogue if _catalogue is not None else _Catalogue()
        #: `None` on an unbound handle — see `_active_target`. Set once by `bind_target` and
        #: never changed after that: the name was given by name.
        self._bound = _bound
        #: An unbound handle's own resolution of "live", read once and held.
        self._resolved: TargetName | None = None
        #: `None` on a handle not bound to a generation. Set once by `bind_generation` and
        #: never changed after that.
        self._bound_generation = _bound_generation
        #: This handle's own visible generation set, read once — see `_active_target`.
        self._visible: frozenset[str] | None = None
        #: `SingleWriter` — the claim *this handle* placed, or `None`. Compared against the
        #: target's own `writer` on `release_writer`, on `pgvector`'s own footing: releasing
        #: a claim this handle never placed is a no-op, never another holder's.
        self._claimed_writer: WriterClaim | None = None

    def _active_target(self) -> TargetName:
        """The target this handle's storage operations read and write.

        Explicit for a bound handle. For an unbound one, the catalogue's own `live` is read
        the first time any storage operation reaches this method and cached from then on.
        This is also the moment `self._visible` — the generation ids this handle can see —
        is resolved and cached, on `TargetHolding`'s own footing (`34.3`'s Q-C, applied again
        at task `43.14`): one operation never mixes what two different reads of the
        catalogue would have shown it.
        """
        if self._bound is not None:
            target = self._bound
        else:
            if self._resolved is None:
                self._resolved = self._catalogue.live
            target = self._resolved
        if self._visible is None:
            state = self._catalogue.targets.get(target)
            published = _newest_published_per_layer(state.generations if state is not None else {})
            visible = {_BASE, *published}
            if self._bound_generation is not None:
                visible.add(self._bound_generation)
            self._visible = frozenset(visible)
        return target

    def _writable(self) -> _Target:
        return self._catalogue.targets.setdefault(self._active_target(), _Target())

    def _readable(self) -> _Target:
        return self._catalogue.targets.get(self._active_target()) or _Target()

    def _visible_node(self, target: _Target, node_id: NodeId) -> bool:
        """Whether `node_id` is a member of a generation this handle can see.

        A node no generation ever wrote has no entry at all — always visible, task 43.14's
        own rule for content nothing gated. Otherwise visible exactly when its membership
        and this handle's visible set share a generation, `_BASE` included, which is why a
        write through an unbound handle is visible under every set of generations.
        """
        membership = target.node_generations.get(node_id)
        if not membership:
            return True
        visible = self._visible
        return visible is not None and bool(membership & visible)

    # -- NodeStore -----------------------------------------------------------------------

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        """Store `payload` and pass it on unchanged.

        Args:
            payload: The nodes to store.
            ctx: Unused.

        Returns:
            `Produced` carrying `payload`.
        """
        del ctx
        await self.add(payload)
        return Produced(value=payload)

    async def add(self, nodes: Sequence[Node]) -> None:
        """Write `nodes` into this handle's target, as members of its bound generation.

        Args:
            nodes: The nodes to write; one already held under the same id is replaced.
        """
        target = self._writable()
        marker = self._bound_generation if self._bound_generation is not None else _BASE
        for node in nodes:
            target.nodes[node.id] = node
            target.node_generations[node.id] = target.node_generations.get(node.id, frozenset()) | {
                marker
            }

    async def flush(self) -> None:
        """Flush buffered writes; this store buffers none."""
        # Every write above is already durable within this process — nothing buffered.
        return

    async def get(self, ids: Sequence[NodeId]) -> Sequence[Node]:
        """Read back the held nodes among `ids`.

        Args:
            ids: The node ids to look up.

        Returns:
            The nodes found, in `ids` order; an id this target does not hold is absent.
        """
        nodes = self._readable().nodes
        return tuple(nodes[node_id] for node_id in ids if node_id in nodes)

    async def delete_source(self, source_id: SourceId) -> Removed:
        """Delete every node from `source_id`, and its source record.

        Args:
            source_id: The source to remove.

        Returns:
            The source removed and how many nodes went with it.
        """
        target = self._writable()
        record = target.sources.get(source_id)
        if record is not None:
            target.sources[source_id] = record.model_copy(update={"status": SourceStatus.DELETING})
        removed = tuple(
            node_id for node_id, node in target.nodes.items() if source_id in node.lineage.sources
        )
        for node_id in removed:
            del target.nodes[node_id]
        target.sources.pop(source_id, None)
        return Removed(source_id=source_id, node_count=len(removed))

    async def supersede(self, old: NodeId, new: Node) -> None:
        """`NodeSupersedable` — replace one node with another, written from outside the workspace.

        Fitness function 9 clause (c) is why this method is here rather than only on the two
        first-party backends: a capability the built-ins have and a stranger cannot reach is
        requirement 4's failure, and this pack is the stranger.

        The ordering is the contract and is what a real backend must also do — **write `new`
        first, delete `old` second** — so an interruption leaves a duplicate, which `reconcile`
        can find, and never a hole, which nothing can. Refuse first, changing nothing, when the
        replacement covers fewer sources than the node it replaces.
        """
        target = self._writable()
        stored = target.nodes.get(old)
        if stored is not None and not stored.lineage.sources <= new.lineage.sources:
            dropped = ", ".join(sorted(stored.lineage.sources - new.lineage.sources))
            raise SupersedeNarrowsSourcesError(
                f"cannot supersede node {old} with a replacement that drops source(s) "
                f"{dropped}. A superseding node must carry at least the sources of the node "
                f"it replaces."
            )
        target.nodes[new.id] = new
        if old != new.id:
            target.nodes.pop(old, None)

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
        target = self._writable()
        removed = 0
        examined = 0
        for source_id in tuple(self._tombstoned()):
            gone = tuple(
                node_id
                for node_id, node in target.nodes.items()
                if source_id in node.lineage.sources
            )
            for node_id in gone:
                del target.nodes[node_id]
            target.sources.pop(source_id, None)
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
            for source_id, record in self._readable().sources.items()
            if record.status is SourceStatus.DELETING
        )

    async def scan(self, cursor: Cursor | None = None) -> Page[Node]:
        """Return every held node as one page.

        Args:
            cursor: Ignored; there is only ever one page.

        Returns:
            A single page holding the whole target.
        """
        del cursor  # a single in-memory page holds the whole corpus — no real pagination
        return Page(items=tuple(self._readable().nodes.values()))

    async def count(self) -> int:
        """Count the nodes this handle's target holds.

        Returns:
            The number of nodes.
        """
        return len(self._readable().nodes)

    async def put_source(self, record: SourceRecord) -> None:
        """Write one source record, replacing any held under the same id.

        Args:
            record: The record to write.
        """
        self._writable().sources[record.id] = record

    async def get_source(self, source_id: SourceId) -> SourceRecord | None:
        """Read one source record.

        Args:
            source_id: The source to look up.

        Returns:
            The record, or `None` when this target holds none for `source_id`.
        """
        return self._readable().sources.get(source_id)

    async def list_sources(self) -> Sequence[SourceRecord]:
        """List every source record this handle's target holds.

        Returns:
            Every held source record.
        """
        return tuple(self._readable().sources.values())

    # -- VectorSearch ----------------------------------------------------------------------

    async def search_vector(
        self, vector: Vector, top_k: int, filter: Filter | None = None
    ) -> Sequence[Scored[Node]]:
        """Rank the visible embedded nodes by cosine similarity to `vector`.

        Args:
            vector: The query vector.
            top_k: How many results to return at most.
            filter: A metadata filter every result must match, or `None`.

        Returns:
            The best `top_k` nodes, highest score first.
        """
        target = self._readable()
        candidates = (
            node
            for node in target.nodes.values()
            if node.embedding is not None and self._visible_node(target, node.id)
        )
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
        """Rank the visible nodes by the share of `text`'s words they contain.

        Args:
            text: The query text.
            top_k: How many results to return at most.
            filter: A metadata filter every result must match, or `None`.

        Returns:
            The best `top_k` nodes sharing at least one word, highest score first.
        """
        query_words = _words(text)
        if not query_words:
            return ()
        target = self._readable()
        candidates = [node for node in target.nodes.values() if self._visible_node(target, node.id)]
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
        """Return every visible node that matches `filter`, as one page.

        Args:
            filter: The metadata filter to apply.
            cursor: Ignored; there is only ever one page.

        Returns:
            A single page holding every match.
        """
        del cursor  # see `scan` — no real pagination in this example store
        target = self._readable()
        return Page(
            items=tuple(
                node
                for node in target.nodes.values()
                if self._visible_node(target, node.id) and _matches(node, filter)
            )
        )

    # -- TargetHolding -----------------------------------------------------------------------

    async def target_catalogue(self) -> TargetCatalogue:
        """Describe every target, and which are live and previous.

        Returns:
            The catalogue, its targets sorted by name.
        """
        records = tuple(
            sorted(
                (
                    TargetRecord(name=name, embedding=target.embedding)
                    for name, target in self._catalogue.targets.items()
                ),
                key=lambda record: record.name,
            )
        )
        return TargetCatalogue(
            live=self._catalogue.live,
            previous=self._catalogue.previous,
            targets=records,
            promotion=self._catalogue.promotion,
        )

    async def bind_target(self, target: TargetName) -> Self:
        """A second handle onto this store's own catalogue, bound to `target` — never `self`.

        Binding creates nothing in the catalogue; the target is created by the handle's first
        write (`add` or `put_source`), through `_writable`'s own `setdefault`.
        """
        return type(self)(_catalogue=self._catalogue, _bound=target)

    async def claim_embedding(self, identity: EmbeddingIdentity) -> EmbeddingIdentity:
        """Record `identity` as this target's embedding, unless one is already recorded.

        Args:
            identity: The embedding this writer means to use.

        Returns:
            The target's recorded embedding, which a caller compares against its own.
        """
        target = self._writable()
        if target.embedding is None:
            target.embedding = identity
        return target.embedding

    async def promote(self, promotion: Promotion) -> TargetCatalogue:
        """Make `promotion.target` the live target, keeping the old live one as `previous`.

        Promoting the target that is already live is a no-op: `previous` is never rewritten to
        the already-live target, so a converging re-run after a crash leaves the rollback an
        operator needs intact.
        """
        catalogue = self._catalogue
        if promotion.target not in catalogue.targets:
            raise UnknownTargetError(
                promotion.target, valid_options=tuple(sorted(catalogue.targets))
            )
        if promotion.target == catalogue.live:
            return await self.target_catalogue()
        catalogue.previous = catalogue.live
        catalogue.live = TargetName(promotion.target)
        catalogue.promotion = promotion
        return await self.target_catalogue()

    async def rollback(self) -> TargetCatalogue:
        """Swap the live and previous targets.

        Returns:
            The catalogue after the swap.

        Raises:
            NoPreviousTargetError: There is no previous target to roll back to.
        """
        catalogue = self._catalogue
        if catalogue.previous is None:
            raise NoPreviousTargetError(catalogue.live)
        catalogue.live, catalogue.previous = catalogue.previous, catalogue.live
        return await self.target_catalogue()

    async def drop_target(self, target: TargetName) -> None:
        """Forget `target` and everything it holds.

        Args:
            target: The target to drop.

        Raises:
            TargetInUseError: `target` is live or previous.
            UnknownTargetError: No target has that name.
        """
        catalogue = self._catalogue
        if target == catalogue.live or target == catalogue.previous:
            raise TargetInUseError(target)
        if target not in catalogue.targets:
            raise UnknownTargetError(target, valid_options=tuple(sorted(catalogue.targets)))
        del catalogue.targets[target]

    # -- GenerationHolding -------------------------------------------------------------------

    async def open_generation(self, layer: str) -> GenerationRecord:
        """Open a new, building generation for `layer` in this handle's target.

        Args:
            layer: The layer the generation belongs to.

        Returns:
            The new generation's record.
        """
        target = self._writable()
        record = GenerationRecord(
            id=GenerationId(f"g-{uuid4().hex[:12]}"),
            layer=layer,
            status=GenerationStatus.BUILDING,
            opened_at=datetime.now(UTC),
        )
        target.generations[record.id] = record
        return record

    async def bind_generation(self, generation: GenerationId) -> Self:
        """A new handle on the same catalogue and target settings, bound to `generation`.

        A new handle on the same catalogue and the same target settings as this one,
        bound to `generation` — `bind_target`'s own construction is the model.
        """
        target_name = self._active_target()
        state = self._catalogue.targets.get(target_name)
        if state is None or generation not in state.generations:
            valid = tuple(sorted(state.generations)) if state is not None else ()
            raise UnknownGenerationError(generation, valid_options=valid)
        return type(self)(
            _catalogue=self._catalogue, _bound=self._bound, _bound_generation=generation
        )

    async def publish_generation(self, generation: GenerationId) -> GenerationRecord:
        """Mark `generation` published.

        Args:
            generation: The generation to publish.

        Returns:
            The published record.

        Raises:
            UnknownGenerationError: This target holds no such generation.
        """
        target = self._writable()
        record = target.generations.get(generation)
        if record is None:
            raise UnknownGenerationError(
                generation, valid_options=tuple(sorted(target.generations))
            )
        published = record.model_copy(
            update={"status": GenerationStatus.PUBLISHED, "published_at": datetime.now(UTC)}
        )
        target.generations[generation] = published
        return published

    async def retract_generation(self, generation: GenerationId) -> Removed:
        """Delete the nodes only `generation` wrote, strip it from the rest, and forget it.

        Args:
            generation: The generation to retract.

        Returns:
            How many nodes were deleted.

        Raises:
            UnknownGenerationError: This target holds no such generation.
        """
        target = self._writable()
        if generation not in target.generations:
            raise UnknownGenerationError(
                generation, valid_options=tuple(sorted(target.generations))
            )
        return Removed(source_id=SourceId(generation), node_count=_retract(target, generation))

    async def generations(self) -> tuple[GenerationRecord, ...]:
        """List this target's generations, oldest first.

        Returns:
            Every generation record, ordered by when it was opened.
        """
        records = self._readable().generations.values()
        return tuple(sorted(records, key=lambda record: (record.opened_at, record.id)))

    # -- GenerationCarrying ------------------------------------------------------------------

    async def carry_forward(self, into: GenerationId, node_ids: Sequence[NodeId]) -> int:
        """Add `into` to each named node's generation membership, changing nothing else.

        `GenerationCarrying`, ledger task **43.22** — `into` joins each node's membership and
        nothing else about the node changes. Every id is checked before any is carried.
        """
        target = self._writable()
        if into not in target.generations:
            raise UnknownGenerationError(into, valid_options=tuple(sorted(target.generations)))
        published = {
            generation
            for generation, record in target.generations.items()
            if record.status is GenerationStatus.PUBLISHED
        }
        requested = tuple(dict.fromkeys(node_ids))
        refused = [
            node_id
            for node_id in requested
            if node_id not in target.nodes
            or not target.node_generations.get(node_id, frozenset()) & published
        ]
        if refused:
            raise NotAPublishedMemberError(into, node_ids=refused)
        for node_id in requested:
            target.node_generations[node_id] = target.node_generations[node_id] | {into}
        return len(requested)

    # -- GenerationWithdrawing ---------------------------------------------------------------

    async def withdraw_generation(self, generation: GenerationId) -> GenerationRecord:
        """Mark a published generation withdrawn, changing nothing else.

        `GenerationWithdrawing`, repair **R43.29** — the record is marked and nothing else
        changes, so a handle whose visible set already holds `generation` keeps reading it.
        """
        target = self._writable()
        record = target.generations.get(generation)
        if record is None:
            raise UnknownGenerationError(
                generation, valid_options=tuple(sorted(target.generations))
            )
        if record.status is not GenerationStatus.PUBLISHED:
            raise NotAPublishedGenerationError(
                generation,
                status=record.status,
                valid_options=tuple(
                    sorted(
                        held.id
                        for held in target.generations.values()
                        if held.status is GenerationStatus.PUBLISHED
                    )
                ),
            )
        withdrawn = record.model_copy(update={"status": GenerationStatus.WITHDRAWN})
        target.generations[generation] = withdrawn
        return withdrawn

    async def reclaim_withdrawn(self, layer: str) -> Removed:
        """Retract every withdrawn generation of `layer`.

        Args:
            layer: The layer whose withdrawn generations are reclaimed.

        Returns:
            How many nodes were deleted across them.
        """
        target = self._writable()
        doomed = [
            record.id
            for record in target.generations.values()
            if record.layer == layer and record.status is GenerationStatus.WITHDRAWN
        ]
        removed = sum(_retract(target, generation) for generation in doomed)
        return Removed(source_id=SourceId(layer), node_count=removed)

    # -- SingleWriter ------------------------------------------------------------------------

    async def claim_writer(self, writer: WriterClaim) -> None:
        """Claim this target for `writer`, refusing while another writer holds it.

        `SingleWriter`, ledger task **43.18** — the claim lives on the target, which every
        handle `bind_target` hands back onto it shares, so a second handle on the same target
        sees the first's claim immediately.
        """
        target = self._writable()
        if target.writer is not None:
            raise WriterBusyError(target.writer)
        target.writer = writer
        self._claimed_writer = writer

    async def release_writer(self) -> None:
        """Release this handle's writer claim, leaving any other writer's claim in place."""
        target = self._writable()
        if target.writer is not None and target.writer == self._claimed_writer:
            target.writer = None
        self._claimed_writer = None


def _retract(target: _Target, generation: GenerationId) -> int:
    """Delete the nodes only `generation` wrote, strip it from the rest, and forget it.

    Delete the nodes only `generation` wrote, strip it from the rest, and forget it —
    `retract_generation`'s work, and `reclaim_withdrawn`'s per generation. Returns how many
    nodes were deleted.
    """
    doomed = frozenset({generation})
    removed_ids = tuple(
        node_id for node_id, membership in target.node_generations.items() if membership == doomed
    )
    for node_id in removed_ids:
        target.nodes.pop(node_id, None)
        target.node_generations.pop(node_id, None)
    for node_id, membership in list(target.node_generations.items()):
        if generation in membership:
            target.node_generations[node_id] = membership - doomed
    del target.generations[generation]
    return len(removed_ids)


def _newest_published_per_layer(
    generations: dict[GenerationId, GenerationRecord],
) -> frozenset[GenerationId]:
    """Each layer's newest published generation — repair **R43.25**.

    A tie on `published_at` goes to the one opened later, which is the catalogue's insertion order.
    """
    newest: dict[str, GenerationRecord] = {}
    for record in generations.values():
        if record.status is not GenerationStatus.PUBLISHED or record.published_at is None:
            continue
        held = newest.get(record.layer)
        if held is None or held.published_at is None or record.published_at >= held.published_at:
            newest[record.layer] = record
    return frozenset(record.id for record in newest.values())


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
