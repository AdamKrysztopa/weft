"""Unit tests for `weft_kernel.seam`.

Mirrors `packages/weft-kernel/src/weft_kernel/seam.py`. Covers the four
concerns `wrap` applies without the author asking: a span carrying the
derived name and attributes, `__transient__` stripped from a produced
`Node`, an unrelated exception attributed and re-raised with `__cause__`
preserved, and `CancelledError` propagating unwrapped rather than being
caught and rewritten.

Span assertions use a hand-rolled tracer double, not the OpenTelemetry SDK:
`weft-kernel` ships only `opentelemetry-api` (fitness function 1), whose
default tracer is a no-op, so a real span never has content to assert on.
Substituting a recording double at the same seam `wrap` calls through tests
exactly what this module is responsible for — that it calls the tracer
correctly — without pulling in the SDK to test a promise the SDK, not this
module, keeps.
"""

import asyncio
import time
from collections.abc import Generator
from contextlib import contextmanager

import pytest

from weft_kernel import seam
from weft_kernel.blocking import BlockingCallError
from weft_kernel.errors import WeftError
from weft_kernel.payload import ExtModel, MediaType, Node, Outcome, Produced, SourceId


class _Secret(ExtModel):
    __namespace__ = "weft-test-secret"
    __transient__ = True

    blob: str


class _Kept(ExtModel):
    __namespace__ = "weft-test-kept"

    label: str


class _RecordingSpan:
    def __init__(self) -> None:
        self.attributes: dict[str, object] = {}

    def set_attribute(self, key: str, value: object) -> None:
        self.attributes[key] = value


class _RecordingTracer:
    def __init__(self) -> None:
        self.spans: list[tuple[str, _RecordingSpan]] = []

    @contextmanager
    def start_as_current_span(self, name: str, **kwargs: object) -> Generator[_RecordingSpan]:
        span = _RecordingSpan()
        self.spans.append((name, span))
        yield span


@pytest.fixture
def tracer(monkeypatch: pytest.MonkeyPatch) -> _RecordingTracer:
    fake = _RecordingTracer()
    monkeypatch.setattr(seam, "_tracer", fake)
    return fake


async def test_wrap_runs_the_call_and_records_a_span(tracer: _RecordingTracer) -> None:
    # Arrange
    async def run(payload: str) -> Outcome[str]:
        return Produced(value=payload.upper())

    wrapped = seam.wrap(run, distribution="weft-chunk", contract="Chunker", plugin="fixed-size")

    # Act
    outcome = await wrapped("hello")

    # Assert
    assert outcome == Produced(value="HELLO")
    [(name, span)] = tracer.spans
    assert name == "Chunker:fixed-size"
    assert span.attributes == {
        "weft.pack": "weft-chunk",
        "weft.contract": "Chunker",
        "weft.plugin": "fixed-size",
    }


async def test_wrap_strips_transient_ext_from_a_produced_node(tracer: _RecordingTracer) -> None:
    # Arrange
    node = Node.synthetic(
        content="full document text",
        media_type=MediaType.TEXT,
        reason="root of doc-1",
        sources=frozenset({SourceId("doc-1")}),
    )
    node = node.with_ext(_Secret(blob="do-not-persist")).with_ext(_Kept(label="keep-me"))

    async def run() -> Outcome[Node]:
        return Produced(value=node)

    wrapped = seam.wrap(run, distribution="weft-graph", contract="Extractor", plugin="demo")

    # Act
    outcome = await wrapped()

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.ext_as(_Secret) is None
    assert outcome.value.ext_as(_Kept) == _Kept(label="keep-me")


async def test_wrap_strips_transient_ext_from_a_produced_list_of_nodes(
    tracer: _RecordingTracer,
) -> None:
    # Arrange
    node = Node.synthetic(
        content="chunk one",
        media_type=MediaType.TEXT,
        reason="chunk of doc-1",
        sources=frozenset({SourceId("doc-1")}),
    )
    node = node.with_ext(_Secret(blob="do-not-persist")).with_ext(_Kept(label="keep-me"))

    async def run() -> Outcome[list[Node]]:
        return Produced(value=[node])

    wrapped = seam.wrap(run, distribution="weft-chunk", contract="Chunker", plugin="fixed-size")

    # Act
    outcome = await wrapped()

    # Assert
    assert isinstance(outcome, Produced)
    [stripped] = outcome.value
    assert isinstance(outcome.value, list)
    assert stripped.ext_as(_Secret) is None
    assert stripped.ext_as(_Kept) == _Kept(label="keep-me")


async def test_wrap_attributes_an_unrelated_exception_and_keeps_its_cause(
    tracer: _RecordingTracer,
) -> None:
    # Arrange
    failure = ValueError("boom")

    async def run() -> Outcome[str]:
        raise failure

    wrapped = seam.wrap(run, distribution="weft-chunk", contract="Chunker", plugin="fixed-size")

    # Act / Assert
    with pytest.raises(WeftError) as excinfo:
        await wrapped()

    error = excinfo.value
    assert (error.pack, error.contract, error.plugin, error.stage) == (
        "weft-chunk",
        "Chunker",
        "fixed-size",
        "Chunker:fixed-size",
    )
    assert error.__cause__ is failure


async def test_wrap_lets_cancelled_error_propagate_unwrapped(tracer: _RecordingTracer) -> None:
    # Arrange
    async def run() -> Outcome[str]:
        raise asyncio.CancelledError

    wrapped = seam.wrap(run, distribution="weft-chunk", contract="Chunker", plugin="fixed-size")

    # Act / Assert
    with pytest.raises(asyncio.CancelledError):
        await wrapped()


async def test_wrap_fills_only_the_attribution_fields_a_pack_left_none(
    tracer: _RecordingTracer,
) -> None:
    # Arrange
    async def run() -> Outcome[str]:
        raise WeftError("library failure", plugin="its-own-name")

    wrapped = seam.wrap(run, distribution="weft-chunk", contract="Chunker", plugin="fixed-size")

    # Act / Assert
    with pytest.raises(WeftError) as excinfo:
        await wrapped()

    error = excinfo.value
    assert (error.pack, error.contract, error.plugin, error.stage) == (
        "weft-chunk",
        "Chunker",
        "its-own-name",
        "Chunker:fixed-size",
    )


async def test_wrap_integrates_the_blocking_guard(tracer: _RecordingTracer) -> None:
    # Arrange
    async def run() -> Outcome[str]:
        time.sleep(0)
        return Produced(value="unreachable")

    wrapped = seam.wrap(run, distribution="weft-chunk", contract="Chunker", plugin="fixed-size")

    # Act / Assert
    with pytest.raises(BlockingCallError) as excinfo:
        await wrapped()

    assert "Chunker:fixed-size" in str(excinfo.value)


async def test_wrap_uses_a_caller_supplied_stage_label_over_the_contract_plugin_default(
    tracer: _RecordingTracer,
) -> None:
    # Arrange — two pipeline positions naming the same contract and plugin must be
    # distinguishable, which the `contract:plugin` default alone cannot do (`06` step 6).
    async def run(payload: str) -> Outcome[str]:
        return Produced(value=payload)

    wrapped = seam.wrap(
        run,
        distribution="weft-chunk",
        contract="Chunker",
        plugin="fixed-size",
        stage="clean-then-chunk:2",
    )

    # Act
    await wrapped("a")

    # Assert
    [(name, _span)] = tracer.spans
    assert name == "clean-then-chunk:2"


async def test_wrap_attributes_a_failure_with_the_caller_supplied_stage_label(
    tracer: _RecordingTracer,
) -> None:
    # Arrange
    async def run() -> Outcome[str]:
        raise ValueError("boom")

    wrapped = seam.wrap(
        run,
        distribution="weft-chunk",
        contract="Chunker",
        plugin="fixed-size",
        stage="clean-then-chunk:2",
    )

    # Act / Assert
    with pytest.raises(WeftError) as excinfo:
        await wrapped()

    assert excinfo.value.stage == "clean-then-chunk:2"


async def test_wrap_flush_runs_the_call_and_records_a_span(tracer: _RecordingTracer) -> None:
    # Arrange
    flushed: list[str] = []

    async def flush() -> None:
        flushed.append("flushed")

    wrapped = seam.wrap_flush(
        flush, distribution="weft-store", contract="NodeStore", plugin="pgvector", stage="s1"
    )

    # Act
    await wrapped()

    # Assert
    assert flushed == ["flushed"]
    [(name, span)] = tracer.spans
    assert name == "s1:flush"
    assert span.attributes == {
        "weft.pack": "weft-store",
        "weft.contract": "NodeStore",
        "weft.plugin": "pgvector",
    }


async def test_wrap_flush_attributes_an_unrelated_exception_and_keeps_its_cause(
    tracer: _RecordingTracer,
) -> None:
    # Arrange
    failure = ValueError("disk full")

    async def flush() -> None:
        raise failure

    wrapped = seam.wrap_flush(
        flush, distribution="weft-store", contract="NodeStore", plugin="pgvector", stage="s1"
    )

    # Act / Assert
    with pytest.raises(WeftError) as excinfo:
        await wrapped()

    error = excinfo.value
    assert (error.pack, error.contract, error.plugin, error.stage) == (
        "weft-store",
        "NodeStore",
        "pgvector",
        "s1",
    )
    assert error.__cause__ is failure
