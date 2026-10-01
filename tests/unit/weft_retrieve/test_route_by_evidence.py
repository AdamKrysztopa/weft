"""Task 44.24 — the shipped `route-by-evidence` document routes as its comments say it does.

The policy configuration is read out of the shipped document itself, never rebuilt by hand, so a
rule edited in the YAML is the rule exercised here.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Produced, SourceId
from weft_retrieve.contract import RouteCatalogue
from weft_retrieve.payload import Query, RouteCandidate, RuleOutcome, Scorecard
from weft_retrieve.policy import EvidencePolicy, EvidencePolicyConfig
from weft_retrieve.profile import corpus_profile
from weft_store import SourceRecord, SourceStats, SourceStatus

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


class _WithheldWhole:
    """A catalogue that left the whole-corpus rung out and kept the reason."""

    def candidates(self) -> tuple[RouteCandidate, ...]:
        return (RouteCandidate(name=DENSE),)

    def names(self) -> frozenset[str]:
        return frozenset({DENSE})

    def withheld_reason(self, name: str) -> str | None:
        return "its 'generate' role's provider cannot count tokens" if name == WHOLE else None


def _config(budget: int | None = None) -> EvidencePolicyConfig:
    loaded: Any = yaml.safe_load(DOCUMENT.read_text(encoding="utf-8"))
    decide = next(stage for stage in loaded["stages"] if stage["id"] == "decide")
    config: dict[str, Any] = dict(decide["with"])
    if budget is not None:
        config["constraints"] = {"max_prompt_tokens": budget}
    return EvidencePolicyConfig.model_validate(config)


def _ctx(catalogue: RouteCatalogue | None = None) -> Context:
    services = ServiceRegistry()
    services.add(RouteCatalogue, _Catalogue() if catalogue is None else catalogue)
    return Context(tenant_id="t", run_id="r", trace_id="x", locale="en", services=services)


def _card(
    *, tokens: int | None, fits: bool | None = True, base_complete: bool | None = True
) -> Scorecard:
    features: dict[str, int | float | bool] = {}
    if base_complete is not None:
        features["corpus.base_complete"] = base_complete
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
    ("tokens", "fits", "complete"),
    [
        (50_000, True, True),
        (261_000, True, True),
        (253_408, False, True),
        (253_408, None, True),
        (None, True, True),
        (253_408, True, False),
        (253_408, True, None),
    ],
)
async def test_outside_the_measured_regime_it_is_one_search_even_with_a_budget(
    *, tokens: int | None, fits: bool | None, complete: bool | None
) -> None:
    # Act
    pipeline, _, _ = await _pipeline(
        _config(budget=10_000_000), _card(tokens=tokens, fits=fits, base_complete=complete)
    )

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


def _records(*statuses: SourceStatus) -> tuple[SourceRecord, ...]:
    now = datetime.now(UTC)
    return tuple(
        SourceRecord(
            id=SourceId(f"s{index}"),
            uri=f"file:///s{index}.txt",
            content_hash=f"s{index}",
            indexed_at=now,
            pipeline="index-text",
            status=status,
            stats=SourceStats(leaves=10, characters=1000, tokens=126_704, tokenizer="luna"),
        )
        for index, status in enumerate(statuses)
    )


async def _routed(records: tuple[SourceRecord, ...]) -> tuple[str, RuleOutcome]:
    features = corpus_profile(records, context_tokens=300_000).features()
    card = Scorecard(query=Query(text="q"), scores={}, features=features)
    outcome = await EvidencePolicy(_config(budget=300_000)).run(card, _ctx())
    assert isinstance(outcome, Produced)
    return outcome.value.pipeline, outcome.value.outcome


async def test_fast_track_state_decides_whether_the_complete_corpus_rule_may_fire() -> None:
    # Arrange — 253,408 tokens across two sources: the size the claims were measured at.
    complete = _records(SourceStatus.ACTIVE, SourceStatus.ACTIVE)
    one_still_indexing = _records(SourceStatus.ACTIVE, SourceStatus.ACTIVE, SourceStatus.INDEXING)
    one_failed = _records(SourceStatus.ACTIVE, SourceStatus.ACTIVE, SourceStatus.FAILED)

    # Act / Assert
    assert await _routed(complete) == (WHOLE, RuleOutcome.MATCHED)
    assert await _routed(one_still_indexing) == (DENSE, RuleOutcome.FELL_THROUGH)
    assert await _routed(one_failed) == (DENSE, RuleOutcome.FELL_THROUGH)


async def test_the_partial_corpus_becomes_eligible_the_moment_it_completes() -> None:
    # Arrange
    during = _records(SourceStatus.ACTIVE, SourceStatus.ACTIVE, SourceStatus.INDEXING)
    after = _records(SourceStatus.ACTIVE, SourceStatus.ACTIVE)

    # Act
    before_route = await _routed(during)
    after_route = await _routed(after)

    # Assert
    assert before_route[0] == DENSE
    assert after_route[0] == WHOLE


async def test_a_rung_the_catalogue_withheld_is_skipped_with_the_reason_it_kept() -> None:
    # Arrange — everything holds; only the provider's missing count keeps the rung out.
    ctx = _ctx(_WithheldWhole())

    # Act
    outcome = await EvidencePolicy(_config(budget=300_000)).run(_card(tokens=253_408), ctx)

    # Assert
    assert isinstance(outcome, Produced)
    assert (outcome.value.pipeline, outcome.value.outcome) == (DENSE, RuleOutcome.FELL_THROUGH)
    reasons = " ".join(outcome.value.reasons)
    assert f"rung '{WHOLE}' is not offered" in reasons
    assert "provider cannot count tokens" in reasons
