"""`pdf-layout` — the geometry backend, over `pdfplumber`.

The second of the two backends this pack ships, and it exists because it is
**wrong in a different way**, not because it is better. On the same justified
two-column paper `pdf_text`'s docstring measures, `pdfplumber` at its own
default tolerances fuses words together — `betweengenes.The ideaofminimumredundancyisto`
— where `pypdf` splits them apart. A fallback chain over two backends that fail
identically buys nothing; a chain over these two is a genuine choice, and a
cleaning stage that repairs fused words (`weft-clean`) turns this backend's
damage into something recoverable.

`x_tolerance` and `y_tolerance` are the knobs that move it, and they are
configuration for the same reason `pdf_text.ExtractionMode` is: measured on
that document, dropping `x_tolerance` from `pdfplumber`'s default 3.0 to 1.5
takes words longer than eighteen characters from 217 to 35 and raises the word
count from 7 402 to 9 087. The defaults here are `pdfplumber`'s own rather than
that better value on purpose — a wrapper that quietly disagrees with the library
it wraps makes the library's own documentation wrong for its users, and the
number worth reaching for is stated here instead.

**Parsing runs off the event loop, and one thing is weakened by that.**
`pdfplumber` holds the loop for 1.08 s on the first corpus paper — pure
computation, so fitness function 7(b) cannot see it, while `01` → *Colour*
settles the rule regardless: "a CPU-bound stage is still `async def` and
offloads its own blocking work." `run` therefore awaits `asyncio.to_thread`.
The weakening, stated here rather than left to be discovered: a thread cannot
be interrupted, so `CancelledError` delivered mid-batch takes effect when the
current document finishes rather than immediately. It is never swallowed —
`to_thread` re-raises it at the await — but a cancelled run does finish the
document it was on.

**The one figure-producing backend in this pack, and the one stage anywhere that reaches a
service `weft-cli` does not name — ledger `9.7`.** `extract_documents` (`document.py`) runs
entirely inside the single `to_thread` call above, synchronously, so it can find a figure's
bounding box and render its crop, but it cannot `await BlobStore.put` — `BlobStore` is an async
contract and a thread has no event loop to hand the coroutine to. So it hands back each
captioned figure as a `document.PendingFigure` instead of a finished `Node`, and *this* method's
`run` — back on the event loop, past the `await asyncio.to_thread(...)` — is where the blob
actually gets written and the `Node` actually gets built. Two libraries do the finding:
`pdfplumber` reports a bounding box `pypdfium2` has no equivalent for, and its own word
extraction (already loaded for `_read_pages`) is reused to find a caption; `pypdfium2` renders
the crop pypdfium2's own page object at the identical `scale=1` — see `_read_figures` for the
geometry argument that makes a `pdfplumber` box usable as a `pypdfium2` crop box directly.
"""

import asyncio
from collections.abc import Sequence
from enum import StrEnum
from io import BytesIO
from typing import Any, ClassVar

import pdfplumber
import pypdfium2
from pdfplumber.page import Page
from pdfplumber.utils.exceptions import PdfminerException
from pydantic import BaseModel, ConfigDict, Field

from weft_blob.contract import BlobStore
from weft_blob.keys import blob_key
from weft_blob.payload import BlobRef
from weft_extract.contract import SourceDoc
from weft_extract.payload import BoundingBox, PageSpan, TableGrid
from weft_kernel.context import Context
from weft_kernel.payload import ExtModel, MediaType, Node, Outcome, Produced
from weft_pdf.document import (
    EXTENSIONS,
    ExtractedFigure,
    ExtractedTable,
    PageText,
    PdfPages,
    extract_documents,
)

#: The media type stamped on every figure's `BlobRef` and passed to `BlobStore.put` — always
#: PNG, per ledger `9.7`; one resize invariant belongs to `9.9`, not this module.
_FIGURE_MEDIA_TYPE = "image/png"

#: How far below a figure's own bounding box `_caption_below` looks for a caption line, in
#: points. Verified against this pack's own fixture (`tests/unit/weft_pdf/minimal_pdf.py`,
#: `figure_with_caption`): a 9pt caption drawn immediately under the image reads back with its
#: baseline roughly 7pt below the image's bottom edge, and this budget leaves room for a larger
#: font or a blank line above the caption without reaching far enough to pull in a second
#: figure's own caption on a densely packed page.
_CAPTION_BAND_HEIGHT = 40.0

#: The name this backend is registered and selected under — see `weft_pdf.register`.
NAME = "pdf-layout"


class TextDirection(StrEnum):
    """A reading direction `pdfplumber` groups characters and lines along.

    An enum for the project's enum-over-string-constant reason and one
    specific to this parameter: `pdfplumber` accepts exactly these four and
    raises for anything else, so a typo in a pipeline document fails at
    validation naming the valid values rather than inside a worker thread
    halfway through a corpus. `ltr` and `ttb` are the library's own defaults;
    `rtl` is what an Arabic or Hebrew corpus needs, and without it that corpus
    is unreadable through this backend at any setting.
    """

    LEFT_TO_RIGHT = "ltr"
    RIGHT_TO_LEFT = "rtl"
    TOP_TO_BOTTOM = "ttb"
    BOTTOM_TO_TOP = "btt"


class PdfLayoutExtractorConfig(BaseModel):
    """`PdfLayoutExtractor`'s `with:` configuration — see the module docstring for the numbers.

    **Every default here is `pdfplumber`'s own**, for the reason the module
    docstring gives for the tolerances, and it applies to all of them.

    `.phase2-design.md` A.1 makes the coverage of this model a review question
    for task 2.27: "a parser whose library supports layout modes, page ranges
    or a text-extraction strategy, and whose config model does not, has
    satisfied the letter of requirement 6 and failed its second clause."
    `layout` is that example literally — it is `pdfplumber`'s analogue of the
    `ExtractionMode` `pdf-text` ships, and without it the two backends were
    asymmetric on the one axis an operator is most likely to reach for.

    Three things `pdfplumber` offers are **deliberately absent**, so the
    omissions are decisions rather than oversights:

    - **`laparams`** is a raw `pdfminer` parameter dictionary. Accepting it
      would put an untyped `dict[str, Any]` in a configuration model, which is
      the shape this project refuses everywhere else; the parameters worth
      reaching for are named individually above.
    - **`repair` / `gs_path`** shell out to Ghostscript. A stage that starts a
      subprocess is blocking work the seam's detector fails a run for, and an
      external binary is a dependency this pack's `pyproject.toml` cannot
      declare.
    - **page selection**, still absent, but no longer for the reason once recorded here.
      Before G17, `PdfPages.starts` was indexed positionally, so a subset would have made
      `page_at` answer *page 3* for what the reader would find on page 41 — the very
      corruption that argument warned against. G17 (2026-09-12) made the page a scalar fact
      on each page's own node (`weft_extract.payload.PageSpan`), which is exactly what that
      argument said page selection would need; a subset knob would not misattribute a
      citation today. It is still missing because nobody has asked for it, not because
      adding it is unsafe.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    x_tolerance: float = Field(default=3.0, gt=0.0)
    y_tolerance: float = Field(default=3.0, gt=0.0)
    #: `None` is `pdfplumber`'s own default: the tolerances above are absolute unless a
    #: ratio is given, in which case they scale with font size.
    x_tolerance_ratio: float | None = Field(default=None, gt=0.0)
    #: An encrypted corpus has no other route: without this the document is only ever
    #: `Failed`, with no configuration that could have made it succeed.
    password: str | None = None
    #: `pdfplumber`'s geometry-preserving mode — the direct analogue of
    #: `pdf_text.ExtractionMode.LAYOUT`, and the knob A.1 names by example.
    layout: bool = False
    keep_blank_chars: bool = False
    use_text_flow: bool = False
    #: Whether `fi`, `ffl` and their relatives are returned as the letters they stand for.
    #: Directly relevant to the single-character-word measurement the module docstring
    #: reports, which was taken on an academic PDF full of them.
    expand_ligatures: bool = True
    split_at_punctuation: bool = False
    #: How characters run within a line, and how lines run down a page. `pdfplumber`'s own
    #: defaults are the Latin ones; a right-to-left corpus is unreadable without them.
    char_dir: TextDirection = TextDirection.LEFT_TO_RIGHT
    line_dir: TextDirection = TextDirection.TOP_TO_BOTTOM


class PdfLayoutExtractor:
    """Groups each page's characters into words with `pdfplumber`, one `Node` per page with text.

    Also this pack's one figure producer (ledger `9.7`) — see the module docstring for why
    `run` does more than await `extract_documents` once `read_figures` is in play.
    """

    extensions: tuple[str, ...] = EXTENSIONS
    config_model: type[PdfLayoutExtractorConfig] = PdfLayoutExtractorConfig
    #: Every fact this backend attaches, declared so a later stage's `requires` can bind to it —
    #: `02` §3 → *Ordering constraints*. Not one entry per node kind: a document yields a root
    #: carrying `PdfPages`, table nodes carrying `TableGrid`, and figure nodes carrying `BlobRef`
    #: and `PageSpan`, and `provides` is a claim about the *stage*, so all four belong here.
    #:
    #: **Declared at ledger task `9.11`, and it is a gap 9.6 and 9.7 both left.** Those tasks
    #: attached these facts and declared none of them, which cost nothing while no stage asked:
    #: `weft_kernel.resolution` checks `requires` against earlier `provides` and had nothing to
    #: check. `describe-figure` is the first plugin in the tree to declare `requires`, and
    #: fitness function 11 refused `index-pdf-described.yaml` the moment it shipped —
    #: *"requires 'BlobRef' but no earlier stage provides it. Provided so far: (none)."* A
    #: producing side with no consuming side is invisible until the consumer arrives, which is
    #: `L5.15`'s shape; all four are declared rather than only the one that failed, because a
    #: repair cut to the failing instance narrows to it (`L6.13`).
    provides: ClassVar[tuple[type[ExtModel], ...]] = (PdfPages, TableGrid, BlobRef, PageSpan)

    def __init__(self, config: PdfLayoutExtractorConfig | None = None) -> None:
        self._config = config if config is not None else PdfLayoutExtractorConfig()

    async def run(self, payload: Sequence[SourceDoc], ctx: Context) -> Outcome[Sequence[Node]]:
        # `to_thread` rather than a direct call — see the module docstring, both for the
        # rule (`01` → *Colour*) and for what it weakens about cancellation.
        outcome = await asyncio.to_thread(
            extract_documents,
            payload,
            backend=NAME,
            read_pages=self._read_pages,
            unreadable=(PdfminerException,),
            read_tables=self._read_tables,
            read_figures=self._read_figures,
        )
        if not isinstance(outcome, Produced):
            return outcome

        result = outcome.value
        if not result.figures:
            # No captioned figure anywhere in this batch: a text-only project that added
            # `pdf-layout` must not suddenly need `[services] blob` configured — see the module
            # docstring and the class docstring on `PendingFigure` for why this check runs
            # after the figures are already known rather than before extraction starts.
            return Produced(value=result.nodes)

        blob_store = ctx.require(BlobStore)
        nodes = list(result.nodes)
        for figure in result.figures:
            key = blob_key(
                tenant_id=ctx.tenant_id,
                source_id=figure.source_id,
                ordinal=figure.ordinal,
                extension="png",
            )
            uri = await blob_store.put(key, figure.png, _FIGURE_MEDIA_TYPE)
            node = (
                figure.root.derive(
                    content=figure.caption, media_type=MediaType.IMAGE, ordinal=figure.ordinal
                )
                .with_ext(BlobRef(uri=uri, media_type=_FIGURE_MEDIA_TYPE))
                .with_ext(PageSpan(page=figure.page, ordinal=figure.page_ordinal))
            )
            nodes.append(node)
        return Produced(value=nodes)

    def _read_pages(self, content: bytes) -> Sequence[PageText]:
        """Every page of `content`, in order, as `pdfplumber` groups its characters.

        `BytesIO` rather than a path, for the same reason `pdf_text` gives: an
        `Extractor` is handed bytes and never touches the filesystem, which is
        what keeps this call clear of the blocking-call detector at the seam.

        The tuple is built *inside* the `with`, so every page is read before
        `pdfplumber` closes the document underneath it — a generator returned
        from here would be evaluated after the close and raise instead.
        """
        config = self._config
        with pdfplumber.open(BytesIO(content), password=config.password) as document:
            return tuple(
                PageText(
                    number=number,
                    text=page.extract_text(
                        x_tolerance=config.x_tolerance,
                        y_tolerance=config.y_tolerance,
                        x_tolerance_ratio=config.x_tolerance_ratio,
                        layout=config.layout,
                        keep_blank_chars=config.keep_blank_chars,
                        use_text_flow=config.use_text_flow,
                        expand_ligatures=config.expand_ligatures,
                        split_at_punctuation=config.split_at_punctuation,
                        char_dir=config.char_dir.value,
                        line_dir=config.line_dir.value,
                    ),
                    images=len(page.images),
                )
                for number, page in enumerate(document.pages, start=1)
            )

    def _read_tables(self, content: bytes) -> Sequence[ExtractedTable]:
        """Every table `pdfplumber` finds, at its own default table-detection settings.

        `find_tables` rather than a separate call to `extract_tables`: in `pdfplumber`'s
        own source, `extract_tables` is exactly `find_tables` followed by `.extract()`
        per table, so calling `find_tables` once gives the cell matrix and the bounding
        box `9.6` needs for `bbox` paired by construction, rather than by two passes
        that could disagree in order.

        The first row of each table is its header row — a cell `pdfplumber` could not
        read comes back `None`, rendered here as `""` rather than the text `"None"`.
        A table `pdfplumber` found but could not extract any cells from is skipped;
        a table whose header row is blank, or whose grid is ragged, is `document.py`'s
        `_table_node` to skip, not this method's.
        """
        config = self._config
        tables: list[ExtractedTable] = []
        with pdfplumber.open(BytesIO(content), password=config.password) as document:
            for number, page in enumerate(document.pages, start=1):
                for table in page.find_tables():
                    matrix = table.extract()
                    if not matrix:
                        continue
                    headers = tuple(cell or "" for cell in matrix[0])
                    rows = tuple(tuple(cell or "" for cell in row) for row in matrix[1:])
                    x0, top, x1, bottom = table.bbox
                    tables.append(
                        ExtractedTable(
                            page=number,
                            headers=headers,
                            rows=rows,
                            bbox=BoundingBox(x0=x0, y0=top, x1=x1, y1=bottom),
                        )
                    )
        return tuple(tables)

    def _read_figures(self, content: bytes) -> Sequence[ExtractedFigure]:
        """Every image `pdfplumber` finds, cropped to PNG by `pypdfium2`, paired with a caption.

        Two libraries opened on the same `content`: `pdfplumber` for the bounding box and the
        caption text, `pypdfium2` for the render neither `pdfplumber` nor `pypdf` can do — the
        module docstring's argument for why this backend, not `pdf_text.py`, is the one that
        contributes `read_figures` at all. Both are asked to render at `scale=1`, the same scale
        this pack's own fixture module verified a `pdfplumber` bounding box against directly
        (`tests/unit/weft_pdf/minimal_pdf.py`'s `figure_with_caption` docstring): at that scale a
        `pdfplumber` box in points is a `pypdfium2`/`PIL` crop box in pixels with no conversion,
        because both libraries put the coordinate origin at the page's own top-left corner.

        Images on a page are sorted by `top` (then `x0`) before `index_on_page` is assigned, so
        that number is this page's own reading order rather than whatever order `pdfplumber`
        happened to return `page.images` in — `ExtractedFigure`'s own docstring is why that
        number must be stable regardless of which images on the page turn out to have captions.
        """
        config = self._config
        figures: list[ExtractedFigure] = []
        with (
            pdfplumber.open(BytesIO(content), password=config.password) as plumber_document,
            pypdfium2.PdfDocument(content, password=config.password) as pdfium_document,
        ):
            for number, page in enumerate(plumber_document.pages, start=1):
                images = sorted(page.images, key=lambda image: (image["top"], image["x0"]))
                if not images:
                    continue
                rendered = pdfium_document[number - 1].render(scale=1).to_pil()
                for index, image in enumerate(images):
                    box = (
                        round(image["x0"]),
                        round(image["top"]),
                        round(image["x1"]),
                        round(image["bottom"]),
                    )
                    if box[2] <= box[0] or box[3] <= box[1]:
                        # A box with no area holds no pixels, so there is nothing here to lose
                        # by skipping it — and cropping it hands PIL an empty image, whose
                        # `save` raises `ValueError: cannot write empty image` and takes the
                        # whole run with it. That is carried repair `R11.1`, found by running
                        # `weft index --pipeline index-pdf` over this project's own corpus:
                        # `pdfplumber` reports 67 such boxes across one real paper's 21 pages,
                        # two per page at `x0 == x1`, which are rules or invisible marks rather
                        # than pictures. Skipped rather than raised, on the policy
                        # `weft_pdf.document.ExtractedTable`'s own docstring already settles for
                        # the sibling path: a backend's unusable reading "must skip the one
                        # table rather than fail the document". Silent for the same reason
                        # `_table_node`'s refusal is silent — nothing was lost to report.
                        continue
                    buffer = BytesIO()
                    rendered.crop(box).save(buffer, format="PNG")
                    figures.append(
                        ExtractedFigure(
                            page=number,
                            index_on_page=index,
                            caption=_caption_below(page, image),
                            png=buffer.getvalue(),
                        )
                    )
        return tuple(figures)


def _caption_below(page: Page, image: dict[str, Any]) -> str | None:
    """The caption line beneath `image` on `page`, or `None` if the band under it reads blank.

    Spans the page's full width rather than just the image's own: `"Figure 1. Revenue by
    region."` already outruns the 100pt-wide image in this pack's own fixture
    (`tests/unit/weft_pdf/minimal_pdf.py`), and clipping to the image's own x-range would
    truncate a real caption's text — the opposite of what `document.py`'s caption ladder needs,
    which is to tell a real absence from one this method merely cut off.
    """
    bottom = float(image["bottom"])
    band_bottom = min(bottom + _CAPTION_BAND_HEIGHT, page.height)
    if band_bottom <= bottom:
        return None
    text = page.crop((0, bottom, page.width, band_bottom)).extract_text().strip()
    return text or None
