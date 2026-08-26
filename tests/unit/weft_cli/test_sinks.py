"""Unit tests for `weft_cli.sinks`.

Mirrors `packages/weft-cli/src/weft_cli/sinks.py`. Task **3.6**: "tokens reach a reader as
they arrive, through a resolved service." The timing tests below are the point of this
file — `docs/build-ledger.md` 3.6's own brief warns that a test only checking the
*finished* text would pass against a sink that buffered everything and flushed at
`close()`, which is exactly the shape this task exists to refuse. Both timing tests drive
the real `weft_llm.client.LLMClient.complete` against a fake provider that `await
asyncio.sleep`s between chunks — real wall-clock gaps a buffering sink could not produce
between the `write` calls a reader actually sees — rather than asserting anything about
call order alone, which a buffering sink could still satisfy by calling `write` in a tight
loop the instant the whole stream had drained.
"""

from __future__ import annotations

import asyncio
import io
import json
import time
from collections.abc import AsyncIterator

import pytest

from weft_cli.error_envelope import build_error_envelope
from weft_cli.exit_codes import ExitCode
from weft_cli.sinks import (
    DEFAULT_DISPLAY_ROLES,
    JsonSink,
    LineKind,
    PrintingSink,
    StreamEvent,
    StreamEventType,
)
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Outcome, Produced
from weft_kernel.registry import Registry, UnknownPluginError
from weft_llm.client import LLMClient
from weft_llm.contract import LLMProvider, TokenSink
from weft_llm.payload import Completion, Conversation, Message, MessageRole, Rendered, TokenChunk
from weft_llm.roles import LLMRoles, RoleMapping

_CHUNK_DELAY_SECONDS = 0.05
_WORDS = ("alpha", "beta", "gamma")


class _SleepyProvider:
    """An `LLMProvider` that streams `_WORDS`, sleeping for real between each — the fake
    this file's timing tests need and `weft_llm.scripted.ScriptedProvider` does not
    provide (its own `stream` yields with no `await` between words at all, so nothing
    observing it could tell "as they arrive" from "all at once").
    """

    async def complete(
        self, conv: Conversation, *, model: str, ctx: Context
    ) -> Outcome[Completion]:
        del conv, model, ctx
        raise NotImplementedError("this fake is for LLMClient.complete's streaming path only")

    async def stream(self, conv: Conversation, *, model: str, ctx: Context) -> AsyncIterator[str]:
        del conv, model, ctx
        for word in _WORDS:
            await asyncio.sleep(_CHUNK_DELAY_SECONDS)
            yield word

    async def close(self) -> None:
        return


def _ctx(sink: TokenSink) -> Context:
    services = ServiceRegistry()
    services.add(TokenSink, sink)
    return Context(tenant_id="t", run_id="r", trace_id="tr", locale="en", services=services)


def _sleepy_factory(config: object) -> _SleepyProvider:
    del config
    return _SleepyProvider()


async def _stream_words(sink: TokenSink) -> None:
    registry = Registry()
    registry.add(LLMProvider, "sleepy", _sleepy_factory, distribution="test-provider")
    roles = LLMRoles(roles={"generate": RoleMapping(provider="sleepy")})
    client = LLMClient(registry=registry, roles=roles)
    rendered = Rendered(
        conversation=Conversation(messages=(Message(role=MessageRole.USER, content="hi"),))
    )
    outcome = await client.complete(rendered, role="generate", ctx=_ctx(sink))
    assert isinstance(outcome, Produced)


class _TimedWrites(io.StringIO):
    """A stream that records *when* each `write` reached it, not only what — the timing
    proof this module's own tests need. `time.monotonic()` per call, never `time.time()`,
    since only elapsed duration is asserted, never wall-clock position.
    """

    def __init__(self) -> None:
        super().__init__()
        self.at: list[float] = []

    def write(self, text: str) -> int:
        self.at.append(time.monotonic())
        return super().write(text)


async def test_printing_sink_writes_arrive_with_real_elapsed_time_between_them() -> None:
    # Arrange
    stream = _TimedWrites()
    sink = PrintingSink(stream=stream)

    # Act
    await _stream_words(sink)

    # Assert — one write per word (`PrintingSink` never batches), each separated by close
    # to the real sleep the fake provider awaited between yields. A sink that buffered
    # everything and wrote it in `close()` would show every timestamp within a fraction of
    # a millisecond of each other; this asserts the opposite.
    assert len(stream.at) >= len(_WORDS)
    word_writes = stream.at[: len(_WORDS)]
    gaps = [b - a for a, b in zip(word_writes, word_writes[1:], strict=False)]
    assert all(gap >= _CHUNK_DELAY_SECONDS * 0.6 for gap in gaps)
    assert stream.getvalue() == "alphabetagamma"


async def test_json_sink_writes_arrive_with_real_elapsed_time_between_them() -> None:
    # Arrange
    stream = _TimedWrites()
    sink = JsonSink(stream=stream)

    # Act
    await _stream_words(sink)

    # Assert — same timing property, for the JSON sink's own per-event `write` calls (one
    # `write` per event — see `JsonSink._write`'s own docstring for why).
    gaps = [b - a for a, b in zip(stream.at, stream.at[1:], strict=False)]
    assert all(gap >= _CHUNK_DELAY_SECONDS * 0.6 for gap in gaps)
    lines = [line for line in stream.getvalue().splitlines() if line]
    assert len(lines) == len(_WORDS)


async def test_printing_sink_filters_by_display_role() -> None:
    # Arrange
    stream = io.StringIO()
    sink = PrintingSink(stream=stream, display_roles=DEFAULT_DISPLAY_ROLES)

    # Act
    await sink.emit(TokenChunk(role="grade", text="internal scoring chatter"))
    await sink.emit(TokenChunk(role="generate", text="visible"))
    await sink.close()

    # Assert
    assert "internal scoring chatter" not in stream.getvalue()
    assert "visible" in stream.getvalue()


async def test_printing_sink_close_marks_an_error_distinctly_from_a_clean_end() -> None:
    # Arrange
    clean = io.StringIO()
    errored = io.StringIO()

    # Act
    await PrintingSink(stream=clean).close(reason=None)
    await PrintingSink(stream=errored).close(reason="provider 'x' raised RuntimeError: boom")

    # Assert — a human reading either scrollback cannot mistake one for the other.
    assert clean.getvalue() == ""
    assert "stream error" in errored.getvalue()
    assert "boom" in errored.getvalue()


async def test_json_sink_close_emits_done_on_a_clean_end() -> None:
    # Arrange
    stream = io.StringIO()
    sink = JsonSink(stream=stream)

    # Act
    await sink.close(reason=None)

    # Assert
    line = stream.getvalue().strip()
    assert f'"type":"{StreamEventType.DONE.value}"' in line
    assert "error" not in line


async def test_json_sink_close_emits_error_never_mistakable_for_done() -> None:
    # Arrange — the reference correction this sink exists to avoid (`.phase3-design.md` §2.3(b)):
    # an error event must be *structurally* distinct from a clean end, not merely worded
    # differently, so a consumer that only checks `type` can never confuse the two.
    stream = io.StringIO()
    sink = JsonSink(stream=stream)

    # Act
    await sink.close(reason="provider 'x' raised RuntimeError: boom")

    # Assert
    line = stream.getvalue().strip()
    assert f'"type":"{StreamEventType.ERROR.value}"' in line
    assert '"type":"done"' not in line
    assert "boom" in line


@pytest.mark.parametrize("sink_cls", [PrintingSink, JsonSink])
async def test_a_role_outside_the_display_set_never_reaches_the_stream(sink_cls: type) -> None:
    # Arrange
    stream = io.StringIO()
    sink = sink_cls(stream=stream)

    # Act
    await sink.emit(TokenChunk(role="grade", text="should never print"))

    # Assert
    assert stream.getvalue() == ""


# ---------------------------------------------------------------------------
# Task 6.16 — a `--json` consumer tells one line's shape from another.
# `docs/lessons.md` L5.16; `03` -> Output; `09` section 3 (promised, additively).
# ---------------------------------------------------------------------------


def test_a_stream_event_names_its_own_shape() -> None:
    """The two things `--json` writes to one stream must be distinguishable without guessing.

    `weft --json ask` emits `StreamEvent` lines while a pipeline runs, and a failure emits an
    `ErrorEnvelope` on the same descriptor. Before this, a consumer told them apart by looking
    for keys — and worse, `StreamEvent(type="error")` and `ErrorEnvelope` are *both* "an error",
    in different shapes, so key-sniffing had to get the ambiguous case right to be correct at
    all.
    """
    # Arrange
    event = StreamEvent(type=StreamEventType.CHUNK, role="answer", text="hello")

    # Act
    dumped = event.model_dump()

    # Assert
    assert dumped["kind"] == LineKind.STREAM_EVENT
    assert dumped["type"] == StreamEventType.CHUNK, (
        "`type` keeps meaning which stream event this is; `kind` says which *shape* the line is. "
        "One key answering both questions is what `09` section 3 refuses for the status "
        "vocabulary, one surface over."
    )


def test_the_two_line_shapes_are_distinguishable_by_one_key() -> None:
    """The property itself, stated as a consumer would use it."""
    # Arrange
    event = StreamEvent(type=StreamEventType.ERROR, message="the model refused")
    envelope = build_error_envelope(
        UnknownPluginError("no 'nope' is registered", valid_options=("yes",)),
        exit_code=ExitCode.OPERATION_FAILED,
    )

    # Act
    kinds = {event.model_dump()["kind"], envelope.model_dump()["kind"]}

    # Assert
    assert kinds == {LineKind.STREAM_EVENT, LineKind.ERROR_ENVELOPE}, (
        "the ambiguous pair is exactly this one — a stream event whose `type` is 'error', and an "
        "error envelope. A consumer that cannot separate them cannot tell a stage reporting a "
        "problem from the run refusing."
    )


async def test_json_sink_writes_the_discriminant_on_every_line() -> None:
    """It has to be on the wire, not merely on the model — the sink is what a consumer reads.

    `async def`, awaited, rather than a helper calling `asyncio.run`: fitness function 7(a) is
    exactly one `asyncio.run` in the whole tree, at `weft_cli.cli`'s entry point, and it caught
    the first draft of this test. `asyncio_mode = "auto"` means an async test needs no runner.
    """
    # Arrange
    stream = io.StringIO()
    sink = JsonSink(stream=stream, display_roles=frozenset({"answer"}))

    # Act
    await sink.emit(TokenChunk(role="answer", text="hi"))

    # Assert
    lines = [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]
    assert lines, "the sink wrote nothing to parse"
    assert all(line["kind"] == LineKind.STREAM_EVENT.value for line in lines)
