"""Where a chunk sat in its parent — ledger task **32.1**.

`docs/internal/build-ledger.md`'s **32.1** line: every chunk `fixed-size` and `table-rows`
emits carries its position within its parent — an ordinal, plus the character start for
`fixed-size` — so Phase 32's `adjacent-chunks` (`32.3`) can read a hit's siblings back by
ordinal through the store's Filter AST (`32.2`), rather than reaching for something no
chunker ever recorded.

No `end` field: a chunk already carries its own content, so the end is
`start + len(content)` for as long as that content is unchanged — the same reasoning the
withdrawn `ChunkOffset` (`R17.1`) gave for the field it never had either.
"""

from pydantic import Field

from weft_kernel.payload import ExtModel


class ChunkPosition(ExtModel):
    """Where a chunk sat in its parent: `ordinal`-th child, starting at character `start`.

    `start` is `None` for a chunk with no character span in its parent — a table row is
    the `index`-th row, not a slice of the parent's `content`.
    """

    __namespace__ = "weft-chunk"
    __schema_version__ = "1.0.0"

    ordinal: int = Field(ge=0)
    start: int | None = Field(default=None, ge=0)
