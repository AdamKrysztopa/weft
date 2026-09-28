"""`keyword-intents` — a `QueryScorer` that calls no model. Ledger task **44.1**.

`always` takes a `Scorecard`, so before this every router document ran `query-scorer` and paid
a model call on the `route` role, `route-fixed` included. This scorer measures only what
`query-scorer`'s keyword half measures and leaves `scores` empty.
"""

import pytest

from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Produced
from weft_retrieve import KEYWORD_INTENTS_NAME, KeywordIntents, KeywordIntentsConfig
from weft_retrieve.payload import Query


def _ctx() -> Context:
    # An empty registry: any service a scorer reached for would raise.
    return Context(
        tenant_id="tenant-a",
        run_id="run-1",
        trace_id="trace-1",
        locale="en",
        services=ServiceRegistry(),
    )


async def test_a_configured_marker_becomes_an_intent_with_no_model_call() -> None:
    # Arrange
    scorer = KeywordIntents(
        KeywordIntentsConfig(intent_markers={"comparison": ("compare", "versus")})
    )
    question = Query(text="Compare mRMR versus plain relevance ranking")

    # Act
    outcome = await scorer.run(question, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.intents == frozenset({"comparison"})
    assert outcome.value.scores == {}
    assert outcome.value.query == question


async def test_no_markers_configured_yields_no_intent() -> None:
    # Arrange
    scorer = KeywordIntents()

    # Act
    outcome = await scorer.run(Query(text="who discovered polonium?"), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.intents == frozenset()


def test_it_declares_that_it_calls_nothing() -> None:
    assert KeywordIntents.cost_bound == (0, 0)
    assert KEYWORD_INTENTS_NAME == "keyword-intents"


def test_an_unknown_config_key_is_refused() -> None:
    with pytest.raises(ValueError, match="dimensions"):
        KeywordIntentsConfig.model_validate({"dimensions": []})
