"""Pricing one run in money — task **4.7**, `09-release.md` §4 V5's money half.

**What a price needs.** `weft_llm.payload.Completion.usage` (this task) carries the two numbers
a price needs per call — prompt and completion tokens, read off a real provider's own response,
`None` for `weft_llm.scripted.ScriptedProvider`, which made no real call and has nothing to
price. A per-model rate turns a token count into money; `price_calls` below is the whole
computation, folding many `PricedCall`s into one `RunPrice`.

**Where the rate lives, and why it is configuration rather than a closed key space.**
`DEFAULT_RATES` ships in this pack as plain data — a `Mapping[str, TokenRate]`, never a `Literal`
or an `Enum` naming a fixed set of models a future model release would need a kernel change to
extend. `price_calls` never reads `DEFAULT_RATES` by name from inside its own body; `rates` is a
parameter with that mapping as its default, the identical "a typed configuration model, not a
closed key space" argument `weft_eval.at_threshold`'s own module docstring makes for a metric's
tunables — a caller with current numbers passes `rates=` and this module's own table is never
consulted. This is deliberately *not* routed through `weft-eval`'s pack-settings surface
(`weft_eval.Settings`, validated at `discover()` time): that mechanism hands a validated
`Settings` instance to `register()` and nothing downstream can read it back afterward except
through a registered plugin's own constructor, and pricing registers no plugin — the identical
reasoning `aggregate.py`'s and `run_record.py`'s own module docstrings already give for why
neither of *them* registers one either. A future `weft.toml` surface for operator-supplied rates
is a natural extension of this same `rates:` parameter, named here rather than built now.

**Staleness surfaces because it is a fact on the answer, never hidden inside a bare total.**
`RATES_AS_OF` is the date the shipped table was last checked against a real price sheet, and
every `RunPrice` this module produces carries `rates_as_of` alongside `total_usd` — a caller
rendering a price renders the date beside it, by construction, rather than a number that looks
current forever. A caller who overrides `rates=` also states its own `rates_as_of=`, so a
priced run always says which price sheet it used.

**Excluded, counted rather than merely honoured — `weft_eval.aggregate`'s own shape, applied to
money instead of a score.** A call whose model has no entry in `rates` is not silently priced at
`$0` — `aggregate.py`'s own module docstring names the reference's identical mistake one level up,
an aggregator that reported a success count and never the exclusion count a reader actually
wants. `RunPrice.unpriced_calls`/`unpriced_models` are that count and that naming, here.
"""

from collections.abc import Mapping, Sequence
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from weft_llm.payload import TokenUsage

#: The date `DEFAULT_RATES` was last checked against a real, published price sheet — printed on
#: every `RunPrice` this module produces. See the module docstring's own paragraph on staleness.
RATES_AS_OF: Final[str] = "2026-06-01"


class TokenRate(BaseModel):
    """USD per 1,000 tokens, priced separately for input and output — every vendor Weft ships
    a provider for prices the two differently.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_per_1k_usd: float = Field(ge=0.0)
    output_per_1k_usd: float = Field(ge=0.0)


#: Illustrative defaults for the one chat model this tree ships a provider for
#: (`weft_openai.llm.DEFAULT_MODEL`). A caller pricing a different model, or with current
#: numbers for this one, passes `rates=` to `price_calls` — see the module docstring.
DEFAULT_RATES: Final[Mapping[str, TokenRate]] = {
    "openai:gpt-4o-mini": TokenRate(input_per_1k_usd=0.00015, output_per_1k_usd=0.0006),
}


class PricedCall(BaseModel):
    """One provider call a run made — a `provider:model` string, and what it cost in tokens.

    `model` matches `weft_eval.run_record.RunRecord.model_versions`'s own `"provider:model"`
    vocabulary (e.g. `"openai:gpt-4o-mini"`) rather than inventing a second one — the same string
    that pins a run's model versions is what prices its calls.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str = Field(min_length=1)
    usage: TokenUsage


class RunPrice(BaseModel):
    """One run's money cost — never a bare `float`, `MetricAggregate`'s own "no reported number
    travels alone" rule applied to money: a total with no exclusion count and no dated rate
    sheet beside it is a number nobody can audit.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    total_usd: float = Field(ge=0.0)
    priced_calls: int = Field(ge=0)
    #: How many calls this run made whose model has no entry in the `rates` used to price it —
    #: excluded from `total_usd`, never folded in at `$0`. See the module docstring.
    unpriced_calls: int = Field(ge=0)
    unpriced_models: tuple[str, ...] = ()
    #: Which `rates` table priced this run, and when it was last checked. See the module
    #: docstring's own paragraph on staleness.
    rates_as_of: str = Field(min_length=1)


def price_calls(
    calls: Sequence[PricedCall],
    rates: Mapping[str, TokenRate] = DEFAULT_RATES,
    *,
    rates_as_of: str = RATES_AS_OF,
) -> RunPrice:
    """Fold `calls` into one `RunPrice`, against `rates` — `DEFAULT_RATES`/`RATES_AS_OF` unless
    a caller supplies its own, current pair. An empty `calls` prices to `$0.00`, `0` calls
    either way — a run that made no priceable call genuinely cost nothing, not "unknown".
    """
    total = 0.0
    priced = 0
    unpriced = 0
    unpriced_models: set[str] = set()

    for call in calls:
        rate = rates.get(call.model)
        if rate is None:
            unpriced += 1
            unpriced_models.add(call.model)
            continue
        total += (call.usage.prompt_tokens / 1000) * rate.input_per_1k_usd
        total += (call.usage.completion_tokens / 1000) * rate.output_per_1k_usd
        priced += 1

    return RunPrice(
        total_usd=total,
        priced_calls=priced,
        unpriced_calls=unpriced,
        unpriced_models=tuple(sorted(unpriced_models)),
        rates_as_of=rates_as_of,
    )


__all__ = [
    "DEFAULT_RATES",
    "RATES_AS_OF",
    "PricedCall",
    "RunPrice",
    "TokenRate",
    "price_calls",
]
