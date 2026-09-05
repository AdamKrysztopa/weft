"""Task 4.5 — proves a stage's duration and attribution reach a *real* trace, with no pack ever
touching a span.

`test_seam.py`, in this same directory, deliberately tests only that `wrap` calls the tracer API
correctly, using a hand-rolled double rather than the OpenTelemetry SDK — its own docstring states
why: "without pulling in the SDK to test a promise the SDK, not this module, keeps." This file
exists to prove that other promise, end to end: when something outside the kernel configures a
real `TracerProvider` with an exporter, `weft_kernel.seam.wrap`'s calls into `opentelemetry-api`
are — unmodified — enough to produce a span carrying duration and stage attribution, and, on
failure, which stage and why.

**Why a test fixture, not a pack, configures the SDK here.** The kernel ships only
`opentelemetry-api` (fitness function 1's `KERNEL_DEPENDENCIES`); `opentelemetry-sdk` is a
test-only dependency of this repository — root `pyproject.toml`'s dev group — never of any
shipped distribution. Phase 4 builds no exporter pack: task 4.6's `weft trace` reads the run
record task 4.4 persists, not OTel spans (`.phase4-design.md` §3, Q2), so there is no pack home
for a real, SDK-configured exporter yet. A test fixture standing in for whatever such a pack
would one day do — `set_tracer_provider` — is therefore where this demonstration belongs; see
`docs/build-ledger.md` 4.5 for the ledger entry this file backs.

Every `run`/`flush` written below is what a pack actually writes: no `opentelemetry` import, no
span, no attribute. Everything asserted about the exported spans is what `wrap`/`wrap_flush`
produced on the plugin's behalf.
"""

import asyncio

import pytest
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from weft_kernel import seam
from weft_kernel.errors import WeftError
from weft_kernel.payload import Outcome, Produced


@pytest.fixture(scope="module")
def exporter() -> InMemorySpanExporter:
    """A real, in-process SDK exporter, configured once for this module.

    `opentelemetry.trace.set_tracer_provider` can only be set once per process — a second call
    logs a warning and is a no-op — so every test in this module shares one `TracerProvider` and
    isolates itself by clearing the exporter, not by installing a fresh provider.
    """
    memory_exporter = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource.create({"service.name": "weft-test"}))
    provider.add_span_processor(SimpleSpanProcessor(memory_exporter))
    trace.set_tracer_provider(provider)
    return memory_exporter


@pytest.fixture(autouse=True)
def isolated(exporter: InMemorySpanExporter) -> None:
    exporter.clear()


async def test_a_successful_stage_produces_a_span_with_duration_and_attribution(
    exporter: InMemorySpanExporter,
) -> None:
    # Arrange — a plugin's `run`, written exactly as a pack would: no `opentelemetry` import.
    async def run(payload: str) -> Outcome[str]:
        return Produced(value=payload.upper())

    wrapped = seam.wrap(
        run, distribution="weft-chunk", contract="Chunker", plugin="fixed-size", stage="chunk-1"
    )

    # Act
    outcome = await wrapped("hello")

    # Assert
    assert outcome == Produced(value="HELLO")
    [span] = exporter.get_finished_spans()
    assert span.name == "chunk-1"
    assert span.end_time is not None
    assert span.start_time is not None
    assert span.end_time > span.start_time
    assert span.attributes is not None
    assert span.attributes["weft.pack"] == "weft-chunk"
    assert span.attributes["weft.contract"] == "Chunker"
    assert span.attributes["weft.plugin"] == "fixed-size"
    assert span.status.status_code == StatusCode.UNSET


async def test_a_failed_stage_names_which_stage_and_why(exporter: InMemorySpanExporter) -> None:
    # Arrange — the plugin raises a plain exception; it never touches a span or names itself.
    async def run(payload: str) -> Outcome[str]:
        raise ValueError("could not parse page 3")

    wrapped = seam.wrap(
        run, distribution="weft-pdf", contract="Extractor", plugin="pdf-text", stage="extract-1"
    )

    # Act / Assert
    with pytest.raises(WeftError):
        await wrapped("doc")

    [span] = exporter.get_finished_spans()
    assert span.name == "extract-1"  # which stage
    assert span.status.status_code == StatusCode.ERROR
    assert span.status.description is not None
    assert "could not parse page 3" in span.status.description  # why
    [event] = span.events
    assert event.name == "exception"
    assert event.attributes is not None
    assert "could not parse page 3" in str(event.attributes["exception.message"])
    assert span.attributes is not None
    assert span.attributes["weft.pack"] == "weft-pdf"
    assert span.attributes["weft.contract"] == "Extractor"
    assert span.attributes["weft.plugin"] == "pdf-text"


async def test_cancellation_ends_the_span_without_being_recorded_as_a_failure(
    exporter: InMemorySpanExporter,
) -> None:
    # Arrange — `CancelledError` is a `BaseException`. `opentelemetry.trace.use_span` (the
    # function underneath both the no-op API tracer and a real SDK tracer's own
    # `start_as_current_span`) only records and sets ERROR status for `Exception`, never
    # `BaseException`, so a real span still ends but carries neither — the property CLAUDE.md
    # names ("CancelledError propagates and is never swallowed") holding against a real
    # exporter, not only against `test_seam.py`'s hand-rolled double.
    async def run(payload: str) -> Outcome[str]:
        raise asyncio.CancelledError

    wrapped = seam.wrap(
        run, distribution="weft-chunk", contract="Chunker", plugin="fixed-size", stage="chunk-2"
    )

    # Act / Assert
    with pytest.raises(asyncio.CancelledError):
        await wrapped("doc")

    [span] = exporter.get_finished_spans()
    assert span.status.status_code == StatusCode.UNSET
    assert span.events == ()


async def test_wrap_flush_produces_a_span_of_its_own(exporter: InMemorySpanExporter) -> None:
    # Arrange — `flush()` is the runner's, never a stage's (`runner.py`), and gets the same
    # span treatment via `wrap_flush`.
    async def flush() -> None:
        return None

    wrapped = seam.wrap_flush(
        flush, distribution="weft-store", contract="NodeStore", plugin="pgvector", stage="store-1"
    )

    # Act
    await wrapped()

    # Assert
    [span] = exporter.get_finished_spans()
    assert span.name == "store-1:flush"
    assert span.end_time is not None
    assert span.start_time is not None
    assert span.end_time > span.start_time


async def test_two_stages_run_one_after_another_land_in_one_trace(
    exporter: InMemorySpanExporter,
) -> None:
    # Arrange — `packages/weft-rag/src/weft_cli/cli.py::run_command` wraps a whole `Command`
    # invocation through `seam.wrap` (`stage=f"command:{command_name}"`) and only then calls
    # into `Runner`, which wraps each stage the identical way; `Runner._run_one_batch` walks
    # its stages with a plain sequential `await`, never `asyncio.create_task`. Reproduced here
    # with two bare `wrap()` calls nested the same way, to show it is `opentelemetry-api`'s own
    # `contextvars`-based propagation doing this, not anything `weft_cli` adds: a pack's stage
    # spans nest under whatever span was active when the runner reached them, with no pack
    # aware that a parent span exists at all.
    async def extract(payload: str) -> Outcome[str]:
        return Produced(value=payload)

    async def chunk(payload: str) -> Outcome[str]:
        return Produced(value=payload)

    wrapped_extract = seam.wrap(
        extract, distribution="weft-pdf", contract="Extractor", plugin="pdf-text", stage="extract"
    )
    wrapped_chunk = seam.wrap(
        chunk, distribution="weft-chunk", contract="Chunker", plugin="fixed-size", stage="chunk"
    )

    async def command_run(payload: str) -> Outcome[str]:
        extracted = await wrapped_extract(payload)
        assert isinstance(extracted, Produced)
        return await wrapped_chunk(extracted.value)

    wrapped_command = seam.wrap(
        command_run,
        distribution="weft-cli",
        contract="Command",
        plugin="index",
        stage="command:index",
        guard_blocking_calls=False,
    )

    # Act
    await wrapped_command("doc")

    # Assert
    spans = {span.name: span for span in exporter.get_finished_spans()}
    assert set(spans) == {"command:index", "extract", "chunk"}
    command_context = spans["command:index"].context
    extract_parent = spans["extract"].parent
    chunk_parent = spans["chunk"].parent
    assert command_context is not None
    assert extract_parent is not None
    assert chunk_parent is not None
    trace_ids = {command_context.trace_id, extract_parent.trace_id, chunk_parent.trace_id}
    assert len(trace_ids) == 1, "all three spans must share one trace, not three isolated ones"
    assert extract_parent.span_id == command_context.span_id
    assert chunk_parent.span_id == command_context.span_id
