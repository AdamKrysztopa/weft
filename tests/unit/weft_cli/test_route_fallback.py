"""Task 44.23 — a routed ask falls back on a named refusal and on nothing broader.

`whole-corpus` raises `CorpusOverTokenBoundError` while it runs, after the router has already
decided, so the decision cannot have known. The fallback is the rung the policy named on the
`Route`; every other failure, and a cancellation, reaches the caller untouched.
"""

import asyncio

import pytest

from weft_cli.route_ask import answer_with_fallback
from weft_retrieve.payload import Query, Route, RuleOutcome, Scorecard
from weft_retrieve.whole_corpus import CorpusOverTokenBoundError


def _route(fallback: str | None = "retrieve-then-generate") -> Route:
    return Route(
        pipeline="whole-corpus-then-generate",
        outcome=RuleOutcome.MATCHED,
        rule="small-corpus",
        scorecard=Scorecard(query=Query(text="q"), scores={}),
        reasons=("rule 'small-corpus' held",),
        claims=("c.one",),
        fallback=fallback,
    )


def _over_bound() -> CorpusOverTokenBoundError:
    return CorpusOverTokenBoundError(counted=120_000, bound=100_000)


class _Runs:
    """Records which pipelines were run and answers or raises per name."""

    def __init__(self, *, raises: dict[str, BaseException] | None = None) -> None:
        self.ran: list[str] = []
        self._raises = raises or {}

    async def __call__(self, name: str) -> str:
        self.ran.append(name)
        if name in self._raises:
            raise self._raises[name]
        return f"answer from {name}"


async def test_a_run_that_succeeds_is_returned_with_its_route_unchanged() -> None:
    # Arrange
    run = _Runs()
    route = _route()

    # Act
    final_route, answer = await answer_with_fallback(route, run)

    # Assert
    assert final_route == route
    assert answer == "answer from whole-corpus-then-generate"
    assert run.ran == ["whole-corpus-then-generate"]


async def test_an_over_bound_corpus_falls_back_and_the_route_says_so() -> None:
    # Arrange
    run = _Runs(raises={"whole-corpus-then-generate": _over_bound()})

    # Act
    route, answer = await answer_with_fallback(_route(), run)

    # Assert
    assert answer == "answer from retrieve-then-generate"
    assert run.ran == ["whole-corpus-then-generate", "retrieve-then-generate"]
    assert route.pipeline == "retrieve-then-generate"
    assert route.outcome is RuleOutcome.FELL_BACK
    assert route.rule == ""
    assert route.claims == ()
    assert route.fallback is None
    assert route.reasons[0] == "rule 'small-corpus' held"
    assert "120,000" in route.reasons[-1]
    assert "whole-corpus-then-generate" in route.reasons[-1]


async def test_a_refusal_with_no_fallback_named_reaches_the_caller() -> None:
    # Arrange
    run = _Runs(raises={"whole-corpus-then-generate": _over_bound()})

    # Act / Assert
    with pytest.raises(CorpusOverTokenBoundError):
        await answer_with_fallback(_route(fallback=None), run)
    assert run.ran == ["whole-corpus-then-generate"]


async def test_any_other_failure_propagates_without_a_fallback_run() -> None:
    # Arrange
    run = _Runs(raises={"whole-corpus-then-generate": RuntimeError("the model is down")})

    # Act / Assert
    with pytest.raises(RuntimeError, match="the model is down"):
        await answer_with_fallback(_route(), run)
    assert run.ran == ["whole-corpus-then-generate"]


async def test_a_cancellation_propagates_and_is_never_a_fallback() -> None:
    # Arrange
    run = _Runs(raises={"whole-corpus-then-generate": asyncio.CancelledError()})

    # Act / Assert
    with pytest.raises(asyncio.CancelledError):
        await answer_with_fallback(_route(), run)
    assert run.ran == ["whole-corpus-then-generate"]


async def test_a_failing_fallback_is_not_swallowed() -> None:
    # Arrange — the fallback also refuses; the caller sees that, not a half-recorded route.
    run = _Runs(
        raises={
            "whole-corpus-then-generate": _over_bound(),
            "retrieve-then-generate": RuntimeError("store down"),
        }
    )

    # Act / Assert
    with pytest.raises(RuntimeError, match="store down"):
        await answer_with_fallback(_route(), run)
