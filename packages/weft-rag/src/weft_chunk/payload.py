"""Where a chunk's content begins, inside the parent it was windowed from.

`docs/internal/build-ledger.md`'s **2.9** line names this the second half of the page-attribution
gap: `Node.derive` deliberately drops `ext` (`weft_kernel.payload.node`, *"Lineage is
carried; `ext` and `embedding` are not"*), so a chunk built through it carries `ordinal` —
which window this is — never *where* in the parent's content that window starts.

**G17, settled 2026-09-12, retired the reader this offset was for.** A page number used to
be meaningless without one — `weft_pdf.PdfPages.page_at` took "an offset into this node's
content" and turned it into a page — but G17 made the page a scalar fact read directly off
the node it describes (`weft_extract.payload.PageSpan`), so a page is no longer resolved
through this offset at all. `ChunkOffset` itself is unchanged and stays registered: it is
still where a chunk's content begins in its parent, a fact generic enough that any pack
attaching document structure to a root node — headings, section ids, a table of contents —
may yet read it the way page attribution once did.
"""

from pydantic import Field

from weft_kernel.payload import ExtModel


class ChunkOffset(ExtModel):
    """`start`: the character offset in the parent node's content where this chunk begins.

    No `end` field: a chunk already carries its own content, so the end is
    `start + len(content)` for as long as that content is unchanged. Storing it
    separately would be a second number that can drift from the first the moment either
    is edited in isolation — one fact, one place to read it from.
    """

    __namespace__ = "weft-chunk"
    __schema_version__ = "1.0.0"

    start: int = Field(ge=0)
