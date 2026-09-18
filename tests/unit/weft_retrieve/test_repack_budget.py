"""Unit tests for `repack`'s token budget — ledger task **32.7**, counting through **G25**.

With `budget_tokens` set, `repack` keeps whole passages in ranking order until the next one
would push the evidence block past the budget — after `top_n`, before `method` — counting the
block as `weft_generate.cited_answer` renders it: `[label] content`, passages joined by a blank
line. The count comes from the `LLM` service's `TokenCounter` for the configured role, so it is
the count of the model that will read the context. If even the best passage alone exceeds the
budget, `repack` fails naming both numbers: an empty packing would read downstream as *not in
this corpus*, the wrong answer for *budget too small*.

The counter below counts whitespace-separated words, so `[1] w w w w` is five tokens and each
expected cut can be checked by hand.
"""

import pytest

from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Failed, MediaType, Node, Produced
from weft_llm.contract import LLM, TokenCounter
from weft_llm.errors import TokenCountUnavailableError
from weft_retrieve.payload import Passage, Query, Ranking
from weft_retrieve.repack import Repack, RepackConfig, RepackMethod
from weft_store.contract import Scored


class _WordCounter:
    def __init__(self) -> None:
        self.roles: list[str] = []
        self.texts: list[str] = []

    async def count_tokens(self, role: str, text: str) -> int:
        self.roles.append(role)
        self.texts.append(text)
        return len(text.split())


class _CannotCount:
    async def count_tokens(self, role: str, text: str) -> int:
        del text
        raise TokenCountUnavailableError(role=role, provider="scripted", model="any-model")


def _ctx(llm: object | None = None) -> Context:
    services = ServiceRegistry()
    if llm is not None:
        services.add(LLM, llm)
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


def _ranking(*contents: str) -> Ranking:
    hits = tuple(
        Passage(
            scored=Scored(
                value=Node.synthetic(content=content, media_type=MediaType.TEXT, reason="budget"),
                score=1.0 - rank / 10,
            ),
            rank=rank,
            retrieved_by="vector-top-k",
        )
        for rank, content in enumerate(contents)
    )
    return Ranking(origin=Query(text="how much fits?"), hits=hits)


def test_no_budget_and_the_generate_role_are_the_defaults() -> None:
    # Act
    config = RepackConfig()

    # Assert
    assert config.budget_tokens is None
    assert config.role == "generate"


def test_a_budget_below_one_token_is_refused() -> None:
    # Act / Assert
    with pytest.raises(ValueError):
        RepackConfig(budget_tokens=0)


async def test_without_a_budget_no_counter_is_needed_and_nothing_is_dropped() -> None:
    # Act — no LLM service at all: the unbudgeted path must not reach for one.
    outcome = await Repack(RepackConfig(method=RepackMethod.FORWARD)).run(
        _ranking("a", "b", "c"), _ctx()
    )

    # Assert
    assert isinstance(outcome, Produced)
    assert [p.node.content for p in outcome.value.passages] == ["a", "b", "c"]


async def test_whole_passages_are_kept_in_order_until_the_next_would_exceed_the_budget() -> None:
    # Arrange — each passage renders as "[n] w w w w" = 5 words. Two fit in 12 (10); three
    # would be 15.
    ranking = _ranking("w w w w", "x x x x", "y y y y")

    # Act
    outcome = await Repack(RepackConfig(method=RepackMethod.FORWARD, budget_tokens=12)).run(
        ranking, _ctx(_WordCounter())
    )

    # Assert
    assert isinstance(outcome, Produced)
    assert [p.node.content for p in outcome.value.passages] == ["w w w w", "x x x x"]


async def test_the_budget_is_applied_after_top_n_and_before_the_method_arranges() -> None:
    # Arrange — top_n drops the fourth; the budget keeps the best two of the remaining three;
    # `reverse` then puts the best last.
    ranking = _ranking("w w w w", "x x x x", "y y y y", "z z z z")

    # Act
    outcome = await Repack(
        RepackConfig(method=RepackMethod.REVERSE, top_n=3, budget_tokens=12)
    ).run(ranking, _ctx(_WordCounter()))

    # Assert
    assert isinstance(outcome, Produced)
    assert [p.node.content for p in outcome.value.passages] == ["x x x x", "w w w w"]
    assert [p.label for p in outcome.value.passages] == ["1", "2"]


async def test_the_block_counted_is_the_one_the_generator_renders() -> None:
    # Arrange
    counter = _WordCounter()

    # Act
    await Repack(RepackConfig(method=RepackMethod.FORWARD, budget_tokens=100)).run(
        _ranking("first passage", "second passage"), _ctx(counter)
    )

    # Assert — the last text counted is the whole kept block, labelled and blank-line joined.
    assert counter.texts[-1] == "[1] first passage\n\n[2] second passage"


async def test_the_count_is_asked_for_the_configured_role() -> None:
    # Arrange
    counter = _WordCounter()

    # Act
    await Repack(RepackConfig(budget_tokens=100, role="summarize")).run(
        _ranking("a b"), _ctx(counter)
    )

    # Assert
    assert counter.roles and set(counter.roles) == {"summarize"}


async def test_a_best_passage_larger_than_the_budget_fails_naming_both_numbers() -> None:
    # Arrange — "[1] w w w w w w w w w" is 10 words against a budget of 6.
    ranking = _ranking("w w w w w w w w w", "x")

    # Act
    outcome = await Repack(RepackConfig(budget_tokens=6)).run(ranking, _ctx(_WordCounter()))

    # Assert
    assert isinstance(outcome, Failed)
    assert "10" in outcome.reason
    assert "6" in outcome.reason


async def test_a_model_nothing_can_count_is_refused_not_packed_by_characters() -> None:
    # Act / Assert
    with pytest.raises(TokenCountUnavailableError):
        await Repack(RepackConfig(budget_tokens=100)).run(_ranking("a b"), _ctx(_CannotCount()))


async def test_an_llm_service_that_offers_no_counting_is_refused_by_name() -> None:
    # Arrange
    class _NoCounting:
        pass

    # Act
    outcome = await Repack(RepackConfig(budget_tokens=100)).run(
        _ranking("a b"), _ctx(_NoCounting())
    )

    # Assert
    assert isinstance(outcome, Failed)
    assert TokenCounter.__name__ in outcome.reason
