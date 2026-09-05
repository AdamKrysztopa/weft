"""Unit tests for `weft_openai.llm`.

Mirrors `packages/weft-openai/src/weft_openai/llm.py`. Three groups: the happy path and the
missing-credential/blank-conversation edge cases against an injected stub client (no request
leaves this file — see `test_embedder.py`'s own note on why that seam exists), the streaming
path, and `map_openai_error`'s table, one test per row, driven against real `openai` exception
instances rather than a description of what they mean.

**Four repairs for reviewer findings against task 2.30, each with its own test below:**
(1) a mid-stream vendor exception — raised from `__anext__`, after some pieces already
arrived, not from `create()` — must still map through `map_openai_error`. (2)
`OpenAILLMConfig`'s knobs must actually reach the vendor call, both when set and when left at
their omit-shaped default. (3) `OpenAILLMProvider` assigned to a variable the type checker
believes is `weft_llm.contract.LLMProvider` must be usable with `async for provider.stream(...)`
with no `await` — `tests/unit/weft_llm/test_scripted.py` carries the same check for
`ScriptedProvider`, since the defect was in the shared `LLMProvider` Protocol stub, not in
either implementation. (4) the blocking-call guard must be proven against the real
`_connected()` code path, not only against the injected-`client` seam that returns before ever
reaching it.
"""

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import cast

import httpx2
import pytest
from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    Omit,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
    omit,
)
from pydantic import SecretStr

from weft_kernel.context import Context
from weft_kernel.payload import Produced
from weft_kernel.seam import wrap
from weft_llm.contract import LLMProvider
from weft_llm.errors import (
    LLMAuthenticationError,
    LLMBadRequestError,
    LLMConnectionError,
    LLMContentFilterError,
    LLMContextLengthError,
    LLMNotFoundError,
    LLMPermissionDeniedError,
    LLMRateLimitError,
    LLMServiceUnavailableError,
    LLMTimeoutError,
)
from weft_llm.payload import Conversation, Message, MessageRole
from weft_openai import Settings
from weft_openai.llm import NAME, OpenAILLMConfig, OpenAILLMProvider, map_openai_error


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _settings(api_key: str = "sk-test") -> Settings:
    return Settings(api_key=SecretStr(api_key))


def _conversation(*texts: str) -> Conversation:
    return Conversation(messages=tuple(Message(role=MessageRole.USER, content=t) for t in texts))


def _request() -> httpx2.Request:
    return httpx2.Request("POST", "https://api.openai.com/v1/chat/completions")


def _bad_request(code: str | None) -> BadRequestError:
    body = {"message": "refused", "type": "invalid_request_error", "param": None, "code": code}
    response = httpx2.Response(400, request=_request(), json={"error": body})
    return BadRequestError("refused", response=response, body=body)


@dataclass
class _Message:
    content: str | None


@dataclass
class _Choice:
    message: _Message
    finish_reason: str | None = "stop"


@dataclass
class _Usage:
    prompt_tokens: int
    completion_tokens: int


@dataclass
class _Response:
    choices: Sequence[_Choice]
    usage: _Usage | None = None


@dataclass
class _ChunkDelta:
    content: str | None


@dataclass
class _ChunkChoice:
    delta: _ChunkDelta


@dataclass
class _Chunk:
    choices: Sequence[_ChunkChoice]


async def _chunks(
    pieces: Sequence[str | None], *, mid_stream_error: Exception | None = None
) -> AsyncIterator[_Chunk]:
    """`pieces`, then `mid_stream_error` if one was given — a connection that answered, then
    dropped, rather than one that never opened. `create()` raising is `error` below; this is
    the other place a vendor exception can originate, reached only from inside the `async for`
    a caller drives, which is the shape the mid-stream repair test needs.
    """
    for piece in pieces:
        yield _Chunk(choices=[_ChunkChoice(delta=_ChunkDelta(content=piece))])
    if mid_stream_error is not None:
        raise mid_stream_error


@dataclass
class _Call:
    model: str
    messages: list[dict[str, str]]
    stream: bool
    temperature: float | Omit = omit
    max_tokens: int | Omit = omit
    top_p: float | Omit = omit


@dataclass
class _Completions:
    """A stand-in for `AsyncOpenAI.chat.completions` — the shape `ChatCompletionsResource` takes."""

    reply: str = "an answer"
    error: Exception | None = None
    mid_stream_error: Exception | None = None
    usage: _Usage | None = None
    calls: list[_Call] = field(default_factory=lambda: [])

    async def create(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, str]],
        stream: bool = False,
        temperature: float | Omit = omit,
        max_tokens: int | Omit = omit,
        top_p: float | Omit = omit,
    ) -> _Response | AsyncIterator[_Chunk]:
        self.calls.append(
            _Call(
                model=model,
                messages=[dict(m) for m in messages],
                stream=stream,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
            )
        )
        if self.error is not None:
            raise self.error
        if stream:
            return _chunks(self.reply.split(" "), mid_stream_error=self.mid_stream_error)
        return _Response(choices=[_Choice(message=_Message(content=self.reply))], usage=self.usage)


@dataclass
class _Chat:
    completions: _Completions = field(default_factory=_Completions)


@dataclass
class _Client:
    chat: _Chat = field(default_factory=_Chat)
    closed: bool = False

    async def close(self) -> None:
        self.closed = True


async def test_complete_answers_the_stub_clients_reply_under_the_requested_model() -> None:
    # Arrange
    client = _Client()
    provider = OpenAILLMProvider(_settings(), client=client)
    conv = _conversation("why does mRMR subtract redundancy?")

    # Act
    outcome = await provider.complete(conv, model="gpt-4o-mini", ctx=_ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.text == "an answer"
    assert outcome.value.model == "gpt-4o-mini"
    assert outcome.value.finish_reason == "stop"
    assert outcome.value.usage is None
    [sent] = client.chat.completions.calls
    assert sent.messages == [{"role": "user", "content": "why does mRMR subtract redundancy?"}]
    assert sent.stream is False


async def test_complete_reports_the_vendors_own_token_usage_when_the_response_carries_it() -> None:
    # Arrange — task 4.7: a price needs tokens in/out per call, read off the vendor's own
    # response rather than estimated.
    completions = _Completions(usage=_Usage(prompt_tokens=42, completion_tokens=7))
    client = _Client(chat=_Chat(completions=completions))
    provider = OpenAILLMProvider(_settings(), client=client)

    # Act
    outcome = await provider.complete(_conversation("q"), model="gpt-4o-mini", ctx=_ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.usage is not None
    assert outcome.value.usage.prompt_tokens == 42
    assert outcome.value.usage.completion_tokens == 7


async def test_stream_yields_the_same_reply_in_pieces() -> None:
    # Arrange
    client = _Client(chat=_Chat(completions=_Completions(reply="one two three")))
    provider = OpenAILLMProvider(_settings(), client=client)

    # Act
    pieces = [piece async for piece in provider.stream(_conversation("go"), model="m", ctx=_ctx())]

    # Assert
    assert pieces == ["one", "two", "three"]


async def test_stream_maps_a_vendor_error_raised_mid_iteration_not_only_from_create() -> None:
    """Repair for a reviewer finding against task 2.30: `create(..., stream=True)` succeeding
    says nothing about the connection that stays open while it drains. The stub yields two
    real pieces before the connection drops — proving the exception was reached from inside
    the `async for`, the one place `map_openai_error` previously did not stand guard, rather
    than from `create()` itself, which the pre-repair `try` already covered.
    """
    # Arrange
    drop = APIConnectionError(request=_request())
    completions = _Completions(reply="one two", mid_stream_error=drop)
    client = _Client(chat=_Chat(completions=completions))
    provider = OpenAILLMProvider(_settings(), client=client)

    # Act
    collected: list[str] = []
    with pytest.raises(LLMConnectionError) as raised:
        async for piece in provider.stream(_conversation("go"), model="gpt-4o-mini", ctx=_ctx()):
            collected.append(piece)

    # Assert — some pieces arrived before the drop, and the raw vendor exception never escaped.
    assert collected == ["one", "two"]
    assert raised.value.provider == "openai"
    assert raised.value.model == "gpt-4o-mini"


async def test_complete_without_a_credential_names_the_configuration_line_that_supplies_one() -> (
    None
):
    # Arrange — every Settings field has a default, so registration cannot fail on a machine
    # with no key; the refusal belongs here, at use.
    provider = OpenAILLMProvider(Settings())

    # Act / Assert
    with pytest.raises(LLMAuthenticationError) as raised:
        await provider.complete(_conversation("hello"), model="gpt-4o-mini", ctx=_ctx())
    assert "[packs.openai] api_key" in str(raised.value)
    assert raised.value.model == "gpt-4o-mini"


async def test_a_configured_temperature_and_max_tokens_reach_the_underlying_api_call() -> None:
    """Repair for a reviewer finding against task 2.30: `config` used to be discarded
    (`del config`) unconditionally. Two of the three knobs, one call, is enough to prove the
    plumbing — every knob shares the same `_generation_kwargs` code path.
    """
    # Arrange
    client = _Client()
    config = OpenAILLMConfig(temperature=0.0, max_tokens=64)
    provider = OpenAILLMProvider(_settings(), config=config, client=client)

    # Act
    await provider.complete(_conversation("grade this"), model="gpt-4o-mini", ctx=_ctx())

    # Assert
    [sent] = client.chat.completions.calls
    assert sent.temperature == 0.0
    assert sent.max_tokens == 64
    assert sent.top_p is omit  # never set — stays omitted, not coerced to a default


async def test_an_unconfigured_provider_omits_every_generation_knob_from_the_request() -> None:
    """The edge case: unset must reach the vendor call as *omitted*, never as a literal
    `None` — an explicit `null` and "the API's own default" are not the same request.
    """
    # Arrange
    client = _Client()
    provider = OpenAILLMProvider(_settings(), client=client)  # no config at all

    # Act
    await provider.complete(_conversation("hello"), model="gpt-4o-mini", ctx=_ctx())

    # Assert
    [sent] = client.chat.completions.calls
    assert sent.temperature is omit
    assert sent.max_tokens is omit
    assert sent.top_p is omit


def test_a_configured_temperature_outside_the_apis_own_range_is_refused_at_construction() -> None:
    """The error case: `OpenAILLMConfig` validates rather than forwarding a value the vendor
    would refuse itself, three requests later.
    """
    # Act / Assert
    with pytest.raises(ValueError, match="temperature"):
        OpenAILLMConfig(temperature=2.5)


async def _drive_as_the_contract_type(provider: LLMProvider) -> list[str]:
    """`provider.stream(...)` under `async for`, with `provider` typed exactly as
    `weft_llm.contract.LLMProvider` declares it — never as the concrete class. This is what
    makes the test below a check of the *contract's* calling convention rather than of
    whichever concrete `.stream()` pyright happens to see through the variable.
    """
    return [piece async for piece in provider.stream(_conversation("go"), model="m", ctx=_ctx())]


async def test_a_provider_typed_as_the_llmprovider_contract_can_stream_with_no_await() -> None:
    """Repair for a reviewer finding against task 2.30's contract, not this pack: an `async
    def` Protocol stub with an `Ellipsis` body types `.stream(...)` as a coroutine, not an
    async generator, so a value typed `LLMProvider` could not be driven with a bare
    `async for` — it would need an `await` first, which `OpenAILLMProvider` (a real async
    generator) does not want and does not need. `cast` stands in only for the unrelated gap
    every Weft contract shares — none of their `version: ClassVar[str]` is ever declared on a
    concrete plugin, so pyright refuses the assignment on that ground alone, in every pack,
    not on the ground this test exists to check; `tests/unit/weft_llm/test_scripted.py`
    carries the same check for `ScriptedProvider`, since the defect under test was in the
    shared Protocol, not in either plugin.
    """
    # Arrange
    client = _Client(chat=_Chat(completions=_Completions(reply="one two")))
    provider = cast("LLMProvider", OpenAILLMProvider(_settings(), client=client))

    # Act
    pieces = await _drive_as_the_contract_type(provider)

    # Assert
    assert pieces == ["one", "two"]


async def test_aclose_closes_the_client_it_was_given() -> None:
    # Arrange
    client = _Client()
    provider = OpenAILLMProvider(_settings(), client=client)

    # Act
    await provider.close()

    # Assert
    assert client.closed is True


async def test_driving_the_provider_through_the_registration_seam_makes_no_blocking_call() -> None:
    """Fitness function 7(b) against the one path every registered plugin is called through —
    the group note against every task from 2.6 forward, applied to this pack's second plugin.

    An injected `client` is what every other test in this file uses, deliberately, to avoid a
    network call — but `_connected()` returns on its very first line when `self._client is not
    None`, before it ever reaches the `asyncio.to_thread(build_client, settings)` call this
    guard actually exists to police. That gap is a reviewer finding against this task, repaired
    below.
    """
    # Arrange
    client = _Client()
    provider = OpenAILLMProvider(_settings(), client=client)
    wrapped = wrap(
        provider.complete, distribution="weft-openai", contract="LLMProvider", plugin=NAME
    )

    # Act
    outcome = await wrapped(_conversation("through the seam"), model="gpt-4o-mini", ctx=_ctx())

    # Assert
    assert isinstance(outcome, Produced)


# The blocking-call guard against a *freshly built* client — no injected `client`, so
# `_connected()` actually reaches `asyncio.to_thread(build_client, settings)` rather than
# returning on its first line — needs a real credential and a real vendor client, the same
# way `tests/unit/weft_qdrant/test_store.py`'s task 2.6 repair needs a real Qdrant container.
# That test lives in `tests/integration/test_openai_llm.py`, driving the public `.complete()`
# through `wrap`, not a private method reached from outside its own module.


# --- `map_openai_error` — one test per row, most-specific-first --------------------------------


def test_context_length_bad_request_maps_to_context_length() -> None:
    mapped = map_openai_error(_bad_request("context_length_exceeded"), model="m")
    assert isinstance(mapped, LLMContextLengthError)


def test_content_filter_bad_request_maps_to_content_filter() -> None:
    mapped = map_openai_error(_bad_request("content_policy_violation"), model="m")
    assert isinstance(mapped, LLMContentFilterError)


def test_timeout_maps_to_timeout_and_not_to_connection() -> None:
    # `openai.APITimeoutError` is itself an `APIConnectionError` — the row this test exists
    # to pin, so the two branches can never silently swap order.
    exc = APITimeoutError(request=_request())
    assert isinstance(exc, APIConnectionError)
    mapped = map_openai_error(exc, model="m")
    assert isinstance(mapped, LLMTimeoutError)


def test_connection_error_maps_to_connection() -> None:
    mapped = map_openai_error(APIConnectionError(request=_request()), model="m")
    assert isinstance(mapped, LLMConnectionError)


def test_rate_limit_maps_to_rate_limit() -> None:
    body = {"message": "slow down", "type": "rate_limit_error", "code": "rate_limit_exceeded"}
    response = httpx2.Response(429, request=_request(), json={"error": body})
    mapped = map_openai_error(RateLimitError("slow down", response=response, body=body), model="m")
    assert isinstance(mapped, LLMRateLimitError)
    assert mapped.transient is True


def test_internal_server_error_maps_to_service_unavailable() -> None:
    body = {"message": "oops", "type": "server_error", "code": None}
    response = httpx2.Response(500, request=_request(), json={"error": body})
    mapped = map_openai_error(InternalServerError("oops", response=response, body=body), model="m")
    assert isinstance(mapped, LLMServiceUnavailableError)


def test_authentication_error_maps_to_authentication() -> None:
    body = {"message": "bad key", "type": "invalid_request_error", "code": "invalid_api_key"}
    response = httpx2.Response(401, request=_request(), json={"error": body})
    mapped = map_openai_error(
        AuthenticationError("bad key", response=response, body=body), model="m"
    )
    assert isinstance(mapped, LLMAuthenticationError)


def test_permission_denied_maps_to_permission_denied() -> None:
    body = {"message": "no access", "type": "invalid_request_error", "code": None}
    response = httpx2.Response(403, request=_request(), json={"error": body})
    mapped = map_openai_error(
        PermissionDeniedError("no access", response=response, body=body), model="m"
    )
    assert isinstance(mapped, LLMPermissionDeniedError)


def test_not_found_maps_to_not_found() -> None:
    body = {"message": "no such model", "type": "invalid_request_error", "code": "model_not_found"}
    response = httpx2.Response(404, request=_request(), json={"error": body})
    mapped = map_openai_error(
        NotFoundError("no such model", response=response, body=body), model="m"
    )
    assert isinstance(mapped, LLMNotFoundError)


def test_a_bad_request_with_no_recognised_code_maps_to_bad_request() -> None:
    mapped = map_openai_error(_bad_request(None), model="m")
    assert isinstance(mapped, LLMBadRequestError)


def test_any_other_api_error_falls_back_to_bad_request() -> None:
    body = {"message": "conflict", "type": "invalid_request_error", "code": None}
    response = httpx2.Response(422, request=_request(), json={"error": body})
    mapped = map_openai_error(
        UnprocessableEntityError("conflict", response=response, body=body), model="m"
    )
    assert isinstance(mapped, LLMBadRequestError)


def test_the_mapped_error_always_names_the_provider_and_model() -> None:
    mapped = map_openai_error(APIConnectionError(request=_request()), model="gpt-4o-mini")
    assert mapped.provider == "openai"
    assert mapped.model == "gpt-4o-mini"


def testmap_openai_error_only_ever_returns_an_api_error_subclass_target() -> None:
    # The self-test: prove `map_openai_error` is actually reached with a real vendor type, not
    # merely with a stand-in shaped like one.
    assert isinstance(_bad_request("context_length_exceeded"), APIError)
