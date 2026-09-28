"""`query-profile` — the model-free scorer the default router uses. Task 44.12b.

It measures the question with `profile_query` and hands the features to the policy on the
`Scorecard`, keeping `keyword-intents`' configured intent markers, which it supersedes: neither was
ever released, so the fixed router moves to it and the old name goes. It calls no model and
reaches for no service.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from weft_cli.pipeline_catalogue import load_pipeline_document
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import Produced
from weft_kernel.registry import Registry
from weft_retrieve import (
    QUERY_PROFILE_NAME,
    QueryProfileScorer,
    QueryProfileScorerConfig,
    QueryScorer,
    Settings,
    register,
)
from weft_retrieve.payload import Query
from weft_retrieve.profile_cues import CueLexicon

_ROUTE_FIXED = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "weft-rag"
    / "src"
    / "weft_retrieve"
    / "pipelines"
    / "route-fixed.yaml"
)
_CUES = CueLexicon.model_validate(
    {
        "phrases": {
            "en": {"aggregation": ("how many",), "comparison": ("versus",)},
            "pl": {"aggregation": ("ile",)},
        }
    }
)


def _ctx(locale: str = "en") -> Context:
    # An empty registry: any service the scorer reached for would raise.
    return Context(
        tenant_id="tenant-a",
        run_id="run-1",
        trace_id="trace-1",
        locale=locale,
        services=ServiceRegistry(),
    )


async def test_the_question_s_profile_rides_on_the_scorecard_with_no_model_call() -> None:
    # Arrange
    scorer = QueryProfileScorer(QueryProfileScorerConfig(cues=_CUES))
    question = Query(text="How many looms versus spindles?")

    # Act
    outcome = await scorer.run(question, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    card = outcome.value
    assert card.query == question
    assert card.scores == {}
    assert card.features["query.word_count"] == 5
    assert card.features["query.cue.aggregation"] is True
    assert card.features["query.cue.comparison"] is True


async def test_the_context_s_locale_chooses_the_cues() -> None:
    # Arrange
    scorer = QueryProfileScorer(QueryProfileScorerConfig(cues=_CUES))

    # Act
    outcome = await scorer.run(Query(text="Ile jest krosien?"), _ctx("pl-PL"))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.features["query.cue.aggregation"] is True
    assert outcome.value.features["query.locale_fallback"] is False


async def test_configured_intent_markers_still_become_intents() -> None:
    # Arrange — `keyword-intents`' one behaviour, kept.
    scorer = QueryProfileScorer(
        QueryProfileScorerConfig(intent_markers={"comparison": ("compare", "versus")})
    )

    # Act
    outcome = await scorer.run(Query(text="Compare mRMR versus plain ranking"), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.intents == frozenset({"comparison"})


def test_it_declares_that_it_calls_nothing() -> None:
    # Assert
    assert QueryProfileScorer.cost_bound == (0, 0)
    assert QUERY_PROFILE_NAME == "query-profile"


def test_an_unknown_config_key_is_refused() -> None:
    # Act / Assert
    with pytest.raises(ValueError, match="dimensions"):
        QueryProfileScorerConfig.model_validate({"dimensions": []})


def test_the_fixed_router_scores_with_it() -> None:
    # Act
    router = load_pipeline_document(_ROUTE_FIXED)

    # Assert
    assert router.stages[0].use == QUERY_PROFILE_NAME


def test_the_unreleased_keyword_intents_name_is_gone_and_query_profile_is_registered() -> None:
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-rag")
    register(registrar, Settings())
    registrar.commit()

    # Act
    scorers = set(registry.names_for(QueryScorer))

    # Assert
    assert QUERY_PROFILE_NAME in scorers
    assert "keyword-intents" not in scorers
