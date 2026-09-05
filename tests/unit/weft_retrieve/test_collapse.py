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
