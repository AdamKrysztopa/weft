"""Unit tests for `weft_pdf.document`.

Mirrors `packages/weft-pdf/src/weft_pdf/document.py`. Every rule both backends
share lives in that module precisely so it can be checked once, against a
`read_pages` that is a plain function rather than a PDF library: the rules under
test here are about outcomes and offsets, and running a real parser to reach
them would test `pypdf` instead. The two backends' own tests then check that
each library is driven correctly, which is the only thing left for them to get
wrong.

Covers the happy path (pages joined into one root node carrying its page
offsets), the two edge cases the fallback chain rests on (an empty document is
`NothingToProduce`, a page this pack could not see is `Failed`), and the error
case of a library refusing the bytes outright.
"""

from collections.abc import Sequence

import pytest

from weft_extract.contract import SourceDoc
from weft_kernel.payload import Failed, Node, NothingToProduce, Outcome, Produced, SourceId
from weft_pdf.document import PageReader, PageText, PdfPages, extract_documents


class _RefusedError(Exception):
    """Stands in for a parsing library's own "these bytes are not a PDF" exception."""


def _doc(uri: str = "file:///paper.pdf", source: str = "paper") -> SourceDoc:
    return SourceDoc(source_id=SourceId(source), uri=uri, content=b"%PDF-1.4 pretend")


def _reading(*pages: PageText) -> PageReader:
    def read(content: bytes) -> Sequence[PageText]:
        del content
        return pages

    return read


def _extract(
    read: PageReader, *, payload: Sequence[SourceDoc] | None = None
) -> Outcome[Sequence[Node]]:
    return extract_documents(
        [_doc()] if payload is None else payload,
        backend="stand-in",
        read_pages=read,
        unreadable=(_RefusedError,),
        separator="\n\n",
    )


def test_pages_become_one_node_carrying_the_offset_each_page_starts_at() -> None:
    # Arrange
    read = _reading(
        PageText(number=1, text="first page", images=0),
        PageText(number=2, text="second page", images=1),
    )

    # Act
    outcome = _extract(read)

    # Assert
    assert isinstance(outcome, Produced)
    [node] = outcome.value
    pages = node.ext_as(PdfPages)
    assert node.content == "first page\n\nsecond page"
    assert node.lineage.sources == frozenset({SourceId("paper")})
    assert pages is not None
    assert pages.backend == "stand-in"
    assert pages.starts == (0, 12)


def test_page_at_answers_the_page_a_content_offset_falls_on() -> None:
    # Arrange
    pages = PdfPages(backend="stand-in", starts=(0, 12, 40))

    # Act / Assert — the boundary in both directions, and past the end
    assert pages.page_at(0) == 1
    assert pages.page_at(11) == 1
    assert pages.page_at(12) == 2
    assert pages.page_at(9_000) == 3


def test_page_at_refuses_a_negative_offset() -> None:
    # Arrange
    pages = PdfPages(backend="stand-in", starts=(0,))

    # Act / Assert
    with pytest.raises(ValueError, match="cannot be negative"):
        pages.page_at(-1)


def test_an_empty_batch_is_nothing_to_produce() -> None:
    # Act
    outcome = _extract(_reading(), payload=[])

    # Assert
    assert outcome == NothingToProduce(reason="no source documents to extract")


def test_a_document_read_with_no_text_and_no_images_is_nothing_to_produce() -> None:
    # Arrange — the backend looked at both pages; there is genuinely nothing there,
    # so a second backend would find nothing either and the chain must stop.
    read = _reading(PageText(number=1, text="", images=0), PageText(number=2, text="   ", images=0))

    # Act
    outcome = _extract(read)

    # Assert
    assert isinstance(outcome, NothingToProduce)
    assert "2 page(s)" in outcome.reason
    assert "file:///paper.pdf" in outcome.reason


def test_a_page_with_no_text_but_an_image_fails_so_another_backend_can_try() -> None:
    # Arrange — this backend cannot tell a scan from a blank page, and the rule is
    # that it must say so rather than report an empty document it did not verify.
    read = _reading(
        PageText(number=1, text="a caption", images=0),
        PageText(number=2, text="", images=3),
    )

    # Act
    outcome = _extract(read)

    # Assert
    assert isinstance(outcome, Failed)
    assert "page 2" in outcome.reason
    assert "3 image(s)" in outcome.reason
    assert "stand-in" in outcome.reason


def test_a_reading_that_recovered_no_pages_at_all_is_failed_not_empty() -> None:
    # Arrange — repair for a reviewer finding, measured: `pdfplumber` answers zero pages
    # for a truncated PDF rather than raising, so "no pages" reached the empty-content
    # check and was reported as a document that is genuinely empty. Zero pages is the one
    # reading from which a backend can conclude nothing at all.
    read = _reading()

    # Act
    outcome = _extract(read)

    # Assert
    assert isinstance(outcome, Failed)
    assert "no pages" in outcome.reason
    assert "file:///paper.pdf" in outcome.reason
    assert "stand-in" in outcome.reason


def test_an_empty_document_beside_a_full_one_keeps_the_full_one() -> None:
    # Arrange — repair for a reviewer finding: an empty document produces nothing
    # *because there is nothing in it*, which is not a reason to discard what the
    # documents beside it produced. Only a `Failed` is all-or-nothing.
    full = SourceDoc(source_id=SourceId("a"), uri="file:///a.pdf", content=b"a")
    empty = SourceDoc(source_id=SourceId("b"), uri="file:///b.pdf", content=b"b")

    def read(content: bytes) -> Sequence[PageText]:
        text = "real text" if content == b"a" else ""
        return (PageText(number=1, text=text, images=0),)

    # Act
    outcome = _extract(read, payload=[full, empty])

    # Assert
    assert isinstance(outcome, Produced)
    [node] = outcome.value
    assert node.content == "real text"


def test_a_batch_in_which_no_document_had_any_text_names_every_one_of_them() -> None:
    # Arrange
    first = SourceDoc(source_id=SourceId("a"), uri="file:///a.pdf", content=b"a")
    second = SourceDoc(source_id=SourceId("b"), uri="file:///b.pdf", content=b"b")

    # Act
    outcome = _extract(_reading(PageText(number=1, text="", images=0)), payload=[first, second])

    # Assert — the reason names both, not only whichever was reached first.
    assert isinstance(outcome, NothingToProduce)
    assert "file:///a.pdf" in outcome.reason
    assert "file:///b.pdf" in outcome.reason


def test_one_unreadable_document_fails_the_whole_batch_rather_than_shrinking_it() -> None:
    # Arrange — a batch is extracted whole or not at all: `Produced` has no room to
    # report what was dropped, so a partial answer would be indistinguishable from a
    # complete one downstream.
    good = SourceDoc(source_id=SourceId("a"), uri="file:///a.pdf", content=b"%PDF-1.4")
    bad = SourceDoc(source_id=SourceId("b"), uri="file:///b.pdf", content=b"not a pdf")
    calls: list[bytes] = []

    def read(content: bytes) -> Sequence[PageText]:
        calls.append(content)
        if content == b"not a pdf":
            raise _RefusedError("no cross-reference table")
        return (PageText(number=1, text="fine", images=0),)

    # Act
    outcome = _extract(read, payload=[good, bad])

    # Assert
    assert isinstance(outcome, Failed)
    assert "file:///b.pdf" in outcome.reason
    assert "no cross-reference table" in outcome.reason
    assert len(calls) == 2
