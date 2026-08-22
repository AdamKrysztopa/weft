"""Unit tests for `weft_generate.page`.

Mirrors `packages/weft-generate/src/weft_generate/page.py`. Covers the happy path (an
offset and a locator on the same node resolve to a page), the edge case of a node
carrying only one of the two facts (no page, not a crash), and the error case is folded
into that same edge case — this module never raises, by design, so there is no separate
failure path to exercise. Also proves the point of the module: it resolves a page from
two locally-declared stand-ins, never importing `weft_chunk.payload.ChunkOffset` or
`weft_pdf.PdfPages`, which is what keeps `weft-generate` off a PDF-only dependency.
"""

from weft_generate.page import page_for
from weft_kernel.payload import ExtModel, MediaType, Node


class _Offset(ExtModel):
    """Structurally identical to `weft_chunk.payload.ChunkOffset`, declared fresh so this
    test proves the duck-typed match rather than a same-class coincidence."""

    __namespace__ = "test-offset"
    __schema_version__ = "1.0.0"

    start: int


class _Locator(ExtModel):
    """Structurally identical to `weft_pdf.PdfPages`'s one relevant method."""

    __namespace__ = "test-locator"
    __schema_version__ = "1.0.0"

    boundaries: tuple[int, ...]

    def page_at(self, offset: int) -> int:
        for page, boundary in enumerate(self.boundaries, start=1):
            if offset < boundary:
                return page
        return len(self.boundaries)


def _node() -> Node:
    return Node.synthetic(content="whatever", media_type=MediaType.TEXT, reason="test fixture")


def test_a_node_carrying_both_facts_resolves_to_a_page() -> None:
    # Arrange
    node = _node().with_ext(_Offset(start=15)).with_ext(_Locator(boundaries=(10, 20, 30)))

    # Act
    page = page_for(node)

    # Assert
    assert page == 2


def test_a_node_carrying_only_an_offset_resolves_to_no_page() -> None:
    # Arrange — the common real case: a chunk from a plain-text source carries
    # `ChunkOffset` (every chunker attaches one) but nothing that can locate a page,
    # because nothing paginated the document it came from.
    node = _node().with_ext(_Offset(start=15))

    # Act / Assert
    assert page_for(node) is None


def test_a_node_carrying_neither_fact_resolves_to_no_page() -> None:
    # Arrange
    node = _node()

    # Act / Assert
    assert page_for(node) is None


def test_the_real_pdf_and_chunk_ext_models_satisfy_the_same_duck_typed_match() -> None:
    """The production case, not just a structural coincidence: a node carrying the two
    real ext models this pack never imports — `weft_pdf.PdfPages` and `weft_chunk.payload.
    ChunkOffset` — resolves through exactly the same code as the stand-ins above."""
    # Arrange
    from weft_chunk.payload import ChunkOffset
    from weft_pdf import PdfPages

    pages = PdfPages(backend="pdf-text", starts=(0, 12, 40))
    node = _node().with_ext(pages).with_ext(ChunkOffset(start=15))

    # Act / Assert
    assert page_for(node) == pages.page_at(15) == 2
