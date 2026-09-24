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
import re
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import TYPE_CHECKING, ClassVar, Final, Protocol, cast

import tiktoken
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

#: The `[packs.<name>]` block this provider's settings come from when nobody says otherwise —
#: `weft_openai.embedder.DEFAULT_ACCOUNT`'s own note says why it is not derived from `NAME`.
DEFAULT_ACCOUNT = "openai"

#: A small, current chat model. Measured against, not read off a page: every claim this
#: pack's docstrings make about `openai` is checked by `tests/integration/test_openai_llm.py`
#: against this exact model.
#:
#: **This is a pinned external fact, not a code constant** — ledger task **8.14**,
#: `docs/internal/lessons.md` L8.13. It names a model on somebody else's price list, and nothing in
#: this repository can ever detect that the vendor moved on; only `MODEL_PINNED_AS_OF`,
#: below, tells a reader when it was last checked. Every caller that needs the shipped
#: default imports this constant rather than repeating the literal — a copy is a second pin
#: that silently stops tracking the first the moment this one moves, and
#: `tests/architecture/test_pinned_external_facts.py` sweeps every tracked file to hold that.
DEFAULT_MODEL = "gpt-5.6-luna"

#: The date `DEFAULT_MODEL` was last checked against a real, current model list — the
#: deliberate twin of `weft_eval.pricing.RATES_AS_OF`, which exists for the identical reason:
#: a pinned external fact with no date looks current forever, because nothing downstream of
#: it can ever compute its own staleness — only a person re-checking the source and moving
#: this string can. Read, never compared: no code here weighs this date against the wall
#: clock, because how old is too old is a policy question this task leaves open, on the same
#: footing `09` §4.4 argues against inventing an unowned quality threshold.
MODEL_PINNED_AS_OF: Final[str] = "2026-09-05"

#: A `BadRequestError` carrying one of these vendor codes is a context-length refusal, not
#: an arbitrary malformed request — the one place `map_openai_error` looks inside the body rather
#: than switching on the exception's own class.
_CONTEXT_LENGTH_CODES = frozenset({"context_length_exceeded"})

#: Likewise for a request the vendor's own moderation refused.
_CONTENT_FILTER_CODES = frozenset({"content_filter", "content_policy_violation"})

#: `json_schema.name`'s own character rule — `openai/types/shared_params/
#: response_format_json_schema.py` (read 2026-09-21): "must be a-z, A-Z, 0-9, or contain
#: underscores and dashes, with a maximum length of 64."
_STRUCTURED_NAME_DISALLOWED = re.compile(r"[^A-Za-z0-9_-]")
_STRUCTURED_NAME_MAX_LENGTH = 64
#: What `complete_structured` names the schema when it carries no string `title` — see
#: `_schema_name`.
_DEFAULT_STRUCTURED_NAME = "answer"


class OpenAILLMConfig(BaseModel):
    """`OpenAILLMProvider`'s configuration — the generation knobs the chat completions API exposes.

    Reachable from code today the same way `OpenAIEmbedderConfig` is: nothing in
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
    def choices(self) -> Sequence[ChatCompletionChoice]:
        """The answer's alternatives; this pack reads only the first."""
        ...

    @property
    def usage(self) -> ChatCompletionUsage | None:
        """What the answer cost, where the endpoint reported it."""
        ...


class ChatCompletionChunkDelta(Protocol):
    @property
    def content(self) -> str | None: ...


class ChatCompletionChunkChoice(Protocol):
    @property
    def delta(self) -> ChatCompletionChunkDelta: ...


class ChatCompletionChunk(Protocol):
    """One streamed fragment — a delta, or the final usage-only chunk.

    The usage-only chunk arrives only with `stream_options.include_usage` sent, and its
    `choices` is always empty. See `stream_reporting_usage`.
    """

    @property
    def choices(self) -> Sequence[ChatCompletionChunkChoice]:
        """The fragment's deltas — empty on the final usage-only chunk."""
        ...

    @property
    def usage(self) -> ChatCompletionUsage | None:
        """The whole request's token counts, set only on the final usage-only chunk."""
        ...


class ChatCompletionsResource(Protocol):
    """The one endpoint this pack calls, declared as the shape it calls rather than imported.

    One method covers both call shapes, exactly as the vendor SDK's own `create` does:
    `stream=False` answers a `ChatCompletionResponse`, `stream=True` answers an async
    iterator of `ChatCompletionChunk`. A caller on the real client is cast to whichever this
    module asked for — see `_connected`'s docstring for why that cast, rather than a second,
    narrower Protocol per call shape, is the honest way to describe one vendor method.

    `stream_options` is sent only by `stream_reporting_usage` — `stream` itself never sends
    it, so a compatible endpoint that rejects the argument still serves a plain `stream` call.
    `response_format` is sent only by `complete_structured`, through
    `_StructuredChatCompletionsResource`.
    """

    async def create(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, str]],
        stream: bool = False,
        stream_options: Mapping[str, bool] | None = None,
        temperature: float | Omit = omit,
        max_tokens: int | Omit = omit,
        top_p: float | Omit = omit,
    ) -> ChatCompletionResponse | AsyncIterator[ChatCompletionChunk]:
        """Ask the endpoint for one answer, whole or streamed.

        Args:
            model: The model to answer under.
            messages: The conversation, as role/content mappings.
            stream: Whether to answer as an iterator of chunks.
            stream_options: Streaming options, sent only when usage is asked for.
            temperature: Sampling temperature, or `omit` for the API's own default.
            max_tokens: The answer's token cap, or `omit` for the model's own.
            top_p: Nucleus-sampling mass, or `omit` for the API's own default.

        Returns:
            A whole answer when `stream` is false, otherwise an iterator of chunks.
        """
        ...


class _StructuredChatCompletionsResource(Protocol):
    """`ChatCompletionsResource` plus `response_format`, which only `complete_structured` sends.

    Kept apart so doubles of the shared Protocol need not grow a parameter their call shape
    never uses.
    """

    async def create(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, str]],
        stream: bool = False,
        response_format: Mapping[str, object] | None = None,
        temperature: float | Omit = omit,
        max_tokens: int | Omit = omit,
        top_p: float | Omit = omit,
    ) -> ChatCompletionResponse: ...


class ChatResource(Protocol):
    """The client's `chat` namespace — the one resource this pack reaches through it."""

    @property
    def completions(self) -> ChatCompletionsResource:
        """The chat completions endpoint."""
        ...


class ChatClient(Protocol):
    """The client this pack holds: one resource, and a way to give its sockets back."""

    @property
    def chat(self) -> ChatResource:
        """The chat namespace the completions endpoint hangs off."""
        ...

    async def close(self) -> None:
        """Give the client's sockets back."""
        ...


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
        account: str = DEFAULT_ACCOUNT,
    ) -> None:
        self._settings = settings
        self._config = config if config is not None else OpenAILLMConfig()
        self._client = client
        self._account = account

    async def complete(
        self, conv: Conversation, *, model: str, ctx: Context
    ) -> Outcome[Completion]:
        """Answer `conv` in one non-streaming call.

        Args:
            conv: The conversation to answer.
            model: The model to answer under.
            ctx: Unused; no service or locale this provider needs.

        Returns:
            The answer, with its finish reason and token usage where reported.

        Raises:
            LLMError: The vendor's failure, mapped by `map_openai_error`; or
                `LLMAuthenticationError` when no credential is configured.
        """
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
        """Answer `conv` as a stream of text fragments.

        Args:
            conv: The conversation to answer.
            model: The model to answer under.
            ctx: Unused; no service or locale this provider needs.

        Yields:
            Each non-empty text fragment, in order.

        Raises:
            LLMError: The vendor's failure, from opening or draining the stream, mapped by
                `map_openai_error`; or `LLMAuthenticationError` when no credential is
                configured.
        """
        del ctx
        client = await self._connected(model=model)
        try:
            # Repair for a reviewer finding against task 2.30: `map_openai_error` is "the
            # whole answer" for a vendor exception only if every path a vendor exception can
            # take reaches it, and the request that opens an SSE stream succeeding tells you
            # nothing about the connection that stays open while it drains — a socket drop, a
            # timeout or a mid-stream 5xx surfaces from `__anext__`, inside this loop, not
            # from `create()` in `_open_stream`. Both calls are in one `try` so both raise
            # through the same `except APIError` below, rather than leaving a raw vendor
            # exception to escape past a caller that only knows how to catch
            # `weft_llm.errors.LLMError`.
            async for chunk in await self._open_stream(client, conv, model=model):
                piece = chunk.choices[0].delta.content
                if piece:
                    yield piece
        except APIError as exc:
            raise map_openai_error(exc, model=model) from exc

    async def stream_reporting_usage(
        self, conv: Conversation, *, model: str, ctx: Context
    ) -> AsyncIterator[str | TokenUsage]:
        """`stream`, with the vendor asked for the one extra chunk that carries the token count.

        Satisfies `weft_llm.contract.UsageReporting` structurally.

        `openai/types/chat/chat_completion_stream_options_param.py` (read 2026-09-15) on
        `include_usage`: "If set, an additional chunk will be streamed before the
        `data: [DONE]` message. The `usage` field on this chunk shows the token usage
        statistics for the entire request, and the `choices` field will always be an empty
        array." So `choices` is checked before being indexed — that final chunk has none.
        """
        del ctx
        client = await self._connected(model=model)
        try:
            async for chunk in await self._open_usage_stream(client, conv, model=model):
                usage = chunk.usage
                if usage is not None:
                    yield TokenUsage(
                        prompt_tokens=usage.prompt_tokens,
                        completion_tokens=usage.completion_tokens,
                    )
                    continue
                if not chunk.choices:
                    continue
                piece = chunk.choices[0].delta.content
                if piece:
                    yield piece
        except APIError as exc:
            raise map_openai_error(exc, model=model) from exc

    async def close(self) -> None:
        """Give the client's sockets back, if a client was ever built."""
        if self._client is not None:
            await self._client.close()

    async def _open_stream(
        self, client: ChatClient, conv: Conversation, *, model: str
    ) -> AsyncIterator[ChatCompletionChunk]:
        """The chunk iterator for `conv`, opened with this provider's generation knobs."""
        temperature, max_tokens, top_p = _generation_kwargs(self._config)
        chunks = await client.chat.completions.create(
            model=model,
            messages=_messages_of(conv),
            stream=True,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
        )
        return cast("AsyncIterator[ChatCompletionChunk]", chunks)

    async def _open_usage_stream(
        self, client: ChatClient, conv: Conversation, *, model: str
    ) -> AsyncIterator[ChatCompletionChunk]:
        """`_open_stream`, with the vendor asked for the final usage-only chunk."""
        temperature, max_tokens, top_p = _generation_kwargs(self._config)
        chunks = await client.chat.completions.create(
            model=model,
            messages=_messages_of(conv),
            stream=True,
            stream_options={"include_usage": True},
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
        )
        return cast("AsyncIterator[ChatCompletionChunk]", chunks)

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

        The SDK's own transport retries are disabled here because `[llm.retry]` wraps this
        provider and is the sole retry mechanism for LLM calls (repair R41.2).
        """
        if self._client is not None:
            return self._client
        settings = self._settings
        if not settings.api_key.get_secret_value():
            raise LLMAuthenticationError(
                f"no credential is configured for the '{self._account}' account, so the "
                f"'{self._account}' provider has nothing to authenticate with. Add "
                f'`[packs.{self._account}] api_key = "${{env:OPENAI_API_KEY}}"` to weft.toml — '
                "the settings loader interpolates `${env:...}`, so the key stays in the "
                "environment and out of the file.",
                provider=self._account,
                model=model,
            )
        client = await asyncio.to_thread(
            build_client, settings.model_copy(update={"max_retries": 0})
        )
        self._client = cast("ChatClient", client)
        return self._client

    async def count_tokens(self, text: str, *, model: str) -> int | None:
        """`text`'s token count under `model`'s own encoding — task **32.6**, gate **G25**.

        Satisfies `weft_llm.contract.TokenCounting`. `tiktoken.encoding_for_model` is the
        vendor's own model→encoding map; a model it has no mapping for raises `KeyError`, turned
        into `None`, never a default encoding — a wrong one would silently over- or under-fill a
        budgeted prompt. Runs in a worker thread: `tiktoken` reads its encoding file from a cache
        and downloads it on first use, and the seam's blocking-call guard stopped `32.10`'s paid
        run on that `open()`.
        """
        return await asyncio.to_thread(_count_tokens, text, model)


class NativeStructuredOpenAILLMProvider(OpenAILLMProvider):
    """`OpenAILLMProvider`, with `complete_structured` added — repair **R41.5**.

    Registered instead of `OpenAILLMProvider` when `Settings.structured_output` is true — see
    `weft_openai.register` and `weft_openai_compatible.register`, which choose the class at
    registration time, the same precedent R33.1 set for `stream_usage`. Satisfies
    `weft_llm.contract.NativeStructured` structurally: nothing declares the capability, the
    method's presence is the whole claim, the pattern every derived capability in that module
    takes.

    **A subclass, not a method on `OpenAILLMProvider` itself**, because the capability is
    opt-in per account: an account that has not set `structured_output` must register a class
    with no `complete_structured` attribute at all, or `isinstance(provider,
    NativeStructured)` would be true regardless of what the account's own settings say.
    """

    async def complete_structured(
        self, conv: Conversation, schema: Mapping[str, object], *, model: str, ctx: Context
    ) -> Outcome[Completion]:
        """Answer `conv` in one call, constrained by the vendor to `schema`.

        Args:
            conv: The conversation to answer.
            schema: The JSON schema the answer must satisfy.
            model: The model to answer under.
            ctx: Unused; no service or locale this provider needs.

        Returns:
            The answer, with its finish reason and token usage where reported.

        Raises:
            LLMError: The vendor's failure, mapped by `map_openai_error`; or
                `LLMAuthenticationError` when no credential is configured.
        """
        del ctx  # no service or locale this provider needs — same as `complete`
        client = await self._connected(model=model)
        temperature, max_tokens, top_p = _generation_kwargs(self._config)
        completions = cast("_StructuredChatCompletionsResource", client.chat.completions)
        try:
            response = await completions.create(
                model=model,
                messages=_messages_of(conv),
                stream=False,
                response_format=_response_format_of(schema),
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
            )
        except APIError as exc:
            raise map_openai_error(exc, model=model) from exc
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


def _response_format_of(schema: Mapping[str, object]) -> Mapping[str, object]:
    """`schema`, wrapped in the SDK's own `ResponseFormatJSONSchema` wire shape.

    No `strict` key: unset is the API's own default, and `OpenAILLMConfig`'s rule for every
    knob this pack sends is that unset means omitted, never sent as an explicit falsy value.
    """
    return {"type": "json_schema", "json_schema": {"name": _schema_name(schema), "schema": schema}}


def _schema_name(schema: Mapping[str, object]) -> str:
    """`json_schema.name` for `schema`, derived from its own `title`.

    The title with every disallowed character replaced by `_` and cut to 64, or
    `_DEFAULT_STRUCTURED_NAME` where `title` is missing or not a string.
    """
    title = schema.get("title")
    if not isinstance(title, str):
        return _DEFAULT_STRUCTURED_NAME
    return _STRUCTURED_NAME_DISALLOWED.sub("_", title)[:_STRUCTURED_NAME_MAX_LENGTH]


def _count_tokens(text: str, model: str) -> int | None:
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        return None
    return len(encoding.encode(text))


def _messages_of(conv: Conversation) -> list[dict[str, str]]:
    """`conv`'s turns, as the plain role/content mapping every chat-completion API takes."""
    return [{"role": message.role.value, "content": message.content} for message in conv.messages]


def _generation_kwargs(config: OpenAILLMConfig) -> tuple[float | Omit, int | Omit, float | Omit]:
    """`config`'s knobs, each `omit` where unset.

    The same "unset means omitted from the request, not sent as null" rule
    `OpenAIEmbedder._embed`'s `dimensions` already takes,
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
    "MODEL_PINNED_AS_OF",
    "NAME",
    "ChatClient",
    "ChatCompletionChunk",
    "ChatCompletionResponse",
    "ChatCompletionsResource",
    "ChatResource",
    "NativeStructuredOpenAILLMProvider",
    "OpenAILLMConfig",
    "OpenAILLMProvider",
    "map_openai_error",
]
