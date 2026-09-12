"""`pdf-layout` recovers a table as its own node — ledger task `9.6`.

`MediaType.TABLE` has existed since Phase 0 and, measured 2026-09-06, no code in `packages/` had
ever produced one (`docs/internal/README.md`'s `S11` row). This is its first producer.

**One node, whose media type says so, carrying its grid.** The table node is `derive`d from the
node for the page it was found on — G17, settled 2026-09-12, made that one node per page rather
than one per document — so lineage and `sources` are carried and `weft delete` reaps it with
everything else. Its `content` is the **index-form** serialisation from
`weft_extract.table_text` — the pack that publishes `TableGrid`, not this one — so the day
`9.13`'s Docling backend produces a grid, the same table renders to the same text and a cell
containing a pipe cannot break one extractor and not the other. Its `ext` carries the `TableGrid`
itself, which is what lets `9.6`'s index form and a generator's prompt form both exist without
either being reconstructed from the other.

**It stays whole through the chunker, and that is `9.2`'s doing rather than this pack's.**
`FixedSizeChunker` claims `MediaType.TEXT`; the runner routes everything else past it untouched. So
a table node reaches the store as one node with no code here knowing a chunker exists — which is the
cross-pack property `docs/11-multimodal.md` §2 states and ledger `1.6` ticked against a fixture
before it was true of the product.

**`pdf-text` produces no tables and that is not an omission.** `pypdf` has no table extraction at
all; the backend that cannot see a table must not guess at one. What the two backends must agree
about is what a table *is once found*, which is why the serialiser is shared and the finder is not.
"""

from collections.abc import Sequence

import pytest

from tests.unit.weft_pdf.minimal_pdf import ruled_table, text_pages
from weft_extract.contract import SourceDoc
from weft_extract.payload import BoundingBox, TableGrid
from weft_extract.table_text import index_text
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, Produced, SourceId
from weft_pdf.document import ExtractedTable, PageText, extract_documents
from weft_pdf.pdf_layout import PdfLayoutExtractor

_ROWS = (("Region", "Revenue"), ("EMEA", "1,204"), ("APAC", "988"))


def _ctx() -> Context:
    return Context(tenant_id="t", run_id="r", trace_id="tr", locale="en")


def _doc(content: bytes) -> SourceDoc:
    return SourceDoc(source_id=SourceId("s-1"), uri="file:///report.pdf", content=content)


async def _nodes(content: bytes) -> Sequence[Node]:
    outcome = await PdfLayoutExtractor().run([_doc(content)], _ctx())
    assert isinstance(outcome, Produced), outcome
    return outcome.value


async def test_a_table_arrives_as_its_own_node_whose_media_type_says_so() -> None:
    """`MediaType.TABLE`'s first producer in the whole tree."""
    # Act
    nodes = await _nodes(ruled_table(_ROWS))

    # Assert
    tables = [node for node in nodes if node.media_type is MediaType.TABLE]
    assert len(tables) == 1


async def test_the_table_node_carries_the_grid_it_was_read_from() -> None:
    """The grid survives extraction — `11` §2.4's whole argument for keeping it in `ext`.

    Asserted as the cells rather than as a whole model, because the bounding box is pdfplumber's
    geometry and pinning it here would make this test a claim about the library's coordinates.
    """
    # Act
    nodes = await _nodes(ruled_table(_ROWS))
    grid = next(n for n in nodes if n.media_type is MediaType.TABLE).ext_as(TableGrid)

    # Assert
    assert grid is not None
    assert grid.headers == ("Region", "Revenue")
    assert grid.rows == (("EMEA", "1,204"), ("APAC", "988"))
    assert grid.page == 1


async def test_the_table_nodes_content_is_the_shared_index_serialisation() -> None:
    """Not this pack's own rendering: the one `weft_extract` publishes, byte for byte.

    This is what makes `9.6`'s pipe clause true across extractors — two backends that both find
    the same grid produce the same content, so the same table gets the same node id.
    """
    # Act
    nodes = await _nodes(ruled_table(_ROWS))
    table = next(n for n in nodes if n.media_type is MediaType.TABLE)
    grid = table.ext_as(TableGrid)

    # Assert
    assert grid is not None
    assert table.content == index_text(grid)


async def test_the_table_node_is_a_child_of_the_page_node_it_was_found_on() -> None:
    """Lineage carried, so `weft delete` of the source reaps the table with everything else.

    This fixture is one page, so it cannot tell *the page it was found on* from *the only
    node there is* — `tests/unit/weft_pdf/test_document.py` carries the two-page version,
    where the choice is observable.
    """
    # Act
    nodes = await _nodes(ruled_table(_ROWS))
    root = next(n for n in nodes if n.media_type is MediaType.TEXT)
    table = next(n for n in nodes if n.media_type is MediaType.TABLE)

    # Assert
    assert table.lineage.parents == (root.id,)
    assert table.lineage.sources == frozenset({SourceId("s-1")})


async def test_the_documents_text_is_still_produced_beside_the_table() -> None:
    """A table node replaces nothing. The page node it hangs off is still produced beside it."""
    # Act
    nodes = await _nodes(ruled_table(_ROWS))

    # Assert
    assert any(node.media_type is MediaType.TEXT for node in nodes)


async def test_a_pdf_with_no_table_produces_no_table_node() -> None:
    """The contrast that makes every assertion above a property of the table and not of the path."""
    # Act
    nodes = await _nodes(text_pages("just some prose, ruled by nothing"))

    # Assert
    assert not [node for node in nodes if node.media_type is MediaType.TABLE]


async def test_two_tables_in_one_document_are_two_nodes_with_distinct_ids() -> None:
    """Identical tables on one page would collide by content digest if nothing distinguished them.

    `11` §1.4's positional-index defect is the neighbouring failure: an ordinal that shifts when a
    parse finds one table fewer rebinds every later table onto the wrong content.
    """
    # Arrange — the same rows twice, so only the ordinal can tell the two nodes apart.
    content = ruled_table(_ROWS + _ROWS[1:])

    # Act
    nodes = await _nodes(content)
    tables = [node for node in nodes if node.media_type is MediaType.TABLE]

    # Assert
    assert len({node.id for node in tables}) == len(tables)


@pytest.mark.parametrize("cell", ["a|b", "a\\b"])
async def test_a_cell_containing_the_delimiter_survives_extraction(cell: str) -> None:
    """9.6's clause, end to end: the awkward cell reaches the grid and the content unbroken."""
    # Act
    nodes = await _nodes(ruled_table((("A", "B"), (cell, "x"))))
    grid = next(n for n in nodes if n.media_type is MediaType.TABLE).ext_as(TableGrid)

    # Assert
    assert grid is not None
    assert grid.rows == ((cell, "x"),)


# --- the three skip conditions, which the tests above do not reach --------------------------
#
# Driven through `extract_documents` with a stub table reader rather than through
# `_table_node` directly: the private helper is not the seam, and a malformed grid is far easier
# to hand a reader than to draw into a PDF that `pdfplumber` will misread the same way twice.


def _extracted(headers: tuple[str, ...], rows: tuple[tuple[str, ...], ...]) -> ExtractedTable:
    return ExtractedTable(
        page=1,
        headers=headers,
        rows=rows,
        bbox=BoundingBox(x0=0.0, y0=0.0, x1=1.0, y1=1.0),
    )


def _through_extract(*tables: ExtractedTable) -> Sequence[Node]:
    """One prose document, with `tables` supplied by a stub reader."""
    outcome = extract_documents(
        [_doc(text_pages("some prose"))],
        backend="stub",
        read_pages=lambda _: (PageText(number=1, text="some prose", images=0),),
        unreadable=(),
        read_tables=lambda _: tables,
    )
    assert isinstance(outcome, Produced), outcome
    return outcome.value


def _table_count(*tables: ExtractedTable) -> int:
    return len([n for n in _through_extract(*tables) if n.media_type is MediaType.TABLE])


def test_a_ragged_table_is_skipped_rather_than_repaired_or_raised() -> None:
    """One unreadable table is not a reason to fail a document, and padding it is a lie.

    `pdfplumber` returns a ragged grid for a table whose rules it partly missed. `TableGrid`
    refuses one by construction (`9.5`), so the choice here is skip, repair, or fail the whole
    document — and repairing means emitting cells under the wrong headers, silently, which is the
    scar `11` §1.4 records four renderers sharing.
    """
    # Act / Assert — the document still produces its root, and no table node.
    assert _table_count(_extracted(("A", "B"), (("1", "2"), ("3",)))) == 0


def test_a_table_with_no_headers_at_all_is_skipped() -> None:
    """`ExtractedTable` permits an empty header tuple; a table with no columns is not a table."""
    # Act / Assert
    assert _table_count(_extracted((), ())) == 0


def test_a_table_whose_header_row_is_entirely_blank_is_skipped() -> None:
    """The case a ruled grid drawn around nothing produces — every header cell empty.

    Distinct from *no headers*: the tuple has the right width, so nothing structural refuses it,
    and the index form would render `: 1 | : 2` — cells labelled by nothing at all.
    """
    # Act / Assert
    assert _table_count(_extracted(("", "  "), (("1", "2"),))) == 0


def test_a_table_with_headers_and_no_data_rows_is_kept() -> None:
    """The contrast that stops the three skips above from being "skip anything unusual".

    A table an extractor found and recovered no body from is still a table — `9.5`'s `TableGrid`
    accepts it and `9.6`'s serialiser renders its headers. Skipping it here would make *empty*
    silently mean two different things depending on which layer noticed.
    """
    # Act / Assert
    assert _table_count(_extracted(("A", "B"), ())) == 1


def test_one_bad_table_does_not_take_a_good_one_with_it() -> None:
    """The property the skip exists for, rather than the skip itself."""
    # Act / Assert
    assert _table_count(_extracted(("A",), (("1",), ())), _extracted(("A",), (("1",),))) == 1
