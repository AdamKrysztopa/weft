"""Unit tests for `weft_retrieve.corrective`.

Mirrors `packages/weft-rag/src/weft_retrieve/corrective.py`. Ledger **2.21**: "a
knowledge action that reaches a second retriever is what earns the name `corrective`." This
module covers the happy path (grading leaves enough hits, `knowledge_action` never runs), the
edge case (grading leaves too few, `knowledge_action` runs and its own hits are appended
beside the graded ones), the error case (`knowledge_action` configured equal to `primary` is
refused at construction, per `10` §1.1's own condition), and a drive through
`weft_kernel.seam.wrap`.

`primary`, `grader` and `knowledge_action` are all stubs reached through a `_StubLookup`,
never the real `vector-top-k` or `graded-retrieval` — this task's own scope is `weft_retrieve/
corrective.py`, and exercising the real sub-plugins here would test them a second time and
this one not at all, the same boundary `test_iterative.py`'s own module docstring draws for
`leaf` and `sufficiency`.

`out.origin == in.origin` is asserted, per this pack's own recorded obligation.
"""

import pytest
from pydantic import ValidationError

from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import MediaType, Node, NothingToProduce, Outcome, Produced
from weft_kernel.seam import wrap
from weft_retrieve.contract import Reranker, Retriever, StageLookup
from weft_retrieve.corrective import NAME, Corrective, CorrectiveConfig, CorrectiveTrace
from weft_retrieve.payload import Candidates, Passage, Query, QuerySet, RankedList, Ranking
from weft_store.contract import Scored


def _asked() -> Query:
    return Query(text="what caused the 2003 blackout?")


def _passage(content: str, retrieved_by: str = "primary") -> Passage:
    node = Node.synthetic(content=content, media_type=MediaType.TEXT, reason="fixture")
    return Passage(scored=Scored(value=node, score=1.0), rank=0, retrieved_by=retrieved_by)


def _candidates(origin: Query, *contents: str, retriever: str = "primary") -> Candidates:
    hits = tuple(_passage(content, retrieved_by=retriever) for content in contents)
    return Candidates(
        origin=origin, lists=(RankedList(query=origin, retriever=retriever, hits=hits),)
    )


class _FakeRetriever:
    """A `Retriever`-shaped callable, scripted one `Outcome[Candidates]` per call."""

    def __init__(self, outcome: Outcome[Candidates]) -> None:
        self._outcome = outcome
        self.calls: list[QuerySet] = []

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[Candidates]:
        del ctx
        self.calls.append(payload)
        return self._outcome


class _FakeGrader:
    """A `Reranker`-shaped callable, scripted one `Outcome[Ranking]` per call — a stand-in
    for `graded-retrieval` that keeps or drops whole hits by content rather than actually
    grading, so this module's own trigger arithmetic is what is under test, not a grader."""

    def __init__(self, keep: frozenset[str]) -> None:
        self._keep = keep
        self.calls: list[Ranking] = []

    async def run(self, payload: Ranking, ctx: Context) -> Outcome[Ranking]:
        del ctx
        self.calls.append(payload)
        hits = tuple(passage for passage in payload.hits if passage.node.content in self._keep)
        renumbered = tuple(
            Passage(scored=hit.scored, rank=rank, retrieved_by=hit.retrieved_by)
            for rank, hit in enumerate(hits)
        )
        return Produced(
            value=Ranking(origin=payload.origin, hits=renumbered, contributors=payload.contributors)
        )


class _StubLookup:
    """A `StageLookup` handing back exactly one scripted primary, grader and action."""

    def __init__(
        self, primary: _FakeRetriever, grader: _FakeGrader, action: _FakeRetriever | None = None
    ) -> None:
        self._primary = primary
        self._grader = grader
        self._action = action
        self.asked: list[tuple[str, str]] = []

    def names(self, contract: type[object]) -> frozenset[str]:
        del contract
        return frozenset()

    async def build(self, contract: type[object], name: str, config: object = None) -> object:
        del config
        assert contract in (Retriever, Reranker)
        self.asked.append(("build", name))
        if name == "primary":
            return self._primary.run
        if name == "grader":
            return self._grader.run
        assert self._action is not None, f"unexpected build('{name}')"
        return self._action.run


def _services(lookup: _StubLookup) -> ServiceRegistry:
    services = ServiceRegistry()
    services.add(StageLookup, lookup)
    return services


def _ctx(services: ServiceRegistry) -> Context:
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


def _config() -> CorrectiveConfig:
    return CorrectiveConfig(primary="primary", grader="grader", knowledge_action="action")


# --------------------------------------------------------------------------------------
# Happy path — enough survives grading, `knowledge_action` never runs.
# --------------------------------------------------------------------------------------


async def test_enough_kept_hits_never_reaches_the_knowledge_action() -> None:
    # Arrange — three hits, all three graded relevant, default trigger (3) not crossed.
    origin = _asked()
    q1 = QuerySet(origin=origin, queries=(origin,))
    primary = _FakeRetriever(Produced(value=_candidates(origin, "a", "b", "c")))
    grader = _FakeGrader(keep=frozenset({"a", "b", "c"}))
    action = _FakeRetriever(Produced(value=_candidates(origin, "should never be asked for")))
    lookup = _StubLookup(primary, grader, action)

    # Act
    outcome = await Corrective(_config()).run(q1, _ctx(_services(lookup)))

    # Assert
    assert isinstance(outcome, Produced)
    candidates = outcome.value
    assert candidates.origin == origin
    contents = [passage.node.content for ranked in candidates.lists for passage in ranked.hits]
    assert contents == ["a", "b", "c"]
    assert action.calls == []
    trace = candidates.ext[CorrectiveTrace.__namespace__]
    assert isinstance(trace, CorrectiveTrace)
    assert trace.triggered is False
    assert trace.kept == 3


# --------------------------------------------------------------------------------------
# Edge case — too few survive grading, `knowledge_action` runs and its hits are appended.
# --------------------------------------------------------------------------------------


async def test_too_few_kept_hits_triggers_the_knowledge_action_and_combines_both() -> None:
    # Arrange — three hits, grading keeps only one ("a"); default `trigger_kept_below=3`
    # fires, and `action`'s own hits arrive beside the one that survived grading.
    origin = _asked()
    q1 = QuerySet(origin=origin, queries=(origin,))
    primary = _FakeRetriever(Produced(value=_candidates(origin, "a", "b", "c")))
    grader = _FakeGrader(keep=frozenset({"a"}))
    action = _FakeRetriever(Produced(value=_candidates(origin, "d", "e", retriever="action")))
    lookup = _StubLookup(primary, grader, action)

    # Act
    outcome = await Corrective(_config()).run(q1, _ctx(_services(lookup)))

    # Assert
    assert isinstance(outcome, Produced)
    candidates = outcome.value
    assert candidates.origin == origin
    assert len(action.calls) == 1
    contents = [passage.node.content for ranked in candidates.lists for passage in ranked.hits]
    assert contents == ["a", "d", "e"]
    trace = candidates.ext[CorrectiveTrace.__namespace__]
    assert isinstance(trace, CorrectiveTrace)
    assert trace.triggered is True
    assert trace.kept == 1


async def test_a_primary_that_declines_to_act_is_relayed_exactly_as_it_answered() -> None:
    origin = _asked()
    q1 = QuerySet(origin=origin, queries=(origin,))
    primary = _FakeRetriever(NothingToProduce(reason="the configured primary declined"))
    grader = _FakeGrader(keep=frozenset())
    lookup = _StubLookup(primary, grader)

    outcome = await Corrective(_config()).run(q1, _ctx(_services(lookup)))

    assert isinstance(outcome, NothingToProduce)


# --------------------------------------------------------------------------------------
# Error case — `knowledge_action` equal to `primary` is refused at construction.
# --------------------------------------------------------------------------------------


def test_a_knowledge_action_equal_to_primary_is_refused_at_construction() -> None:
    with pytest.raises(ValidationError, match="knowledge_action"):
        CorrectiveConfig(primary="vector-top-k", knowledge_action="vector-top-k")


def test_config_has_no_default_for_knowledge_action() -> None:
    with pytest.raises(ValidationError, match="knowledge_action"):
        CorrectiveConfig()  # type: ignore[call-arg]


def test_the_plugin_refuses_construction_with_no_config_by_name() -> None:
    # `factory(None)` is the one real caller that can reach this — `weft_kernel.runner.
    # _build`'s `fallback:` path, which carries no `with:` block by definition. This is what
    # makes 'corrective' unusable as a `fallback:` candidate a named, readable fact rather
    # than a bare pydantic ValidationError about a field the fallback list never mentioned.
    with pytest.raises(ValueError, match="knowledge_action"):
        Corrective(None)


# --------------------------------------------------------------------------------------
# Seam.
# --------------------------------------------------------------------------------------


async def test_driving_corrective_through_the_seam_produces_candidates() -> None:
    """Fitness function 7(b) against the one path a registered plugin is actually called
    through in production — `weft_kernel.seam.wrap`, not a direct method call."""
    origin = _asked()
    q1 = QuerySet(origin=origin, queries=(origin,))
    primary = _FakeRetriever(Produced(value=_candidates(origin, "a", "b", "c")))
    grader = _FakeGrader(keep=frozenset({"a", "b", "c"}))
    lookup = _StubLookup(primary, grader)
    retriever = Corrective(_config())
    wrapped = wrap(retriever.run, distribution="weft-retrieve", contract="Retriever", plugin=NAME)

    outcome = await wrapped(q1, _ctx(_services(lookup)))

    assert isinstance(outcome, Produced)
    assert isinstance(retriever, Retriever)


def test_the_declared_cost_bound_is_one_and_unbounded() -> None:
    assert Corrective.cost_bound == (1, -1)


def test_config_defaults_match_the_design_table() -> None:
    # `primary` and `grader` default to the single-pass baseline and to the plugin this
    # module's own naming condition is about — `knowledge_action` has no default at all
    # (checked separately, above), so it is the only field supplied here.
    config = CorrectiveConfig(knowledge_action="a-distinct-retriever")
    assert config.primary == "vector-top-k"
    assert config.grader == "graded-retrieval"
    assert config.trigger_kept_below == 3
    assert config.primary_config is None
    assert config.grader_config is None
    assert config.knowledge_action_config is None
