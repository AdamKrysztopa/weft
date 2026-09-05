"""Unit tests for `weft_llm.client`.

Mirrors `packages/weft-rag/src/weft_llm/client.py`. Covers the happy path (a role resolves to
a registered provider and the answer comes back decided), the streaming property task 2.17
rests on (every call emits to the `TokenSink`, tagged with the role), the model-string
resolution a declared catalogue turns on, and the two loud refusals — an unmapped role and a
provider name nothing registered.

**Every call here goes through the real seam.** `LLMClient` runs a provider outside `Runner`,
so it wraps each call in `weft_kernel.seam.wrap`; a test that reached the provider directly
would prove nothing about what a real run does, which is exactly how a `BlockingCallError`
reached production once already in this build.
"""

from collections.abc import AsyncIterator

import pytest

from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import NothingToProduce, Outcome, Produced
from weft_kernel.registry import Registry, UnknownPluginError
from weft_llm.client import NullSink, llm_service
from weft_llm.contract import LLMProvider, TokenSink
from weft_llm.errors import LLMGenerationLoopError, LLMProviderFaultError
from weft_llm.loop_guard import LoopGuardConfig
from weft_llm.models import UnknownModelError
from weft_llm.payload import Completion, Conversation, Message, MessageRole, Rendered, TokenChunk
from weft_llm.roles import LLMRoles, RoleMapping, UnmappedLLMRoleError
from weft_llm.scripted import ScriptedProvider

RENDERED = Rendered(
    conversation=Conversation(messages=(Message(role=MessageRole.USER, content="why?"),))
)


class _RecordingSink:
    """A `TokenSink` that keeps what it was handed, so a test can assert on the tagging."""

    def __init__(self) -> None:
        self.chunks: list[TokenChunk] = []
        self.closed = False

    async def emit(self, chunk: TokenChunk) -> None:
        self.chunks.append(chunk)

    async def close(self, *, reason: str | None = None) -> None:
        del reason
        self.closed = True


def _ctx(sink: TokenSink) -> Context:
    services = ServiceRegistry()
    services.add(TokenSink, sink)
    return Context(tenant_id="t", run_id="r", trace_id="x", locale="en", services=services)


def _registry() -> Registry:
    registry = Registry()
    registry.add(LLMProvider, "scripted", ScriptedProvider, distribution="weft-llm")
    return registry


async def test_a_mapped_role_reaches_its_provider_and_the_answer_is_decided() -> None:
    # Arrange
    client = llm_service(
        registry=_registry(),
        roles=LLMRoles(roles={"generate": RoleMapping(provider="scripted")}),
    )

    # Act
    outcome = await client.complete(RENDERED, role="generate", ctx=_ctx(NullSink()))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.text == "[scripted] why?"


async def test_every_call_emits_to_the_token_sink_tagged_with_its_role() -> None:
    # Arrange — decision 10: streaming attaches here, so a generator that forgets to stream
    # cannot exist. The sink sees the whole answer whether or not anyone displays it.
    sink = _RecordingSink()
    client = llm_service(
        registry=_registry(),
        roles=LLMRoles(roles={"grade": RoleMapping(provider="scripted")}),
    )

    # Act
    await client.complete(RENDERED, role="grade", ctx=_ctx(sink))

    # Assert
    assert {chunk.role for chunk in sink.chunks} == {"grade"}
    assert "".join(chunk.text for chunk in sink.chunks).strip() == "[scripted] why?"


async def test_an_unmapped_role_is_refused_before_any_provider_is_built() -> None:
    # Arrange
    client = llm_service(
        registry=_registry(),
        roles=LLMRoles(roles={"generate": RoleMapping(provider="scripted")}),
    )

    # Act / Assert
    with pytest.raises(UnmappedLLMRoleError):
        await client.complete(RENDERED, role="route", ctx=_ctx(NullSink()))


async def test_a_role_naming_an_unregistered_provider_fails_listing_the_registered_ones() -> None:
    # Arrange
    client = llm_service(
        registry=_registry(),
        roles=LLMRoles(roles={"generate": RoleMapping(provider="anthropic")}),
    )

    # Act / Assert — requirement 5, through the registry's own refusal rather than a new one.
    with pytest.raises(UnknownPluginError) as raised:
        await client.complete(RENDERED, role="generate", ctx=_ctx(NullSink()))
    assert "scripted" in str(raised.value)


async def test_a_provider_declaring_a_catalogue_refuses_a_model_it_does_not_offer() -> None:
    # Arrange
    class _Catalogued:
        models = ("small-v2", "large-v2")

        def __init__(self, config: object = None) -> None:
            del config

        async def complete(
            self, conv: Conversation, *, model: str, ctx: Context
        ) -> Outcome[Completion]:
            raise NotImplementedError

        async def stream(
            self, conv: Conversation, *, model: str, ctx: Context
        ) -> AsyncIterator[str]:
            del conv, ctx, model
            yield "unreachable"

        async def close(self) -> None:
            return

    registry = Registry()
    registry.add(LLMProvider, "acme", _Catalogued, distribution="weft-acme")
    client = llm_service(
        registry=registry,
        roles=LLMRoles(roles={"generate": RoleMapping(provider="acme", model="tiny")}),
    )

    # Act / Assert — the refusal arrives before the network, naming what is on offer.
    with pytest.raises(UnknownModelError) as raised:
        await client.complete(RENDERED, role="generate", ctx=_ctx(NullSink()))
    assert "small-v2" in str(raised.value)


async def test_a_provider_raising_something_outside_the_taxonomy_is_wrapped_and_named() -> None:
    # Arrange — "a taxonomy nobody catches is documentation": nothing but an `LLMError` may
    # escape the client, or every consumer downstream has to catch `Exception`.
    class _Buggy:
        def __init__(self, config: object = None) -> None:
            del config

        async def complete(
            self, conv: Conversation, *, model: str, ctx: Context
        ) -> Outcome[Completion]:
            raise NotImplementedError

        async def stream(
            self, conv: Conversation, *, model: str, ctx: Context
        ) -> AsyncIterator[str]:
            del conv, ctx, model
            raise KeyError("choices")
            yield ""  # pragma: no cover — makes this an async generator

        async def close(self) -> None:
            return

    registry = Registry()
    registry.add(LLMProvider, "buggy", _Buggy, distribution="weft-buggy")
    client = llm_service(
        registry=registry, roles=LLMRoles(roles={"generate": RoleMapping(provider="buggy")})
    )

    # Act / Assert
    with pytest.raises(LLMProviderFaultError) as raised:
        await client.complete(RENDERED, role="generate", ctx=_ctx(NullSink()))
    assert "buggy" in str(raised.value)


async def test_a_provider_that_answers_with_nothing_produces_nothing_rather_than_empty_text() -> (
    None
):
    # Arrange
    class _Silent:
        def __init__(self, config: object = None) -> None:
            del config

        async def complete(
            self, conv: Conversation, *, model: str, ctx: Context
        ) -> Outcome[Completion]:
            raise NotImplementedError

        async def stream(
            self, conv: Conversation, *, model: str, ctx: Context
        ) -> AsyncIterator[str]:
            del conv, ctx, model
            return
            yield ""  # pragma: no cover — makes this an async generator

        async def close(self) -> None:
            return

    registry = Registry()
    registry.add(LLMProvider, "silent", _Silent, distribution="weft-silent")
    client = llm_service(
        registry=registry, roles=LLMRoles(roles={"generate": RoleMapping(provider="silent")})
    )

    # Act
    outcome = await client.complete(RENDERED, role="generate", ctx=_ctx(NullSink()))

    # Assert — never an empty `Produced`, the trap every contract in this tree documents.
    assert isinstance(outcome, NothingToProduce)


async def test_native_structured_is_derived_from_the_provider_never_declared() -> None:
    # Arrange
    class _Native:
        def __init__(self, config: object = None) -> None:
            del config

        async def complete(
            self, conv: Conversation, *, model: str, ctx: Context
        ) -> Outcome[Completion]:
            raise NotImplementedError

        async def complete_structured(
            self,
            conv: Conversation,
            schema: object,
            *,
            model: str,
            ctx: Context,
        ) -> Outcome[Completion]:
            del conv, schema, ctx
            return Produced(value=Completion(text='{"ok": true}', model=model))

        async def stream(
            self, conv: Conversation, *, model: str, ctx: Context
        ) -> AsyncIterator[str]:
            del conv, ctx, model
            yield "unreachable"

        async def close(self) -> None:
            return

    registry = Registry()
    registry.add(LLMProvider, "native", _Native, distribution="weft-native")
    registry.add(LLMProvider, "scripted", ScriptedProvider, distribution="weft-llm")
    client = llm_service(
        registry=registry,
        roles=LLMRoles(
            roles={
                "grade": RoleMapping(provider="native"),
                "generate": RoleMapping(provider="scripted"),
            }
        ),
    )

    # Act
    native = await client.native_structured_available("grade")
    plain = await client.native_structured_available("generate")

    # Assert — capability derived by `isinstance`, never by a flag a provider could lie about.
    assert (native, plain) == (True, False)


# --- the degenerate-loop guard (task 3.10) -----------------------------------------------


def _streaming_provider(chunks: tuple[str, ...]) -> type:
    """A throwaway `LLMProvider` that streams exactly `chunks`, one `stream` call at a time."""

    class _Streaming:
        def __init__(self, config: object = None) -> None:
            del config

        async def complete(
            self, conv: Conversation, *, model: str, ctx: Context
        ) -> Outcome[Completion]:
            raise NotImplementedError

        async def stream(
            self, conv: Conversation, *, model: str, ctx: Context
        ) -> AsyncIterator[str]:
            del conv, ctx, model
            for chunk in chunks:
                yield chunk

        async def close(self) -> None:
            return

    return _Streaming


async def test_a_provider_stuck_in_a_loop_is_stopped_and_only_the_shown_tokens_survive() -> None:
    # Arrange — task 3.10: a small model repeating the same short phrase forever, well past
    # the guard's length floor. `LoopGuardConfig` here is the client's default.
    phrase = "the answer is the answer is "
    chunks = tuple(phrase for _ in range(20))  # 580 characters if never interrupted
    registry = Registry()
    registry.add(LLMProvider, "looping", _streaming_provider(chunks), distribution="weft-looping")
    client = llm_service(
        registry=registry, roles=LLMRoles(roles={"generate": RoleMapping(provider="looping")})
    )
    sink = _RecordingSink()

    # Act / Assert
    with pytest.raises(LLMGenerationLoopError) as raised:
        await client.complete(RENDERED, role="generate", ctx=_ctx(sink))
    assert "looping" in str(raised.value)
    # The stream was cut off well before all 20 chunks were asked for — proving the `async
    # for` stopped early rather than the guard merely being computed and ignored.
    assert len(sink.chunks) < len(chunks)
    # Every token shown before the loop was recognised is still exactly what the sink saw —
    # nothing already displayed is retracted.
    assert "".join(chunk.text for chunk in sink.chunks) == phrase * len(sink.chunks)


async def test_a_streamed_markdown_table_is_not_stopped_by_the_loop_guard() -> None:
    # Arrange — the trap task 3.10 exists to avoid: a table's rows are legitimately
    # repetitive, and must not be mistaken for a model stuck in a loop.
    rows = ("Intro text before the table begins here for good measure.\n",) + tuple(
        f"| row {i} | value {i} | note {i} |\n" for i in range(8)
    )
    registry = Registry()
    registry.add(LLMProvider, "tabular", _streaming_provider(rows), distribution="weft-tabular")
    client = llm_service(
        registry=registry, roles=LLMRoles(roles={"generate": RoleMapping(provider="tabular")})
    )

    # Act
    outcome = await client.complete(RENDERED, role="generate", ctx=_ctx(NullSink()))

    # Assert — every row arrived; nothing was cut off.
    assert isinstance(outcome, Produced)
    assert outcome.value.text == "".join(rows)


async def test_a_tighter_loop_guard_configuration_is_honoured() -> None:
    # Arrange — parameterisable, not hard-coded: a caller-supplied `LoopGuardConfig` changes
    # what fires, proving the client actually reads it rather than always using its own default.
    chunks = tuple("ab" for _ in range(40))  # 80 characters of a two-character repeat
    registry = Registry()
    registry.add(LLMProvider, "looping", _streaming_provider(chunks), distribution="weft-looping")
    tight = LoopGuardConfig(min_period=2, min_text_length=10)
    client = llm_service(
        registry=registry,
        roles=LLMRoles(roles={"generate": RoleMapping(provider="looping")}),
        loop_guard=tight,
    )

    # Act / Assert — the default `LoopGuardConfig` (`min_text_length=100`) would never even
    # start checking an 80-character answer; the tighter one supplied here does.
    with pytest.raises(LLMGenerationLoopError):
        await client.complete(RENDERED, role="generate", ctx=_ctx(NullSink()))
