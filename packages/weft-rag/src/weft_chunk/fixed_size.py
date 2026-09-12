"""`FixedSizeChunker` — the built-in chunker: fixed-size windows with overlap.

Specified in `docs/06-phase-0-build.md` step 8: "a fixed-size chunker with
overlap." Every chunk is built through `Node.derive`, so lineage is carried
automatically (`docs/02-extension-model.md` → *The payload model*): a chunk's
`sources` is the union of its parent's sources, computed by the kernel, never
authored here.

`size` and `overlap` are `with:` configuration, per `docs/02-extension-model.md`
§1's rule that "a contract's registration API carries a typed configuration
model, or the extension point is decorative" — this is the model, validated
before `FixedSizeChunker` is ever constructed.

`destroys = (WordBoundaries,)` is task 1.2's — `docs/02-extension-model.md`
§3 → *Ordering constraints*. `Chunker` publishes a property vocabulary, so
`weft_kernel.registry` refuses to register any implementation that omits
`destroys` entirely; this one states the truth rather than an empty tuple,
because a fixed window really can and does split a word in half. See
`weft_chunk.property` for why.

**`config_model = FixedSizeChunkerConfig` — a repair, not part of the
original lift.** Without this class attribute, `weft_kernel.resolution.
resolve` reads `getattr(declared, "config_model", None)` as `None` and
refuses *any* `with:` block naming `size`/`overlap` with `StageNotConfigurableError`,
falsely claiming this stage "cannot be parameterised at all" — even though
`FixedSizeChunkerConfig`, immediately above, is exactly the model task 1.5's
mechanism was built to validate against. `02` §3's own canonical pipeline
example (`with: {size: 512, overlap: 50}`) could not resolve until this line
existed.

**Every window carries forward what its parent's `ext` said — ledger 2.9's
page-attribution gap, closed here.** `Node.derive` drops `ext` on purpose ("later stages
attach their own"); this is that later stage. `weft_kernel.payload.carry_forward` copies
each namespace in the parent's `ext` onto the chunk verbatim, so a fact a pack attached to
the whole document — `weft_extract.payload.PageSpan`, a future heading map — survives a
window cut from that document's content, without this pack importing `weft-extract` or
knowing what the fact means. `SyntheticOrigin` is the one namespace excluded: it states
that *this* node has no real lineage, and a derived chunk always does, so copying it
forward would attach a claim about the chunk that is false the moment it is read.

**`carry_forward` moved to `weft_kernel.payload` at G17, 2026-09-12** — it was `weft_chunk.
carry.carry_forward` (ledger task `9.14`, where it was this module's own private
`_carry_forward` before `weft_chunk.table_rows.TableRowChunker` needed the identical shape
for a second caller) until G17 added a third consumer, `weft_clean`, which shares no
import with either of the first two — only `weft-kernel`. This module now imports it from
there rather than from a sibling pack.

**A window no longer records where it starts — repair `R17.1`, 2026-09-12.** This chunker
attached `weft_chunk.payload.ChunkOffset` to every window, and ledger 2.9's repair made that
offset compound across nested chunking so it stayed root-relative for `weft_pdf.PdfPages.
page_at` to resolve. **G17** retired that reader: a page became a scalar fact on the node it
describes (`weft_extract.payload.PageSpan`), carried forward above like any other, and no
caller has asked where a window begins since. A field a persisted record carries and nothing
renders is deleted rather than held for a reader that may arrive (`R9.11`'s rule, `L5.19`),
so the offset, its ext model and the compounding repair are all gone. A pack that later needs
a chunk's position in its parent adds it back as its own `ExtModel`, with the reader in the
same commit.
"""

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, model_validator

from weft_chunk.property import WordBoundaries
from weft_kernel.context import Context
from weft_kernel.payload import (
    Applies,
    MediaType,
    Node,
    NothingToProduce,
    Outcome,
    Produced,
    Property,
    carry_forward,
)

#: `docs/02-extension-model.md` §3's own pipeline example: `{size: 512, overlap: 50}`.
_DEFAULT_SIZE = 512
_DEFAULT_OVERLAP = 50


class FixedSizeChunkerConfig(BaseModel):
    """`FixedSizeChunker`'s `with:` configuration: a window size and its overlap, in characters."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    size: int = _DEFAULT_SIZE
    overlap: int = _DEFAULT_OVERLAP

    @model_validator(mode="after")
    def _overlap_is_smaller_than_size(self) -> "FixedSizeChunkerConfig":
        if self.size < 1:
            raise ValueError(f"size must be at least 1 (got {self.size})")
        if self.overlap < 0:
            raise ValueError(f"overlap must not be negative (got {self.overlap})")
        if self.overlap >= self.size:
            raise ValueError(
                f"overlap ({self.overlap}) must be smaller than size ({self.size}), or "
                f"chunking never advances past the first window"
            )
        return self


class FixedSizeChunker:
    """Splits each node's content into overlapping, fixed-size windows.

    Satisfies `weft_chunk.contract.Chunker` structurally — this class never
    imports it, the same path any third-party chunker pack takes. A node
    with empty content contributes no chunks; a batch that contributes none
    at all answers `NothingToProduce`, never an empty `Produced([])`.
    """

    destroys: tuple[type[Property], ...] = (WordBoundaries,)
    #: `_windows` slices `node.content` as a character string — a fixed window cut through a
    #: table's cell grid or an image's caption would not honour either shape, so `TEXT` is the
    #: one media type this splitting logic can claim.
    applies_to: tuple[Applies, ...] = (Applies(media_type=MediaType.TEXT),)
    config_model: type[FixedSizeChunkerConfig] = FixedSizeChunkerConfig

    def __init__(self, config: FixedSizeChunkerConfig | None = None) -> None:
        self._config = config if config is not None else FixedSizeChunkerConfig()

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx  # no service or locale this stage needs
        chunks: list[Node] = []
        for node in payload:
            chunks.extend(_windows(node, size=self._config.size, overlap=self._config.overlap))
        if not chunks:
            return NothingToProduce(reason="no chunk had any content to carry")
        return Produced(value=chunks)


def _windows(node: Node, *, size: int, overlap: int) -> list[Node]:
    """Every fixed-size, overlapping window of `node.content`, each a child of `node`."""
    text = node.content
    if not text:
        return []
    step = size - overlap
    windows: list[Node] = []
    ordinal = 0
    start = 0
    while start < len(text):
        piece = text[start : start + size]
        windows.append(carry_forward(node.derive(content=piece, ordinal=ordinal), parent=node))
        ordinal += 1
        start += step
    return windows
