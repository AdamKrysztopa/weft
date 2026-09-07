"""Unit tests for `weft_retrieve.collapse`.

Mirrors `packages/weft-rag/src/weft_retrieve/collapse.py`. Task **2.33**: "one passage
cannot occupy several slots of a ranking merely because it was indexed several ways,
because collapsing a ranking to its parents is a named stage with a stated policy."
Covers the happy path (a chunk indexed four ways — itself plus three hypothetical
questions, ledger 2.31's own shape — collapses to one slot at the parent's own id, scored
by the default `max` policy, re-sorted ahead of an unrelated hit it now outranks), the edge
case (a group with no direct parent among the ranking's own hits, so the parent is fetched
from the store once, batched, and `sum` combines every representation's own score rather
than taking the best of them), the error case (an unregistered policy name is refused at
configuration, naming the valid set), a drive through `weft_kernel.seam.wrap` (fitness
function 7(b)), and the documented degrade-not-fail path for a parent the store could not
find.

`out.origin == in.origin` and `out.contributors == in.contributors` are asserted in the
happy-path test rather than assumed, the same obligation every other query-path plugin in
this pack carries in its own tests.
"""

from collections.abc import Sequence

import pytest
from pydantic import ValidationError

from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import ExtModel, MediaType, Node, NodeId, Produced
from weft_kernel.seam import wrap
from weft_retrieve.collapse import NAME, CollapsePolicy, CollapseToParent, CollapseToParentConfig
from weft_retrieve.contract import Reranker
from weft_retrieve.payload import Passage, Query, Ranking
from weft_store.contract import NodeStore, Scored


class _Representation(ExtModel):
    """A structural stand-in for `weft_index.payload.Representation`, deliberately not that
    class — the same duck-typed shape `weft_generate.representation`'s own test suite
    exercises, proving `collapse.py` reads no import of the pack that ships the real one."""

    __namespace__ = "test-collapse"
    __schema_version__ = "1.0.0"

    technique: str = "test-representation"


class _StubStore:
    """A `NodeStore` answering `get` from a fixed table, and nothing else — this plugin
    calls no other method."""

    def __init__(self, nodes: dict[NodeId, Node]) -> None:
        self._nodes = nodes
        self.fetched: list[NodeId] = []

    async def get(self, ids: Sequence[NodeId]) -> tuple[Node, ...]:
        self.fetched.extend(ids)
        return tuple(self._nodes[node_id] for node_id in ids if node_id in self._nodes)


def _ctx(services: ServiceRegistry | None = None) -> Context:
    return Context(
        tenant_id="tenant-a",
        run_id="run-1",
        trace_id="trace-1",
        locale="en",
        services=services if services is not None else ServiceRegistry(),
    )


def _passage(node: Node, score: float, rank: int, retrieved_by: str = "vector-top-k") -> Passage:
    return Passage(scored=Scored(value=node, score=score), rank=rank, retrieved_by=retrieved_by)


def _ranking(*hits: Passage) -> Ranking:
    asked = Query(text="what does mRMR reduce?")
    return Ranking(origin=asked, hits=hits, contributors=("vector-top-k:vector",))


async def test_four_representations_of_one_parent_collapse_to_one_hit_scored_by_max() -> None:
    # Arrange — a chunk retrieved alongside three hypothetical questions derived from it
    # (ledger 2.31's own shape: one `Lineage.parents` entry, a `Representation`-shaped
    # marker), plus an unrelated second parent that proves the collapse is per-group, not
    # a blanket top-1 truncation of the whole ranking.
    parent = Node.synthetic(
        content="mRMR reduces redundancy.", media_type=MediaType.TEXT, reason="test fixture"
    )
    q1 = parent.derive(content="What does mRMR reduce?", ordinal=1).with_ext(_Representation())
    q2 = parent.derive(content="Why use mRMR?", ordinal=2).with_ext(_Representation())
    q3 = parent.derive(content="What is mRMR for?", ordinal=3).with_ext(_Representation())
    other = Node.synthetic(
        content="unrelated passage", media_type=MediaType.TEXT, reason="test fixture"
    )
    ranking = _ranking(
        _passage(parent, 0.5, 0),
        _passage(q1, 0.95, 1, retrieved_by="hypothetical-questions"),
        _passage(other, 0.6, 2),
        _passage(q2, 0.4, 3, retrieved_by="hypothetical-questions"),
        _passage(q3, 0.3, 4, retrieved_by="hypothetical-questions"),
    )
    collapser = CollapseToParent()

    # Act
    outcome = await collapser.run(ranking, _ctx())

    # Assert — four representations of `parent` become one hit at `parent`'s own id (no
    # store call needed: `parent` was already a direct hit), scored by the best individual
    # score in the group (`q1`'s 0.95, the default `max` policy) and attributed to whichever
    # representation earned it — ranked ahead of `other` because 0.95 beats 0.6, which the
    # pre-collapse order did not have arranged that way.
    assert isinstance(outcome, Produced)
    assert [passage.node.id for passage in outcome.value.hits] == [parent.id, other.id]
    assert outcome.value.hits[0].score == 0.95
    assert outcome.value.hits[0].retrieved_by == "hypothetical-questions"
    assert [passage.rank for passage in outcome.value.hits] == [0, 1]
    assert outcome.value.origin == ranking.origin
    assert outcome.value.contributors == ranking.contributors


async def test_a_parent_absent_from_the_ranking_is_fetched_once_and_summed_by_policy() -> None:
    # Arrange — two representations of `parent` reach this ranking; `parent` itself never
    # did (a plausible shape when an earlier reranker filtered it out but kept both
    # questions). `sum`, unlike the default, adds every representation's own score rather
    # than taking the best of them.
    parent = Node.synthetic(content="parent text", media_type=MediaType.TEXT, reason="test fixture")
    q1 = parent.derive(content="question one").with_ext(_Representation())
    q2 = parent.derive(content="question two", ordinal=1).with_ext(_Representation())
    ranking = _ranking(_passage(q1, 0.4, 0), _passage(q2, 0.3, 1))
    store = _StubStore({parent.id: parent})
    services = ServiceRegistry()
    services.add(NodeStore, store)
    collapser = CollapseToParent(CollapseToParentConfig(policy=CollapsePolicy.SUM))

    # Act
    outcome = await collapser.run(ranking, _ctx(services))

    # Assert
    assert isinstance(outcome, Produced)
    assert len(outcome.value.hits) == 1
    assert outcome.value.hits[0].node.id == parent.id
    assert outcome.value.hits[0].score == pytest.approx(0.7)
    assert store.fetched == [parent.id]


async def test_a_parent_the_store_cannot_find_falls_back_to_the_best_representation() -> None:
    # Arrange — the parent was deleted (or never stored) between indexing and this run; the
    # group must not vanish, and the stage must not raise over a store race it did not cause.
    parent = Node.synthetic(content="gone", media_type=MediaType.TEXT, reason="test fixture")
    q1 = parent.derive(content="question one").with_ext(_Representation())
    ranking = _ranking(_passage(q1, 0.6, 0))
    services = ServiceRegistry()
    services.add(NodeStore, _StubStore({}))
    collapser = CollapseToParent()

    # Act
    outcome = await collapser.run(ranking, _ctx(services))

    # Assert — the representation itself survives, cited as itself, rather than the group
    # disappearing because its one lookup failed.
    assert isinstance(outcome, Produced)
    assert outcome.value.hits[0].node.id == q1.id
    assert outcome.value.hits[0].score == 0.6


def test_an_unregistered_policy_name_is_refused_at_configuration() -> None:
    # Act / Assert — `CollapsePolicy` is a closed `StrEnum`, not a `str`, so a typo is a
    # pydantic `ValidationError` naming the valid set rather than a silent no-op at `run`.
    with pytest.raises(ValidationError, match="max"):
        CollapseToParentConfig(policy="best")  # type: ignore[arg-type]


async def test_an_empty_ranking_collapses_to_an_empty_ranking() -> None:
    # Act / Assert — the emptiness rule every contract in `weft_retrieve.contract` states:
    # `Produced` carrying an empty `Ranking`, never `NothingToProduce`.
    asked = Query(text="nothing retrieved")
    outcome = await CollapseToParent().run(Ranking(origin=asked), _ctx())

    assert isinstance(outcome, Produced)
    assert outcome.value.hits == ()
    assert outcome.value.origin == asked


async def test_an_empty_rankings_note_survives_collapse_unchanged() -> None:
    """A `Fuser` upstream (e.g. `BooleanCombine` on an unsatisfiable AND) can produce an
    empty `Ranking` carrying a diagnostic `note` explaining *why* nothing matched. The
    emptiness rule this stage documents says `note` passes through unchanged same as
    `origin` and `contributors` — this regression guards that the empty-hits branch does
    not silently drop it before `repack`/`generate` ever see it."""
    # Arrange
    asked = Query(text="A AND B")
    explanation = "the conjunction A AND B matched no document in common"
    empty_with_note = Ranking(origin=asked, note=explanation)

    # Act
    outcome = await CollapseToParent().run(empty_with_note, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.note == explanation


async def test_driving_collapse_to_parent_through_the_seam_produces_a_ranking() -> None:
    """Fitness function 7(b) against the one path a registered plugin is actually called
    through in production — `weft_kernel.seam.wrap`, not a direct method call a registered
    instance never receives."""
    # Arrange
    node = Node.synthetic(content="only candidate", media_type=MediaType.TEXT, reason="t")
    ranking = _ranking(_passage(node, 0.9, 0))
    collapser = CollapseToParent()
    wrapped = wrap(collapser.run, distribution="weft-retrieve", contract="Reranker", plugin=NAME)

    # Act
    outcome = await wrapped(ranking, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert [p.node.content for p in outcome.value.hits] == ["only candidate"]
    assert isinstance(collapser, Reranker)


def test_the_declared_cost_bound_is_zero_zero() -> None:
    # Act / Assert — `run` resolves `NodeStore`, never an `LLM`-shaped service, and only
    # when a group's parent is not already among the ranking's own hits.
    assert CollapseToParent.cost_bound == (0, 0)


# --- Ledger task 10.12 — a summary and its own members do not both consume the budget.


async def test_a_summary_and_the_leaves_it_was_built_from_do_not_both_occupy_the_budget() -> None:
    """A retrieved summary is evidence *about* the passages it abstracts, not a passage beside
    them — so a ranking holding both spends several slots of the answer's budget on one piece of
    evidence.

    This is the shape `_collapse_key` cannot reach on its own: it maps a **single-parent**
    representation onto the node it stands in for, and a `Node.combine` summary has several
    parents, so it returns the summary's own id and the leaves keep theirs. Three separate
    groups, three slots, one fact. `repack`'s `top_n: 8` then packs the same content four times
    over on a corpus where a cluster is four chunks.

    **The higher-scoring one survives**, which is the only choice that does not decide in advance
    whether an abstraction or a passage answers better — the ranking already has an opinion and
    this keeps it. No paper settles the question: RAPTOR's collapsed tree treats every node
    uniformly (its own §3, p.5) without ever asking about double-counting, T-Retriever's eq. 13
    expands a summary to its members and drops the summary text, and Chucri summarises the
    retrieved set at query time. Nothing in the four weights a hierarchical arm against a leaf
    arm at all.
    """
    # Arrange — two leaves and the summary built over them, all three retrieved.
    root = Node.synthetic(
        content="doc", media_type=MediaType.TEXT, reason="fixture", sources=frozenset()
    )
    first = root.derive(content="mRMR reduces redundancy among selected features.", ordinal=0)
    second = root.derive(
        content="It maximises relevance to the target at the same time.", ordinal=1
    )
    summary = Node.combine(
        (first, second),
        content="mRMR trades redundancy against relevance.",
        media_type=MediaType.TEXT,
    )
    ranking = _ranking(
        _passage(summary, 0.91, 1),
        _passage(first, 0.62, 2),
        _passage(second, 0.55, 3),
    )

    # Act
    outcome = await CollapseToParent().run(ranking, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    kept = [hit.scored.value.id for hit in outcome.value.hits]
    assert summary.id in kept, "the higher-scoring hit must be the one that survives"
    assert first.id not in kept and second.id not in kept, (
        "a summary and the leaves it was built from both occupied the budget. That is one piece "
        "of evidence taking three of the answer's slots, and `repack`'s `top_n` cannot tell."
    )


async def test_a_leaf_outscoring_its_own_summary_is_the_one_that_survives() -> None:
    """The rule is *the higher-scoring one*, in both directions — not *always the summary*.

    Deciding in advance that an abstraction beats a passage would be this plugin overruling the
    ranking, and would make a specific question answerable only through a summary written for a
    broad one. `raptor-and-leaves-rrf` exists precisely because both kinds are worth searching.
    """
    # Arrange — the same three nodes, with a leaf scoring highest this time.
    root = Node.synthetic(
        content="doc", media_type=MediaType.TEXT, reason="fixture", sources=frozenset()
    )
    first = root.derive(content="mRMR reduces redundancy among selected features.", ordinal=0)
    second = root.derive(
        content="It maximises relevance to the target at the same time.", ordinal=1
    )
    summary = Node.combine(
        (first, second),
        content="mRMR trades redundancy against relevance.",
        media_type=MediaType.TEXT,
    )
    ranking = _ranking(
        _passage(first, 0.93, 1),
        _passage(summary, 0.44, 2),
        _passage(second, 0.40, 3),
    )

    # Act
    outcome = await CollapseToParent().run(ranking, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    kept = [hit.scored.value.id for hit in outcome.value.hits]
    assert first.id in kept
    assert summary.id not in kept, (
        "the summary outlived a leaf that scored higher than it, which decides in advance that "
        "an abstraction answers better than a passage"
    )


async def test_a_summary_whose_members_were_not_retrieved_is_untouched() -> None:
    """The rule fires on an overlap, never on a summary alone — otherwise a broad question, which
    is the one a summary exists to answer, would lose the only node that can answer it."""
    # Arrange
    root = Node.synthetic(
        content="doc", media_type=MediaType.TEXT, reason="fixture", sources=frozenset()
    )
    first = root.derive(content="one", ordinal=0)
    second = root.derive(content="two", ordinal=1)
    other = root.derive(content="an unrelated passage", ordinal=2)
    summary = Node.combine(
        (first, second), content="a summary of one and two", media_type=MediaType.TEXT
    )
    ranking = _ranking(_passage(summary, 0.80, 1), _passage(other, 0.70, 2))

    # Act
    outcome = await CollapseToParent().run(ranking, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert [hit.scored.value.id for hit in outcome.value.hits] == [summary.id, other.id]
