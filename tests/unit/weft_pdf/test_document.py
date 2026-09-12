"""Unit tests for `weft_pdf.document`.

Mirrors `packages/weft-pdf/src/weft_pdf/document.py`. Every rule both backends
share lives in that module precisely so it can be checked once, against a
`read_pages` that is a plain function rather than a PDF library: the rules under
test here are about outcomes and offsets, and running a real parser to reach
them would test `pypdf` instead. The two backends' own tests then check that
each library is driven correctly, which is the only thing left for them to get
wrong.

Covers the happy path (**one root node per page**, each carrying the page it is —
G17, settled 2026-09-12), the two edge cases the fallback chain rests on (an empty
document is `NothingToProduce`, a page this pack could not see is `Failed`), and the
error case of a library refusing the bytes outright.

**The happy-path test varies the page number and the content together**, because a
fixture whose pages are indistinguishable cannot tell *one node per page* from *one
node per document*, and that is the entire dimension under test.
"""

from collections.abc import Sequence
from typing import Final

import pytest

from weft_extract.contract import SourceDoc
from weft_extract.payload import BoundingBox, PageSpan
from weft_kernel.payload import (
    Failed,
    MediaType,
    Node,
    NothingToProduce,
    Outcome,
    Produced,
    SchemaVersionRefusedError,
    SourceId,
)
from weft_pdf.document import (
    ExtractedFigure,
    ExtractedTable,
    PageReader,
    PageText,
    PdfPages,
    extract_documents,
)


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
    )


def test_each_page_becomes_its_own_node_carrying_the_page_it_is() -> None:
    # Arrange — two pages that differ in both number and text, so neither dimension
    # can stand in for the other.
    read = _reading(
        PageText(number=1, text="first page", images=0),
        PageText(number=2, text="second page", images=1),
    )

    # Act
    outcome = _extract(read)

    # Assert
    assert isinstance(outcome, Produced)
    first, second = outcome.value
    assert [node.content for node in outcome.value] == ["first page", "second page"]
    assert first.ext_as(PageSpan) == PageSpan(page=1, ordinal=0)
    assert second.ext_as(PageSpan) == PageSpan(page=2, ordinal=0)
    assert first.lineage.sources == second.lineage.sources == frozenset({SourceId("paper")})


def test_a_page_node_still_says_which_backend_read_it() -> None:
    # Arrange — `PdfPages` keeps `backend` and nothing else: it is the payload's own
    # answer to which backend won the fallback chain, which `PageSpan` cannot give.
    read = _reading(PageText(number=1, text="only page", images=0))

    # Act
    outcome = _extract(read)

    # Assert
    assert isinstance(outcome, Produced)
    [node] = outcome.value
    assert node.ext_as(PdfPages) == PdfPages(backend="stand-in")


def test_two_pages_holding_the_same_text_are_two_nodes_not_one() -> None:
    # Arrange — the page is now a fact *about the node*, so one node cannot hold two
    # contradictory pages. `Node.synthetic`'s `ordinal` is what keeps their digests apart;
    # G20's own answer (identical content is one node) is unchanged, because these
    # nodes are no longer identical.
    read = _reading(
        PageText(number=3, text="continued overleaf", images=0),
        PageText(number=7, text="continued overleaf", images=0),
    )

    # Act
    outcome = _extract(read)

    # Assert
    assert isinstance(outcome, Produced)
    third, seventh = outcome.value
    assert third.id != seventh.id
    assert third.ext_as(PageSpan) == PageSpan(page=3, ordinal=0)
    assert seventh.ext_as(PageSpan) == PageSpan(page=7, ordinal=0)


def test_a_pdf_pages_stored_before_the_page_became_a_node_upgrades_rather_than_refusing() -> None:
    # Arrange — what `weft-rag 2.4.0` wrote: a backend and an offset table.
    stored = {"backend": "pdf-layout", "starts": [0, 1200, 2400]}

    # Act
    upgraded = PdfPages.upgrade(stored, "1.0.0")

    # Assert — the offsets are dropped, because there is no longer anything they index into.
    assert PdfPages.model_validate(dict(upgraded)) == PdfPages(backend="pdf-layout")


def test_a_pdf_pages_stored_at_a_version_this_class_never_wrote_still_refuses() -> None:
    # Arrange / Act / Assert — the upgrade path is for the one shape that existed, not a
    # licence to guess at any older row.
    with pytest.raises(SchemaVersionRefusedError, match="weft-pdf"):
        PdfPages.upgrade({"backend": "pdf-layout"}, None)


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
    assert node.ext_as(PageSpan) == PageSpan(page=1, ordinal=0)


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


_TWO_PAGES: Final[PageReader] = _reading(
    PageText(number=1, text="first page", images=0),
    PageText(number=2, text="second page", images=0),
)


def test_a_table_is_a_child_of_the_page_it_was_found_on() -> None:
    # Arrange — the table is on page 2, so a parent chosen by "the first text node" or
    # "the only root" would pass while naming the wrong page.
    def read_tables(content: bytes) -> Sequence[ExtractedTable]:
        del content
        return (
            ExtractedTable(
                page=2,
                headers=("Region", "Revenue"),
                rows=(("EMEA", "1,204"),),
                bbox=BoundingBox(x0=0.0, y0=0.0, x1=10.0, y1=10.0),
            ),
        )

    # Act
    outcome = extract_documents(
        [_doc()],
        backend="stand-in",
        read_pages=_TWO_PAGES,
        unreadable=(_RefusedError,),
        read_tables=read_tables,
    )

    # Assert
    assert isinstance(outcome, Produced)
    pages = [node for node in outcome.value if node.media_type is MediaType.TEXT]
    tables = [node for node in outcome.value if node.media_type is MediaType.TABLE]
    second = next(node for node in pages if node.ext_as(PageSpan) == PageSpan(page=2, ordinal=0))
    assert [table.lineage.parents for table in tables] == [(second.id,)]


def test_a_figure_is_owed_against_the_page_it_was_found_on() -> None:
    # Arrange — same shape for the figure path, which `run` finishes after a blob write.
    def read_figures(content: bytes) -> Sequence[ExtractedFigure]:
        del content
        return (ExtractedFigure(page=2, index_on_page=0, caption="Figure 1. A chart", png=b"png"),)

    # Act
    outcome = extract_documents(
        [_doc()],
        backend="stand-in",
        read_pages=_TWO_PAGES,
        unreadable=(_RefusedError,),
        read_figures=read_figures,
    )

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    second = next(
        node for node in result.nodes if node.ext_as(PageSpan) == PageSpan(page=2, ordinal=0)
    )
    [pending] = result.figures
    assert pending.root.id == second.id
