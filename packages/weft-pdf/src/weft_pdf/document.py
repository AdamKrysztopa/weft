"""What every PDF backend in this pack shares: a page, where it starts, and the batch rules.

`.phase2-findings.md` finding 9 — *swapping a parser must be a configuration
edit* — is what shapes this module. Two backends registering under one
`Extractor` contract must differ in **how they read a page and nothing else**:
the moment a rule about empty documents, scanned pages or node construction
is written twice, the two copies can disagree, and an operator swapping
`use: pdf-text` for `use: pdf-layout` gets a different engine rather than a
different parser. So every such rule lives here once, and a backend
contributes exactly one thing — a `read_pages` callable. There is no
`if backend == ...` anywhere in this distribution, and there is nowhere for
one to be written.

**The rule a backend author must not get wrong**, stated where the author
will read it and enforced below rather than left as a convention:

> Return `NothingToProduce` only when you can distinguish *"there is nothing
> here"* from *"I could not see it"*. If your backend cannot tell those apart
> for this input, return `Failed`.

Applied to a PDF, that is one concrete distinction, and it is the one the
fallback chain (task 2.28) rests on. A page with a text layer that draws no
glyphs is a page a backend **looked at** — nothing is there, and a second
backend will find nothing either, so the chain must stop. A page with no text
but with an embedded image is a page a text-layer backend **could not see**:
it may be a scan, it may be a blank page with a logo, and this pack has no
way to tell. That is `Failed`, so the chain continues to another backend and,
if one is ever installed, to OCR. Both cases are unit-tested in this
distribution, so the distinction is a checked fact rather than a promise.

There is a third case, and it is the one a reviewer caught this module getting
wrong: a reading that recovered **no pages at all**. `pdfplumber` answers zero
pages — rather than raising — for a truncated download, where `pypdf` raises;
zero pages reached the empty-content test below and was reported as a document
that is genuinely empty, which stops the chain on a document the other backend
would have recovered. Nothing can be concluded from zero pages, so that is
`Failed` too, checked before the emptiness test rather than after it.

**A batch that could not be *read* is refused whole. A batch containing an
empty document is not.** The first document that raises, or that this pack
could not see, decides the outcome for the whole batch, exactly as
`weft_extract.text.TextExtractor` already does for a file that is not valid
UTF-8: `Produced` carries no room to report what was dropped, so a partial
answer would be indistinguishable downstream from a complete one, and a corpus
that silently shrinks is the shape of reference defect 7. A document that was read
and legitimately holds no text is the opposite case and was originally
conflated with it — it drops nothing, because there was nothing in it to drop,
and discarding the four documents beside it *is* the shrinking corpus that
argument exists to refuse. So `NothingToProduce` is answered only when **no**
document in the batch produced content, and its reason names every one of
them.
"""

from bisect import bisect_right
from collections.abc import Callable, Sequence

from pydantic import BaseModel, ConfigDict, Field

from weft_extract.contract import SourceDoc
from weft_kernel.payload import (
    ExtModel,
    Failed,
    MediaType,
    Node,
    NothingToProduce,
    Outcome,
    Produced,
)

#: The one suffix both backends in this pack claim. Capability metadata, per
#: `docs/02-extension-model.md` section 1 — declared once here and read off each
#: plugin class as `extensions`, the same shape `weft_extract.text` established, so a
#: dispatcher choosing an extractor by file extension reads it rather than a second,
#: hand-maintained list.
EXTENSIONS: tuple[str, ...] = (".pdf",)


class PageText(BaseModel):
    """One page as a backend read it — the whole of what a backend has to supply.

    `images` is a count rather than the images themselves: nothing in this
    pack decodes an image, and the only question it answers is the one the
    module docstring poses — whether an empty page is a page with nothing on
    it or a page this backend could not see.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    number: int = Field(ge=1)
    text: str
    images: int = Field(ge=0)


class PdfPages(ExtModel):
    """Which backend read a document, and where each of its pages starts in the content.

    `.phase2-findings.md` finding 10: what a parser recovers beyond plain text
    attaches as a declared extension model, never as a widened `Node` and never
    as `dict[str, object]`. Page boundaries are the first thing a PDF parser
    knows that plain text does not.

    **What this reaches, and how — closed by ledger 2.9, corrected here.** This model is
    built once, on the **root node** this pack extracts, and `Node.derive` carries lineage
    but deliberately drops `ext` (`weft_kernel.payload.node`, *"Lineage is carried; `ext`
    and `embedding` are not"*) — so on its own, this fact would die at the first `derive`
    call the chunker makes. `weft_chunk.fixed_size._carry_forward` is the fix: it copies
    every namespace a parent's `ext` carries, this one included, onto each window before
    the chunker returns it, so a chunk reaching a store carries this same `PdfPages`
    unchanged. What a chunk adds on top is `weft_chunk.payload.ChunkOffset` — the
    character offset *this window* starts at within the content `starts` above is
    indexed into — so `page_at` still answers correctly once the content it is called
    against is a chunk's, not the root's: `pdf_pages.page_at(chunk_offset.start)`.

    `page_at`'s own docstring still says "this node's content" because that is still
    literally true: a `PdfPages` carried onto a chunk is unchanged data, indexed against
    the *root's* content it was built from, and `ChunkOffset.start` is what supplies the
    matching root-relative offset rather than the chunk's own local one.

    Not `__transient__`: a page boundary is a durable fact about the document,
    not a working value. A pack wanting nodes carrying it to survive a round
    trip through `weft-store` calls `weft_store.register_ext_model(PdfPages)`
    itself — the explicit, second call `weft_store.rehydrate`'s own docstring
    describes, which is why this distribution does not depend on the store.
    """

    __namespace__ = "weft-pdf"

    backend: str = Field(min_length=1)
    starts: tuple[int, ...] = Field(min_length=1)

    def page_at(self, offset: int) -> int:
        """The 1-based page holding the character at `offset` of **this node's** content.

        The reason `starts` is worth carrying at all: an offset into extracted
        text is meaningless to a reader, and a page number is exactly what they
        can go and check. `offset` is into the content of the node this model is
        attached to — the root, and only the root; see the class docstring for
        why nothing downstream can call this yet. An offset past the end of the
        content answers the last page rather than raising: this model does not
        hold the content and so cannot know where it ends, and inventing a bound
        it cannot verify would be worse than answering the nearest page.
        """
        if offset < 0:
            raise ValueError(f"a content offset cannot be negative; got {offset}")
        return bisect_right(self.starts, offset)


#: What a backend contributes, and the only thing it contributes: bytes in, pages out.
#: Anything it cannot read is raised as its own library's exception and named in
#: `unreadable` — see `extract_documents`.
type PageReader = Callable[[bytes], Sequence[PageText]]


def extract_documents(
    payload: Sequence[SourceDoc],
    *,
    backend: str,
    read_pages: PageReader,
    unreadable: tuple[type[Exception], ...],
    separator: str,
) -> Outcome[Sequence[Node]]:
    """One root `Node` per source document, under the rules in the module docstring.

    `unreadable` is the calling backend's own library exception classes, passed
    rather than caught broadly: a parsing library's failure to read a file is a
    documented, expected outcome that belongs in `Failed` so the fallback chain
    can try the next backend, while anything else escaping a backend is a bug
    that must reach the registration seam with its traceback intact.
    """
    if not payload:
        return NothingToProduce(reason="no source documents to extract")

    nodes: list[Node] = []
    empty: list[str] = []
    for doc in payload:
        try:
            pages = read_pages(doc.content)
        except unreadable as exc:
            return Failed(reason=f"{backend} could not read '{doc.uri}': {exc}")

        if not pages:
            return Failed(
                reason=(
                    f"{backend} recovered no pages from '{doc.uri}' — it could not read "
                    "the document, so another backend should try it."
                )
            )

        unseen = _first_unseen_page(pages)
        if unseen is not None:
            return Failed(
                reason=(
                    f"'{doc.uri}' page {unseen.number}: no text layer, "
                    f"{unseen.images} image(s) present — {backend} cannot tell a scanned "
                    f"page from a blank one, so another backend should try this document."
                )
            )

        content, starts = _joined(pages, separator=separator)
        if not content.strip():
            empty.append(f"'{doc.uri}': {len(pages)} page(s), and no text on any of them")
            continue

        nodes.append(
            Node.synthetic(
                content=content,
                media_type=MediaType.TEXT,
                reason=f"extracted from '{doc.uri}' by {backend}",
                sources=frozenset({doc.source_id}),
            ).with_ext(PdfPages(backend=backend, starts=starts))
        )
    if not nodes:
        return NothingToProduce(reason="; ".join(empty))
    return Produced(value=nodes)


def _first_unseen_page(pages: Sequence[PageText]) -> PageText | None:
    """The first page with no text and at least one image, or `None` if there is none.

    "Unseen" rather than "scanned" on purpose: this pack cannot tell a scan from
    a photograph beside a caption that failed to extract, and naming it for the
    guess would make the reason line claim more than the evidence supports.
    """
    return next((page for page in pages if not page.text.strip() and page.images > 0), None)


def _joined(pages: Sequence[PageText], *, separator: str) -> tuple[str, tuple[int, ...]]:
    """Every page's text as one string, and the offset each page starts at within it.

    Every page contributes an entry, including one that extracted to nothing —
    dropping empty pages would shift every later page number by an amount only
    this function knows, which is precisely the error `PdfPages.page_at` exists
    to make impossible.
    """
    starts: list[int] = []
    offset = 0
    for index, page in enumerate(pages):
        if index:
            offset += len(separator)
        starts.append(offset)
        offset += len(page.text)
    return separator.join(page.text for page in pages), tuple(starts)
