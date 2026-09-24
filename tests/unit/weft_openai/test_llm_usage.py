"""`OpenAILLMProvider` reports a streamed call's usage — ledger task **33.6**.

The vendor reports usage on a stream only when asked. The OpenAI SDK's own documentation of
`stream_options.include_usage` (`openai/types/chat/chat_completion_stream_options_param.py`,
read 2026-09-15): *"If set, an additional chunk will be streamed before the `data: [DONE]`
message. The `usage` field on this chunk shows the token usage statistics for the entire request,
and the `choices` field will always be an empty array."* So the provider asks, and the final chunk
has no `choices[0]` to read — indexing it would raise on exactly the chunk that carries the count.

The doubles are copied from `test_llm.py`'s, widened by the one field this task reads (`usage` on
a chunk) and the one argument it sends (`stream_options`), rather than written from the SDK's
prose (`L11.17`).
"""

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field

from pydantic import SecretStr

from weft_kernel.context import Context
from weft_llm.contract import UsageReporting
from weft_llm.payload import Conversation, Message, MessageRole, TokenUsage
from weft_openai import Settings
from weft_openai.llm import OpenAILLMProvider


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _conversation(text: str) -> Conversation:
    return Conversation(messages=(Message(role=MessageRole.USER, content=text),))


@dataclass
class _Usage:
    prompt_tokens: int
    completion_tokens: int


@dataclass
class _ChunkDelta:
    content: str | None


@dataclass
class _ChunkChoice:
    delta: _ChunkDelta


@dataclass
class _Chunk:
    choices: Sequence[_ChunkChoice]
    usage: _Usage | None = None


async def _chunks(pieces: Sequence[str], usage: _Usage | None) -> AsyncIterator[_Chunk]:
    for piece in pieces:
        yield _Chunk(choices=[_ChunkChoice(delta=_ChunkDelta(content=piece))])
    if usage is not None:
        yield _Chunk(choices=[], usage=usage)


@dataclass
class _Completions:
    reply: str = "an answer"
    usage: _Usage | None = None
    stream_options: list[Mapping[str, bool] | None] = field(default_factory=lambda: [])

    async def create(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, str]],
        stream: bool = False,
        stream_options: Mapping[str, bool] | None = None,
        **_: object,
    ) -> AsyncIterator[_Chunk]:
        del model, messages, stream
        self.stream_options.append(stream_options)
        include = bool(stream_options and stream_options.get("include_usage"))
        return _chunks(self.reply.split(" "), self.usage if include else None)


@dataclass
class _Chat:
    completions: _Completions = field(default_factory=_Completions)


@dataclass
class _Client:
    chat: _Chat = field(default_factory=_Chat)

    async def close(self) -> None:
        return


def _provider(client: _Client) -> OpenAILLMProvider:
    return OpenAILLMProvider(Settings(api_key=SecretStr("sk-test")), client=client)


def test_the_openai_provider_is_a_usage_reporting_provider() -> None:
    # Act / Assert
    assert isinstance(_provider(_Client()), UsageReporting)


async def test_a_streamed_call_asks_for_usage_and_yields_it_after_the_text() -> None:
    # Arrange
    client = _Client()
    client.chat.completions.usage = _Usage(prompt_tokens=7, completion_tokens=2)
    provider = _provider(client)

    # Act
    items = [
        item
        async for item in provider.stream_reporting_usage(
            _conversation("why?"), model="gpt-4o-mini", ctx=_ctx()
        )
    ]

    # Assert
    assert client.chat.completions.stream_options == [{"include_usage": True}]
    assert items == ["an", "answer", TokenUsage(prompt_tokens=7, completion_tokens=2)]


async def test_a_stream_the_vendor_sent_no_usage_for_yields_text_only() -> None:
    """A compatible server that ignores `stream_options` sends no usage chunk.

    The provider then reports nothing rather than inventing a count.
    """
    # Arrange
    client = _Client()
    provider = _provider(client)

    # Act
    items = [
        item
        async for item in provider.stream_reporting_usage(
            _conversation("why?"), model="gpt-4o-mini", ctx=_ctx()
        )
    ]

    # Assert
    assert items == ["an", "answer"]
