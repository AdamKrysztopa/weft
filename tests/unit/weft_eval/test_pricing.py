"""Unit tests for `weft_eval.pricing`.

Mirrors `packages/weft-eval/src/weft_eval/pricing.py`. Covers the happy path (a known model
prices to the expected total, `rates_as_of` carried alongside it), the edge case (an empty call
list prices to `$0.00`, not an error), and the error-shaped case that is not an exception here by
design (an unpriced model is excluded and counted, never silently folded in at `$0`) — matching
`weft_eval.aggregate`'s own "excluded, counted rather than merely honoured" shape.
"""

from weft_eval.pricing import DEFAULT_RATES, PricedCall, RunPrice, TokenRate, price_calls
from weft_llm.payload import TokenUsage


def test_a_known_model_prices_from_its_own_rate() -> None:
    # Arrange
    rate = TokenRate(input_per_1k_usd=1.0, output_per_1k_usd=2.0)
    call = PricedCall(
        model="test:model", usage=TokenUsage(prompt_tokens=1000, completion_tokens=500)
    )

    # Act
    price = price_calls([call], {"test:model": rate}, rates_as_of="2026-01-01")

    # Assert — 1000 prompt tokens at $1.00/1k, plus 500 completion tokens at $2.00/1k.
    assert price.total_usd == 1.0 + 1.0
    assert price.priced_calls == 1
    assert price.unpriced_calls == 0
    assert price.unpriced_models == ()
    assert price.rates_as_of == "2026-01-01"


def test_an_empty_run_prices_to_zero_not_an_error() -> None:
    # Act
    price = price_calls([])

    # Assert
    assert price == RunPrice(
        total_usd=0.0,
        priced_calls=0,
        unpriced_calls=0,
        unpriced_models=(),
        rates_as_of=price.rates_as_of,
    )


def test_a_call_with_no_rate_entry_is_excluded_and_counted_never_priced_at_zero() -> None:
    # Arrange — a model nothing in `rates` prices, beside one that does.
    priced = PricedCall(
        model="openai:gpt-4o-mini", usage=TokenUsage(prompt_tokens=1000, completion_tokens=0)
    )
    unpriced = PricedCall(
        model="openai:some-future-model", usage=TokenUsage(prompt_tokens=1000, completion_tokens=0)
    )

    # Act
    price = price_calls([priced, unpriced], DEFAULT_RATES)

    # Assert — the known call is priced; the unknown one is excluded and named, not folded in at
    # $0, which would be indistinguishable from a real, free call.
    assert price.priced_calls == 1
    assert price.unpriced_calls == 1
    assert price.unpriced_models == ("openai:some-future-model",)
    assert price.total_usd > 0.0
