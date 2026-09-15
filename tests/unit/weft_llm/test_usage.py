"""A run knows what each role and pipeline position spent in tokens — ledger task **33.6**.

`LLMClient.complete` always streams, and `LLMProvider.stream` yields bare text, so until this task
no token count reached a run at all: `Completion.usage` was filled only by `complete`, which the
client never calls. A provider that can report usage on a stream now says so by satisfying the
optional `UsageReporting` protocol — derived by `isinstance`, like `NativeStructured` — and the
client records one `UsageEntry` per call into an open `recording_usage()` scope.

**A provider that cannot report is named, never counted as zero.** Its entry carries `usage=None`;
a zero would be a plausible number about a call that was never measured.
"""

from collections.abc import AsyncIterator, Mapping
from typing import cast

from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Outcome, Produced
from weft_kernel.registry import Registry
from weft_kernel.seam import wrap
from weft_llm.client import NullSink, llm_service
from weft_llm.contract import LLMProvider, NativeStructured, TokenSink, UsageReporting
from weft_llm.payload import (
    Completion,
    Conversation,
    Message,
    MessageRole,
    Rendered,
    TokenChunk,
    TokenUsage,
)
from weft_llm.retry import RetryPolicy, with_retry
from weft_llm.roles import LLMRoles, RoleMapping
from weft_llm.scripted import ScriptedProvider
from weft_llm.usage import UsageEntry, recording_usage

RENDERED = Rendered(
    conversation=Conversation(messages=(Message(role=MessageRole.USER, content="why?"),))
)
USAGE = TokenUsage(prompt_tokens=11, completion_tokens=2)


class _RecordingSink:
    def __init__(self) -> None:
        self.chunks: list[TokenChunk] = []

    async def emit(self, chunk: TokenChunk) -> None:
        self.chunks.append(chunk)

    async def close(self, *, reason: str | None = None) -> None:
        del reason


class _Reporting:
    """A provider that streams two pieces and then reports what the call cost."""

    def __init__(self, config: object = None) -> None:
        del config

    async def complete(
        self, conv: Conversation, *, model: str, ctx: Context
    ) -> Outcome[Completion]:
        del conv, ctx
        return Produced(value=Completion(text="an answer", model=model, usage=USAGE))

    async def stream(self, conv: Conversation, *, model: str, ctx: Context) -> AsyncIterator[str]:
        del conv, model, ctx
        yield "an "
        yield "answer"

    async def stream_reporting_usage(
        self, conv: Conversation, *, model: str, ctx: Context
    ) -> AsyncIterator[str | TokenUsage]:
        del conv, model, ctx
        yield "an "
        yield "answer"
        yield USAGE

    async def close(self) -> None:
        return


class _ReportingAndStructured(_Reporting):
    async def complete_structured(
        self, conv: Conversation, schema: Mapping[str, object], *, model: str, ctx: Context
    ) -> Outcome[Completion]:
        del conv, schema, ctx
        return Produced(value=Completion(text="{}", model=model))


def _ctx(sink: TokenSink) -> Context:
    services = ServiceRegistry()
    services.add(TokenSink, sink)
    return Context(tenant_id="t", run_id="r", trace_id="x", locale="en", services=services)


async def test_a_reporting_provider_puts_its_usage_on_the_completion_and_in_the_tally() -> None:
    # Arrange
    registry = Registry()
    registry.add(LLMProvider, "reporting", _Reporting, distribution="weft-test")
    client = llm_service(
        registry=registry, roles=LLMRoles(roles={"generate": RoleMapping(provider="reporting")})
    )
    sink = _RecordingSink()

    # Act
    with recording_usage() as tally:
        outcome = await client.complete(RENDERED, role="generate", ctx=_ctx(sink))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.text == "an answer"
    assert outcome.value.usage == USAGE
    assert tally.entries == (
        UsageEntry(
            role="generate",
            position="",
            provider="reporting",
            model=outcome.value.model,
            usage=USAGE,
        ),
    )
    assert [chunk.text for chunk in sink.chunks] == ["an ", "answer"]


async def test_a_provider_that_cannot_report_is_named_as_not_reporting_never_zero() -> None:
    # Arrange
    registry = Registry()
    registry.add(LLMProvider, "scripted", ScriptedProvider, distribution="weft-llm")
    client = llm_service(
        registry=registry, roles=LLMRoles(roles={"grade": RoleMapping(provider="scripted")})
    )

    # Act
    with recording_usage() as tally:
        outcome = await client.complete(RENDERED, role="grade", ctx=_ctx(NullSink()))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.usage is None
    (entry,) = tally.entries
    assert (entry.role, entry.provider, entry.usage) == ("grade", "scripted", None)


async def test_an_entry_names_the_pipeline_position_that_asked() -> None:
    """Two roles can share a position and one role can serve two positions, so the position is
    read off the seam (`current_stage`, repair `R10.1`), never inferred from the role."""
    # Arrange
    registry = Registry()
    registry.add(LLMProvider, "reporting", _Reporting, distribution="weft-test")
    client = llm_service(
        registry=registry, roles=LLMRoles(roles={"generate": RoleMapping(provider="reporting")})
    )
    ctx = _ctx(NullSink())

    async def _stage(payload: object) -> Outcome[Completion]:
        del payload
        return await client.complete(RENDERED, role="generate", ctx=ctx)

    stage = wrap(
        _stage, distribution="weft-test", contract="Generator", plugin="g", position="answer"
    )

    # Act
    with recording_usage() as tally:
        await stage(None)

    # Assert
    (entry,) = tally.entries
    assert entry.position == "answer"


async def test_outside_a_scope_nothing_is_tallied_and_the_completion_still_carries_usage() -> None:
    # Arrange
    registry = Registry()
    registry.add(LLMProvider, "reporting", _Reporting, distribution="weft-test")
    client = llm_service(
        registry=registry, roles=LLMRoles(roles={"generate": RoleMapping(provider="reporting")})
    )

    # Act
    outcome = await client.complete(RENDERED, role="generate", ctx=_ctx(NullSink()))
    with recording_usage() as tally:
        pass

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.usage == USAGE
    assert tally.entries == ()


def test_the_retry_wrapper_advertises_usage_reporting_exactly_when_the_provider_has_it() -> None:
    """A wrapper that erased the capability would make every retried provider silently report
    nothing — the failure `RetryingNativeStructuredProvider` exists to prevent, one protocol over.
    """
    # Arrange
    policy = RetryPolicy()

    # Act
    reporting = with_retry(cast("LLMProvider", _Reporting()), policy)
    plain = with_retry(cast("LLMProvider", ScriptedProvider()), policy)
    both = with_retry(cast("LLMProvider", _ReportingAndStructured()), policy)

    # Assert
    assert isinstance(reporting, UsageReporting)
    assert not isinstance(reporting, NativeStructured)
    assert not isinstance(plain, UsageReporting)
    assert isinstance(both, UsageReporting)
    assert isinstance(both, NativeStructured)


def test_a_usage_entry_is_a_frozen_model() -> None:
    # Act / Assert
    assert UsageEntry.model_config.get("frozen") is True
