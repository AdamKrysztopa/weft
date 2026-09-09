"""`graph-walk` — a question naming an entity, answered from a bounded walk. Ledger **11.10**.

Mirrors `packages/weft-rag/src/weft_kg/retrieval.py`. No container: the walk is doubled at
`weft_kg.contract.GraphTraversal` and the corpus at `weft_store.contract.NodeStore`, which are
exactly the two services this plugin reaches and the two declarations it makes.

**The name, settled before the code through `paper-to-plugin` and `10` §2.1.** `10` §4 reserves
`grag`, `g-retriever`, `archrag` and `hipporag` for techniques Weft does not implement, and taking
one for a bounded neighbourhood walk would be rule 4's overclaim — none of them is this. `graph-
walk` states the mechanism (rule 2) and is qualified against the siblings a graph family will grow
(rule 6): `graph-ppr` and `graph-community` stay free, where a bare `graph` would have let the
first implementation seize a namespace meant to be shared. There is no paper: walking a
neighbourhood from a matched entity is ordinary practice, and `10` §5 records the absence rather
than inventing a provenance.

**Two declarations, and the split is the point of this task.** `needs_store = (NodeStore,)` says
what the *configured store* must be — this plugin reads node bodies back with `store.get`, exactly
as `weft_retrieve.collapse` does. `needs_services = (GraphTraversal,)` is new at `11.10` and says
what the *run* must have: a capability no store provides and no `[services] store` can supply,
reached through `ctx.require` and named by a `[services] graph` role. Declaring the traversal
under `needs_store` would compare it against `pgvector` and refuse every run with a remedy pointing
at the wrong setting — which is the defect `weft_cli.run_services.SelectedCapabilityMissingError`
was written to describe and, until this task, nothing ever raised.

**Seeding is capitalisation, not a model — settled with the owner 2026-09-09.** A question's
Title-Case runs are the entity-name candidates, the identical rule `weft_kg.cooccurrence` already
applies to a chunk, now published once in `weft_kg.names` so the pack holds one notion of what a
name looks like rather than two. It keeps `cost_bound = (0, 0)`, so a graph question costs no
credential — the property `index-with-cooccurrence` was built for, carried to the query side. It is
crude in the same way and the row in `10` says so: it cannot see a lower-cased name, and it cannot
see a language that does not capitalise.

**The score decays by hop distance**, also settled with the owner: a walk produces no ranking, and
the two honest options were to invent an interpretable one or to flatten every hit to `1.0`. Flat
scores make every hit tie, and `reciprocal-rank-fusion` turns an arbitrary tie-break into an
arbitrary weight with nothing saying so. `1/(1 + hops)` is a number a reader can interpret and is
what makes `graph-2hop-then-generate` visibly a different rung rather than merely a larger one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import MediaType, Node, NodeId, Produced, SourceId
from weft_kg.contract import Entity, EntityId, GraphTraversal
from weft_kg.retrieval import NAME, GraphWalkConfig, GraphWalkRetriever
from weft_retrieve.payload import Query, QuerySet
from weft_store.contract import NodeStore


class _Walk:
    """A `GraphTraversal` over a graph written as three plain mappings.

    Copied in shape from `tests/unit/weft_kg/test_contract.py`'s own `_Stranger`, which is this
    pack's existing double for this Protocol, and narrowed to the three members the contract
    actually declares. `asked` records the seeds so a test can assert *what was walked from*
    rather than only what came back — the difference between a retriever that matched the
    question's entity and one that happened to return the right nodes.
    """

    def __init__(
        self,
        *,
        entities: Mapping[str, str],
        neighbours: Mapping[str, tuple[str, ...]],
        nodes: Mapping[str, tuple[str, ...]],
    ) -> None:
        self._entities = entities
        self._neighbours = neighbours
        self._nodes = nodes
        self.asked: list[Sequence[str]] = []
        self.hops_asked: list[int] = []

    async def entities_by_name(self, names: Sequence[str]) -> tuple[Entity, ...]:
        self.asked.append(list(names))
        return tuple(
            Entity(id=EntityId(self._entities[name]), name=name)
            for name in names
            if name in self._entities
        )

    async def nodes_for_entities(
        self, entity_ids: Sequence[EntityId]
    ) -> Mapping[EntityId, tuple[NodeId, ...]]:
        return {
            entity_id: tuple(NodeId(node) for node in self._nodes.get(entity_id, ()))
            for entity_id in entity_ids
            if entity_id in self._nodes
        }

    async def neighbourhood(
        self, entity_ids: Sequence[EntityId], *, hops: int
    ) -> Mapping[EntityId, tuple[Entity, ...]]:
        self.hops_asked.append(hops)
        reached: dict[EntityId, tuple[Entity, ...]] = {}
        for seed in entity_ids:
            found: list[Entity] = []
            frontier = [seed]
            seen = {seed}
            for _ in range(hops):
                nxt: list[str] = []
                for node in frontier:
                    for other in self._neighbours.get(node, ()):
                        if other not in seen:
                            seen.add(EntityId(other))
                            nxt.append(other)
                            found.append(Entity(id=EntityId(other), name=other))
                frontier = [EntityId(one) for one in nxt]
            reached[seed] = tuple(found)
        return reached


class _Store:
    """A `NodeStore` answering `get` and nothing else — the one method this plugin calls.

    Copied in shape from `tests/unit/weft_retrieve/test_collapse.py`'s own store double, which
    exists for the same reason one contract over: `collapse-to-parent` also declares
    `needs_store = (NodeStore,)` and also reads bodies back by id.
    """

    def __init__(self, nodes: Sequence[Node]) -> None:
        self._nodes = {node.id: node for node in nodes}
        self.fetched: list[NodeId] = []

    async def get(self, ids: Sequence[NodeId]) -> tuple[Node, ...]:
        self.fetched.extend(ids)
        return tuple(self._nodes[one] for one in ids if one in self._nodes)


def _node(content: str) -> Node:
    return Node.synthetic(
        content=content,
        media_type=MediaType.TEXT,
        reason="weft_kg's own graph-retrieval test",
        sources=frozenset({SourceId("doc-a")}),
    )


def _ctx(walk: object, store: object) -> Context:
    services = ServiceRegistry()
    services.add(GraphTraversal, walk)
    services.add(NodeStore, store)
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


def _queryset(text: str) -> QuerySet:
    return QuerySet(origin=Query(text=text), queries=(Query(text=text),))


def _fixture() -> tuple[_Walk, _Store, dict[str, Node]]:
    """One question's worth of graph: `Chucri` wrote `adRAP`, which extends `RAPTOR`.

    Each entity anchors one node, so a hop count and a node count are the same number and a
    test asserting reach cannot pass by accident on a fan-out.
    """
    nodes = {
        "chucri": _node("Chucri wrote adRAP."),
        "adrap": _node("adRAP extends RAPTOR."),
        "raptor": _node("RAPTOR builds a tree of summaries."),
    }
    walk = _Walk(
        entities={"Chucri": "e:chucri", "adRAP": "e:adrap", "RAPTOR": "e:raptor"},
        neighbours={"e:chucri": ("e:adrap",), "e:adrap": ("e:raptor",)},
        nodes={
            "e:chucri": (nodes["chucri"].id,),
            "e:adrap": (nodes["adrap"].id,),
            "e:raptor": (nodes["raptor"].id,),
        },
    )
    return walk, _Store(list(nodes.values())), nodes


async def test_a_question_naming_an_entity_is_answered_from_that_entity_s_nodes() -> None:
    """The headline property. The question names `Chucri`; the answer is the node that mention
    anchors, fetched from the corpus by the id the walk returned.
    """
    # Arrange
    walk, store, nodes = _fixture()

    # Act
    outcome = await GraphWalkRetriever(GraphWalkConfig(hops=0)).run(
        _queryset("What did Chucri write?"), _ctx(walk, store)
    )

    # Assert
    assert isinstance(outcome, Produced)
    [ranked] = outcome.value.lists
    assert [hit.scored.value.id for hit in ranked.hits] == [nodes["chucri"].id]
    assert ["Chucri"] in walk.asked, (
        "the retriever did not ask the graph about the entity the question actually named"
    )


async def test_the_hop_count_is_a_parameter_and_the_control_disagrees() -> None:
    """Requirement 6, and `L9.58`: a parameterised control has to be shown to change something.
    One hop reaches `adRAP`; two reach `RAPTOR` as well. This is the whole difference between
    `graph-then-generate` and `graph-2hop-then-generate`, so a `hops` that did not travel would
    make one of those two rungs a copy of the other with a different name.
    """
    # Arrange
    walk, store, nodes = _fixture()
    question = _queryset("What did Chucri write?")

    # Act
    one = await GraphWalkRetriever(GraphWalkConfig(hops=1)).run(question, _ctx(walk, store))
    two = await GraphWalkRetriever(GraphWalkConfig(hops=2)).run(question, _ctx(*_fixture()[:2]))

    # Assert
    assert isinstance(one, Produced)
    assert isinstance(two, Produced)
    reached_at_one = {hit.scored.value.content for hit in one.value.lists[0].hits}
    reached_at_two = {hit.scored.value.content for hit in two.value.lists[0].hits}
    assert nodes["adrap"].content in reached_at_one
    assert nodes["raptor"].content not in reached_at_one
    assert nodes["raptor"].content in reached_at_two
    assert walk.hops_asked == [1], "the walk was not asked for the configured bound"


async def test_a_node_further_away_scores_lower_than_one_nearer() -> None:
    """The score is `1/(1 + hops)`, so a seed's own node outranks its neighbour's.

    Asserted as an ordering rather than against the literals, because what the number has to
    mean is *nearer is better* — a fuser weights on it and a reader reads it, and pinning the
    arithmetic would freeze a formula neither of them cares about.
    """
    # Arrange
    walk, store, nodes = _fixture()

    # Act
    outcome = await GraphWalkRetriever(GraphWalkConfig(hops=2)).run(
        _queryset("What did Chucri write?"), _ctx(walk, store)
    )

    # Assert
    assert isinstance(outcome, Produced)
    scores = {hit.scored.value.content: hit.scored.score for hit in outcome.value.lists[0].hits}
    assert scores[nodes["chucri"].content] > scores[nodes["adrap"].content]
    assert scores[nodes["adrap"].content] > scores[nodes["raptor"].content]


async def test_hits_are_ranked_nearest_first() -> None:
    """`Passage.rank` is what a `Fuser` reads when it reads nothing else — `reciprocal-rank-
    fusion` uses rank alone — so an ordering that disagreed with the score would make the two
    fusers in this tree disagree about the same list.
    """
    # Arrange
    walk, store, _ = _fixture()

    # Act
    outcome = await GraphWalkRetriever(GraphWalkConfig(hops=2)).run(
        _queryset("What did Chucri write?"), _ctx(walk, store)
    )

    # Assert
    assert isinstance(outcome, Produced)
    hits = outcome.value.lists[0].hits
    assert [hit.rank for hit in hits] == list(range(len(hits)))
    assert [hit.scored.score for hit in hits] == sorted(
        (hit.scored.score for hit in hits), reverse=True
    )


async def test_a_question_naming_no_entity_returns_an_empty_list_not_no_list() -> None:
    """`L5.9` at the retrieval seam, and `vector-top-k`'s own distinction: a query that *was*
    searched and matched nothing still gets a `RankedList` with `hits=()`. Returning no list at
    all would be indistinguishable from a query this retriever declined to search.
    """
    # Arrange
    walk, store, _ = _fixture()

    # Act
    outcome = await GraphWalkRetriever().run(
        _queryset("what does the corpus say about all of this"), _ctx(walk, store)
    )

    # Assert
    assert isinstance(outcome, Produced)
    [ranked] = outcome.value.lists
    assert ranked.hits == ()


async def test_the_arm_label_is_configurable_so_a_fuser_can_weight_it() -> None:
    """`vector-top-k`'s own argument, unchanged: with the channel hardcoded, two lists carry
    one label and an operator has no key to type in a `weights` mapping. `graph-and-vector-rrf`
    is the document that needs this to be true.
    """
    # Arrange
    walk, store, _ = _fixture()

    # Act
    outcome = await GraphWalkRetriever(GraphWalkConfig(arm="entities")).run(
        _queryset("What did Chucri write?"), _ctx(walk, store)
    )

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.lists[0].channel == "entities"
    assert outcome.value.lists[0].retriever == NAME


async def test_the_walk_is_asked_once_for_every_seed_the_question_named() -> None:
    """One round trip, not one per name — `weft_kg.contract.GraphTraversal`'s own module
    docstring states that granularity, and a retriever that looped would make a question naming
    five entities five times as expensive against a real database.
    """
    # Arrange
    walk, store, _ = _fixture()

    # Act
    await GraphWalkRetriever(GraphWalkConfig(hops=1)).run(
        _queryset("Did Chucri write adRAP or RAPTOR?"), _ctx(walk, store)
    )

    # Assert
    assert len(walk.asked) == 1, "entities_by_name was asked more than once for one question"
    assert set(walk.asked[0]) >= {"Chucri", "RAPTOR"}
    # `Chucri` arrives only because `with_subspans` splits it out: `Did` is not in `11.6`'s
    # stopword list, so the raw candidate is `Did Chucri`. That is the sub-span expansion
    # earning its place rather than a convenience — without it, a question phrased as an
    # ordinary sentence seeds nothing at all.
    assert "Did Chucri" in walk.asked[0]
    # `adRAP` is absent and must be: the rule matches a run beginning at a capital, and this
    # plugin's own docstring says so. `test_names.py` asserts that boundary directly.
    assert "adRAP" not in walk.asked[0]


def test_the_plugin_declares_both_of_the_things_it_needs() -> None:
    """The split this task exists for, asserted on the class because the assembler reads it
    there: the configured store must be a `NodeStore`, and the *run* must offer a
    `GraphTraversal`, which no store provides and no `[services] store` can supply.
    """
    # Assert
    assert GraphWalkRetriever.needs_store == (NodeStore,)
    assert GraphWalkRetriever.needs_services == (GraphTraversal,)


def test_the_plugin_claims_no_model_call() -> None:
    """`cost_bound = (0, 0)` is a published claim, on `vector-top-k`'s own footing: it is true
    here because seeding is a regular expression and the walk is SQL, and this module imports
    nothing from `weft_llm`. A future seeding strategy that asked a model would have to move
    this number, which is the point of stating it.
    """
    # Assert
    assert GraphWalkRetriever.cost_bound == (0, 0)
