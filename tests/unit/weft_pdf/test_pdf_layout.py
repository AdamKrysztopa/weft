"""Unit tests for `weft_pdf.pdf_layout`.

Mirrors `packages/weft-pdf/src/weft_pdf/pdf_layout.py`, and deliberately the same
shape as `test_pdf_text.py`: the point of this pack is that two backends are
interchangeable by a name in a pipeline document, and a pair of test files that
check different things would be the first place that claim quietly stopped being
true. The two boundary cases are asserted against `pdfplumber` separately rather
than assumed to follow from `pypdf` agreeing — that they agree is exactly what
task 2.28's chain depends on and is therefore worth a test rather than a belief.
"""

import threading
from collections.abc import Sequence

from tests.unit.weft_pdf import minimal_pdf
from weft_extract.contract import Extractor, SourceDoc
from weft_kernel.context import Context
from weft_kernel.payload import Failed, Node, NothingToProduce, Outcome, Produced, SourceId
from weft_pdf.document import PageText, PdfPages
from weft_pdf.pdf_layout import PdfLayoutExtractor, PdfLayoutExtractorConfig


class _ThreadRecordingExtractor(PdfLayoutExtractor):
    """`PdfLayoutExtractor`, recording which thread each page reading actually ran on."""

    def __init__(self) -> None:
        super().__init__()
        self.threads: list[int] = []

    def _read_pages(self, content: bytes) -> Sequence[PageText]:
        self.threads.append(threading.get_ident())
        return super()._read_pages(content)


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _doc(content: bytes, uri: str = "file:///paper.pdf") -> SourceDoc:
    return SourceDoc(source_id=SourceId("paper"), uri=uri, content=content)


async def test_two_text_pages_become_one_node_whose_offsets_find_each_page() -> None:
    # Arrange
    extractor = PdfLayoutExtractor()
    doc = _doc(minimal_pdf.text_pages("mutual information", "feature selection"))

    # Act
    outcome: Outcome[Sequence[Node]] = await extractor.run([doc], _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    [node] = outcome.value
    pages = node.ext_as(PdfPages)
    assert "mutual information" in node.content
    assert "feature selection" in node.content
    assert pages is not None
    assert pages.backend == "pdf-layout"
    assert pages.page_at(node.content.index("feature selection")) == 2


async def test_the_word_tolerance_reaches_pdfplumber_rather_than_only_being_declared() -> None:
    # Arrange — `x_tolerance` is the gap below which two characters are one word, and it
    # is the knob that decides this backend's known failure: at `pdfplumber`'s own
    # default it fuses words together. A tolerance small enough splits them apart again.
    doc = _doc(minimal_pdf.text_columns("relevance", "redundancy"))
    at_default = PdfLayoutExtractor()
    too_tolerant = PdfLayoutExtractor(PdfLayoutExtractorConfig(x_tolerance=50.0))

    # Act
    separate = await at_default.run([doc], _ctx())
    fused = await too_tolerant.run([doc], _ctx())

    # Assert — the second is this backend's documented failure reproduced in
    # miniature: two words a hundred points apart returned as one.
    assert isinstance(separate, Produced)
    assert isinstance(fused, Produced)
    assert separate.value[0].content == "relevance redundancy"
    assert fused.value[0].content == "relevanceredundancy"


async def test_a_text_layer_that_draws_no_glyphs_is_nothing_to_produce() -> None:
    # Arrange
    extractor = PdfLayoutExtractor()
    doc = _doc(minimal_pdf.text_pages(""))

    # Act
    outcome = await extractor.run([doc], _ctx())

    # Assert
    assert isinstance(outcome, NothingToProduce)
    assert "1 page(s)" in outcome.reason


async def test_a_page_with_an_image_and_no_text_is_failed_not_empty() -> None:
    # Arrange
    extractor = PdfLayoutExtractor()
    doc = _doc(minimal_pdf.image_without_text())

    # Act
    outcome = await extractor.run([doc], _ctx())

    # Assert
    assert isinstance(outcome, Failed)
    assert "page 1" in outcome.reason
    assert "1 image(s)" in outcome.reason


async def test_the_layout_mode_reaches_pdfplumber_rather_than_only_being_declared() -> None:
    # Arrange — repair for a reviewer finding: `layout` is `pdfplumber`'s geometry-
    # preserving mode and the direct analogue of the `mode` knob `pdf-text` ships, so
    # without it the same operator choice was reachable on one backend and not the other.
    doc = _doc(minimal_pdf.text_columns("relevance", "redundancy"))
    flowing = PdfLayoutExtractor()
    positioned = PdfLayoutExtractor(PdfLayoutExtractorConfig(layout=True))

    # Act
    packed = await flowing.run([doc], _ctx())
    spaced = await positioned.run([doc], _ctx())

    # Assert — layout mode pads the page out to where the characters actually sat.
    assert isinstance(packed, Produced)
    assert isinstance(spaced, Produced)
    assert packed.value[0].content == "relevance redundancy"
    assert "relevance     redundancy" in spaced.value[0].content


async def test_an_encrypted_document_is_readable_only_with_the_password_configured() -> None:
    # Arrange
    doc = _doc(minimal_pdf.encrypted(minimal_pdf.text_pages("relevance"), "opensesame"))
    without = PdfLayoutExtractor()
    with_password = PdfLayoutExtractor(PdfLayoutExtractorConfig(password="opensesame"))  # noqa: S106 - the fixture's own password, set one line above

    # Act
    refused = await without.run([doc], _ctx())
    opened = await with_password.run([doc], _ctx())

    # Assert
    assert isinstance(refused, Failed)
    assert isinstance(opened, Produced)
    assert "relevance" in opened.value[0].content


async def test_a_reading_that_recovers_no_pages_is_failed_rather_than_empty() -> None:
    # Arrange — the measured case: `pdfplumber` answers zero pages for a truncated
    # download rather than raising, and zero pages used to reach the empty-content test.
    extractor = PdfLayoutExtractor()
    doc = _doc(minimal_pdf.no_pages())

    # Act
    outcome = await extractor.run([doc], _ctx())

    # Assert
    assert isinstance(outcome, Failed)
    assert "no pages" in outcome.reason


async def test_parsing_runs_off_the_event_loop_thread() -> None:
    # Arrange — measured at 1.08 s of held loop on the first corpus paper before this.
    extractor = _ThreadRecordingExtractor()
    doc = _doc(minimal_pdf.text_pages("relevance"))

    # Act
    await extractor.run([doc], _ctx())

    # Assert
    assert extractor.threads
    assert threading.get_ident() not in extractor.threads


async def test_bytes_pdfplumber_refuses_become_failed_naming_the_document() -> None:
    # Arrange
    extractor = PdfLayoutExtractor()
    doc = _doc(minimal_pdf.not_a_pdf(), uri="file:///broken.pdf")

    # Act
    outcome = await extractor.run([doc], _ctx())

    # Assert
    assert isinstance(outcome, Failed)
    assert "file:///broken.pdf" in outcome.reason
    assert "pdf-layout" in outcome.reason


def test_it_claims_pdf_and_satisfies_the_extractor_contract_structurally() -> None:
    # Act / Assert
    assert PdfLayoutExtractor.extensions == (".pdf",)
    assert PdfLayoutExtractor.config_model is PdfLayoutExtractorConfig
    assert isinstance(PdfLayoutExtractor(), Extractor)
