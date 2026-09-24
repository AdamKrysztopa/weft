"""Doubles for a corpus-scoped layer build that can be interrupted — ledger task **43.20**.

The store is `tests/unit/weft_cli/test_corpus_layers.py`'s own `_GenerationStore`, copied: a bound
handle writes into its generation and sees it, every other handle sees only what was published
when it first touched storage. Two things differ from that copy: each generation opens later
than the one before it, so "the newest `BUILDING` generation" names one; and the filter reads
`EQ`, `OR` and `CONTAINS` over `ext.<namespace>.<field>`, so a build reading back what it kept is
not refused by the double rather than by the code.

`ScriptedModel` is an `LLMProvider` that counts the requests it is sent and, on the request
named by `trip`, cancels the task named by `victim` and waits, which is what Ctrl-C does to
`weft index`: the cancellation arrives inside an in-flight model call.
"""

import asyncio
import hashlib
from collections.abc import AsyncIterator, Callable, Sequence
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import ClassVar, Self

from weft_chunk import Chunker
from weft_chunk.fixed_size import FixedSizeChunker
from weft_cli.ingest import IndexResult, run_index
from weft_embed import Embedder
from weft_embed.hash_embedder import HashEmbedder
from weft_engine.llm_roles import LLMSection
from weft_extract import Extractor
from weft_extract.text import TextExtractor
from weft_index import Expander
from weft_index.payload import RaptorFacts
from weft_index.prompts import SUMMARIZE_CLUSTER_NAME, SummarizeClusterPrompt
from weft_index.raptor import RaptorSummarizer
from weft_kernel.context import Context
from weft_kernel.payload import Node, NodeId, Outcome, Produced, SourceId
from weft_kernel.registry import Registry
from weft_llm.contract import LLMProvider
from weft_llm.payload import Completion, Conversation
from weft_llm.roles import LLMRoles, RoleMapping
from weft_prompts.contract import Prompt
from weft_store import NodeStore
from weft_store.contract import (
    Cursor,
    Filter,
    FilterOp,
    GenerationId,
    GenerationRecord,
    GenerationStatus,
    Page,
    Removed,
    SourceRecord,
    UnknownGenerationError,
)

LAYER = "enrich-with-tree"
LEAVES = 8
#: `cluster_size: 2` over `LEAVES` leaves, with a threshold every pair clears.
CLUSTERS = 4
TERSE_PROMPT = "summarize-cluster-terse"

_PAGE = 2
_FIRST_OPENED = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)


def _values(node: Node, field: str) -> tuple[str, ...] | None:
    """`field`'s value on `node` as strings — every member of a sequence field, one otherwise."""
    if field == "id":
        return (str(node.id),)
    if field == "lineage.sources":
        return tuple(str(source) for source in node.lineage.sources)
    if field == "lineage.parents":
        return tuple(str(parent) for parent in node.lineage.parents)
    head, namespace, *rest = field.split(".")
    if head != "ext" or len(rest) != 1:
        raise AssertionError(f"the build read a field this double lacks: {field}")
    held = node.ext.get(namespace)
    found: object = getattr(held, rest[0], None) if held is not None else None
    return None if found is None else (str(found),)


def holds(node: Node, filter: Filter) -> bool:
    if filter.op is FilterOp.AND:
        return all(holds(node, clause) for clause in filter.clauses)
    if filter.op is FilterOp.OR:
        return any(holds(node, clause) for clause in filter.clauses)
    if filter.op is FilterOp.NOT:
        return not holds(node, filter.clauses[0])
    return _holds_field(node, filter)


def _holds_field(node: Node, filter: Filter) -> bool:
    if filter.field is None:
        raise AssertionError(f"the build used an operator this double lacks: {filter}")
    if filter.op is FilterOp.EXISTS:
        _, namespace, *_ = filter.field.split(".")
        return namespace in node.ext
    found = set(_values(node, filter.field) or ())
    value = filter.value
    wanted = {str(item) for item in value} if isinstance(value, tuple) else {str(value)}
    if filter.op is FilterOp.IN:
        return bool(found & wanted)
    if filter.op in (FilterOp.EQ, FilterOp.CONTAINS):
        return bool(wanted) and wanted <= found
    raise AssertionError(f"the build used an operator this double lacks: {filter}")


class State:
    """What every handle onto one store shares: nodes, records, generations, members."""

    def __init__(self) -> None:
        self.nodes: dict[NodeId, Node] = {}
        self.members: dict[NodeId, set[str]] = {}
        self.records: dict[SourceId, SourceRecord] = {}
        self.generations: dict[GenerationId, GenerationRecord] = {}
        self.adds: list[tuple[Node, ...]] = []
        self.opened = 0


class GenerationStore:
    """`test_corpus_layers._GenerationStore`, `GenerationHolding` implemented whole (`L28.20`)."""

    def __init__(self, state: State | None = None, generation: GenerationId | None = None) -> None:
        self._state = state if state is not None else State()
        self._generation = generation
        self._published: frozenset[str] | None = None

    @property
    def state(self) -> State:
        return self._state

    def _touch(self) -> frozenset[str]:
        if self._published is None:
            self._published = frozenset(
                g
                for g, r in self._state.generations.items()
                if r.status is GenerationStatus.PUBLISHED
            )
        return self._published

    def _visible(self, node: Node) -> bool:
        own: set[str] = {self._generation} if self._generation else set()
        seen: frozenset[str] = self._touch() | {""} | own
        return bool(self._state.members.get(node.id, {""}) & seen)

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        await self.add(payload)
        return Produced(value=payload)

    async def add(self, nodes: Sequence[Node]) -> None:
        self._touch()
        self._state.adds.append(tuple(nodes))
        marker = self._generation or ""
        for node in nodes:
            self._state.nodes[node.id] = node
            self._state.members.setdefault(node.id, set()).add(marker)

    async def flush(self) -> None:
        return

    async def count(self) -> int:
        return len(self._state.nodes)

    async def get(self, ids: Sequence[NodeId]) -> Sequence[Node]:
        return tuple(self._state.nodes[i] for i in ids if i in self._state.nodes)

    async def scan(self, cursor: Cursor | None = None) -> Page[Node]:
        del cursor
        return Page(items=tuple(self._state.nodes.values()))

    async def delete_source(self, source_id: SourceId) -> Removed:
        doomed = [i for i, n in self._state.nodes.items() if source_id in n.lineage.sources]
        for i in doomed:
            del self._state.nodes[i]
            self._state.members.pop(i, None)
        self._state.records.pop(source_id, None)
        return Removed(source_id=source_id, node_count=len(doomed))

    async def put_source(self, record: SourceRecord) -> None:
        self._state.records[record.id] = record

    async def get_source(self, source_id: SourceId) -> SourceRecord | None:
        return self._state.records.get(source_id)

    async def list_sources(self) -> Sequence[SourceRecord]:
        return tuple(self._state.records.values())

    async def matching(self, filter: Filter, cursor: Cursor | None = None) -> Page[Node]:
        selected = sorted(
            (n for n in self._state.nodes.values() if self._visible(n) and holds(n, filter)),
            key=lambda n: n.id,
        )
        start = int(cursor) if cursor is not None else 0
        end = start + _PAGE
        return Page(
            items=tuple(selected[start:end]),
            next_cursor=Cursor(str(end)) if end < len(selected) else None,
        )

    async def open_generation(self, layer: str) -> GenerationRecord:
        self._state.opened += 1
        record = GenerationRecord(
            id=GenerationId(f"g-{self._state.opened:03d}"),
            layer=layer,
            status=GenerationStatus.BUILDING,
            opened_at=_FIRST_OPENED + timedelta(seconds=self._state.opened),
        )
        self._state.generations[record.id] = record
        return record

    def _known(self, generation: GenerationId) -> GenerationRecord:
        if generation not in self._state.generations:
            raise UnknownGenerationError(generation, valid_options=tuple(self._state.generations))
        return self._state.generations[generation]

    async def bind_generation(self, generation: GenerationId) -> Self:
        self._known(generation)
        return type(self)(self._state, generation)

    async def publish_generation(self, generation: GenerationId) -> GenerationRecord:
        record = self._known(generation).model_copy(
            update={"status": GenerationStatus.PUBLISHED, "published_at": _FIRST_OPENED}
        )
        self._state.generations[generation] = record
        return record

    async def retract_generation(self, generation: GenerationId) -> Removed:
        self._known(generation)
        doomed = [i for i, m in self._state.members.items() if m == {generation}]
        for i in doomed:
            self._state.nodes.pop(i, None)
            del self._state.members[i]
        for m in self._state.members.values():
            m.discard(generation)
        del self._state.generations[generation]
        return Removed(source_id=SourceId(generation), node_count=len(doomed))

    async def generations(self) -> tuple[GenerationRecord, ...]:
        return tuple(self._state.generations.values())


def plant_older_orphan(store: GenerationStore) -> GenerationId:
    """Plant the oldest `BUILDING` generation of `LAYER`, as an interrupted build leaves one.

    A `BUILDING` generation of `LAYER` opened before every other, as a build interrupted
    before task 43.20 would have left one.
    """
    orphan = GenerationId("g-000")
    store.state.generations[orphan] = GenerationRecord(
        id=orphan,
        layer=LAYER,
        status=GenerationStatus.BUILDING,
        opened_at=_FIRST_OPENED - timedelta(hours=1),
    )
    return orphan


def building(store: GenerationStore) -> list[GenerationRecord]:
    return [
        g
        for g in store.state.generations.values()
        if g.layer == LAYER and g.status is GenerationStatus.BUILDING
    ]


def published(store: GenerationStore) -> list[GenerationRecord]:
    return [
        g
        for g in store.state.generations.values()
        if g.layer == LAYER and g.status is GenerationStatus.PUBLISHED
    ]


def visible_summaries(store: GenerationStore) -> list[Node]:
    """Every summary a fresh handle finds: written by no generation, or by a published one."""
    seen = {
        g.id for g in store.state.generations.values() if g.status is GenerationStatus.PUBLISHED
    }
    return [
        node
        for node in store.state.nodes.values()
        if node.ext_as(RaptorFacts) is not None
        and store.state.members.get(node.id, {""}) & (seen | {""})
    ]


def kept_in(store: GenerationStore, generation: GenerationId) -> list[Node]:
    """Every summary `generation` wrote."""
    return [
        node
        for node in store.state.nodes.values()
        if node.ext_as(RaptorFacts) is not None
        and generation in store.state.members.get(node.id, set())
    ]


def memberships(summaries: Sequence[Node]) -> set[frozenset[NodeId]]:
    return {frozenset(node.lineage.parents) for node in summaries}


class ScriptedModel:
    """An `LLMProvider` that answers with a digest tagged by model and run label.

    An `LLMProvider` answering each request with a digest of it, tagged with the model that
    was asked and the run's `label`, so a stored summary says which run wrote it.
    """

    calls: ClassVar[list[str]] = []
    label: ClassVar[str] = "first"
    trip: ClassVar[int | None] = None
    victim: ClassVar[asyncio.Task[IndexResult] | None] = None
    watched: ClassVar[GenerationStore | None] = None
    building_seen: ClassVar[list[int]] = []

    def __init__(self, config: object = None) -> None:
        del config

    @classmethod
    def reset(cls) -> None:
        cls.calls = []
        cls.label = "first"
        cls.trip = None
        cls.victim = None
        cls.watched = None
        cls.building_seen = []

    @staticmethod
    def _text(conv: Conversation, *, model: str) -> str:
        asked = hashlib.sha256(conv.messages[-1].content.encode()).hexdigest()[:16]
        return f"summary {asked}, written by {model} in the {ScriptedModel.label} run"

    async def complete(
        self, conv: Conversation, *, model: str, ctx: Context
    ) -> Outcome[Completion]:
        del ctx
        text = self._text(conv, model=model)
        return Produced(value=Completion(text=text, model=model, finish_reason="stop"))

    async def stream(self, conv: Conversation, *, model: str, ctx: Context) -> AsyncIterator[str]:
        del ctx
        ScriptedModel.calls.append(model)
        if ScriptedModel.watched is not None:
            ScriptedModel.building_seen.append(len(building(ScriptedModel.watched)))
        if ScriptedModel.trip is not None and len(ScriptedModel.calls) == ScriptedModel.trip:
            assert ScriptedModel.victim is not None
            ScriptedModel.victim.cancel()
            await asyncio.Event().wait()
        yield self._text(conv, model=model)

    async def close(self) -> None:
        return


class TersePrompt(SummarizeClusterPrompt):
    """The same request under another name — what moving a layer's `prompt:` looks like."""

    name: ClassVar[str] = TERSE_PROMPT


class CountingEmbedder(HashEmbedder):
    summaries: ClassVar[int] = 0

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        CountingEmbedder.summaries += sum(
            1 for node in payload if node.ext_as(RaptorFacts) is not None
        )
        return await super().run(payload, ctx)


def _factory(store: GenerationStore, config: object) -> GenerationStore:
    del config
    return store


def registry_for(
    store: GenerationStore,
    *,
    second: GenerationStore | None = None,
    extra: Callable[[Registry], None] | None = None,
) -> Registry:
    registry = Registry()
    registry.add(Extractor, "text", TextExtractor, distribution="weft-extract")
    registry.add(Chunker, "fixed-size", FixedSizeChunker, distribution="weft-chunk")
    registry.add(Embedder, "hash", CountingEmbedder, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", partial(_factory, store), distribution="weft-store")
    if second is not None:
        registry.add(NodeStore, "second", partial(_factory, second), distribution="weft-example")
    registry.add(Expander, "raptor", RaptorSummarizer, distribution="weft-index")
    registry.add(Prompt, SUMMARIZE_CLUSTER_NAME, SummarizeClusterPrompt, distribution="weft-index")
    registry.add(Prompt, TERSE_PROMPT, TersePrompt, distribution="weft-index")
    registry.add(LLMProvider, "scripted", ScriptedModel, distribution="weft-llm")
    if extra is not None:
        extra(registry)
    return registry


def llm_section(model: str) -> LLMSection:
    return LLMSection(
        roles=LLMRoles(roles={"index": RoleMapping(provider="scripted", model=model)})
    )


def make_ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def write_corpus(project: Path, *, documents: int = LEAVES) -> Path:
    docs = project / "docs"
    docs.mkdir(exist_ok=True)
    for i in range(documents):
        (docs / f"doc{i}.txt").write_text(f"document number {i} says something of its own.")
    return docs


def write_layer(project: Path, *, prompt: str = SUMMARIZE_CLUSTER_NAME) -> None:
    (project / "pipelines").mkdir(exist_ok=True)
    (project / "pipelines" / f"{LAYER}.yaml").write_text(
        f"name: {LAYER}\n"
        "vars:\n  layer.scope: corpus\n"
        "stages:\n"
        "  - id: raptor\n"
        "    use: raptor\n"
        "    with:\n"
        "      cluster_size: 2\n"
        "      similarity_threshold: -1.0\n"
        "      max_concurrent_summaries: 1\n"
        f"      prompt: {prompt}\n"
    )


def write_two_store_base(project: Path) -> None:
    (project / "pipelines").mkdir(exist_ok=True)
    (project / "pipelines" / "index-two-stores.yaml").write_text(
        "name: index-two-stores\n"
        "stages:\n"
        "  - {id: extract, use: text}\n"
        "  - {id: chunk, use: fixed-size}\n"
        "  - {id: embed, use: hash}\n"
        "  - {id: store, use: pgvector}\n"
        "  - {id: second-store, use: second}\n"
    )


async def index(
    store: GenerationStore,
    corpus: Path,
    *,
    model: str = "m1",
    second: GenerationStore | None = None,
    extra: Callable[[Registry], None] | None = None,
) -> IndexResult:
    return await run_index(
        corpus,
        registry=registry_for(store, second=second, extra=extra),
        ctx=make_ctx(),
        llm=llm_section(model),
        pipeline="index-two-stores" if second is not None else None,
        layers=(LAYER,),
    )


async def interrupt_after(
    store: GenerationStore,
    corpus: Path,
    *,
    summaries: int,
    model: str = "m1",
    second: GenerationStore | None = None,
) -> BaseException | None:
    """Run the build, cancel it mid-summary, and return what the cancelled task raised.

    Run the build and cancel it while the model writes summary `summaries + 1`; what the
    cancelled task raised, which is `asyncio.CancelledError` when cancellation propagated.
    """
    ScriptedModel.trip = summaries + 1
    task = asyncio.create_task(index(store, corpus, model=model, second=second))
    ScriptedModel.victim = task
    try:
        await task
    except asyncio.CancelledError as cancelled:
        return cancelled
    finally:
        ScriptedModel.trip = None
        ScriptedModel.victim = None
    return None
