"""Resolving a citation's page number, without this pack knowing what produced it.

**G17, settled 2026-09-12, is why this module walks one fact instead of two.** Before this,
the page was an offset into a whole document's joined text (`weft_pdf.PdfPages.starts`), so
resolving it needed *two* facts on one node — an offset (`ChunkOffset`, `weft-chunk`'s own
ext model) and something that could turn that offset into a page (`PdfPages.page_at`) — and
a cleaner rewriting the content invalidated the offset silently. G17 made the page a scalar
fact directly on the node it describes, so there is one fact to find and nothing a rewrite
can invalidate. Both of the retired halves are gone from the tree: `PdfPages.starts` at
`R9.1`, and `ChunkOffset` at `R17.1` once this module stopped being its only reader.

`weft-generate` depends on `weft-kernel`, `weft-retrieve`, `weft-llm` and `weft-prompts`
only (`.phase2-design.md` §1's own table), and importing `weft_extract.payload.PageSpan` or
`weft_extract.payload.TableGrid` here would mean every deployment that generates an answer —
even one whose corpus is Markdown and never touches a PDF — has to install an extraction pack
to resolve a citation. That is the opposite of `.phase2-findings.md` finding 10's own
generalisation: "the same argument applies to embedders, providers, retrieval strategies,
fusers and rerankers. If the design makes parser-swapping easy by a mechanism special to
extraction, the mechanism is wrong."

So this module never imports either type. It asks a node's `ext` values, structurally, for
one shape — a `runtime_checkable` `Protocol` the project's own rule prefers over `hasattr`
(`weft_prompts.cascade`'s tier-1 guard is the precedent). `PageSpan` (on a prose or figure
node) and `TableGrid` (on a table node) both already satisfy it without either class
changing, and any future pack whose ext model locates a page satisfies it the same way, for
free.
"""

from typing import Protocol, runtime_checkable

from weft_kernel.payload import Node


@runtime_checkable
class _PageCarrier(Protocol):
    """Structurally, `weft_extract.payload.PageSpan` or `weft_extract.payload.TableGrid`: a
    fact about a node that names the page it sits on directly."""

    page: int


def page_for(node: Node) -> int | None:
    """`node`'s page, if something in its `ext` carries one — `None` otherwise, which is a
    legitimate answer, not a failure.

    The first matching namespace wins; a node carries at most one page-shaped fact in
    practice, so there is nothing to disambiguate between two candidates.
    """
    for model in node.ext.values():
        if isinstance(model, _PageCarrier):
            return model.page
    return None
