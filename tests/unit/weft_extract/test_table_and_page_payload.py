"""`TableGrid` and `PageSpan` — what a structured extractor recovers. Ledger task `9.5`.

`docs/11-multimodal.md` §2.4 gives the ingest path's payload table: a prose node carries a
`PageSpan` (page, reading-order ordinal), a table node carries a `TableGrid` (rows, headers,
spans, caption, page, bbox), and a figure node carries a `PageSpan` and a `BlobRef`. `BlobRef`
shipped with the blob store at `9.4`; these two are the rest of it.

**Why they live in `weft_extract` and not in `weft-pdf`, which is what `11:181` proposes.** That
line predates `9.13`, which ships a *second* structured extractor — `weft-docling`, its own
distribution, kept separate for its dependency weight — and that extractor produces tables too. A
`TableGrid` published from `weft-pdf` would make every future table producer depend on the
pdfplumber pack to name the fact it produces. `11` §6 rank 11 already states the rule this
follows, and calls it the canonical example of itself: *"if two extractors both need it, it
belongs to the contract's pack"*. `weft_extract` is the pack that publishes `Extractor`, so it is
that pack, and `9.6`'s two serialisations land beside the grid rather than beside one parser.

**Neither is transient.** `11` §2.4 is explicit for the grid — *"a cell grid is kilobytes of JSONB,
which is what `ext` is for. Only bytes were ever a transience problem"* — and a comparable design
destroyed its grid inside the cleaning pipeline, which is why nothing downstream could choose a
representation. Stripping either would leave a `TABLE` node in the store that no serialiser could
re-render and no retriever could filter by page.

**Every field is typed, and the bounding box is a model rather than a 4-tuple.** A positional
quadruple is a convention a docstring states and nothing enforces — the exact shape `11` §6 records
a third party paying for, where "the cache key is a positional assumption its own docstring states
and nothing enforces". Naming the edges costs one class and makes the mistake unrepresentable.
"""

import pytest
from pydantic import ValidationError

from weft_extract.payload import BoundingBox, CellSpan, PageSpan, TableGrid
from weft_kernel.payload import ExtModel, MediaType, Node


def _grid() -> TableGrid:
    return TableGrid(
        headers=("Region", "Revenue"),
        rows=(("EMEA", "1,204"), ("APAC", "988")),
        caption="Table 2. Revenue by region.",
        page=7,
        bbox=BoundingBox(x0=72.0, y0=520.5, x1=523.0, y1=610.25),
    )


def test_both_facts_are_ext_models_carrying_their_own_schema_version() -> None:
    """`S5`: a persisted shape carries a version in the stored bytes, not in a `ClassVar` nobody
    serialises. `ExtModel` enforces both declarations at class definition, so this reads them back.
    """
    # Act / Assert
    for model in (TableGrid, PageSpan):
        assert issubclass(model, ExtModel)
        assert model.__namespace__
        assert model.__schema_version__


def test_neither_fact_is_transient() -> None:
    """Stripping either at the seam would leave a `TABLE` node nothing can re-render."""
    # Act / Assert
    assert TableGrid.__transient__ is False
    assert PageSpan.__transient__ is False


def test_the_two_facts_occupy_different_namespaces() -> None:
    """A node carries at most one model per namespace, and a table on a page needs both."""
    # Act / Assert
    assert TableGrid.__namespace__ != PageSpan.__namespace__


def test_a_grid_survives_a_round_trip_through_json() -> None:
    """`L9.43`: a model that dumps correctly and reads back wrong is write-only, and this tree has
    paid for that twice. Asserted in the red phase rather than after reading a diff.
    """
    # Arrange
    grid = _grid()

    # Act
    rebuilt = TableGrid.model_validate(grid.model_dump(mode="json"))

    # Assert
    assert rebuilt == grid


def test_a_page_span_survives_a_round_trip_through_json() -> None:
    # Arrange
    span = PageSpan(page=3, ordinal=11)

    # Act / Assert
    assert PageSpan.model_validate(span.model_dump(mode="json")) == span


def test_a_grid_reaches_a_node_and_comes_back_as_the_model_it_was() -> None:
    """The fact `ext` exists for: a typed model in, the same typed model out via `ext_as`."""
    # Arrange
    grid = _grid()

    # Act
    node = Node.synthetic(
        content="Region | Revenue", media_type=MediaType.TABLE, reason="9.5's subject"
    ).with_ext(grid)

    # Assert
    assert node.ext_as(TableGrid) == grid


def test_a_grid_states_its_own_shape_rather_than_leaving_it_to_a_reader() -> None:
    """Headers and every row agree on width, or the grid is not a grid.

    A ragged grid is representable in a list-of-lists and meaningless as a table: a serialiser
    would emit rows whose cells line up under the wrong headers, silently. Refused here, where the
    fact is built, rather than at whichever of the two serialisers notices first.
    """
    # Act / Assert
    with pytest.raises(ValidationError):
        TableGrid(
            headers=("Region", "Revenue"),
            rows=(("EMEA", "1,204"), ("APAC",)),
            caption=None,
            page=1,
            bbox=BoundingBox(x0=0.0, y0=0.0, x1=1.0, y1=1.0),
        )


def test_a_grid_with_no_caption_says_so_rather_than_inventing_one() -> None:
    """`11` §2.4 refuses a synthesised label outright; `None` is the honest absence."""
    # Act
    grid = TableGrid(
        headers=("A",),
        rows=(("1",),),
        caption=None,
        page=1,
        bbox=BoundingBox(x0=0.0, y0=0.0, x1=1.0, y1=1.0),
    )

    # Assert
    assert grid.caption is None


def test_a_merged_cell_is_named_rather_than_positional() -> None:
    """`spans` carries `CellSpan`s, so a reader never has to know which index means what."""
    # Act
    span = CellSpan(row=0, column=1, row_span=1, column_span=2)

    # Assert
    assert (span.row, span.column, span.row_span, span.column_span) == (0, 1, 1, 2)


def test_a_bounding_box_with_inverted_edges_is_refused() -> None:
    """`x1 > x0` and `y1 > y0` or it is not a box — the check a 4-tuple cannot carry."""
    # Act / Assert
    with pytest.raises(ValidationError):
        BoundingBox(x0=10.0, y0=0.0, x1=1.0, y1=5.0)


def test_a_negative_page_is_refused() -> None:
    """A page number an extractor could not determine is a bug upstream, not a `-1` sentinel."""
    # Act / Assert
    with pytest.raises(ValidationError):
        PageSpan(page=-1, ordinal=0)
