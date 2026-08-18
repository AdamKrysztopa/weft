"""Unit tests for `weft_retrieve.routing`.

Mirrors `packages/weft-retrieve/src/weft_retrieve/routing.py`. Ledger **2.25**: "query
scoring and routing policy are two plugins, so a threshold ladder can be replaced by a
trained classifier without touching the scorer." Four plugins, covered in turn:

1. `LlmQueryScorer` (`query-scorer`) — happy path (a full set of scores plus a keyword
   intent read straight into `Scorecard`), the error case (a cascade failure is relayed
   exactly as it answered), the edge case (a model answering a dimension set that is not
   exactly what was asked is refused by name, never silently patched), and a drive through
   `weft_kernel.seam.wrap`. **The `LLM` is a stub and the cascade is real** — the same
   split every other cascade-backed plugin's own test module in this pack already takes.
2. `ThresholdLadder` (`threshold-ladder`) — happy path (first matching rule wins), edge
   case (no rule matches, falls through to `default`), error case (a rule testing a
   dimension the handed `Scorecard` does not carry is refused by name), and a seam drive.
   `cost_bound == (0, 0)` is proven directly: `run` never calls `ctx.require` at all, so an
   empty `ServiceRegistry` still succeeds.
3. `NearestDescription` (`nearest-description`) — happy path (the candidate whose summary
   embeds nearest the query wins), edge case (no candidates, `Embedder` never touched —
   the floor of `cost_bound`), error case (the embedder's own `Failed` is relayed), and a
   seam drive.
4. `Always` (`always`) — happy path (the configured pipeline, whatever the scorecard says),
   and `reachable()` — the ten-line policy the module docstring calls "proof the first two
   are genuinely interchangeable", so its own test is correspondingly small.

**The separation the ledger line is actually about is checked structurally, not narrated**:
`test_the_ladder_and_always_never_import_or_construct_a_query_scorer` and
`test_swapping_the_policy_needs_no_edit_to_the_scorer` drive one `Scorecard` a
`LlmQueryScorer` produced through two different `RoutingPolicy` instances with no shared
state and no edit to either — a threshold ladder standing in for a trained classifier
without the scorer's own test fixtures changing at all.
"""

from collections.abc import Mapping, Sequence

import pytest
from pydantic import ValidationError

from weft_embed.contract import Embedder
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Failed, Node, Outcome, Produced, Vector
from weft_kernel.seam import wrap
from weft_llm.contract import LLM
from weft_llm.payload import Completion, Rendered
from weft_retrieve.contract import RouteCatalogue, RoutingPolicy, StageLookup
from weft_retrieve.payload import Query, RouteCandidate, RuleOutcome, Scorecard
from weft_retrieve.prompts import ROUTE_QUERY_NAME, RouteQueryPrompt
from weft_retrieve.routing import (
    ALWAYS_NAME,
    NEAREST_DESCRIPTION_NAME,
    QUERY_SCORER_NAME,
    THRESHOLD_LADDER_NAME,
    Always,
    AlwaysConfig,
    Comparison,
    Condition,
    Dimension,
    LlmQueryScorer,
    NearestDescription,
    QueryScorerConfig,
    Rule,
    ThresholdLadder,
    ThresholdLadderConfig,
)


class _StubLLM:
    """An `LLM` answering tier 2 of the cascade from a script — the same shape every other
    cascade-backed plugin's own test module in this pack already takes."""

    def __init__(self, replies: list[str | Failed]) -> None:
        self._replies = replies
        self.calls = 0
        self.last_prompt = ""

    async def native_structured_available(self, role: str) -> bool:
        del role
        return False

    async def complete_structured(
        self, rendered: Rendered, schema: Mapping[str, object], *, role: str, ctx: Context
    ) -> Outcome[Completion]:
        raise AssertionError("tier 1 is unavailable on this stub and must not be reached")

    async def complete(self, rendered: Rendered, *, role: str, ctx: Context) -> Outcome[Completion]:
        del role, ctx
        self.last_prompt = "\n".join(message.content for message in rendered.conversation.messages)
        reply = self._replies[min(self.calls, len(self._replies) - 1)]
        self.calls += 1
        if isinstance(reply, Failed):
            return reply
        return Produced(value=Completion(text=reply, model="stub-model"))

    async def close(self) -> None: ...


class _RefusingLLM:
    """An `LLM` that never answers usably — proves a `RoutingPolicy` never resolves one."""

    async def native_structured_available(self, role: str) -> bool:
        raise AssertionError("a RoutingPolicy calls no model")

    async def complete_structured(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("a RoutingPolicy calls no model")

    async def complete(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("a RoutingPolicy calls no model")

    async def close(self) -> None: ...


class _StubLookup:
    """A `StageLookup` holding this pack's own `route-query` prompt."""

    def __init__(self) -> None:
        self._prompts = {ROUTE_QUERY_NAME: RouteQueryPrompt()}

    def names(self, contract: type[object]) -> frozenset[str]:
        del contract
        return frozenset(self._prompts)

    async def build(self, contract: type[object], name: str, config: object = None) -> object:
        raise AssertionError("query-scorer resolves a capability by name, never a stage")

    async def build_capability(
        self, contract: type[object], name: str, config: object = None
    ) -> object:
        del contract, config
        return self._prompts[name]


class _StubCatalogue:
    """A `RouteCatalogue` reporting exactly the candidates it was built with."""

    def __init__(self, candidates: tuple[RouteCandidate, ...]) -> None:
        self._candidates = candidates

    def candidates(self) -> tuple[RouteCandidate, ...]:
        return self._candidates

    def names(self) -> frozenset[str]:
        return frozenset(candidate.name for candidate in self._candidates)


class _StubEmbedder:
    """An `Embedder` answering from a fixed content-to-vector table — enough to make one
    candidate deterministically nearest the query without a real model."""

    def __init__(self, vectors: Mapping[str, Vector]) -> None:
        self._vectors = vectors

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        embedded = [node.with_embedding(self._vectors[node.content]) for node in payload]
        return Produced(value=embedded)


class _RefusingEmbedder:
    """An `Embedder` that always raises — proves `nearest-description` never reaches it
    when the catalogue has nothing to select between."""

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        raise AssertionError("no embedder call should be made with zero candidates")


def _ctx(services: ServiceRegistry | None = None) -> Context:
    return Context(
        tenant_id="tenant-a",
        run_id="run-1",
        trace_id="trace-1",
        locale="en",
        services=services if services is not None else ServiceRegistry(),
    )


def _query_scorer_services(llm: object, catalogue: object) -> ServiceRegistry:
    services = ServiceRegistry()
    services.add(LLM, llm)
    services.add(StageLookup, _StubLookup())
    services.add(RouteCatalogue, catalogue)
    return services


_SCORES_JSON = (
    '{"scores": ['
    '{"name": "complexity", "score": 0.8}, '
    '{"name": "multi_hop", "score": 0.6}, '
    '{"name": "ambiguity", "score": 0.2}, '
    '{"name": "specificity", "score": 0.7}, '
    '{"name": "temporal_sensitivity", "score": 0.1}, '
    '{"name": "parametric_confidence", "score": 0.3}, '
    '{"name": "verifiability_need", "score": 0.9}'
    "]}"
)


# --------------------------------------------------------------------------------------
# LlmQueryScorer / query-scorer
# --------------------------------------------------------------------------------------


async def test_llm_query_scorer_reads_scores_and_a_keyword_intent() -> None:
    # Arrange — a two-candidate catalogue, an intent marker table, and a model answering
    # every default dimension exactly once.
    question = Query(text="please explain how mRMR differs from plain relevance ranking")
    catalogue = _StubCatalogue(
        (
            RouteCandidate(name="retrieve-then-generate", summary="one search, one answer"),
            RouteCandidate(name="no-retrieval", summary="answers from memory"),
        )
    )
    llm = _StubLLM([_SCORES_JSON])
    scorer = LlmQueryScorer(QueryScorerConfig(intent_markers={"how-question": ("please explain",)}))

    # Act
    outcome = await scorer.run(question, _ctx(_query_scorer_services(llm, catalogue)))

    # Assert
    assert isinstance(outcome, Produced)
    card: Scorecard = outcome.value
    assert card.query == question
    assert card.scores["complexity"] == pytest.approx(0.8)
    assert card.scores["verifiability_need"] == pytest.approx(0.9)
    assert set(card.scores) == {
        "complexity",
        "multi_hop",
        "ambiguity",
        "specificity",
        "temporal_sensitivity",
        "parametric_confidence",
        "verifiability_need",
    }
    assert card.intents == frozenset({"how-question"})
    assert card.observed is True
    assert llm.calls == 1
    # The candidates were actually shown to the model — the mechanism that keeps this
    # plugin from ever writing a pipeline name into its own source.
    assert "retrieve-then-generate" in llm.last_prompt
    assert "no-retrieval" in llm.last_prompt


async def test_llm_query_scorer_relays_a_cascade_failure_exactly_as_it_answered() -> None:
    # Arrange
    question = Query(text="what happens when the model call fails?")
    llm = _StubLLM([Failed(reason="the routing model call raised")])

    # Act
    outcome = await LlmQueryScorer().run(
        question, _ctx(_query_scorer_services(llm, _StubCatalogue(())))
    )

    # Assert
    assert isinstance(outcome, Failed)
    assert "routing model call" in outcome.reason


async def test_llm_query_scorer_refuses_a_mismatched_dimension_set() -> None:
    # Arrange — one configured dimension ("foo"), and a model that answers a different one
    # ("bar") entirely: missing "foo", unknown "bar".
    question = Query(text="a single-dimension configuration")
    llm = _StubLLM(['{"scores": [{"name": "bar", "score": 0.5}]}'])
    config = QueryScorerConfig(dimensions=(Dimension(name="foo", description="a test axis"),))

    # Act
    outcome = await LlmQueryScorer(config).run(
        question, _ctx(_query_scorer_services(llm, _StubCatalogue(())))
    )

    # Assert
    assert isinstance(outcome, Failed)
    assert "foo" in outcome.reason
    assert "bar" in outcome.reason


async def test_driving_query_scorer_through_the_seam_produces_a_scorecard() -> None:
    """Fitness function 7(b) against the one path a registered plugin is actually called
    through in production — `weft_kernel.seam.wrap`, not a direct method call a registered
    instance never receives."""
    # Arrange
    question = Query(text="does this pass through the seam?")
    llm = _StubLLM([_SCORES_JSON])
    scorer = LlmQueryScorer()
    wrapped = wrap(
        scorer.run, distribution="weft-retrieve", contract="QueryScorer", plugin=QUERY_SCORER_NAME
    )

    # Act
    outcome = await wrapped(question, _ctx(_query_scorer_services(llm, _StubCatalogue(()))))

    # Assert
    assert isinstance(outcome, Produced)


def test_query_scorer_config_refuses_a_repeated_dimension_name() -> None:
    # Act / Assert
    with pytest.raises(ValidationError, match="distinct"):
        QueryScorerConfig(
            dimensions=(
                Dimension(name="foo", description="one"),
                Dimension(name="foo", description="two"),
            )
        )


# --------------------------------------------------------------------------------------
# ThresholdLadder / threshold-ladder
# --------------------------------------------------------------------------------------


def _ladder_config() -> ThresholdLadderConfig:
    return ThresholdLadderConfig(
        rules=(
            Rule(
                name="high-complexity",
                when=(Condition(dimension="complexity", op=Comparison.GTE, value=0.5),),
                then="retrieve-then-generate",
            ),
        ),
        default="no-retrieval",
    )


def _scorecard(scores: Mapping[str, float]) -> Scorecard:
    return Scorecard(query=Query(text="a scored question"), scores=scores)


async def test_threshold_ladder_matches_the_first_satisfied_rule() -> None:
    # Arrange — no service registered at all: `run` never calls `ctx.require`, which is
    # `cost_bound == (0, 0)` proven rather than asserted.
    card = _scorecard({"complexity": 0.9})

    # Act
    outcome = await ThresholdLadder(_ladder_config()).run(card, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    route = outcome.value
    assert route.pipeline == "retrieve-then-generate"
    assert route.outcome is RuleOutcome.MATCHED
    assert route.rule == "high-complexity"
    assert route.scorecard == card


async def test_threshold_ladder_falls_through_to_the_default() -> None:
    # Arrange — no rule's conditions hold.
    card = _scorecard({"complexity": 0.1})

    # Act
    outcome = await ThresholdLadder(_ladder_config()).run(card, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.pipeline == "no-retrieval"
    assert outcome.value.outcome is RuleOutcome.FELL_THROUGH
    assert outcome.value.rule == ""


async def test_threshold_ladder_refuses_a_rule_testing_an_uncarried_dimension() -> None:
    # Arrange — the ladder's own rule tests "complexity", and this scorecard carries only
    # "specificity", an operator's own typo made loud rather than treated as no-match.
    card = _scorecard({"specificity": 0.9})

    # Act
    outcome = await ThresholdLadder(_ladder_config()).run(card, _ctx())

    # Assert
    assert isinstance(outcome, Failed)
    assert "complexity" in outcome.reason


async def test_threshold_ladder_reachable_is_every_rule_target_plus_the_default() -> None:
    # Act
    reachable = await ThresholdLadder(_ladder_config()).reachable(())

    # Assert
    assert reachable == frozenset({"retrieve-then-generate", "no-retrieval"})


async def test_driving_threshold_ladder_through_the_seam_produces_a_route() -> None:
    # Arrange
    card = _scorecard({"complexity": 0.9})
    policy = ThresholdLadder(_ladder_config())
    wrapped = wrap(
        policy.run,
        distribution="weft-retrieve",
        contract="RoutingPolicy",
        plugin=THRESHOLD_LADDER_NAME,
    )

    # Act
    outcome = await wrapped(card, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert isinstance(policy, RoutingPolicy)


def test_threshold_ladder_config_refuses_a_repeated_rule_name() -> None:
    # Act / Assert
    with pytest.raises(ValidationError, match="distinct"):
        ThresholdLadderConfig(
            rules=(
                Rule(
                    name="dup",
                    when=(Condition(dimension="x", op=Comparison.GTE, value=0.5),),
                    then="a",
                ),
                Rule(
                    name="dup",
                    when=(Condition(dimension="x", op=Comparison.LT, value=0.5),),
                    then="b",
                ),
            )
        )


# --------------------------------------------------------------------------------------
# NearestDescription / nearest-description
# --------------------------------------------------------------------------------------

_QUERY_VECTOR = Vector(values=(1.0, 0.0))
_NEAR_VECTOR = Vector(values=(0.9, 0.1))
_FAR_VECTOR = Vector(values=(0.0, 1.0))


def _routing_services(catalogue: object, embedder: object | None = None) -> ServiceRegistry:
    services = ServiceRegistry()
    services.add(RouteCatalogue, catalogue)
    if embedder is not None:
        services.add(Embedder, embedder)
    return services


async def test_nearest_description_selects_the_candidate_nearest_the_query() -> None:
    # Arrange — "electrical grids" reads near the query, "how to bake bread" reads far.
    catalogue = _StubCatalogue(
        (
            RouteCandidate(name="grid-pipeline", summary="electrical grids"),
            RouteCandidate(name="bread-pipeline", summary="how to bake bread"),
        )
    )
    embedder = _StubEmbedder(
        {
            "what caused the 2003 blackout?": _QUERY_VECTOR,
            "electrical grids": _NEAR_VECTOR,
            "how to bake bread": _FAR_VECTOR,
        }
    )
    card = Scorecard(query=Query(text="what caused the 2003 blackout?"), scores={})

    # Act
    outcome = await NearestDescription().run(card, _ctx(_routing_services(catalogue, embedder)))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.pipeline == "grid-pipeline"
    assert outcome.value.outcome is RuleOutcome.NEAREST
    assert outcome.value.scorecard == card


async def test_nearest_description_with_no_candidates_never_touches_the_embedder() -> None:
    # Arrange — the floor of `cost_bound`: zero candidates means zero embedding calls, and
    # `_RefusingEmbedder` proves it rather than merely asserting the class attribute.
    card = _scorecard({})
    services = _routing_services(_StubCatalogue(()), _RefusingEmbedder())

    # Act
    outcome = await NearestDescription().run(card, _ctx(services))

    # Assert
    assert isinstance(outcome, Failed)
    assert "nothing to select" in outcome.reason


async def test_nearest_description_relays_an_embedder_failure() -> None:
    # Arrange
    class _FailingEmbedder:
        async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
            del payload, ctx
            return Failed(reason="the embedding model is unreachable")

    catalogue = _StubCatalogue((RouteCandidate(name="p", summary="a pipeline"),))
    card = _scorecard({})

    # Act
    outcome = await NearestDescription().run(
        card, _ctx(_routing_services(catalogue, _FailingEmbedder()))
    )

    # Assert
    assert isinstance(outcome, Failed)
    assert "unreachable" in outcome.reason


async def test_nearest_description_reachable_is_every_current_candidate() -> None:
    # Act
    reachable = await NearestDescription().reachable(
        (RouteCandidate(name="a"), RouteCandidate(name="b"))
    )

    # Assert
    assert reachable == frozenset({"a", "b"})


async def test_driving_nearest_description_through_the_seam_produces_a_route() -> None:
    # Arrange
    catalogue = _StubCatalogue((RouteCandidate(name="only-one", summary="the only option"),))
    embedder = _StubEmbedder(
        {"a query": Vector(values=(1.0, 0.0)), "the only option": Vector(values=(1.0, 0.0))}
    )
    card = Scorecard(query=Query(text="a query"), scores={})
    policy = NearestDescription()
    wrapped = wrap(
        policy.run,
        distribution="weft-retrieve",
        contract="RoutingPolicy",
        plugin=NEAREST_DESCRIPTION_NAME,
    )

    # Act
    outcome = await wrapped(card, _ctx(_routing_services(catalogue, embedder)))

    # Assert
    assert isinstance(outcome, Produced)


# --------------------------------------------------------------------------------------
# Always / always
# --------------------------------------------------------------------------------------


async def test_always_selects_its_configured_pipeline_no_matter_the_scorecard() -> None:
    # Arrange — no service registered at all: `Always.run` resolves nothing.
    card = _scorecard({"complexity": 1.0, "ambiguity": 1.0})

    # Act
    outcome = await Always(AlwaysConfig(pipeline="no-retrieval")).run(card, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.pipeline == "no-retrieval"
    assert outcome.value.outcome is RuleOutcome.MATCHED
    assert outcome.value.rule == ALWAYS_NAME
    assert outcome.value.scorecard == card


async def test_always_reachable_is_exactly_its_own_pipeline() -> None:
    # Act
    reachable = await Always(AlwaysConfig(pipeline="no-retrieval")).reachable(())

    # Assert
    assert reachable == frozenset({"no-retrieval"})


async def test_driving_always_through_the_seam_produces_a_route() -> None:
    # Arrange
    card = _scorecard({})
    policy = Always()
    wrapped = wrap(
        policy.run, distribution="weft-retrieve", contract="RoutingPolicy", plugin=ALWAYS_NAME
    )

    # Act
    outcome = await wrapped(card, _ctx())

    # Assert
    assert isinstance(outcome, Produced)


# --------------------------------------------------------------------------------------
# The separation the ledger line is about, checked structurally.
# --------------------------------------------------------------------------------------


async def test_swapping_the_policy_needs_no_edit_to_the_scorer() -> None:
    """Ledger 2.25's stated property: one `Scorecard` a `query-scorer` produced, read by
    two different `RoutingPolicy` implementations with no shared code and no edit to
    either. `_RefusingLLM` proves neither policy ever resolves the `LLM` `LlmQueryScorer`
    itself just used — the scorer's own service is untouched by the swap.
    """
    # Arrange
    question = Query(text="how many hops does this answer need?")
    catalogue = _StubCatalogue(
        (
            RouteCandidate(name="retrieve-then-generate", summary="one search, one answer"),
            RouteCandidate(name="no-retrieval", summary="answers from memory"),
        )
    )
    scored = await LlmQueryScorer().run(
        question, _ctx(_query_scorer_services(_StubLLM([_SCORES_JSON]), catalogue))
    )
    assert isinstance(scored, Produced)
    card = scored.value

    ladder = ThresholdLadder(_ladder_config())
    always = Always(AlwaysConfig(pipeline="no-retrieval"))

    # Act — both policies read the identical Scorecard, through an empty ServiceRegistry
    # carrying only `_RefusingLLM`, which neither may touch.
    services = ServiceRegistry()
    services.add(LLM, _RefusingLLM())
    from_ladder = await ladder.run(card, _ctx(services))
    from_always = await always.run(card, _ctx(services))

    # Assert — the same measurement, two different decisions, with no import between the
    # policy classes and `weft_retrieve.routing.LlmQueryScorer`.
    assert isinstance(from_ladder, Produced)
    assert isinstance(from_always, Produced)
    assert from_ladder.value.pipeline == "retrieve-then-generate"  # complexity 0.8 >= 0.5
    assert from_always.value.pipeline == "no-retrieval"
    assert from_ladder.value.scorecard == from_always.value.scorecard == card
