"""Unit tests for `weft_kernel.seam`.

Mirrors `packages/weft-kernel/src/weft_kernel/seam.py`. Covers the concerns
`wrap` applies without the author asking: a span carrying the derived name
and attributes, `__transient__` stripped from a produced `Node`, every NUL
byte a produced `Node`'s `content` or ext `str` fields carry replaced with a
space and counted on that same span, an unrelated exception attributed and
re-raised with `__cause__` preserved, and `CancelledError` propagating
unwrapped rather than being caught and rewritten.

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
from pydantic import Field, ValidationError

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


class _TextField(ExtModel):
    __namespace__ = "weft-test-textfield"

    body: str


class _NoWhitespace(ExtModel):
    __namespace__ = "weft-test-nowhitespace"

    word: str = Field(pattern=r"^\S+$")


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
        "weft.nul_bytes_removed": 0,
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


async def test_wrap_sanitizes_nul_bytes_in_produced_node_content(
    tracer: _RecordingTracer,
) -> None:
    # Arrange
    node = Node.synthetic(
        content="page one\x00\x00page two",
        media_type=MediaType.TEXT,
        reason="extracted from doc-1",
        sources=frozenset({SourceId("doc-1")}),
    )

    async def run() -> Outcome[Node]:
        return Produced(value=node)

    wrapped = seam.wrap(run, distribution="weft-pdf", contract="Extractor", plugin="pdf-text")

    # Act
    outcome = await wrapped()

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.content == "page one  page two"
    assert "\x00" not in outcome.value.content
    [(_name, span)] = tracer.spans
    assert span.attributes["weft.nul_bytes_removed"] == 2


async def test_wrap_sanitizes_nul_bytes_in_an_ext_models_str_field(
    tracer: _RecordingTracer,
) -> None:
    # Arrange — a NUL byte in a non-transient ext model's `str` field, not in `content`.
    node = Node.synthetic(
        content="clean content",
        media_type=MediaType.TEXT,
        reason="extracted from doc-1",
        sources=frozenset({SourceId("doc-1")}),
    ).with_ext(_TextField(body="dirty\x00body"))

    async def run() -> Outcome[Node]:
        return Produced(value=node)

    wrapped = seam.wrap(run, distribution="weft-pdf", contract="Extractor", plugin="pdf-text")

    # Act
    outcome = await wrapped()

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.content == "clean content"
    assert outcome.value.ext_as(_TextField) == _TextField(body="dirty body")
    [(_name, span)] = tracer.spans
    assert span.attributes["weft.nul_bytes_removed"] == 1


async def test_wrap_raises_when_nul_sanitisation_breaks_an_ext_models_own_constraint(
    tracer: _RecordingTracer,
) -> None:
    # Arrange — a NUL satisfies `_NoWhitespace`'s pattern; the space the sanitiser
    # turns it into does not, so the rebuild must fail loudly rather than smuggle it through.
    node = Node.synthetic(
        content="clean content",
        media_type=MediaType.TEXT,
        reason="extracted from doc-1",
        sources=frozenset({SourceId("doc-1")}),
    ).with_ext(_NoWhitespace(word="dirty\x00word"))

    async def run() -> Outcome[Node]:
        return Produced(value=node)

    wrapped = seam.wrap(run, distribution="weft-pdf", contract="Extractor", plugin="pdf-text")

    # Act / Assert
    with pytest.raises(WeftError) as excinfo:
        await wrapped()

    error = excinfo.value
    assert "_NoWhitespace" in str(error)
    assert isinstance(error.__cause__, ValidationError)


async def test_wrap_returns_the_same_node_object_when_nothing_needs_cleaning(
    tracer: _RecordingTracer,
) -> None:
    # Arrange — no NUL anywhere, and no transient ext, so nothing this seam does should rebuild.
    node = Node.synthetic(
        content="already clean",
        media_type=MediaType.TEXT,
        reason="extracted from doc-1",
        sources=frozenset({SourceId("doc-1")}),
    ).with_ext(_Kept(label="keep-me"))

    async def run() -> Outcome[Node]:
        return Produced(value=node)

    wrapped = seam.wrap(run, distribution="weft-pdf", contract="Extractor", plugin="pdf-text")

    # Act
    outcome = await wrapped()

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value is node
    [(_name, span)] = tracer.spans
    assert span.attributes["weft.nul_bytes_removed"] == 0


async def test_wrap_sanitizes_nul_bytes_in_a_produced_list_of_nodes(
    tracer: _RecordingTracer,
) -> None:
    # Arrange — one dirty node and one clean node in the same batch.
    dirty = Node.synthetic(
        content="dirty\x00page",
        media_type=MediaType.TEXT,
        reason="chunk one of doc-1",
        sources=frozenset({SourceId("doc-1")}),
    )
    clean = Node.synthetic(
        content="clean page",
        media_type=MediaType.TEXT,
        reason="chunk two of doc-1",
        sources=frozenset({SourceId("doc-1")}),
    )

    async def run() -> Outcome[list[Node]]:
        return Produced(value=[dirty, clean])

    wrapped = seam.wrap(run, distribution="weft-pdf", contract="Extractor", plugin="pdf-text")

    # Act
    outcome = await wrapped()

    # Assert
    assert isinstance(outcome, Produced)
    assert isinstance(outcome.value, list)
    [cleaned_dirty, cleaned_clean] = outcome.value
    assert cleaned_dirty.content == "dirty page"
    assert cleaned_clean is clean
    [(_name, span)] = tracer.spans
    assert span.attributes["weft.nul_bytes_removed"] == 1


async def test_wrap_leaves_a_non_node_payload_untouched(tracer: _RecordingTracer) -> None:
    # Arrange — a scalar payload carrying a NUL byte of its own, not wrapped in a `Node`.
    async def run() -> Outcome[str]:
        return Produced(value="not a node\x00at all")

    wrapped = seam.wrap(run, distribution="weft-llm", contract="LLMProvider", plugin="demo")

    # Act
    outcome = await wrapped()

    # Assert
    assert outcome == Produced(value="not a node\x00at all")
    [(_name, span)] = tracer.spans
    assert span.attributes["weft.nul_bytes_removed"] == 0


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
