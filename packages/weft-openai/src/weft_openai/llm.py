"""`openai` — an `LLMProvider` over OpenAI's chat completions API.

The counterpart to `weft_openai.embedder.OpenAIEmbedder`, and the second half of task 2.30:
"the generation pack names no vendor... this pack registers `openai` under `LLMProvider`."
Both plugins share one `weft_openai.Settings` — one account, per that module's own
docstring — and the same account-construction function, `weft_openai.embedder.build_client`,
so the base-URL and timeout corrections that function's docstring records apply here without
being re-derived. Registered under the *same name*, `"openai"`, as the embedder — the two
live under different contracts (`LLMProvider` here, `Embedder` there), so nothing collides,
and an operator reads one vendor name across both `[services] embed` and `[llm.roles]`.

**The vendor→domain mapping table is this module's other half.** OpenAI's SDK raises its
own thirteen-class hierarchy (`openai.APIError` and its subclasses); nothing downstream of
`weft-llm` — the retry wrapper, the structured-output cascade — may import `openai` to
decide what one of those means, because deciding *is* the vendor lock-in this pack exists to
contain. `map_openai_error` is the whole answer: every branch, ordered most-specific-first because
`openai.APITimeoutError` is itself a subclass of `openai.APIConnectionError` (measured
against the installed SDK, not assumed), turns one vendor exception into exactly one
`weft_llm.errors.LLMError` leaf, and `tests/unit/weft_openai/test_llm.py` drives one real
vendor exception instance through every row.

**Repair for a reviewer finding against this task: the vendor→domain mapping now covers
the stream too, not only the call that opens it.** `create(..., stream=True)` succeeding
says nothing about the connection that stays open while the answer drains — `map_openai_error`
now wraps the `async for` that reads it, not only the `create()` call, so a connection drop
mid-stream still leaves as an `LLMError` a caller can catch, not a raw `openai.APIError`.

**The generation knobs are real, on `OpenAILLMConfig`, the same shape
`weft_openai.embedder.OpenAIEmbedderConfig` already takes for the embedder — this pack does
not discard what it is handed.** Nothing in `[llm.roles]` routes to it yet (see that class's
own docstring), but a library caller reaches every field today, and `OpenAILLMProvider`
threads it into every `create()` call rather than accepting and dropping it.

**Missing credential raises `LLMAuthenticationError`, not a bespoke class.** Unlike the
embedder — which predates `weft-llm`'s taxonomy and so raises its own `MissingApiKeyError`
— a call with no key configured *is* an authentication failure in exactly the sense the
taxonomy already names, and a caller catching `LLMAuthenticationError` to decide whether a
credential problem occurred should not also have to know this pack's private class.

**The client is built off the event loop, for the same measured reason `build_client`'s own
docstring gives.** Constructing `AsyncOpenAI` loads a CA bundle through `open()`; one
`asyncio.to_thread` at first use, once per provider instance, and nothing else runs there.
"""

import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import TYPE_CHECKING, ClassVar, Protocol, cast

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
    omit,
)
from pydantic import BaseModel, ConfigDict, Field

from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_llm.errors import (
    LLMAuthenticationError,
    LLMBadRequestError,
    LLMConnectionError,
    LLMContentFilterError,
    LLMContextLengthError,
    LLMError,
    LLMNotFoundError,
    LLMPermissionDeniedError,
    LLMRateLimitError,
    LLMServiceUnavailableError,
    LLMTimeoutError,
)
from weft_llm.payload import Completion, Conversation, TokenUsage
from weft_openai.embedder import build_client

if TYPE_CHECKING:
    from weft_openai.settings import Settings

#: The name this provider is registered and selected under — see `weft_openai.register`.
NAME = "openai"

#: A small, current chat model. Measured against, not read off a page: every claim this
#: pack's docstrings make about `openai` is checked by `tests/integration/test_openai_llm.py`
#: against this exact model.
DEFAULT_MODEL = "gpt-4o-mini"

#: A `BadRequestError` carrying one of these vendor codes is a context-length refusal, not
#: an arbitrary malformed request — the one place `map_openai_error` looks inside the body rather
#: than switching on the exception's own class.
_CONTEXT_LENGTH_CODES = frozenset({"context_length_exceeded"})

#: Likewise for a request the vendor's own moderation refused.
_CONTENT_FILTER_CODES = frozenset({"content_filter", "content_policy_violation"})


class OpenAILLMConfig(BaseModel):
    """`OpenAILLMProvider`'s configuration — the generation knobs the chat completions API
    exposes, reachable from code today the same way `OpenAIEmbedderConfig` is: nothing in
    `[llm.roles]` can route a value here yet (`weft_llm.contract.LLMProvider`'s own module
    docstring: the `LLM` service that resolves a role to a provider instance is one task
    later), but a library caller constructing `OpenAILLMProvider` directly — or a future
    `[llm.roles]` entry, once that route exists — can already reach every field below.

    **Every default is the API's own**, the same rule `OpenAIEmbedderConfig` states: a
    provider built with no config gets what the vendor's documentation describes, not this
    pack's opinion of it. Unset means *omitted from the request*, not "sent as null" — see
    `_generation_kwargs` — because the API's own default for an omitted `temperature` or
    `top_p` is not the same thing as an explicit `0`, and collapsing that distinction would
    silently change what an operator who set nothing gets.

    Three of the endpoint's generation knobs, not all of them: `presence_penalty` and
    `frequency_penalty` push a chat model away from repeating itself, `temperature` and
    `top_p` are two different controls over the same sampling decision, and this class ships
    the pair the worked example in `.phase2-design.md` §7 actually needs — a `generate` role
    and a `grade` role sharing one account at two different temperatures — plus `max_tokens`,
    the one that bounds cost per call. A field this project has no worked use for yet is a
    field nobody has verified the right default for; the same restraint `OpenAIEmbedderConfig`
    takes with `encoding_format` and `user`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: `None` = the API's own default (currently `1.0`). See the class docstring.
    temperature: float | None = Field(default=None, ge=0, le=2)
    #: `None` = the model's own context-derived cap.
    max_tokens: int | None = Field(default=None, ge=1)
    #: `None` = the API's own default (currently `1.0`, i.e. no nucleus truncation).
    top_p: float | None = Field(default=None, gt=0, le=1)


class ChatCompletionMessage(Protocol):
    @property
    def content(self) -> str | None: ...


class ChatCompletionChoice(Protocol):
    @property
    def message(self) -> ChatCompletionMessage: ...

    @property
    def finish_reason(self) -> str | None: ...


class ChatCompletionUsage(Protocol):
    """Token counts one non-streaming answer actually cost — task **4.7**'s money half."""

    @property
    def prompt_tokens(self) -> int: ...

    @property
    def completion_tokens(self) -> int: ...


class ChatCompletionResponse(Protocol):
    """One non-streaming answer — the three fields this pack reads."""

    @property
    def choices(self) -> Sequence[ChatCompletionChoice]: ...

    @property
    def usage(self) -> ChatCompletionUsage | None: ...


class ChatCompletionChunkDelta(Protocol):
    @property
    def content(self) -> str | None: ...


class ChatCompletionChunkChoice(Protocol):
    @property
    def delta(self) -> ChatCompletionChunkDelta: ...


class ChatCompletionChunk(Protocol):
    """One streamed fragment — a delta, never the whole answer."""

    @property
    def choices(self) -> Sequence[ChatCompletionChunkChoice]: ...


class ChatCompletionsResource(Protocol):
    """The one endpoint this pack calls, declared as the shape it calls rather than imported.

    One method covers both call shapes, exactly as the vendor SDK's own `create` does:
    `stream=False` answers a `ChatCompletionResponse`, `stream=True` answers an async
    iterator of `ChatCompletionChunk`. A caller on the real client is cast to whichever this
    module asked for — see `_connected`'s docstring for why that cast, rather than a second,
    narrower Protocol per call shape, is the honest way to describe one vendor method.
    """

    async def create(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, str]],
        stream: bool = False,
        temperature: float | Omit = omit,
        max_tokens: int | Omit = omit,
        top_p: float | Omit = omit,
    ) -> ChatCompletionResponse | AsyncIterator[ChatCompletionChunk]: ...


class ChatResource(Protocol):
    @property
    def completions(self) -> ChatCompletionsResource: ...


class ChatClient(Protocol):
    """The client this pack holds: one resource, and a way to give its sockets back."""

    @property
    def chat(self) -> ChatResource: ...

    async def close(self) -> None: ...


class OpenAILLMProvider:
    """Answers a `Conversation` by calling OpenAI's chat completions endpoint.

    Satisfies `weft_llm.contract.LLMProvider` structurally: this class never imports it, the
    same path every third-party provider pack takes.

    `client` is a seam for a test, not a configuration surface — nothing in `[llm.roles]` or
    a pack settings block can reach it. Left unset, the real client is built on first use.

    `config` is real, unlike `client`: see `OpenAILLMConfig`'s own docstring for what each
    field reaches and why nothing routes to it from a pipeline document yet.
    """

    config_model: ClassVar[type[OpenAILLMConfig]] = OpenAILLMConfig

    def __init__(
        self,
        settings: "Settings",
        config: OpenAILLMConfig | None = None,
        *,
        client: ChatClient | None = None,
    ) -> None:
        self._settings = settings
        self._config = config if config is not None else OpenAILLMConfig()
        self._client = client

    async def complete(
        self, conv: Conversation, *, model: str, ctx: Context
    ) -> Outcome[Completion]:
        del ctx  # no service or locale this provider needs
        client = await self._connected(model=model)
        temperature, max_tokens, top_p = _generation_kwargs(self._config)
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=_messages_of(conv),
                stream=False,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
            )
        except APIError as exc:
            raise map_openai_error(exc, model=model) from exc
        response = cast("ChatCompletionResponse", response)
        choice = response.choices[0]
        text = choice.message.content or ""
        usage = (
            TokenUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
            )
            if response.usage is not None
            else None
        )
        return Produced(
            value=Completion(
                text=text, model=model, finish_reason=choice.finish_reason or "", usage=usage
            )
        )

    async def stream(self, conv: Conversation, *, model: str, ctx: Context) -> AsyncIterator[str]:
        del ctx
        client = await self._connected(model=model)
        temperature, max_tokens, top_p = _generation_kwargs(self._config)
        try:
            chunks = await client.chat.completions.create(
                model=model,
                messages=_messages_of(conv),
                stream=True,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
            )
            # Repair for a reviewer finding against task 2.30: `map_openai_error` is "the
            # whole answer" for a vendor exception only if every path a vendor exception can
            # take reaches it, and the request that opens an SSE stream succeeding tells you
            # nothing about the connection that stays open while it drains — a socket drop, a
            # timeout or a mid-stream 5xx surfaces from `__anext__`, inside this loop, not
            # from `create()` above. Both calls are in one `try` so both raise through the
            # same `except APIError` below, rather than leaving a raw vendor exception to
            # escape past a caller that only knows how to catch `weft_llm.errors.LLMError`.
            async for chunk in cast("AsyncIterator[ChatCompletionChunk]", chunks):
                piece = chunk.choices[0].delta.content
                if piece:
                    yield piece
        except APIError as exc:
            raise map_openai_error(exc, model=model) from exc

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()

    async def _connected(self, *, model: str) -> ChatClient:
        """The client, built on first use — off the loop, refusing without a credential.

        Reuses `weft_openai.embedder.build_client` — one careful account-construction
        function for both plugins this pack registers, rather than a second copy of its
        base-URL and timeout corrections. That function's own return type is the narrower
        `EmbeddingsClient` Protocol; the object it builds is a real `AsyncOpenAI`, which also
        satisfies `ChatClient` at runtime, so the cast states a fact about the concrete type
        rather than asking a type checker to re-derive it from an unrelated Protocol.

        `model` is only for the refusal message below — naming the call that would have run,
        not a fact this method otherwise needs, since one account answers under many models.
        """
        if self._client is not None:
            return self._client
        settings = self._settings
        if not settings.api_key.get_secret_value():
            raise LLMAuthenticationError(
                "no OpenAI credential is configured, so the 'openai' provider has nothing to "
                'authenticate with. Add `[packs.weft-openai] api_key = "${env:OPENAI_API_KEY}"` '
                "to weft.toml — the settings loader interpolates `${env:...}`, so the key stays "
                "in the environment and out of the file.",
                provider=NAME,
                model=model,
            )
        client = await asyncio.to_thread(build_client, settings)
        self._client = cast("ChatClient", client)
        return self._client


def _messages_of(conv: Conversation) -> list[dict[str, str]]:
    """`conv`'s turns, as the plain role/content mapping every chat-completion API takes."""
    return [{"role": message.role.value, "content": message.content} for message in conv.messages]


def _generation_kwargs(config: OpenAILLMConfig) -> tuple[float | Omit, int | Omit, float | Omit]:
    """`config`'s knobs, each `omit` where unset — the same "unset means omitted from the
    request, not sent as null" rule `OpenAIEmbedder._embed`'s `dimensions` already takes,
    applied to the three `OpenAILLMConfig` carries. Shared by `complete` and `stream` so the
    two call shapes cannot drift apart on which knobs they honour.
    """
    temperature = config.temperature if config.temperature is not None else omit
    max_tokens = config.max_tokens if config.max_tokens is not None else omit
    top_p = config.top_p if config.top_p is not None else omit
    return temperature, max_tokens, top_p


def map_openai_error(exc: APIError, *, model: str) -> LLMError:
    """`exc`, translated to exactly one `weft_llm.errors.LLMError` leaf.

    Most-specific-first, and the order is load-bearing rather than stylistic:
    `openai.APITimeoutError` **is** an `openai.APIConnectionError` (checked against the
    installed SDK — see `tests/unit/weft_openai/test_llm.py`), so a timeout reaching the
    connection check first would misclassify every timeout as a plain connection failure,
    which the retry wrapper this pack's own docstring names would still retry correctly by
    luck (both are transient) but which the message an operator reads would misname. The two
    context-aware `BadRequestError` branches look inside the vendor's own error `code`
    because the SDK does not raise a distinct exception class for either case — a
    context-length refusal and a content-filter refusal are both, structurally, "the request
    was rejected", and only the body says why.
    """
    if isinstance(exc, BadRequestError):
        code = getattr(exc, "code", None)
        if code in _CONTEXT_LENGTH_CODES:
            return LLMContextLengthError(str(exc), provider=NAME, model=model)
        if code in _CONTENT_FILTER_CODES:
            return LLMContentFilterError(str(exc), provider=NAME, model=model)
    if isinstance(exc, APITimeoutError):
        return LLMTimeoutError(str(exc), provider=NAME, model=model)
    if isinstance(exc, APIConnectionError):
        return LLMConnectionError(str(exc), provider=NAME, model=model)
    if isinstance(exc, RateLimitError):
        return LLMRateLimitError(str(exc), provider=NAME, model=model)
    if isinstance(exc, InternalServerError):
        return LLMServiceUnavailableError(str(exc), provider=NAME, model=model)
    if isinstance(exc, AuthenticationError):
        return LLMAuthenticationError(str(exc), provider=NAME, model=model)
    if isinstance(exc, PermissionDeniedError):
        return LLMPermissionDeniedError(str(exc), provider=NAME, model=model)
    if isinstance(exc, NotFoundError):
        return LLMNotFoundError(str(exc), provider=NAME, model=model)
    if isinstance(exc, BadRequestError):
        return LLMBadRequestError(str(exc), provider=NAME, model=model)
    # Every other `openai.APIError` — `ConflictError`, `UnprocessableEntityError`, and any
    # future class this pack's own test suite has not seen yet. None of these has retrying
    # the identical request as its fix, which is what puts it here rather than under a
    # transient leaf.
    return LLMBadRequestError(str(exc), provider=NAME, model=model)


__all__ = [
    "DEFAULT_MODEL",
    "NAME",
    "ChatClient",
    "ChatCompletionChunk",
    "ChatCompletionResponse",
    "ChatCompletionsResource",
    "ChatResource",
    "OpenAILLMConfig",
    "OpenAILLMProvider",
    "map_openai_error",
]
