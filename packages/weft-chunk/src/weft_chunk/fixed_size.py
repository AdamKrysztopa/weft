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
"""

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, model_validator

from weft_chunk.property import WordBoundaries
from weft_kernel.context import Context
from weft_kernel.payload import Node, NothingToProduce, Outcome, Produced, Property

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
        windows.append(node.derive(content=piece, ordinal=ordinal))
        ordinal += 1
        start += step
    return windows
