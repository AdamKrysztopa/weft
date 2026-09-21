"""Repair R41.2: `[llm.retry]` is the only retry an LLM call gets.

`manual/operations-guide.md` → *How hard to try*: "Retry is attached **once**, around the provider".
The OpenAI SDK retries transient failures itself, `max_retries` times, below anything Weft sees, so
each of `[llm.retry]`'s attempts could become up to three requests. Counted here at the wire — a
local server answering every request with a 500 — because a request count is the fact an operator's
bill and a rate limit see, and neither sees how many layers asked for it.
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import cast

import pytest
from pydantic import SecretStr

from weft_kernel.context import Context
from weft_llm.contract import LLMProvider
from weft_llm.errors import LLMServiceUnavailableError
from weft_llm.payload import Conversation, Message, MessageRole
from weft_llm.retry import RetryPolicy, with_retry
from weft_openai import Settings
from weft_openai.llm import OpenAILLMProvider

_BODY = b'{"error": {"message": "overloaded", "type": "server_error"}}'


@dataclass
class _FailingServer:
    url: str
    requests: int = 0


async def _answer_with_a_500(
    server: _FailingServer, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    head = await reader.readuntil(b"\r\n\r\n")
    length = 0
    for line in head.decode("latin-1").split("\r\n"):
        name, _, value = line.partition(":")
        if name.strip().lower() == "content-length":
            length = int(value.strip())
    await reader.readexactly(length)
    server.requests += 1
    writer.write(
        b"HTTP/1.1 500 Internal Server Error\r\n"
        b"Content-Type: application/json\r\n"
        b"Content-Length: " + str(len(_BODY)).encode() + b"\r\n"
        b"Connection: close\r\n\r\n" + _BODY
    )
    await writer.drain()
    writer.close()


@asynccontextmanager
async def _failing_server() -> AsyncGenerator[_FailingServer]:
    server = _FailingServer(url="")
    listening = await asyncio.start_server(
        lambda r, w: _answer_with_a_500(server, r, w), host="127.0.0.1", port=0
    )
    port = listening.sockets[0].getsockname()[1]
    server.url = f"http://127.0.0.1:{port}/v1"
    try:
        yield server
    finally:
        listening.close()
        await listening.wait_closed()


def _provider(url: str) -> OpenAILLMProvider:
    # `max_retries=2` stated rather than defaulted: the account's own transport setting is
    # the thing that must not multiply the policy.
    return OpenAILLMProvider(
        Settings(api_key=SecretStr("sk-test"), base_url=url, max_retries=2, timeout_seconds=5.0)
    )


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _conversation() -> Conversation:
    return Conversation(messages=(Message(role=MessageRole.USER, content="hello"),))


async def test_one_attempt_at_the_provider_sends_one_request() -> None:
    # Arrange
    async with _failing_server() as server:
        provider = _provider(server.url)

        # Act
        with pytest.raises(LLMServiceUnavailableError):
            await provider.complete(_conversation(), model="gpt-4o-mini", ctx=_ctx())
        await provider.close()

    # Assert
    assert server.requests == 1


async def test_a_retried_completion_sends_exactly_the_policys_attempts() -> None:
    # Arrange
    async with _failing_server() as server:
        provider = _provider(server.url)
        retrying = with_retry(
            cast("LLMProvider", provider), RetryPolicy(attempts=3, base_delay_ms=0)
        )

        # Act
        with pytest.raises(LLMServiceUnavailableError):
            await retrying.complete(_conversation(), model="gpt-4o-mini", ctx=_ctx())
        await retrying.close()

    # Assert
    assert server.requests == 3


async def test_a_retried_stream_sends_exactly_the_policys_attempts() -> None:
    # Arrange
    async with _failing_server() as server:
        provider = _provider(server.url)
        retrying = with_retry(
            cast("LLMProvider", provider), RetryPolicy(attempts=2, base_delay_ms=0)
        )

        # Act
        with pytest.raises(LLMServiceUnavailableError):
            async for _ in retrying.stream(_conversation(), model="gpt-4o-mini", ctx=_ctx()):
                pass
        await retrying.close()

    # Assert
    assert server.requests == 2
