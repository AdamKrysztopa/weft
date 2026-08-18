"""Task 2.28's exit demonstration: two backends of one contract, composed by the kernel.

`build-ledger.md` 2.28 states the property this file has to make true — *"two extractor
backends for one media type compose as a kernel combinator, and a backend that failed is
distinguishable from a document that is genuinely empty"* — and its exit demonstration
adds the observable: *"with two backends registered and the first one raising, the run
reports which backend answered."*

Both are asserted against the **real** registered plugins, through a real `Runner`,
because the claim is about composition: a stub on either side would test the combinator
alone, which `tests/unit/weft_kernel/test_fallback.py` already does and which is exactly
the kind of green that lets a real chain ship broken. `weft_pdf.register` is called
through the ordinary `PackRegistrar`, so nothing here is a path a third-party pack would
not get.

Nothing mocks a PDF library. The backends are `pdf-text` (pypdf) and `pdf-layout`
(pdfplumber); the documents are the hand-assembled bytes `minimal_pdf.py` builds — no
corpus file, no network, no system binary.

**Which backend answered is read off the span**, not off a return value: `Outcome` has
nowhere to carry it, and adding a field would put chain bookkeeping into every payload
type in the tree. `weft_kernel.seam.wrap` names a chain candidate's span
`f"{stage_id}:{plugin}"`, so a trace says which position was filled and by whom. The
payload's own answer is `PdfPages.backend`, asserted last — the two must agree, or a
citation would credit a parser that refused the document.
"""

from collections.abc import AsyncIterator, Callable, Generator, Sequence
from contextlib import contextmanager
from typing import Protocol

import pytest

from tests.unit.weft_pdf import minimal_pdf
from weft_extract.contract import Extractor, SourceDoc
from weft_kernel import seam
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import Node, Outcome, Produced, SourceId
from weft_kernel.registry import Registry
from weft_kernel.runner import (
    Lifetime,
    RunnablePipeline,
    Runner,
    RunSummary,
    Stage,
    StageSpec,
    UnknownFallbackError,
)
from weft_pdf import Settings, register
from weft_pdf.document import PdfPages

_A_PAPER = "mutual information and minimum redundancy"


class _NodeStage(Stage[Sequence[Node], Sequence[Node]], Protocol):
    """A stand-in contract for the capture stage — this file publishes none of its own."""

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]: ...


class _RecordingSpan:
    def set_attribute(self, key: str, value: object) -> None:
        del key, value


class _RecordingTracer:
    """The shape `tests/unit/weft_kernel/test_seam.py` uses — the default tracer is a no-op."""

    def __init__(self) -> None:
        self.names: list[str] = []

    @contextmanager
    def start_as_current_span(self, name: str, **kwargs: object) -> Generator[_RecordingSpan]:
        del kwargs
        self.names.append(name)
        yield _RecordingSpan()


def _capture_factory(captured: list[Sequence[Node]]) -> Callable[[object], object]:
    """A second stage that records what extraction produced — `run` returns counts, not payloads."""

    class _Capture:
        lifetime = Lifetime.RUN

        def __init__(self, config: object) -> None: ...

        async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
            del ctx
            captured.append(list(payload))
            return Produced(value=payload)

    return _Capture


@pytest.fixture
def tracer(monkeypatch: pytest.MonkeyPatch) -> _RecordingTracer:
    fake = _RecordingTracer()
    monkeypatch.setattr(seam, "_tracer", fake)
    return fake


@pytest.fixture
def captured() -> list[Sequence[Node]]:
    return []


@pytest.fixture
def engine(captured: list[Sequence[Node]]) -> Runner:
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-pdf")
    register(registrar, Settings())
    registrar.commit()
    registry.add(_NodeStage, "capture", _capture_factory(captured), distribution="weft-test")
    return Runner(registry)


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _pipeline(engine: Runner, *, fallback: tuple[str, ...]) -> RunnablePipeline:
    return engine.resolve(
        (
            StageSpec(id="extract", contract=Extractor, name="pdf-text", fallback=fallback),
            StageSpec(id="capture", contract=_NodeStage, name="capture"),
        ),
        tenant_id="tenant-a",
    )


async def _index(engine: Runner, pipeline: RunnablePipeline, content: bytes) -> RunSummary:
    async def batches() -> AsyncIterator[Sequence[SourceDoc]]:
        yield [SourceDoc(source_id=SourceId("paper"), uri="file:///paper.pdf", content=content)]

    return await engine.run(pipeline, batches(), _ctx())


async def test_a_document_the_first_backend_cannot_read_is_answered_by_the_second(
    engine: Runner, tracer: _RecordingTracer, captured: list[Sequence[Node]]
) -> None:
    # Arrange — a PDF truncated before its `%%EOF`: pypdf raises, pdfplumber recovers it.
    pipeline = _pipeline(engine, fallback=("pdf-layout",))

    # Act
    summary = await _index(engine, pipeline, minimal_pdf.truncated_tail(_A_PAPER))

    # Assert — the run produced; the span and the payload agree on which backend answered.
    assert summary == RunSummary(produced=1)
    assert tracer.names[:2] == ["extract:pdf-text", "extract:pdf-layout"]
    [node] = captured[0]
    assert node.ext["weft-pdf"] == PdfPages(backend="pdf-layout", starts=(0,))


async def test_the_same_document_without_the_chain_fails_naming_the_backend(
    engine: Runner,
) -> None:
    # Arrange — the control. Without it, the test above would pass just as well if
    # `pdf-text` had quietly read the document all along and the chain had done nothing.
    pipeline = _pipeline(engine, fallback=())

    # Act
    summary = await _index(engine, pipeline, minimal_pdf.truncated_tail(_A_PAPER))

    # Assert
    assert summary.produced == 0
    assert summary.failed == 1
    assert "pdf-text" in summary.failed_reasons[0]


async def test_a_genuinely_empty_document_stops_the_chain_instead_of_walking_it(
    engine: Runner, tracer: _RecordingTracer
) -> None:
    # Arrange — a page whose text layer draws no glyphs and carries no image. `pdf-text`
    # *looked*, and there is nothing there; a second backend cannot improve on that claim.
    pipeline = _pipeline(engine, fallback=("pdf-layout",))

    # Act
    summary = await _index(engine, pipeline, minimal_pdf.text_pages(""))

    # Assert — the reference's defect closed in both directions: an empty document is a
    # different outcome from a failed one, and it is not reported as a chain-wide failure.
    assert summary.nothing_to_produce == 1
    assert summary.failed == 0
    assert "no text on any of them" in summary.nothing_to_produce_reasons[0]
    assert tracer.names == ["extract:pdf-text"], "an empty document reached a second backend"


async def test_a_page_no_backend_could_see_walks_the_whole_chain_and_names_every_refusal(
    engine: Runner, tracer: _RecordingTracer
) -> None:
    # Arrange — the mirror case: no text and an image present, which neither backend can
    # tell apart from a blank page. Both refuse, so the chain exhausts.
    pipeline = _pipeline(engine, fallback=("pdf-layout",))

    # Act
    summary = await _index(engine, pipeline, minimal_pdf.image_without_text())

    # Assert — one `Failed` naming every candidate and what each said, in order, so an
    # operator reading it knows an OCR pack is what is missing rather than one parser.
    assert summary.failed == 1
    reason = summary.failed_reasons[0]
    assert "pdf-text" in reason
    assert "pdf-layout" in reason
    assert reason.index("pdf-text") < reason.index("pdf-layout")
    assert tracer.names == ["extract:pdf-text", "extract:pdf-layout"]


def test_a_fallback_naming_a_pack_nobody_installed_is_refused_before_any_document_is_read(
    engine: Runner,
) -> None:
    # Arrange / Act / Assert — `ocr` is the name every document in this tree uses as the
    # example of a fallback that is not installed yet. It stays authorable (`resolve()`
    # carries it through unchecked); what is refused is making the pipeline runnable.

    with pytest.raises(UnknownFallbackError) as caught:
        _pipeline(engine, fallback=("pdf-layout", "ocr"))

    message = str(caught.value)
    assert "'ocr'" in message
    assert "'pdf-layout'" in message
    assert "'pdf-text'" in message
