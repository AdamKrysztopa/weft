"""A router that cites evidence is held to it when it is loaded, not only when the gate runs.

`weft_eval.eligibility` is what fitness function 38 holds every shipped router to; a router a
project derives never reaches that gate, so `weft_cli.evidence_guard` runs the same rules over it
as `weft route explain` and `weft ask` resolve it.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from weft_cli.evidence_guard import (
    UnsupportedEvidenceError,
    guard_claims,
    refuse_unsupported_evidence,
)
from weft_eval.claims import Claim, load_claims, shipped_claims_dir
from weft_kernel.resolution import ResolvedPipeline, ResolvedStage
from weft_retrieve.policy import EvidencePolicyConfig

_BELOW_MARGIN = "enrich-with-raptor.global.answer-correctness"
_WORTHWHILE = (
    "whole-corpus.fetch-operator.answer-correctness",
    "whole-corpus.global.answer-correctness",
)


def _rule(**overrides: Any) -> dict[str, Any]:
    rule: dict[str, Any] = {
        "name": "whole-corpus-when-it-fits",
        "when": [
            {"feature": "corpus.base_complete", "op": "eq", "value": True},
            {"feature": "corpus.fits_context", "op": "eq", "value": True},
            {"feature": "corpus.leaf_tokens", "op": "gte", "value": 200000},
            {"feature": "corpus.leaf_tokens", "op": "lte", "value": 260000},
        ],
        "then": "whole-corpus-wide-then-generate",
        "cites": list(_WORTHWHILE),
    }
    return {**rule, **overrides}


def _router(*rules: dict[str, Any], use: str = "evidence-policy") -> ResolvedPipeline:
    config = EvidencePolicyConfig.model_validate(
        {"fallback": "retrieve-then-generate", "defaults": list(rules)}
    )
    stage = ResolvedStage(
        id="decide",
        contract="RoutingPolicy",
        use=use,
        config=config,
        distribution="weft-rag",
        provenance="derived",
    )
    return ResolvedPipeline(name="derived", stages=(stage,))


@pytest.fixture(scope="module")
def claims() -> tuple[Claim, ...]:
    return load_claims(shipped_claims_dir())


def test_the_shipped_claims_are_found_and_the_cited_ones_are_worthwhile(
    claims: tuple[Claim, ...],
) -> None:
    # Arrange
    by_id: Mapping[str, Claim] = {claim.id: claim for claim in claims}

    # Assert
    assert len(claims) > 40
    assert all(by_id[cited].adoptable_for_routing for cited in _WORTHWHILE)
    assert not by_id[_BELOW_MARGIN].adoptable_for_routing


def test_a_derived_router_that_cites_a_supported_claim_pair_loads(
    claims: tuple[Claim, ...],
) -> None:
    # Act / Assert
    refuse_unsupported_evidence(_router(_rule()), claims)


def test_a_derived_router_citing_a_positive_effect_below_its_margin_is_refused(
    claims: tuple[Claim, ...],
) -> None:
    # Arrange — RAPTOR's +0.025 is real and below the pre-registered 0.05.
    router = _router(_rule(then="enrich-with-raptor", cites=[_BELOW_MARGIN, _WORTHWHILE[0]]))

    # Act
    with pytest.raises(UnsupportedEvidenceError) as raised:
        refuse_unsupported_evidence(router, claims)

    # Assert
    assert _BELOW_MARGIN in str(raised.value)
    assert "positive-below-margin" in str(raised.value)


def test_a_claim_nobody_stated_is_refused_naming_the_claims_that_would_do(
    claims: tuple[Claim, ...],
) -> None:
    # Arrange
    router = _router(_rule(cites=["whole-corpus.made-up", _WORTHWHILE[0]]))

    # Act
    with pytest.raises(UnsupportedEvidenceError) as raised:
        refuse_unsupported_evidence(router, claims)

    # Assert
    assert "'whole-corpus.made-up', which is not a known claim" in str(raised.value)
    assert _WORTHWHILE[1] in str(raised.value)


def test_a_rule_that_does_not_carry_the_regime_of_its_claim_is_refused(
    claims: tuple[Claim, ...],
) -> None:
    # Arrange — the claims were measured on a complete corpus.
    when = [
        {"feature": "corpus.fits_context", "op": "eq", "value": True},
        {"feature": "corpus.leaf_tokens", "op": "lte", "value": 260000},
    ]

    # Act
    with pytest.raises(UnsupportedEvidenceError) as raised:
        refuse_unsupported_evidence(_router(_rule(when=when)), claims)

    # Assert
    assert "corpus.base_complete" in str(raised.value)


def test_every_problem_is_named_in_one_refusal(claims: tuple[Claim, ...]) -> None:
    # Arrange
    router = _router(
        _rule(name="one", cites=["no.such.claim", _WORTHWHILE[0]]),
        _rule(name="two", cites=[_BELOW_MARGIN, _WORTHWHILE[0]]),
    )

    # Act
    with pytest.raises(UnsupportedEvidenceError) as raised:
        refuse_unsupported_evidence(router, claims)

    # Assert
    assert "rule 'one'" in str(raised.value)
    assert "rule 'two'" in str(raised.value)


def test_a_router_with_no_evidence_policy_stage_is_not_asked_anything(
    claims: tuple[Claim, ...],
) -> None:
    # Act / Assert — `threshold-ladder` cites nothing, so there is nothing to hold it to.
    stage = ResolvedStage(
        id="decide",
        contract="RoutingPolicy",
        use="threshold-ladder",
        distribution="weft-rag",
        provenance="derived",
    )
    refuse_unsupported_evidence(ResolvedPipeline(name="ladder", stages=(stage,)), claims)


def test_a_project_directory_of_claims_adds_to_the_shipped_ones(tmp_path: Path) -> None:
    # Arrange
    project = tmp_path / "eval" / "claims"
    project.mkdir(parents=True)

    # Act
    loaded = guard_claims(tmp_path)

    # Assert — an empty project directory leaves exactly the shipped set.
    assert {claim.id for claim in loaded} == {
        claim.id for claim in load_claims(shipped_claims_dir())
    }
