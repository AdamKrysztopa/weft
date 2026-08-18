"""Unit tests for `weft_llm.retry`.

Mirrors `packages/weft-llm/src/weft_llm/retry.py`. Covers the happy path (a transient failure
followed by a success returns the success), the edge case (a permanent failure is not retried
even once), and the error case that matters most — `CancelledError` is a `BaseException` and
must pass through a retry loop untouched, because a retry wrapper that swallows cancellation
is the one bug this file could introduce that no other test in the tree would notice.
"""

import asyncio
from collections.abc import AsyncIterator
from typing import cast

import pytest

from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Outcome, Produced
from weft_llm.contract import LLMProvider
from weft_llm.errors import LLMBadRequestError, LLMRateLimitError
from weft_llm.payload import Completion, Conversation, Message, MessageRole
from weft_llm.retry import RetryPolicy, with_retry

CONV = Conversation(messages=(Message(role=MessageRole.USER, content="ask"),))


def _ctx() -> Context:
    return Context(tenant_id="t", run_id="r", trace_id="x", locale="en", services=ServiceRegistry())


class _Flaky:
    """Fails with whatever it was handed, `failures` times, then answers."""

    def __init__(self, error: BaseException, failures: int) -> None:
        self._error = error
        self._failures = failures
        self.calls = 0

    async def complete(
        self, conv: Conversation, *, model: str, ctx: Context
    ) -> Outcome[Completion]:
        del conv, ctx
        self.calls += 1
        if self.calls <= self._failures:
            raise self._error
        return Produced(value=Completion(text="answered", model=model))

    async def stream(self, conv: Conversation, *, model: str, ctx: Context) -> AsyncIterator[str]:
        del conv, ctx, model
        self.calls += 1
        if self.calls <= self._failures:
            raise self._error
        yield "answered"

    async def close(self) -> None:
        return


async def test_a_transient_failure_is_retried_and_the_next_attempt_is_returned() -> None:
    # Arrange
    flaky = _Flaky(LLMRateLimitError("slow down", provider="p", model="m"), failures=1)
    provider = with_retry(cast("LLMProvider", flaky), RetryPolicy(attempts=3, base_delay_ms=0))

    # Act
    outcome = await provider.complete(CONV, model="m", ctx=_ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert flaky.calls == 2


async def test_a_permanent_failure_is_not_retried_even_once() -> None:
    # Arrange
    flaky = _Flaky(LLMBadRequestError("malformed", provider="p", model="m"), failures=5)
    provider = with_retry(cast("LLMProvider", flaky), RetryPolicy(attempts=3, base_delay_ms=0))

    # Act / Assert
    with pytest.raises(LLMBadRequestError):
        await provider.complete(CONV, model="m", ctx=_ctx())
    assert flaky.calls == 1


async def test_the_last_transient_failure_is_raised_once_the_attempts_are_spent() -> None:
    # Arrange
    flaky = _Flaky(LLMRateLimitError("slow down", provider="p", model="m"), failures=9)
    provider = with_retry(cast("LLMProvider", flaky), RetryPolicy(attempts=2, base_delay_ms=0))

    # Act / Assert — the vendor's own class survives, never a generic wrapper.
    with pytest.raises(LLMRateLimitError):
        await provider.complete(CONV, model="m", ctx=_ctx())
    assert flaky.calls == 2


async def test_cancellation_passes_through_the_retry_loop_untouched() -> None:
    # Arrange
    flaky = _Flaky(asyncio.CancelledError(), failures=9)
    provider = with_retry(cast("LLMProvider", flaky), RetryPolicy(attempts=3, base_delay_ms=0))

    # Act / Assert
    with pytest.raises(asyncio.CancelledError):
        await provider.complete(CONV, model="m", ctx=_ctx())
    assert flaky.calls == 1


async def test_a_stream_that_already_yielded_is_never_restarted() -> None:
    # Arrange — a provider that fails *after* its first chunk. Re-running it would replay
    # tokens a reader has already seen, so retry stops at the first yield.
    class _HalfStream:
        def __init__(self) -> None:
            self.calls = 0

        async def complete(
            self, conv: Conversation, *, model: str, ctx: Context
        ) -> Outcome[Completion]:
            raise NotImplementedError

        async def stream(
            self, conv: Conversation, *, model: str, ctx: Context
        ) -> AsyncIterator[str]:
            del conv, ctx, model
            self.calls += 1
            yield "half "
            raise LLMRateLimitError("dropped", provider="p", model="m")

        async def close(self) -> None:
            return

    half = _HalfStream()
    provider = with_retry(cast("LLMProvider", half), RetryPolicy(attempts=3, base_delay_ms=0))

    # Act / Assert
    seen: list[str] = []
    with pytest.raises(LLMRateLimitError):
        async for chunk in provider.stream(CONV, model="m", ctx=_ctx()):
            seen.append(chunk)
    assert seen == ["half "]
    assert half.calls == 1
