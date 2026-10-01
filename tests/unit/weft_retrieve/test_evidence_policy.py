"""Task 44.21 — `evidence-policy`, a routing policy whose every rule cites the claim behind it.

Mirrors `packages/weft-rag/src/weft_retrieve/policy.py`. Rules are first-match, exceptions before
defaults; a rule that held but cannot be used is skipped with its reason recorded in
`Route.reasons`; nothing matching falls to the fallback; a fallback that is not offered is refused
naming what is. The policy is configured through the model a pipeline document's `with:` block is
validated against, never a hand-built shape.
"""

import itertools
from collections.abc import Mapping

import pytest
from pydantic import ValidationError

from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Failed, Outcome, Produced
from weft_kernel.seam import wrap
from weft_retrieve.contract import RouteCatalogue, RoutingPolicy
from weft_retrieve.payload import Query, Route, RouteCandidate, RuleOutcome, Scorecard
from weft_retrieve.policy import (
    EVIDENCE_POLICY_NAME,
    EvidencePolicy,
    EvidencePolicyConfig,
    PromptCost,
)

WHOLE = "whole-corpus-then-generate"
DENSE = "retrieve-then-generate"
GRAPH = "graph-2hop-then-generate"


class _StubCatalogue:
    """A `RouteCatalogue` reporting exactly the candidates it was built with."""

    def __init__(self, names: tuple[str, ...]) -> None:
        self._candidates = tuple(RouteCandidate(name=name) for name in names)

    def candidates(self) -> tuple[RouteCandidate, ...]:
        return self._candidates

    def names(self) -> frozenset[str]:
        return frozenset(candidate.name for candidate in self._candidates)


def _ctx(offered: tuple[str, ...] = (WHOLE, DENSE, GRAPH)) -> Context:
    services = ServiceRegistry()
    services.add(RouteCatalogue, _StubCatalogue(offered))
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


def _card(features: Mapping[str, int | float | bool]) -> Scorecard:
    return Scorecard(query=Query(text="a profiled question"), scores={}, features=features)


def _rule(
    name: str,
    then: str,
    *,
    feature: str = "corpus.fits_context",
    op: str = "eq",
    value: float | bool = True,  # noqa: FBT001
    cites: tuple[str, ...] = ("claim.one",),
    prompt_tokens: int | str | None = None,
    model_calls: int | None = None,
) -> dict[str, object]:
    rule: dict[str, object] = {
        "name": name,
        "when": [{"feature": feature, "op": op, "value": value}],
        "then": then,
        "cites": list(cites),
    }
    if prompt_tokens is not None:
        rule["prompt_tokens"] = prompt_tokens
    if model_calls is not None:
        rule["model_calls"] = model_calls
    return rule


def _config(
    *,
    exceptions: list[dict[str, object]] | None = None,
    defaults: list[dict[str, object]] | None = None,
    fallback: str = DENSE,
    constraints: dict[str, int] | None = None,
) -> EvidencePolicyConfig:
    return EvidencePolicyConfig.model_validate(
        {
            "exceptions": exceptions or [],
            "defaults": defaults or [],
            "fallback": fallback,
            "constraints": constraints or {},
        }
    )


async def _route(
    config: EvidencePolicyConfig,
    card: Scorecard,
    offered: tuple[str, ...] = (WHOLE, DENSE, GRAPH),
) -> Outcome[Route]:
    return await EvidencePolicy(config).run(card, _ctx(offered))


async def test_the_first_holding_exception_beats_a_default_that_also_holds() -> None:
    # Arrange
    config = _config(
        exceptions=[_rule("exception", GRAPH)],
        defaults=[_rule("default", WHOLE)],
    )

    # Act
    outcome = await _route(config, _card({"corpus.fits_context": True}))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.pipeline == GRAPH
    assert outcome.value.outcome is RuleOutcome.MATCHED
    assert outcome.value.rule == "exception"


async def test_a_chosen_rule_reports_the_claims_it_cites_and_the_rung_to_fall_back_to() -> None:
    # Arrange
    config = _config(defaults=[_rule("small", WHOLE, cites=("c.one", "c.two"))])

    # Act
    outcome = await _route(config, _card({"corpus.fits_context": True}))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.claims == ("c.one", "c.two")
    assert outcome.value.fallback == DENSE
    assert any("small" in reason for reason in outcome.value.reasons)


async def test_no_rule_holding_routes_to_the_fallback_as_fell_through() -> None:
    # Arrange
    config = _config(defaults=[_rule("small", WHOLE)])

    # Act
    outcome = await _route(config, _card({"corpus.fits_context": False}))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.pipeline == DENSE
    assert outcome.value.outcome is RuleOutcome.FELL_THROUGH
    assert outcome.value.claims == ()
    assert outcome.value.fallback is None


async def test_a_rule_whose_rung_is_not_offered_is_skipped_and_says_so() -> None:
    # Arrange — the rung is named by the first rule and absent from the catalogue.
    config = _config(
        defaults=[_rule("needs-graph", GRAPH), _rule("small", WHOLE)],
    )

    # Act
    outcome = await _route(config, _card({"corpus.fits_context": True}), offered=(WHOLE, DENSE))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.pipeline == WHOLE
    assert any(GRAPH in reason and "not offered" in reason for reason in outcome.value.reasons)


@pytest.mark.parametrize(
    ("leaf_tokens", "chosen"),
    [(90_000, WHOLE), (100_000, WHOLE), (100_001, DENSE)],
)
async def test_a_corpus_cost_rule_is_skipped_when_the_corpus_breaks_the_token_budget(
    leaf_tokens: int, chosen: str
) -> None:
    # Arrange
    config = _config(
        defaults=[_rule("small", WHOLE, prompt_tokens="corpus")],
        constraints={"max_prompt_tokens": 100_000},
    )

    # Act
    outcome = await _route(
        config, _card({"corpus.fits_context": True, "corpus.leaf_tokens": leaf_tokens})
    )

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.pipeline == chosen
    if chosen == DENSE:
        assert any("max_prompt_tokens" in reason for reason in outcome.value.reasons)


async def test_a_corpus_cost_rule_with_an_unknown_corpus_size_is_skipped_under_a_budget() -> None:
    # Arrange — `corpus.leaf_tokens` is omitted when unknown; an unknown cost is not a cheap one.
    config = _config(
        defaults=[_rule("small", WHOLE, prompt_tokens="corpus")],
        constraints={"max_prompt_tokens": 100_000},
    )

    # Act
    outcome = await _route(config, _card({"corpus.fits_context": True}))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.pipeline == DENSE
    assert any("unknown" in reason for reason in outcome.value.reasons)


async def test_a_corpus_cost_rule_with_no_budget_is_chosen_whatever_the_size() -> None:
    # Arrange
    config = _config(defaults=[_rule("small", WHOLE, prompt_tokens="corpus")])

    # Act
    outcome = await _route(config, _card({"corpus.fits_context": True}))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.pipeline == WHOLE


async def test_a_fixed_cost_and_a_model_call_count_are_held_to_their_constraints() -> None:
    # Arrange
    config = _config(
        defaults=[
            _rule("dear", WHOLE, prompt_tokens=50_000),
            _rule("chatty", GRAPH, model_calls=8),
        ],
        constraints={"max_prompt_tokens": 10_000, "max_model_calls": 4},
    )

    # Act
    outcome = await _route(config, _card({"corpus.fits_context": True}))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.pipeline == DENSE
    assert any("max_prompt_tokens" in reason for reason in outcome.value.reasons)
    assert any("max_model_calls" in reason for reason in outcome.value.reasons)


async def test_a_fallback_that_is_not_offered_is_refused_naming_what_is() -> None:
    # Arrange
    config = _config(defaults=[_rule("small", WHOLE)], fallback=DENSE)

    # Act
    outcome = await _route(config, _card({"corpus.fits_context": False}), offered=(WHOLE, GRAPH))

    # Assert
    assert isinstance(outcome, Failed)
    assert DENSE in outcome.reason
    assert GRAPH in outcome.reason
    assert WHOLE in outcome.reason


async def test_a_misspelt_feature_in_a_rule_is_refused_naming_the_valid_ones() -> None:
    # Arrange
    config = _config(defaults=[_rule("typo", WHOLE, feature="corpus.fits_contxt")])

    # Act
    outcome = await _route(config, _card({"corpus.documents": 3}))

    # Assert
    assert isinstance(outcome, Failed)
    assert "corpus.fits_contxt" in outcome.reason
    assert "corpus.fits_context" in outcome.reason


async def test_a_declared_feature_the_corpus_does_not_report_holds_no_rule() -> None:
    # Arrange
    config = _config(defaults=[_rule("small", WHOLE)])

    # Act
    outcome = await _route(config, _card({"corpus.documents": 3}))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.pipeline == DENSE


def test_a_rule_that_cites_no_claim_is_refused() -> None:
    # Act / Assert
    with pytest.raises(ValidationError, match="cites"):
        _config(defaults=[_rule("uncited", WHOLE, cites=())])


def test_a_rule_name_is_unique_across_exceptions_and_defaults() -> None:
    # Act / Assert
    with pytest.raises(ValidationError, match="distinct"):
        _config(exceptions=[_rule("same", GRAPH)], defaults=[_rule("same", WHOLE)])


def test_prompt_cost_is_a_fixed_integer_or_the_corpus_member() -> None:
    # Act
    config = _config(
        defaults=[_rule("a", WHOLE, prompt_tokens="corpus"), _rule("b", GRAPH, prompt_tokens=7)]
    )

    # Assert
    assert config.defaults[0].prompt_tokens is PromptCost.CORPUS
    assert config.defaults[1].prompt_tokens == 7
    with pytest.raises(ValidationError):
        _config(defaults=[_rule("c", WHOLE, prompt_tokens="cheap")])


async def test_reachable_is_every_rule_rung_plus_the_fallback_whatever_is_installed() -> None:
    # Arrange
    policy = EvidencePolicy(_config(exceptions=[_rule("e", GRAPH)], defaults=[_rule("d", WHOLE)]))

    # Act
    reachable = await policy.reachable(())

    # Assert
    assert reachable == frozenset({GRAPH, WHOLE, DENSE})


@pytest.mark.parametrize("fits", [True, False])
async def test_the_decision_is_always_an_offered_rung_or_a_refusal_over_every_catalogue(
    *, fits: bool
) -> None:
    # Arrange
    config = _config(
        exceptions=[_rule("e", GRAPH)],
        defaults=[_rule("d", WHOLE, prompt_tokens="corpus")],
        constraints={"max_prompt_tokens": 100},
    )
    card = _card({"corpus.fits_context": fits, "corpus.leaf_tokens": 50})
    rungs = (WHOLE, DENSE, GRAPH, "other")

    # Act / Assert
    for size in range(len(rungs) + 1):
        for offered in itertools.combinations(rungs, size):
            outcome = await _route(config, card, offered=offered)
            if isinstance(outcome, Produced):
                assert outcome.value.pipeline in offered, offered
            else:
                assert isinstance(outcome, Failed), offered


async def test_driving_evidence_policy_through_the_seam_produces_a_route() -> None:
    # Arrange
    policy = EvidencePolicy(_config(defaults=[_rule("small", WHOLE)]))
    wrapped = wrap(
        policy.run,
        distribution="weft-retrieve",
        contract="RoutingPolicy",
        plugin=EVIDENCE_POLICY_NAME,
    )

    # Act
    outcome = await wrapped(_card({"corpus.fits_context": True}), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert isinstance(policy, RoutingPolicy)
    assert EVIDENCE_POLICY_NAME == "evidence-policy"


async def test_a_decision_carries_the_facts_it_turned_on_and_no_others() -> None:
    # Arrange — the card also states a query feature no rule tests; it is not the decision's.
    config = _config(
        defaults=[_rule("small", WHOLE, prompt_tokens="corpus")],
        constraints={"max_prompt_tokens": 300_000},
    )
    card = _card(
        {"corpus.fits_context": True, "corpus.leaf_tokens": 250_000, "query.word_count": 7}
    )

    # Act
    outcome = await _route(config, card)

    # Assert
    assert isinstance(outcome, Produced)
    assert dict(outcome.value.facts) == {"corpus.fits_context": True}
    assert outcome.value.unstated == ()
    assert dict(outcome.value.constraints) == {"max_prompt_tokens": 300_000}


async def test_a_fact_the_profile_did_not_state_is_named_as_unstated_not_as_false() -> None:
    # Arrange — a rule keyed to a feature the corpus omitted holds nothing, and says why.
    config = _config(
        defaults=[_rule("sized", WHOLE, feature="corpus.leaf_tokens", op="lte", value=1)]
    )

    # Act
    outcome = await _route(config, _card({"corpus.fits_context": True}))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.outcome is RuleOutcome.FELL_THROUGH
    assert outcome.value.unstated == ("corpus.leaf_tokens",)
    assert "corpus.leaf_tokens" not in outcome.value.facts


async def test_a_fell_through_decision_still_shows_the_facts_every_rule_was_judged_on() -> None:
    # Arrange
    config = _config(
        exceptions=[_rule("a", GRAPH, feature="corpus.base_complete")],
        defaults=[_rule("b", WHOLE)],
    )

    # Act
    outcome = await _route(
        config, _card({"corpus.base_complete": False, "corpus.fits_context": False})
    )

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.outcome is RuleOutcome.FELL_THROUGH
    assert dict(outcome.value.facts) == {
        "corpus.base_complete": False,
        "corpus.fits_context": False,
    }


async def test_the_rules_digest_moves_with_a_rule_a_threshold_or_a_ceiling_and_nothing_else() -> (
    None
):
    # Arrange
    def digest_of(config: EvidencePolicyConfig) -> str:
        return EvidencePolicy(config).digest

    base = _config(defaults=[_rule("r", WHOLE, value=True)], constraints={"max_prompt_tokens": 1})

    # Act / Assert
    assert digest_of(base) == digest_of(
        _config(defaults=[_rule("r", WHOLE, value=True)], constraints={"max_prompt_tokens": 1})
    )
    assert digest_of(base) != digest_of(
        _config(defaults=[_rule("r", WHOLE, value=False)], constraints={"max_prompt_tokens": 1})
    )
    assert digest_of(base) != digest_of(
        _config(defaults=[_rule("r", WHOLE, value=True)], constraints={"max_prompt_tokens": 2})
    )
    assert digest_of(base) != digest_of(
        _config(
            defaults=[_rule("r", WHOLE, cites=("claim.two",))], constraints={"max_prompt_tokens": 1}
        )
    )


async def test_the_receipt_reaches_the_route_view_and_the_policy_span() -> None:
    # Arrange
    config = _config(
        defaults=[_rule("small", WHOLE, prompt_tokens="corpus")],
        constraints={"max_prompt_tokens": 300_000},
    )

    # Act
    outcome = await _route(
        config, _card({"corpus.fits_context": True, "corpus.leaf_tokens": 250_000})
    )

    # Assert
    assert isinstance(outcome, Produced)
    route = outcome.value
    view = route.view()
    assert (dict(view.facts), dict(view.constraints), view.policy) == (
        dict(route.facts),
        dict(route.constraints),
        route.policy,
    )
    assert len(route.policy) == 16
    attributes = route.telemetry_attributes()
    assert attributes["weft.route.claims"] == "claim.one"
    assert attributes["weft.route.fallback"] == DENSE
    assert attributes["weft.route.policy"] == route.policy
    assert attributes["weft.route.constraint.max_prompt_tokens"] == 300_000
