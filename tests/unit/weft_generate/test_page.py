"""Unit tests for `weft_generate.page`.

Mirrors `packages/weft-rag/src/weft_generate/page.py`. Covers the happy path (a node
carrying a page answers it), the edge case of a node carrying no such fact (no page, not a
crash), and the error case is folded into that same edge case — this module never raises, by
design, so there is no separate failure path to exercise. Also proves the point of the module:
it resolves a page from a locally-declared stand-in, never importing
`weft_extract.payload.PageSpan` or `weft_extract.payload.TableGrid`, which is what keeps
`weft-generate` off an extraction dependency.

**G17, settled 2026-09-12, is why the shape changed.** This module used to need *two* facts on
one node — an offset and something that could turn an offset into a page — because the page was
stored as a table of offsets into the whole document's text. A cleaner rewriting that text
invalidated the offsets silently. The page is now a scalar fact about the node it describes, so
there is one fact to find and nothing a rewrite can invalidate; the offset-plus-locator pair is
retired with `PdfPages.starts`, rather than kept as machinery no shipped pack can fire.
"""

from weft_generate.page import page_for
from weft_kernel.payload import ExtModel, MediaType, Node


class _Span(ExtModel):
    """Structurally identical to `weft_extract.payload.PageSpan`, declared fresh so this test
    proves the duck-typed match rather than a same-class coincidence."""

    __namespace__ = "test-span"
    __schema_version__ = "1.0.0"

    page: int
    ordinal: int


class _Offset(ExtModel):
    """Structurally identical to `weft_chunk.payload.ChunkOffset` — a fact every chunker
    attaches, which locates nothing on its own and must not be mistaken for a page."""

    __namespace__ = "test-offset"
    __schema_version__ = "1.0.0"

    start: int


def _node() -> Node:
    return Node.synthetic(content="whatever", media_type=MediaType.TEXT, reason="test fixture")


def test_a_node_carrying_a_page_resolves_to_it() -> None:
    # Arrange — page 4 rather than page 1, so an implementation that lost the value and
    # answered the first page would not satisfy this.
    node = _node().with_ext(_Span(page=4, ordinal=0))

    # Act
    page = page_for(node)

    # Assert
    assert page == 4


def test_a_node_carrying_only_a_chunk_offset_resolves_to_no_page() -> None:
    # Arrange — the common real case: a chunk from a plain-text source carries
    # `ChunkOffset` and nothing else, because nothing paginated the document it came from.
    node = _node().with_ext(_Offset(start=15))

    # Act / Assert
    assert page_for(node) is None


def test_a_node_carrying_no_facts_at_all_resolves_to_no_page() -> None:
    # Arrange
    node = _node()

    # Act / Assert
    assert page_for(node) is None


def test_the_real_extraction_ext_models_satisfy_the_same_duck_typed_match() -> None:
    """The production case, not a structural coincidence: the two real ext models this pack
    never imports — `PageSpan` on a prose or figure node, `TableGrid` on a table node —
    resolve through exactly the same code as the stand-in above."""
    # Arrange
    from weft_extract.payload import BoundingBox, PageSpan, TableGrid

    prose = _node().with_ext(PageSpan(page=4, ordinal=0))
    table = _node().with_ext(
        TableGrid(
            headers=("Region",),
            rows=(("EMEA",),),
            page=9,
            bbox=BoundingBox(x0=0.0, y0=0.0, x1=1.0, y1=1.0),
        )
    )

    # Act / Assert — two different namespaces, two different pages, one walk.
    assert page_for(prose) == 4
    assert page_for(table) == 9
