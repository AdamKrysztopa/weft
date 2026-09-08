"""Unit tests for `weft_index.adrap`.

Mirrors `packages/weft-rag/src/weft_index/adrap.py`. Ledger **10.14**: "a newly indexed
document joins the existing tree rather than founding a second one, and no query ever returns
both the old and the new summary of one cluster."

**Both halves of that sentence are asserted through the store, not through a call log.**
"Joins the existing tree" is a fact about which node the new leaf ends up under, and "no query
returns both" is a fact about what the store still holds — a test that only checked
`supersede` was *called* would pass against an implementation that called it and left the old
row in place, which is exactly the failure the property names. `_RecordingStore` therefore
implements `supersede` for real, write-new-then-delete-old in that order, and the assertions
read its contents afterwards.

**Grilling session G15 settled the shape this exercises**: `adrap` is a `Revisable` (task
10.23) reaching the corpus through `ctx.require(NodeStore)`, assigning each new leaf to the
nearest existing cluster by a centroid *recomputed from that cluster's stored members*, and
replacing each affected summary and every ancestor above it through `NodeSupersedable`
(task 10.24). Nothing it persists is anything but a `Node` — Chucri §4.2 stores fitted UMAP
and GMM instances with the tree, Weft's clusterer fits no model, so a cluster's whole state is
a centroid derivable from nodes already stored, and these tests recompute it that way.

**The rebuilt summary carries `Representation(technique="raptor")`, not `"adrap"`**, and one
test pins it. `raptor-and-leaves-rrf.yaml` selects its summary arm on
`ext.weft-index.technique == raptor`, so a rebuilt summary marked `adrap` would silently drop
out of a shipped retrieval rung — and the marker describes the *kind* of node rather than the
stage that built it, which is the argument `RaptorFacts.level`'s own docstring already makes
for deriving level "from the members, never from the stage".

`Prompts` and `LLM` doubles follow `tests/unit/weft_index/test_raptor.py`'s split — the real
`SummarizeClusterPrompt`, a scripted `LLM` — so a cluster's re-summarisation is a real render.
"""

from collections.abc import Sequence

from pydantic import BaseModel

from weft_index.adrap import NAME, AdrapConfig, AdrapJoiner
from weft_index.contract import Revisable
from weft_index.payload import RaptorFacts, Representation
from weft_index.prompts import SUMMARIZE_CLUSTER_NAME, SummarizeClusterPrompt
from weft_index.raptor import NAME as RAPTOR_NAME
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import (
    Failed,
    MediaType,
    Node,
    NodeId,
    NothingToProduce,
    Outcome,
    Produced,
    SourceId,
    Vector,
)
from weft_llm.contract import LLM
from weft_llm.payload import Completion, Rendered
from weft_prompts.contract import Prompts
from weft_store import NodeStore
from weft_store.contract import Filter, Page

_SOURCE = SourceId("doc-1")

# Two tight pairs, far apart from each other, exactly as `test_raptor.py` arranges them: `A`
# and `B` cluster with each other (cosine ~1) and not with the far vector (cosine ~0).
# `_A_PRIME` is the newly indexed leaf — near enough to the A/B centroid to join it, which is
# the happy path — and `_FAR` is near nothing, which is the "founds no second tree" case.
_A = Vector(values=(1.0, 0.0))
_B = Vector(values=(0.9, 0.1))
_A_PRIME = Vector(values=(0.95, 0.05))
_FAR = Vector(values=(0.0, 1.0))

#: What the tree under test was built with, stored on its summaries by task 10.9 and read
#: back by `adrap` rather than re-derived — see `test_the_threshold_is_read_from_the_tree`.
_TREE_THRESHOLD = 0.75
_TREE_CLUSTER_SIZE = 8


def _leaf(content: str, vector: Vector) -> Node:
    """A stored leaf: no `RaptorFacts`, so it states no level at all."""
    return Node.synthetic(
        content=content,
        media_type=MediaType.TEXT,
        reason="test fixture",
        sources=frozenset({_SOURCE}),
    ).with_embedding(vector)


def _summary(members: Sequence[Node], *, content: str, level: int) -> Node:
    """A stored summary of `members`, shaped exactly as `raptor` writes one.

    Built with `Node.combine` rather than by hand so its id is the real content digest over
    media type, content, parent ids and ordinal — which is *why* a summary that gains a member
    is a new node, and therefore why `supersede` exists at all.
    """
    return (
        Node.combine(members, content=content, media_type=MediaType.TEXT)
        .with_ext(Representation(technique=RAPTOR_NAME))
        .with_ext(
            RaptorFacts(
                members=len(members),
                members_truncated=0,
                characters_held=sum(len(member.content) for member in members),
                characters_shown=sum(len(member.content) for member in members),
                level=level,
                resolved_similarity_threshold=_TREE_THRESHOLD,
                resolved_cluster_size=_TREE_CLUSTER_SIZE,
            )
        )
    )


class _RecordingStore:
    """A `NodeStore` + `MetadataFilter` + `NodeSupersedable` holding nodes in a dict.

    `supersede` is implemented for real and in the contract's own order — write `new`, then
    delete `old` — because `NodeSupersedable`'s docstring makes that ordering the contract
    ("an interruption then leaves a duplicate... and never a hole"). A double that merely
    recorded the call could not falsify the property this task exists to prove.

    `matching` answers the one filter `adrap` asks — `ext.weft-index-raptor.level` exists —
    by checking for `RaptorFacts` rather than by interpreting the AST, which is enough to be
    honest about *which nodes come back* without reimplementing a filter engine in a test.
    """

    def __init__(self, nodes: Sequence[Node]) -> None:
        self.nodes: dict[NodeId, Node] = {node.id: node for node in nodes}
        self.superseded: list[tuple[NodeId, NodeId]] = []

    async def put(self, nodes: Sequence[Node]) -> None:
        for node in nodes:
            self.nodes[node.id] = node

    async def get(self, ids: Sequence[NodeId]) -> Sequence[Node]:
        return tuple(self.nodes[node_id] for node_id in ids if node_id in self.nodes)

    async def scan(self, cursor: object | None = None) -> Page[Node]:
        del cursor
        return Page(items=tuple(self.nodes.values()), next_cursor=None)

    async def count(self) -> int:
        return len(self.nodes)

    async def matching(self, filter: Filter, cursor: object | None = None) -> Page[Node]:
        del filter, cursor
        summaries = tuple(
            node for node in self.nodes.values() if node.ext_as(RaptorFacts) is not None
        )
        return Page(items=summaries, next_cursor=None)

    async def supersede(self, old: NodeId, new: Node) -> None:
        self.nodes[new.id] = new
        if old != new.id:
            self.nodes.pop(old, None)
        self.superseded.append((old, new.id))


class _StoreThatCannotSupersede:
    """A `NodeStore` with no `supersede` — the refusal path G15's *Remove* face anticipated:
    "`adrap` asks the store it was handed and refuses by name when the answer is no."
    """

    def __init__(self, nodes: Sequence[Node]) -> None:
        self.nodes: dict[NodeId, Node] = {node.id: node for node in nodes}

    async def put(self, nodes: Sequence[Node]) -> None:
        for node in nodes:
            self.nodes[node.id] = node

    async def get(self, ids: Sequence[NodeId]) -> Sequence[Node]:
        return tuple(self.nodes[node_id] for node_id in ids if node_id in self.nodes)

    async def scan(self, cursor: object | None = None) -> Page[Node]:
        del cursor
        return Page(items=tuple(self.nodes.values()), next_cursor=None)

    async def count(self) -> int:
        return len(self.nodes)

    async def matching(self, filter: Filter, cursor: object | None = None) -> Page[Node]:
        del filter, cursor
        summaries = tuple(
            node for node in self.nodes.values() if node.ext_as(RaptorFacts) is not None
        )
        return Page(items=summaries, next_cursor=None)


class _StubPrompts:
    """A `Prompts` holding this pack's own `summarize-cluster` prompt for real."""

    def __init__(self) -> None:
        self._prompt = SummarizeClusterPrompt()

    async def render(self, name: str, values: BaseModel, ctx: Context) -> Outcome[Rendered]:
        if name != SUMMARIZE_CLUSTER_NAME:
            raise KeyError(name)
        return await self._prompt.render(values, ctx)


class _ScriptedLLM:
    """An `LLM` answering `complete` from a per-call script, keyed by call order."""

    def __init__(self, replies: Sequence[str]) -> None:
        self._replies = list(replies)
        self.calls = 0

    async def complete(self, rendered: Rendered, *, role: str, ctx: Context) -> Outcome[Completion]:
        del rendered, role, ctx
        index = min(self.calls, len(self._replies) - 1)
        self.calls += 1
        return Produced(value=Completion(text=self._replies[index], model="stub-model"))


def _ctx(*, store: object, llm: object | None = None) -> Context:
    services = ServiceRegistry()
    services.add(NodeStore, store)
    services.add(LLM, llm if llm is not None else _ScriptedLLM(["A rebuilt summary."]))
    services.add(Prompts, _StubPrompts())
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


def _tree_of_one_cluster() -> tuple[Node, Node, Node]:
    """Two leaves and the level-1 summary built over them — the tree a new document joins."""
    a = _leaf("passage a", _A)
    b = _leaf("passage b", _B)
    return a, b, _summary((a, b), content="A summary of A and B.", level=1)


def _facts(node: Node) -> RaptorFacts:
    facts = node.ext_as(RaptorFacts)
    assert facts is not None, "expected a summary carrying RaptorFacts"
    return facts


def _summaries(store: _RecordingStore) -> list[Node]:
    return [node for node in store.nodes.values() if node.ext_as(RaptorFacts) is not None]


async def test_a_new_leaf_joins_the_nearest_existing_cluster() -> None:
    # Arrange — a stored tree of one cluster, and one newly indexed leaf near its centroid.
    a, b, _old = _tree_of_one_cluster()
    store = _RecordingStore((a, b, _old))
    new_leaf = _leaf("passage a prime", _A_PRIME)

    # Act
    outcome = await AdrapJoiner().run((new_leaf,), _ctx(store=store))

    # Assert — the rebuilt summary names all three leaves as its members, so the new document
    # joined the existing cluster rather than founding a second one beside it.
    assert isinstance(outcome, Produced)
    rebuilt = _summaries(store)
    assert len(rebuilt) == 1
    assert set(rebuilt[0].lineage.parents) == {a.id, b.id, new_leaf.id}


async def test_no_query_returns_both_the_old_and_the_new_summary_of_one_cluster() -> None:
    # Arrange — the ledger's own second clause, asserted against what the store still holds.
    a, b, old_summary = _tree_of_one_cluster()
    store = _RecordingStore((a, b, old_summary))
    new_leaf = _leaf("passage a prime", _A_PRIME)

    # Act
    await AdrapJoiner().run((new_leaf,), _ctx(store=store))

    # Assert — the superseded summary is gone from the store, not merely joined by a newer
    # one. A retriever searching the corpus can no longer return both.
    assert old_summary.id not in store.nodes
    summaries = _summaries(store)
    assert len(summaries) == 1
    assert summaries[0].id != old_summary.id


async def test_every_ancestor_above_a_joined_cluster_is_superseded_too() -> None:
    # Arrange — a two-level tree. A node id is a content digest over its parent ids, so a
    # rebuilt level-1 summary makes its level-2 parent stale by construction.
    a, b, level_one = _tree_of_one_cluster()
    level_two = _summary((level_one,), content="A summary of the summary.", level=2)
    store = _RecordingStore((a, b, level_one, level_two))
    new_leaf = _leaf("passage a prime", _A_PRIME)

    # Act
    await AdrapJoiner().run((new_leaf,), _ctx(store=store))

    # Assert — neither stale node survives, and the surviving level-2 summary names the
    # *new* level-1 id rather than the superseded one.
    assert level_one.id not in store.nodes
    assert level_two.id not in store.nodes
    surviving = {_facts(node).level: node for node in _summaries(store)}
    assert set(surviving) == {1, 2}
    assert surviving[2].lineage.parents == (surviving[1].id,)


async def test_a_leaf_similar_to_nothing_founds_no_second_tree() -> None:
    # Arrange — a leaf far from the only cluster's centroid.
    a, b, old_summary = _tree_of_one_cluster()
    store = _RecordingStore((a, b, old_summary))
    stranger = _leaf("an unrelated passage", _FAR)

    # Act
    outcome = await AdrapJoiner().run((stranger,), _ctx(store=store))

    # Assert — nothing is superseded and no summary is invented for the lone new leaf.
    # Founding a cluster is `raptor`'s job on the next full pass, never this stage's.
    assert isinstance(outcome, Produced)
    assert store.superseded == []
    assert old_summary.id in store.nodes
    assert stranger in outcome.value


async def test_the_rebuilt_summary_stays_reachable_from_the_shipped_retrieval_rung() -> None:
    # Arrange — `raptor-and-leaves-rrf.yaml` selects its summary arm on
    # `ext.weft-index.technique == raptor`, so the marker is a fact a shipped rung depends on.
    a, b, old_summary = _tree_of_one_cluster()
    store = _RecordingStore((a, b, old_summary))
    new_leaf = _leaf("passage a prime", _A_PRIME)

    # Act
    await AdrapJoiner().run((new_leaf,), _ctx(store=store))

    # Assert — the rebuilt summary is marked as the same kind of node `raptor` produces.
    rebuilt = _summaries(store)[0]
    representation = rebuilt.ext_as(Representation)
    assert representation is not None
    assert representation.technique == RAPTOR_NAME


async def test_the_threshold_is_read_from_the_tree_being_joined() -> None:
    # Arrange — `auto` here cannot mean "derive from this run's payload": the payload is one
    # new document, and a threshold derived from it would describe that document rather than
    # the corpus it is joining. Task 10.9 stored what the tree resolved, so `auto` reads it.
    a, b, old_summary = _tree_of_one_cluster()
    store = _RecordingStore((a, b, old_summary))
    new_leaf = _leaf("passage a prime", _A_PRIME)

    # Act
    await AdrapJoiner().run((new_leaf,), _ctx(store=store))

    # Assert — the rebuilt summary carries the tree's own resolved values forward, so a later
    # join reads the same numbers rather than drifting a little on every document.
    rebuilt = _summaries(store)[0]
    assert _facts(rebuilt).resolved_similarity_threshold == _TREE_THRESHOLD
    assert _facts(rebuilt).resolved_cluster_size == _TREE_CLUSTER_SIZE


async def test_an_empty_corpus_leaves_the_payload_alone() -> None:
    # Arrange — the first ever run: there is no tree to join.
    store = _RecordingStore(())
    new_leaf = _leaf("passage a", _A)

    # Act
    outcome = await AdrapJoiner().run((new_leaf,), _ctx(store=store))

    # Assert — every node handed in continues, unchanged, and nothing is superseded. Building
    # the first tree is `raptor`'s job; this stage has nothing to revise.
    assert isinstance(outcome, Produced)
    assert tuple(outcome.value) == (new_leaf,)
    assert store.superseded == []


async def test_a_store_that_cannot_supersede_is_refused_by_name() -> None:
    # Arrange — a store satisfying `NodeStore` but not `NodeSupersedable`.
    a, b, old_summary = _tree_of_one_cluster()
    store = _StoreThatCannotSupersede((a, b, old_summary))
    new_leaf = _leaf("passage a prime", _A_PRIME)

    # Act
    outcome = await AdrapJoiner().run((new_leaf,), _ctx(store=store))

    # Assert — says what was wanted and why it is unavailable, naming both the plugin and the
    # capability, rather than joining a tree it cannot then repair.
    assert isinstance(outcome, Failed)
    assert NAME in outcome.reason
    assert "supersede" in outcome.reason


async def test_a_leaf_without_a_vector_is_refused_by_name() -> None:
    # Arrange — `adrap` clusters by the vectors it is handed, exactly as `raptor` does since
    # task 10.4, so a payload reaching it before `embed` is a stage-order mistake.
    a, b, old_summary = _tree_of_one_cluster()
    store = _RecordingStore((a, b, old_summary))
    unembedded = Node.synthetic(
        content="passage a prime",
        media_type=MediaType.TEXT,
        reason="test fixture",
        sources=frozenset({_SOURCE}),
    )

    # Act
    outcome = await AdrapJoiner().run((unembedded,), _ctx(store=store))

    # Assert — names the plugin and the stage it must follow.
    assert isinstance(outcome, Failed)
    assert NAME in outcome.reason
    assert "embed" in outcome.reason


async def test_an_empty_payload_produces_nothing() -> None:
    # Arrange
    store = _RecordingStore(())

    # Act
    outcome = await AdrapJoiner().run((), _ctx(store=store))

    # Assert — the ambiguous-empty-case answer every contract in this tree documents.
    assert isinstance(outcome, NothingToProduce)


def test_the_joiner_satisfies_revisable_and_not_by_declaring_it() -> None:
    # Arrange / Act / Assert — capability is derived, never declared (`02` §1). `Revisable`
    # and `Expander` are structurally identical, which `Revisable`'s own docstring states, so
    # this asserts the structural fact rather than trying to tell them apart.
    assert isinstance(AdrapJoiner(), Revisable)
    assert AdrapJoiner.config_model is AdrapConfig
