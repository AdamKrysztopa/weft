"""Task 44.24 — the shipped `route-by-evidence` document routes as its comments say it does.

The policy configuration is read out of the shipped document itself, never rebuilt by hand, so a
rule edited in the YAML is the rule exercised here.
"""

from pathlib import Path
from typing import Any

import pytest
import yaml

from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Produced
from weft_retrieve.contract import RouteCatalogue
from weft_retrieve.payload import Query, RouteCandidate, RuleOutcome, Scorecard
from weft_retrieve.policy import EvidencePolicy, EvidencePolicyConfig

DOCUMENT = (
    Path(__file__).resolve().parents[3]
    / "packages/weft-rag/src/weft_retrieve/pipelines/route-by-evidence.yaml"
)
WHOLE = "whole-corpus-wide-then-generate"
DENSE = "retrieve-then-generate"


class _Catalogue:
    def candidates(self) -> tuple[RouteCandidate, ...]:
        return tuple(RouteCandidate(name=name) for name in (WHOLE, DENSE))

    def names(self) -> frozenset[str]:
        return frozenset({WHOLE, DENSE})


def _config(budget: int | None = None) -> EvidencePolicyConfig:
    loaded: Any = yaml.safe_load(DOCUMENT.read_text(encoding="utf-8"))
    decide = next(stage for stage in loaded["stages"] if stage["id"] == "decide")
    config: dict[str, Any] = dict(decide["with"])
    if budget is not None:
        config["constraints"] = {"max_prompt_tokens": budget}
    return EvidencePolicyConfig.model_validate(config)


def _ctx() -> Context:
    services = ServiceRegistry()
    services.add(RouteCatalogue, _Catalogue())
    return Context(tenant_id="t", run_id="r", trace_id="x", locale="en", services=services)


def _card(*, tokens: int | None, fits: bool | None = True) -> Scorecard:
    features: dict[str, int | float | bool] = {}
    if tokens is not None:
        features["corpus.leaf_tokens"] = tokens
    if fits is not None:
        features["corpus.fits_context"] = fits
    return Scorecard(query=Query(text="q"), scores={}, features=features)


async def _pipeline(config: EvidencePolicyConfig, card: Scorecard) -> tuple[str, RuleOutcome, str]:
    outcome = await EvidencePolicy(config).run(card, _ctx())
    assert isinstance(outcome, Produced)
    route = outcome.value
    return route.pipeline, route.outcome, " ".join(route.reasons)


async def test_a_budget_that_holds_the_corpus_has_it_read_whole() -> None:
    # Act
    pipeline, outcome, _ = await _pipeline(_config(budget=300_000), _card(tokens=253_408))

    # Assert
    assert (pipeline, outcome) == (WHOLE, RuleOutcome.MATCHED)


async def test_shipped_with_no_budget_it_answers_through_one_search_and_says_why() -> None:
    # Act
    pipeline, outcome, reasons = await _pipeline(_config(), _card(tokens=253_408))

    # Assert
    assert (pipeline, outcome) == (DENSE, RuleOutcome.FELL_THROUGH)
    assert "max_prompt_tokens 0" in reasons


@pytest.mark.parametrize(
    ("tokens", "fits"),
    [(50_000, True), (261_000, True), (253_408, False), (253_408, None), (None, True)],
)
async def test_outside_the_measured_regime_it_is_one_search_even_with_a_budget(
    *, tokens: int | None, fits: bool | None
) -> None:
    # Act
    pipeline, _, _ = await _pipeline(_config(budget=10_000_000), _card(tokens=tokens, fits=fits))

    # Assert
    assert pipeline == DENSE


async def test_a_budget_below_the_corpus_keeps_the_rule_from_firing() -> None:
    # Act
    pipeline, _, reasons = await _pipeline(_config(budget=100_000), _card(tokens=253_408))

    # Assert
    assert pipeline == DENSE
    assert "max_prompt_tokens 100000" in reasons


async def test_the_chosen_route_carries_both_claims_and_the_fallback() -> None:
    # Act
    outcome = await EvidencePolicy(_config(budget=300_000)).run(_card(tokens=253_408), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.claims == (
        "whole-corpus.fetch-operator.answer-correctness",
        "whole-corpus.global.answer-correctness",
    )
    assert outcome.value.fallback == DENSE
