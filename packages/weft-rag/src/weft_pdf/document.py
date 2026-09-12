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

**Figures split the same way tables do, and then split further — ledger `9.7`.** A backend that
can crop a page (only `pdf_layout.py` can; `pdf_text.py`'s `pypdf` has no page-rendering
capability) contributes a `read_figures` reader beside `read_tables`, and this function decides
the one rule every such backend must share: a figure with no caption produces nothing at all —
no node, no bytes written anywhere — per `docs/11-multimodal.md` §2.4 and G5-b (`11:667`); the
caption feeds the node's identity digest, and a synthesised placeholder would collide every
captionless figure in a corpus onto one id. Where this function stops, and why: `extract_documents`
runs synchronously inside `asyncio.to_thread` (`pdf_layout.py`'s module docstring), so it cannot
`await BlobStore.put` — a figure's bytes never reach a `Node.ext` here. Instead this function
returns each captioned figure as a `PendingFigure`, the caller's own work order, inside an
`ExtractionResult` rather than a bare node list; `PdfLayoutExtractor.run` is where the `await`
happens and the `Node` actually gets built.

**A figure narrows what "unseen" means, and only for a caller that can look.** A caller with no
`read_figures` — every caller before `9.7`, and `pdf_text.py` still today — has nothing beyond a
bare count for a page with no text and an image, so the ambiguity is refused unconditionally,
whatever the rest of the document holds: `test_document.py`'s own check pairs a real caption on
page 1 with an unseen page 2 and still requires `Failed`, because losing page 2's content
silently, uninspected, is the exact corpus-shrinkage this check exists to prevent, and having
text elsewhere does not change what page 2 held. A `read_figures` reader has actually rendered
every image on the page it sits on and searched under it for a caption — so for a `read_figures`
caller specifically, that one page's ambiguity is resolved, not merely counted. This exception
still stops short of "any unseen page is fine once a backend can crop": `pdf_layout`'s own
`image_without_text` fixture is a single unseen page and the *entire* document, so letting it
through would report the exact "genuinely empty" conclusion the check exists to prevent — it
still `Failed`s, `read_figures` or not. Scoped to both facts together — a `read_figures` reader,
**and** a document that is not otherwise blank — is what lets `9.7`'s own fixture
(`figures_on_two_pages`, one page holding only a captionless figure beside a page of real text)
through as `Produced` without also excusing a page that is the whole document.

**A batch that could not be *read* is refused whole. A batch containing an
empty document is not.** The first document that raises, or that this pack
could not see, decides the outcome for the whole batch, exactly as
`weft_extract.text.TextExtractor` already does for a file that is not valid
UTF-8: `Produced` carries no room to report what was dropped, so a partial
answer would be indistinguishable downstream from a complete one, and a corpus
that silently shrinks is exactly the failure mode this design refuses. A document that was read
and legitimately holds no text is the opposite case and was originally
conflated with it — it drops nothing, because there was nothing in it to drop,
and discarding the four documents beside it *is* the shrinking corpus that
argument exists to refuse. So `NothingToProduce` is answered only when **no**
document in the batch produced content, and its reason names every one of
them.
"""

from collections.abc import Callable, Mapping, Sequence
from typing import overload

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from weft_extract.contract import SourceDoc
from weft_extract.payload import BoundingBox, PageSpan, TableGrid
from weft_extract.table_text import index_text
from weft_kernel.payload import (
    ExtModel,
    Failed,
    MediaType,
    Node,
    NothingToProduce,
    Outcome,
    Produced,
    SourceId,
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
    """Which backend read a document — the payload's own answer to which backend won the
    fallback chain, a fact `weft_extract.payload.PageSpan` cannot give.

    `.phase2-findings.md` finding 10: what a parser recovers beyond plain text
    attaches as a declared extension model, never as a widened `Node` and never
    as `dict[str, object]`.

    **G17, settled 2026-09-12: the extractor now emits one node per page, and `starts`
    retires.** Before this, one node held a whole document's joined text and `starts` was
    an offset table indexed into it, so a fact this pack attached to the whole document had
    to travel through `weft_kernel.payload.carry_forward` and then be re-read through an
    offset a later `Node.derive` cut (a chunk, a table) could invalidate simply by existing.
    A `TEXT` node is now one page, and the page it describes is a scalar fact attached
    directly (`weft_extract.payload.PageSpan`) rather than reconstructed from an offset and
    a locator — there is no offset left for a rewrite to invalidate, and no `page_at` left
    to call.

    Not `__transient__`: a page boundary is a durable fact about the document,
    not a working value. Nodes carrying it survive a round trip through
    `weft-store` because `weft_pdf.register()` declares it — `registrar.
    add_ext_model(PdfPages)` — through the same `PackRegistrar` this pack
    already uses for its two `Extractor` plugins (task 5.2g); this class
    itself still names no store and this distribution still depends on none.
    """

    __namespace__ = "weft-pdf"
    __schema_version__ = "2.0.0"

    backend: str = Field(min_length=1)

    @classmethod
    def upgrade(cls, data: Mapping[str, object], from_version: str | None) -> Mapping[str, object]:
        """A `weft-rag 2.4.0` corpus — `backend` plus an offset table — reads rather than refuses.

        Only `"1.0.0"` — the one shape this class ever wrote — upgrades; every other
        `from_version`, `None` included, still refuses through the base class, because the
        offsets are the only shape this pack has ever produced and guessing at any other one
        would be exactly the silent misread `ExtModel.upgrade`'s own docstring forbids.
        `starts` is dropped rather than migrated: it indexed into a joined document string
        that no longer exists, so there is nothing left for it to mean.

        What a corpus written before this migrates loses, and does not. On a pipeline that
        ran any cleaner, the page was already gone before this repair — `Node.derive` drops
        `ext` and, until `R9.1`, no cleaner put it back — so nothing regresses there. On a
        no-cleaner pipeline, a page `page_at` used to answer correctly is now simply absent
        until the corpus is reindexed: an honest `None`, never a wrong number.
        """
        if from_version == "1.0.0":
            return {"backend": data["backend"]}
        return super().upgrade(data, from_version)


#: What a backend contributes, and the only thing it contributes: bytes in, pages out.
#: Anything it cannot read is raised as its own library's exception and named in
#: `unreadable` — see `extract_documents`.
type PageReader = Callable[[bytes], Sequence[PageText]]


class ExtractedTable(BaseModel):
    """One table a backend found, before it becomes a `TableGrid` — ledger task `9.6`.

    Deliberately not `TableGrid` itself: a backend's own reading of a table can be
    ragged, headerless or otherwise malformed in ways `TableGrid` refuses by
    construction (see `weft_extract.payload`'s module docstring), and refusing that
    grid must skip the one table rather than fail the document. This model is what
    a backend hands back before that check runs.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: 1-based, matching `PageText.number`.
    page: int = Field(ge=1)
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    bbox: BoundingBox


#: What a backend contributes for tables, and the only thing it contributes: bytes in,
#: tables out. `None` (the default on `extract_documents`) means the backend cannot see
#: a table at all — see the module docstring's argument for why `pdf_text.py` passes
#: no reader rather than one that always answers empty.
type TableReader = Callable[[bytes], Sequence[ExtractedTable]]


class ExtractedFigure(BaseModel):
    """One image a backend found on a page, already cropped to PNG bytes — ledger task `9.7`.

    Deliberately not a `Node`, for the reason the module docstring gives: building one needs a
    `BlobStore.put` call this function runs inside `asyncio.to_thread` and cannot make. This is
    everything a backend can produce with no event loop and no service: the pixels it rendered,
    and the caption it found beneath them, if any.

    `index_on_page` is assigned by the backend to *every* image it finds on a page, whether or
    not that image has a caption — a captionless figure earlier on the page must not shift a
    later figure's own position, which is exactly the positional-index defect `docs/11-
    multimodal.md` §1.4 records a third party paying for. See `PendingFigure.ordinal` for what
    this becomes once `extract_documents` has filtered by caption.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: 1-based, matching `PageText.number`.
    page: int = Field(ge=1)
    #: 0-based reading-order position of this figure among every figure a backend found on this
    #: same page, independent of caption presence — see the class docstring.
    index_on_page: int = Field(ge=0)
    #: `None` when no caption line was found beneath this figure. Never an empty string: a
    #: backend that read only blank text under the image reports that as `None` too, so this
    #: function's caption ladder (module docstring) has one thing to check, not two.
    caption: str | None
    #: Already-rendered PNG bytes, opaque to this module — it never decodes or re-encodes them.
    png: bytes


#: What a backend contributes for figures, and the only thing it contributes: bytes in, cropped
#: images out. `None` (the default on `extract_documents`) means the backend cannot crop a page
#: at all — `pdf_text.py` passes nothing, for the identical reason it passes no `read_tables`:
#: `pypdf` has no page-rendering capability, so guessing at a figure would be worse than naming
#: that this backend cannot see one.
type FigureReader = Callable[[bytes], Sequence[ExtractedFigure]]

#: The multiplier separating a figure's page from its position on that page in the stable ordinal
#: `_figure_ordinal` derives — `page * _FIGURE_ORDINAL_PAGE_STRIDE + index_on_page`, so re-
#: extracting a document that lost an earlier figure never shifts a later figure onto another
#: figure's blob (`docs/11-multimodal.md` §1.4's "cache hit that rebinds a figure to a blob by
#: positional index", made unrepresentable rather than merely avoided). `1000` is this budget's
#: own stated limit: a page carrying its thousandth figure would collide with the next page's
#: own ordinal zero. No document this pack has ever read has come close, and a producer that
#: someday does gets a collision to investigate rather than a silent misattribution — the
#: identical trade-off `weft_blob.keys`'s digest truncation states for its own budget.
_FIGURE_ORDINAL_PAGE_STRIDE = 1000


def _figure_ordinal(*, page: int, index_on_page: int) -> int:
    """The stable composite ordinal a figure's `Node.derive` and `weft_blob.keys.blob_key` both
    key off — see `_FIGURE_ORDINAL_PAGE_STRIDE`'s own comment for why it is derived from where
    the figure sits rather than from a running count over the document.
    """
    if index_on_page >= _FIGURE_ORDINAL_PAGE_STRIDE:
        raise ValueError(
            f"page {page} reports figure index {index_on_page}, at or past this pack's "
            f"{_FIGURE_ORDINAL_PAGE_STRIDE}-figure-per-page ordinal budget — it would collide "
            f"with the following page's own figures"
        )
    return page * _FIGURE_ORDINAL_PAGE_STRIDE + index_on_page


class PendingFigure(BaseModel):
    """One figure with a caption, waiting on the `BlobStore.put` call `extract_documents` cannot
    make — see the module docstring for why the split exists. `PdfLayoutExtractor.run` is the
    caller that finishes it: `await`s the blob write, then builds the `Node` this model is not.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: The page node this figure is a child of, once `run` calls `root.derive(...)`.
    root: Node
    #: `doc.source_id`, carried alongside `root` rather than read back off it: `root.lineage.
    #: sources` is a `frozenset` with no ordering guarantee, and this way `run` never has to
    #: assume it holds exactly one element.
    source_id: SourceId
    #: 1-based — becomes this figure's `weft_extract.payload.PageSpan.page`.
    page: int = Field(ge=1)
    #: The stable composite from `_figure_ordinal` — feeds both `Node.derive(ordinal=...)` and
    #: `weft_blob.keys.blob_key(ordinal=...)`, so the two can never disagree about this figure's
    #: address. **Not** `weft_extract.payload.PageSpan.ordinal`, which is `page_ordinal` below.
    ordinal: int = Field(ge=0)
    #: This figure's 0-based reading-order position within its own page alone — becomes
    #: `weft_extract.payload.PageSpan.ordinal`, a different number from `ordinal` above (the
    #: class docstring on `PageSpan` itself carries this same warning). Carried as its own field
    #: rather than derived back out of `ordinal` by `run`, so no caller has to know
    #: `_figure_ordinal`'s stride to recover it.
    page_ordinal: int = Field(ge=0)
    caption: str
    png: bytes


class ExtractionResult(BaseModel):
    """`extract_documents`'s answer when a backend supplies `read_figures` — the nodes it built
    outright, and the figures it found but could not finish. See the module docstring for why a
    figure's own `Node` is not among `nodes`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    nodes: tuple[Node, ...]
    figures: tuple[PendingFigure, ...]


def _pending_figure(
    root: Node, source_id: SourceId, figure: ExtractedFigure
) -> PendingFigure | None:
    """`figure` as work still owed by `PdfLayoutExtractor.run`, or `None` if it has no caption.

    `None` is the caption → OCR text → nothing ladder's last rung (module docstring): no
    `PendingFigure`, so `run` never asks a `BlobStore` to write these pixels and never builds a
    node for them at all.
    """
    if figure.caption is None:
        return None
    return PendingFigure(
        root=root,
        source_id=source_id,
        page=figure.page,
        ordinal=_figure_ordinal(page=figure.page, index_on_page=figure.index_on_page),
        page_ordinal=figure.index_on_page,
        caption=figure.caption,
        png=figure.png,
    )


@overload
def extract_documents(
    payload: Sequence[SourceDoc],
    *,
    backend: str,
    read_pages: PageReader,
    unreadable: tuple[type[Exception], ...],
    read_tables: TableReader | None = None,
) -> Outcome[Sequence[Node]]: ...


@overload
def extract_documents(
    payload: Sequence[SourceDoc],
    *,
    backend: str,
    read_pages: PageReader,
    unreadable: tuple[type[Exception], ...],
    read_tables: TableReader | None = None,
    read_figures: FigureReader,
) -> Outcome[ExtractionResult]: ...


def extract_documents(
    payload: Sequence[SourceDoc],
    *,
    backend: str,
    read_pages: PageReader,
    unreadable: tuple[type[Exception], ...],
    read_tables: TableReader | None = None,
    read_figures: FigureReader | None = None,
) -> Outcome[Sequence[Node]] | Outcome[ExtractionResult]:
    """One node per page with text, per source document, under the rules in the module docstring.

    **Two return shapes, chosen by whether `read_figures` was passed, and that is a fact about
    one specific caller rather than every caller** — the identical footing `read_tables`
    already stands on. `pdf_text.py` never passes `read_figures` (`pypdf` cannot crop a page) and
    keeps getting back `Outcome[Sequence[Node]]` unchanged; `pdf_layout.py` passes one and gets
    back `Outcome[ExtractionResult]`, carrying the figures `PdfLayoutExtractor.run` still owes a
    `BlobStore.put` and a `Node.derive` call — see the module docstring for why this function
    cannot make either call itself. The two `@overload` declarations above are what let
    `pdf_text.py`'s own `run` keep returning `Outcome[Sequence[Node]]` straight through, with
    nothing in that file changed.

    `unreadable` is the calling backend's own library exception classes, passed
    rather than caught broadly: a parsing library's failure to read a file is a
    documented, expected outcome that belongs in `Failed` so the fallback chain
    can try the next backend, while anything else escaping a backend is a bug
    that must reach the registration seam with its traceback intact.

    `read_tables` defaults to `None`, and that default is a fact about one specific
    caller rather than every caller: `pdf_text.py` — the only other backend in this
    pack — wraps `pypdf`, which has no table extraction of any kind, so it passes
    nothing rather than a reader shaped to always answer empty. `pdf_layout.py`
    supplies one because `pdfplumber` can actually find a table; the backend that
    cannot see one must not guess at one.
    """
    if not payload:
        return NothingToProduce(reason="no source documents to extract")

    nodes: list[Node] = []
    figures: list[PendingFigure] = []
    empty: list[str] = []
    for doc in payload:
        outcome = _extract_one(
            doc,
            backend=backend,
            read_pages=read_pages,
            unreadable=unreadable,
            read_tables=read_tables,
            read_figures=read_figures,
        )
        if isinstance(outcome, Failed):
            return outcome
        doc_nodes, doc_figures, empty_reason = outcome
        if empty_reason is not None:
            empty.append(empty_reason)
            continue
        nodes.extend(doc_nodes)
        figures.extend(doc_figures)

    if not nodes:
        return NothingToProduce(reason="; ".join(empty))
    if read_figures is None:
        return Produced(value=nodes)
    return Produced(value=ExtractionResult(nodes=tuple(nodes), figures=tuple(figures)))


def _extract_one(
    doc: SourceDoc,
    *,
    backend: str,
    read_pages: PageReader,
    unreadable: tuple[type[Exception], ...],
    read_tables: TableReader | None,
    read_figures: FigureReader | None,
) -> Failed | tuple[tuple[Node, ...], tuple[PendingFigure, ...], str | None]:
    """One document's worth of `extract_documents`'s own loop body, split out only to keep that
    function's own branching under this tree's complexity budget — the two backends never call
    this directly. `Failed` aborts the whole batch, per the module docstring; otherwise this
    returns the nodes and figures this one document contributed, and a reason string in place of
    both when the document held no text at all.
    """
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

    # Unchanged by task 9.7's figure path — `_first_unseen_page`'s own docstring records why it
    # needed no narrowing, and the two that were nearly written instead.
    found = tuple(read_figures(doc.content)) if read_figures is not None else ()
    unseen = _first_unseen_page(pages)
    if unseen is not None:
        return Failed(
            reason=(
                f"'{doc.uri}' page {unseen.number}: no text layer, "
                f"{unseen.images} image(s) present — {backend} cannot tell a scanned "
                f"page from a blank one, so another backend should try this document."
            )
        )

    page_nodes = _page_nodes(doc, pages, backend=backend)
    if not page_nodes:
        return (), (), f"'{doc.uri}': {len(pages)} page(s), and no text on any of them"
    nodes: list[Node] = list(page_nodes.values())

    if read_tables is not None:
        for ordinal, table in enumerate(read_tables(doc.content)):
            root = _root_for_page(page_nodes, table.page, backend=backend, doc=doc, kind="table")
            table_node = _table_node(root, table, ordinal=ordinal)
            if table_node is not None:
                nodes.append(table_node)

    figures: list[PendingFigure] = []
    for figure in found:
        root = _root_for_page(page_nodes, figure.page, backend=backend, doc=doc, kind="figure")
        pending = _pending_figure(root, doc.source_id, figure)
        if pending is not None:
            figures.append(pending)

    return tuple(nodes), tuple(figures), None


def _page_nodes(doc: SourceDoc, pages: Sequence[PageText], *, backend: str) -> dict[int, Node]:
    """One `Node` per page in `pages` whose text is not blank, keyed by page number.

    Split out of `_extract_one` to keep that function's own branching under this tree's
    complexity budget. `ordinal=page.number` is load-bearing, not cosmetic: `Node.synthetic`
    digests `(media_type, content, parents, ordinal)`, so two pages holding byte-identical
    text would otherwise collide onto one node carrying two contradictory page facts —
    `test_two_pages_holding_the_same_text_are_two_nodes_not_one` is that assertion. A blank
    page contributes no entry: it has already passed the empty-page-with-images check above,
    so a blank page here really is empty, not merely unseen.
    """
    page_nodes: dict[int, Node] = {}
    for page in pages:
        if not page.text.strip():
            continue
        page_nodes[page.number] = (
            Node.synthetic(
                content=page.text,
                media_type=MediaType.TEXT,
                reason=f"extracted from '{doc.uri}' page {page.number} by {backend}",
                sources=frozenset({doc.source_id}),
                ordinal=page.number,
            )
            .with_ext(PdfPages(backend=backend))
            .with_ext(PageSpan(page=page.number, ordinal=0))
        )
    return page_nodes


def _root_for_page(
    page_nodes: Mapping[int, Node], page: int, *, backend: str, doc: SourceDoc, kind: str
) -> Node:
    """The page node a table or figure on `page` should become a child of.

    Raises rather than picking a neighbour when `backend` names a page this document has no
    text node for: per the module docstring, that is a bug inside one backend, not a read
    failure, so it reaches the registration seam with its traceback intact instead of
    becoming a `Failed` that would send a working document to another backend.
    """
    root = page_nodes.get(page)
    if root is None:
        raise ValueError(
            f"{backend} reported a {kind} on page {page} of '{doc.uri}', but reported no "
            "text on that page — a bug in this backend, not a read failure"
        )
    return root


def _table_node(root: Node, table: ExtractedTable, *, ordinal: int) -> Node | None:
    """`table` as a child of `root`, or `None` if its grid could not be built.

    Skipped rather than repaired or raised, per the module docstring: a ragged grid, one
    with no headers at all, or one whose header row is entirely blank is not a table this
    pack can index, and one unreadable table in a document is not a reason to fail the
    document. Raggedness is `TableGrid`'s own refusal (see `weft_extract.payload`'s
    module docstring) — pydantic wraps it as `ValidationError`, caught here rather than
    left to propagate past this one table.
    """
    if not table.headers or not any(header.strip() for header in table.headers):
        return None
    try:
        grid = TableGrid(headers=table.headers, rows=table.rows, page=table.page, bbox=table.bbox)
    except ValidationError:
        return None
    return root.derive(
        content=index_text(grid), media_type=MediaType.TABLE, ordinal=ordinal
    ).with_ext(grid)


def _first_unseen_page(pages: Sequence[PageText]) -> PageText | None:
    """The first page this backend could not see anything on, or `None` if there is none.

    "Unseen" rather than "scanned" on purpose: this pack cannot tell a scan from
    a photograph beside a caption that failed to extract, and naming it for the
    guess would make the reason line claim more than the evidence supports.

    **Task 9.7 examined this rule and left it alone, which is the finding.** Figure extraction
    looked like it needed a narrowing here — surely a page whose content is a picture is not an
    unread page — and two were written before the question was asked properly. It needs none. A
    figure only becomes a node if it has a **caption**, and a caption is text *on that page*, so
    `page.text.strip()` is non-empty and the page was never a candidate. A page with an image and
    genuinely no text recovered nothing, and is exactly as ambiguous as it was before: it may be a
    scan, and another backend should try it.

    Both near-miss narrowings are worth naming, because both looked reasonable. Skipping the check
    whenever a figure reader is configured *and the document holds any text* would pass a
    fifty-page scan whose first page carries a running header. Treating any page a figure reader
    touched as "seen" would pass a scanned page whose image the reader found and could not
    caption — the same page, reported as read. `docs/internal/lessons.md` `L9.62`.
    """
    return next(
        (page for page in pages if not page.text.strip() and page.images > 0),
        None,
    )
