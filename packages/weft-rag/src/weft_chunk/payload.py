"""Where a chunk's content begins, inside the parent it was windowed from.

`docs/build-ledger.md`'s **2.9** line names this the second half of the page-attribution
gap: `Node.derive` deliberately drops `ext` (`weft_kernel.payload.node`, *"Lineage is
carried; `ext` and `embedding` are not"*), so a chunk built through it carries `ordinal` —
which window this is — never *where* in the parent's content that window starts. A page
number is meaningless without one: `weft_pdf.PdfPages.page_at` takes "an offset into this
node's content", and until this chunk carries that offset there is nothing to hand it.

Generic on purpose, not shaped for `weft-pdf`. Any pack that attaches document structure
to a root node — headings, section ids, a table of contents, page boundaries — needs the
same fact: where a window sits in the content it was cut from. `weft-chunk` does not
import `weft-pdf` to get it; see `fixed_size.py`'s module docstring for how a fact like
`PdfPages` still reaches a chunk without that dependency existing.
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
