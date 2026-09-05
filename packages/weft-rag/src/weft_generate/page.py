"""Resolving a citation's page number, without this pack knowing what produced it.

The second half of ledger 2.9's page-attribution gap: `weft_chunk.fixed_size` now carries
a chunk's character offset into its parent (`weft_chunk.payload.ChunkOffset`) and forwards
whatever the parent's own `ext` said, `weft_pdf.PdfPages` included. Turning the two into a
page number is `PdfPages.page_at(offset)` — but `weft-generate` depends on `weft-kernel`,
`weft-retrieve`, `weft-llm` and `weft-prompts` only (`.phase2-design.md` §1's own table),
and adding `weft-pdf` here would mean every deployment that generates an answer — even one
whose corpus is Markdown and never touches a PDF — has to install a PDF extraction pack to
resolve a citation. That is the opposite of `.phase2-findings.md` finding 10's own
generalisation: "the same argument applies to embedders, providers, retrieval strategies,
fusers and rerankers. If the design makes parser-swapping easy by a mechanism special to
extraction, the mechanism is wrong."

So this module never imports `ChunkOffset` or `PdfPages`. It asks a node's `ext` values,
structurally, for the two shapes it needs — `runtime_checkable` `Protocol`s the project's
own rule prefers over `hasattr` (`weft_prompts.cascade`'s tier-1 guard is the precedent).
`ChunkOffset` and `PdfPages` already satisfy them without either class changing, and any
future pack whose ext model locates a position in a document — a heading, a slide number —
satisfies them the same way, for free.
"""

from typing import Protocol, runtime_checkable

from weft_kernel.payload import Node


@runtime_checkable
class _OffsetCarrier(Protocol):
    """Structurally, `weft_chunk.payload.ChunkOffset`: a character offset into a parent."""

    start: int


@runtime_checkable
class _PageLocator(Protocol):
    """Structurally, `weft_pdf.PdfPages`: turns a content offset into a 1-based page."""

    def page_at(self, offset: int) -> int: ...


def page_for(node: Node) -> int | None:
    """`node`'s page, if something in its `ext` carries an offset and something else can
    turn it into one — `None` otherwise, which is a legitimate answer, not a failure.

    Both facts have to come from the same node: a node's `ext` namespaces are all data
    about *this* node's own content, carried there by the chunker's forwarding (`weft_chunk.
    fixed_size._carry_forward`), so there is nothing to mismatch by picking one of each
    from `node.ext.values()` independently — see the module docstring for why that walk
    replaces a direct import of either concrete type.
    """
    offset: int | None = None
    locator: _PageLocator | None = None
    for model in node.ext.values():
        if isinstance(model, _OffsetCarrier):
            offset = model.start
        if isinstance(model, _PageLocator):
            locator = model
    if offset is None or locator is None:
        return None
    return locator.page_at(offset)
