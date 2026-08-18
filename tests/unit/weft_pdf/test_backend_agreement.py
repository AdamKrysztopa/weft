"""The two backends answer the same *kind* of outcome for the same bytes.

Repair for a reviewer finding, and the missing half of `test_pdf_text.py` and
`test_pdf_layout.py`: each of those checks one backend against one fixture, and
both were green while the two backends disagreed about a page whose image sits
inside a Form XObject — `pdf-text` called the document genuinely empty,
`pdf-layout` called it unreadable. Task 2.28's `fallback:` chain stops on
`NothingToProduce` and continues on `Failed`, so a disagreement is not a
cosmetic difference between two parsers: it decides whether a scanned paper
reaches OCR or is dropped from the corpus with a success-shaped outcome.

The assertion is deliberately on the outcome *type*, never on the text: the two
libraries recover different characters from the same page — that is why both
ship — and requiring identical content would be testing that they are the same
parser, which is the opposite of the claim.
"""

from collections.abc import Sequence

import pytest

from tests.unit.weft_pdf import minimal_pdf
from weft_extract.contract import SourceDoc
from weft_kernel.context import Context
from weft_kernel.payload import Failed, Node, NothingToProduce, Outcome, Produced, SourceId
from weft_pdf.pdf_layout import PdfLayoutExtractor
from weft_pdf.pdf_text import PdfTextExtractor

#: Every fixture on which the chain's behaviour differs, and the outcome both backends
#: must reach. `Produced` is here too: a chain whose backends disagree about *success*
#: would be just as broken, and it costs one row to say so.
_AGREED: tuple[tuple[str, type[Outcome[Sequence[Node]]]], ...] = (
    ("text_pages", Produced),
    ("empty_text_layer", NothingToProduce),
    ("image_without_text", Failed),
    ("image_inside_a_form", Failed),
    ("inline_image_without_text", Failed),
    ("no_pages", Failed),
    ("not_a_pdf", Failed),
)


def _bytes_for(fixture: str) -> bytes:
    if fixture == "text_pages":
        return minimal_pdf.text_pages("mutual information", "feature selection")
    if fixture == "empty_text_layer":
        return minimal_pdf.text_pages("")
    return getattr(minimal_pdf, fixture)()


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


@pytest.mark.parametrize(("fixture", "expected"), _AGREED)
async def test_both_backends_reach_the_same_outcome(
    fixture: str, expected: type[Outcome[Sequence[Node]]]
) -> None:
    # Arrange
    doc = SourceDoc(
        source_id=SourceId("paper"), uri="file:///paper.pdf", content=_bytes_for(fixture)
    )

    # Act
    from_text = await PdfTextExtractor().run([doc], _ctx())
    from_layout = await PdfLayoutExtractor().run([doc], _ctx())

    # Assert
    assert isinstance(from_text, expected), f"pdf-text disagreed on {fixture}: {from_text}"
    assert isinstance(from_layout, expected), f"pdf-layout disagreed on {fixture}: {from_layout}"
