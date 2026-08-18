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
"""

import asyncio
from collections.abc import Sequence
from enum import StrEnum
from io import BytesIO

import pdfplumber
from pdfplumber.utils.exceptions import PdfminerException
from pydantic import BaseModel, ConfigDict, Field

from weft_extract.contract import SourceDoc
from weft_kernel.context import Context
from weft_kernel.payload import Node, Outcome
from weft_pdf.document import EXTENSIONS, PageText, extract_documents

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
    - **page selection.** `PdfPages.starts` is indexed positionally, so a
      subset would make `page_at` answer *page 3* for what the reader will find
      on page 41. That needs the page number carried explicitly, which is
      ledger 2.9's — a knob that silently corrupts a citation is worse than one
      that is missing.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    x_tolerance: float = Field(default=3.0, gt=0.0)
    y_tolerance: float = Field(default=3.0, gt=0.0)
    #: `None` is `pdfplumber`'s own default: the tolerances above are absolute unless a
    #: ratio is given, in which case they scale with font size.
    x_tolerance_ratio: float | None = Field(default=None, gt=0.0)
    page_separator: str = "\n\n"
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
    """Groups each page's characters into words with `pdfplumber`, one root `Node` per document."""

    extensions: tuple[str, ...] = EXTENSIONS
    config_model: type[PdfLayoutExtractorConfig] = PdfLayoutExtractorConfig

    def __init__(self, config: PdfLayoutExtractorConfig | None = None) -> None:
        self._config = config if config is not None else PdfLayoutExtractorConfig()

    async def run(self, payload: Sequence[SourceDoc], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx  # no service or locale this stage needs
        # `to_thread` rather than a direct call — see the module docstring, both for the
        # rule (`01` → *Colour*) and for what it weakens about cancellation.
        return await asyncio.to_thread(
            extract_documents,
            payload,
            backend=NAME,
            read_pages=self._read_pages,
            unreadable=(PdfminerException,),
            separator=self._config.page_separator,
        )

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
