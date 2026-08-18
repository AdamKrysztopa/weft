"""Unit tests for `weft_pdf.pdf_text`.

Mirrors `packages/weft-pdf/src/weft_pdf/pdf_text.py`. `weft_pdf.document`'s own
tests already check every rule the two backends share, so what is left for this
one to get wrong is the driving of `pypdf`: that pages come back in order with
their text, that an image on a page is counted at all, that the configuration
model reaches the library rather than sitting there decoratively, and that a
refusal from `pypdf` becomes `Failed` instead of escaping as a stack trace.

The two boundary cases carry the weight, because task 2.28's fallback chain is
built on them being different outcomes: a text layer that draws no glyphs is
`NothingToProduce`, and a page with an image and no text is `Failed`. Both are
constructed here rather than found — see `minimal_pdf`.
"""

import threading
from collections.abc import Sequence

from tests.unit.weft_pdf import minimal_pdf
from weft_extract.contract import Extractor, SourceDoc
from weft_kernel.context import Context
from weft_kernel.payload import Failed, Node, NothingToProduce, Outcome, Produced, SourceId
from weft_pdf.document import PageText, PdfPages
from weft_pdf.pdf_text import (
    ExtractionMode,
    PageOrientation,
    PdfTextExtractor,
    PdfTextExtractorConfig,
)


class _ThreadRecordingExtractor(PdfTextExtractor):
    """`PdfTextExtractor`, recording which thread each page reading actually ran on.

    A subclass rather than a patched attribute so nothing here reaches into a
    private member from outside the class that owns it.
    """

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
    extractor = PdfTextExtractor()
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
    assert pages.backend == "pdf-text"
    assert pages.page_at(node.content.index("feature selection")) == 2


async def test_the_extraction_mode_reaches_pypdf_rather_than_only_being_declared() -> None:
    # Arrange — `layout` reconstructs the page's geometry, so the same page comes back
    # padded to its column positions. A knob a pipeline can set but the library never
    # sees is the defect `02` §1's typed-configuration rule exists to prevent.
    doc = _doc(minimal_pdf.text_columns("relevance", "redundancy"))
    plain = PdfTextExtractor(PdfTextExtractorConfig(mode=ExtractionMode.PLAIN))
    layout = PdfTextExtractor(PdfTextExtractorConfig(mode=ExtractionMode.LAYOUT))

    # Act
    from_plain = await plain.run([doc], _ctx())
    from_layout = await layout.run([doc], _ctx())

    # Assert
    assert isinstance(from_plain, Produced)
    assert isinstance(from_layout, Produced)
    assert from_plain.value[0].content == "relevance redundancy"
    assert "relevance    " in from_layout.value[0].content
    assert "redundancy" in from_layout.value[0].content


async def test_a_text_layer_that_draws_no_glyphs_is_nothing_to_produce() -> None:
    # Arrange — the page has a complete text object; it just writes nothing.
    extractor = PdfTextExtractor()
    doc = _doc(minimal_pdf.text_pages(""))

    # Act
    outcome = await extractor.run([doc], _ctx())

    # Assert — this backend looked, so the fallback chain must stop here.
    assert isinstance(outcome, NothingToProduce)
    assert "1 page(s)" in outcome.reason


async def test_a_page_with_an_image_and_no_text_is_failed_not_empty() -> None:
    # Arrange
    extractor = PdfTextExtractor()
    doc = _doc(minimal_pdf.image_without_text())

    # Act
    outcome = await extractor.run([doc], _ctx())

    # Assert — this backend could not see it, so the chain must continue.
    assert isinstance(outcome, Failed)
    assert "page 1" in outcome.reason
    assert "1 image(s)" in outcome.reason


async def test_an_image_nested_in_a_form_xobject_is_still_seen() -> None:
    # Arrange — repair for a reviewer finding: the resource scan used to read only the
    # page's own `/XObject` entries, so a scan drawn through a form counted zero and the
    # document was reported as genuinely empty, terminating task 2.28's chain.
    extractor = PdfTextExtractor()
    doc = _doc(minimal_pdf.image_inside_a_form())

    # Act
    outcome = await extractor.run([doc], _ctx())

    # Assert
    assert isinstance(outcome, Failed)
    assert "1 image(s)" in outcome.reason


async def test_an_inline_image_is_seen_even_though_no_dictionary_declares_it() -> None:
    # Arrange — the second route past a resource walk: `BI … ID … EI` is declared
    # nowhere, so only the content stream can answer.
    extractor = PdfTextExtractor()
    doc = _doc(minimal_pdf.inline_image_without_text())

    # Act
    outcome = await extractor.run([doc], _ctx())

    # Assert
    assert isinstance(outcome, Failed)
    assert "1 image(s)" in outcome.reason


async def test_a_reading_that_recovers_no_pages_is_failed_rather_than_empty() -> None:
    # Arrange
    extractor = PdfTextExtractor()
    doc = _doc(minimal_pdf.no_pages())

    # Act
    outcome = await extractor.run([doc], _ctx())

    # Assert
    assert isinstance(outcome, Failed)
    assert "no pages" in outcome.reason


async def test_the_orientations_knob_reaches_pypdf() -> None:
    # Arrange — `orientations` decides which rotations are extracted at all. Asking only
    # for sideways text on an upright page returns nothing, which is exactly the point:
    # a corpus of rotated tables is unreadable without it.
    doc = _doc(minimal_pdf.text_pages("relevance"))
    sideways = PdfTextExtractor(
        PdfTextExtractorConfig(orientations=(PageOrientation.ROTATED_LEFT,))
    )

    # Act
    outcome = await sideways.run([doc], _ctx())

    # Assert
    assert isinstance(outcome, NothingToProduce)


async def test_a_layout_mode_knob_reaches_pypdf() -> None:
    # Arrange — `layout_mode_scale_weight` multiplies string length when working out
    # where a glyph sits, so a small enough weight collapses the gap the page had.
    doc = _doc(minimal_pdf.text_columns("relevance", "redundancy"))
    at_default = PdfTextExtractor(PdfTextExtractorConfig(mode=ExtractionMode.LAYOUT))
    collapsed = PdfTextExtractor(
        PdfTextExtractorConfig(mode=ExtractionMode.LAYOUT, layout_mode_scale_weight=0.1)
    )

    # Act
    spaced = await at_default.run([doc], _ctx())
    squashed = await collapsed.run([doc], _ctx())

    # Assert
    assert isinstance(spaced, Produced)
    assert isinstance(squashed, Produced)
    assert "relevance    " in spaced.value[0].content
    assert "relevanceredundancy" in squashed.value[0].content


async def test_an_encrypted_document_is_readable_only_with_the_password_configured() -> None:
    # Arrange — without this knob an encrypted corpus is permanently `Failed`, with no
    # configuration that could have made it succeed.
    doc = _doc(minimal_pdf.encrypted(minimal_pdf.text_pages("relevance"), "opensesame"))
    without = PdfTextExtractor()
    with_password = PdfTextExtractor(PdfTextExtractorConfig(password="opensesame"))  # noqa: S106 - the fixture's own password, set one line above

    # Act
    refused = await without.run([doc], _ctx())
    opened = await with_password.run([doc], _ctx())

    # Assert
    assert isinstance(refused, Failed)
    assert isinstance(opened, Produced)
    assert "relevance" in opened.value[0].content


async def test_parsing_runs_off_the_event_loop_thread() -> None:
    # Arrange — `01` → *Colour*: "a CPU-bound stage is still `async def` and offloads its
    # own blocking work." Fitness function 7(b) is categorical and cannot see pure
    # computation holding the loop, so this is the only place the rule is checked.
    extractor = _ThreadRecordingExtractor()
    doc = _doc(minimal_pdf.text_pages("relevance"))

    # Act
    await extractor.run([doc], _ctx())

    # Assert
    assert extractor.threads
    assert threading.get_ident() not in extractor.threads


async def test_bytes_pypdf_refuses_become_failed_naming_the_document() -> None:
    # Arrange
    extractor = PdfTextExtractor()
    doc = _doc(minimal_pdf.not_a_pdf(), uri="file:///broken.pdf")

    # Act
    outcome = await extractor.run([doc], _ctx())

    # Assert
    assert isinstance(outcome, Failed)
    assert "file:///broken.pdf" in outcome.reason
    assert "pdf-text" in outcome.reason


def test_it_claims_pdf_and_satisfies_the_extractor_contract_structurally() -> None:
    # Act / Assert — `.pdf` is claimed as capability metadata, and the contract is
    # satisfied without this class ever importing it, the path a third party takes.
    assert PdfTextExtractor.extensions == (".pdf",)
    assert PdfTextExtractor.config_model is PdfTextExtractorConfig
    assert isinstance(PdfTextExtractor(), Extractor)
