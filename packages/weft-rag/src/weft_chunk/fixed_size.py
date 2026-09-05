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

**Every window carries `ChunkOffset`, and every window carries forward what its parent's
`ext` said — ledger 2.9's page-attribution gap, closed here.** `Node.derive` drops `ext`
on purpose ("later stages attach their own"); this is that later stage. `_carry_forward`
copies each namespace in the parent's `ext` onto the chunk verbatim, so a fact a pack
attached to the whole document — `weft_pdf.PdfPages`, a future heading map — survives a
window cut from that document's content, without this pack importing `weft-pdf` or
knowing what the fact means. `SyntheticOrigin` is the one namespace excluded: it states
that *this* node has no real lineage, and a derived chunk always does, so copying it
forward would attach a claim about the chunk that is false the moment it is read. The
offset is applied last, after the copy, so a chunk's own `ChunkOffset` always wins over
a stale one a multi-level chunker might otherwise carry in from its own parent.

**Repair, ledger 2.9: `ChunkOffset.start` now compounds across nested chunking.** Three
reviewers of the first cut traced the same defect: `_windows` computed `start` as an offset
into whatever `node` it ran on, so re-chunking an already-chunked node (an ordinary
two-level technique — coarse pass then fine pass — and one `Chunker`'s declared
`Stage[Sequence[Node], Sequence[Node]]` shape explicitly permits the runner to compose) threw
away the parent chunk's own already-nonzero `start` and wrote a bare local offset instead.
`weft_pdf.PdfPages.starts` is indexed against the **root** document, per its own docstring, so
a second-level chunk's offset has to be root-relative too, or `page_at` silently answers the
wrong page rather than the honest `None` this feature exists to avoid. `_windows` now reads
the node it is chunking for its *own* `ChunkOffset`, if it carries one, and adds the local
offset to it before writing the new one — a single-level chunk (no parent offset) behaves
exactly as before, since the addend is `0`.
"""

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, model_validator

from weft_chunk.payload import ChunkOffset
from weft_chunk.property import WordBoundaries
from weft_kernel.context import Context
from weft_kernel.payload import (
    Node,
    NothingToProduce,
    Outcome,
    Produced,
    Property,
    SyntheticOrigin,
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
    """Every fixed-size, overlapping window of `node.content`, each a child of `node`.

    `base_start` is `node`'s own `ChunkOffset.start`, if it carries one — nonzero exactly
    when `node` is itself already a chunk of something else. Each window's local offset
    into `node.content` is added to it, not written alone, so a window's final `start`
    stays relative to the document `node`'s own offset (if any) was relative to, all the
    way back to the root. See the module docstring's *"Repair, ledger 2.9"* note.
    """
    text = node.content
    if not text:
        return []
    step = size - overlap
    base = node.ext_as(ChunkOffset)
    base_start = base.start if base is not None else 0
    windows: list[Node] = []
    ordinal = 0
    start = 0
    while start < len(text):
        piece = text[start : start + size]
        chunk = _carry_forward(node.derive(content=piece, ordinal=ordinal), parent=node)
        windows.append(chunk.with_ext(ChunkOffset(start=base_start + start)))
        ordinal += 1
        start += step
    return windows


def _carry_forward(chunk: Node, *, parent: Node) -> Node:
    """`chunk`, plus every namespace `parent.ext` carries except its root-origin marker.

    See the module docstring for why this is the fix for ledger 2.9's page-attribution
    gap: a fact a pack attached to the whole document is still a fact about a window cut
    from that document's content, and this is the one place that fact would otherwise be
    lost. `SyntheticOrigin` is excluded by name — `weft-chunk` already depends on
    `weft-kernel`, which owns it, so excluding it costs no new dependency — because it
    means "this node has no real lineage" and a derived chunk always has some.
    """
    for namespace, model in parent.ext.items():
        if namespace == SyntheticOrigin.__namespace__:
            continue
        chunk = chunk.with_ext(model)
    return chunk
