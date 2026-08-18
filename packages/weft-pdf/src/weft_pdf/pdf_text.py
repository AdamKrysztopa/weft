"""`pdf-text` — the text-layer backend, over `pypdf`.

The default of the two this pack ships, and the choice is made on **licence,
not on quality**. `pypdf` is BSD-3-Clause; the measurably better `pymupdf` is
AGPL-3.0, and an MIT library must not push AGPL obligations onto everyone who
installs it. That is a fact about distribution, so it belongs in the
`pyproject.toml` this module is packaged by, and the argument is recorded there.

**Its failure mode, measured rather than assumed.** On a justified two-column
paper (Ding & Peng 2005, WSPC), this backend splits letters apart: 19.8 % of
the words it returns are a single character — `p(x)a n dp(y)`, `l o g`.
`pdf-layout` fuses words instead. Neither is a degraded version of the other,
which is exactly why both ship and why composing them (task 2.28) is a real
composition rather than one built to justify a combinator.

`mode` is the one knob that moves that number: `layout` reconstructs the
page's geometry and takes single-character words on the same document from
19.8 % to 7.4 %, at the cost of padding the text with runs of spaces where the
page had columns. Neither setting is right for every corpus, which is precisely
why it is configuration a pipeline document sets and not a decision compiled in
here. `plain` is the default because it is `pypdf`'s own.

**Parsing runs off the event loop, and one thing is weakened by that.**
`pypdf` is pure computation and holds the loop for 0.30 s on the first corpus
paper — invisible to fitness function 7(b), which is categorical and sees only
blocking *calls* (`01` → *Fitness functions* 7). `01` → *Colour* settles the
rule anyway: "a CPU-bound stage is still `async def` and offloads its own
blocking work", so `run` awaits `asyncio.to_thread`. The weakening, stated
where a backend author will read it rather than discovered: a thread cannot be
interrupted, so `CancelledError` delivered while a batch is parsing takes
effect when the current document finishes, not immediately. It is never
swallowed — `to_thread` re-raises it at the await — but a cancelled run does
finish the document it was on.
"""

import asyncio
import re
from collections.abc import Sequence
from enum import IntEnum, StrEnum
from io import BytesIO
from typing import Final

from pydantic import BaseModel, ConfigDict, Field
from pypdf import PageObject, PdfReader
from pypdf.errors import PyPdfError
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject, PdfObject, StreamObject

from weft_extract.contract import SourceDoc
from weft_kernel.context import Context
from weft_kernel.payload import Node, Outcome
from weft_pdf.document import EXTENSIONS, PageText, extract_documents

#: The name this backend is registered and selected under — see `weft_pdf.register`.
NAME = "pdf-text"

#: The `BI` operator that opens an inline image, matched as an operator rather than as
#: two letters — see `_inline_image_count`.
_INLINE_IMAGE: Final[re.Pattern[bytes]] = re.compile(rb"(?:\A|[\s)\]>])BI(?=[\s/])")


class ExtractionMode(StrEnum):
    """How `pypdf` should turn a page's text operators back into a string."""

    PLAIN = "plain"
    LAYOUT = "layout"


class PageOrientation(IntEnum):
    """A text orientation `pypdf` will extract, in degrees of rotation.

    An enum rather than a bare `int` for the project's enum-over-constant
    reason and one specific to this parameter: `pypdf` accepts exactly these
    four and raises for anything else, so a typo in a pipeline document fails
    at validation naming the four valid values instead of inside a worker
    thread halfway through a corpus.
    """

    UPRIGHT = 0
    ROTATED_LEFT = 90
    UPSIDE_DOWN = 180
    ROTATED_RIGHT = 270


#: `pypdf`'s own default set — every orientation extracted. Named so the config
#: model's default is visibly the library's rather than this pack's opinion.
_ALL_ORIENTATIONS: Final[tuple[PageOrientation, ...]] = (
    PageOrientation.UPRIGHT,
    PageOrientation.ROTATED_LEFT,
    PageOrientation.UPSIDE_DOWN,
    PageOrientation.ROTATED_RIGHT,
)


class PdfTextExtractorConfig(BaseModel):
    """`PdfTextExtractor`'s `with:` configuration — every `pypdf` knob an operator would reach for.

    **Every default here is `pypdf`'s own**, for the reason `pdf_layout` states
    for its tolerances: a wrapper that quietly disagrees with the library it
    wraps makes that library's documentation wrong for its users.

    `.phase2-design.md` A.1 makes the coverage of this model a review question
    rather than a matter of taste — "a parser whose library supports layout
    modes, page ranges or a text-extraction strategy, and whose config model
    does not, has satisfied the letter of requirement 6 and failed its second
    clause". Three knobs `pypdf` has are **deliberately absent**, so the
    omissions are decisions rather than oversights:

    - **`visitor_operand_before` / `visitor_operand_after` / `visitor_text`**
      are callables. A pipeline document is data; there is no way to write a
      function in one, and inventing a plugin point for it would be a second
      extension mechanism beside the one this pack already registers through.
    - **`layout_mode_debug_path`** writes files from inside a running stage,
      which is precisely the blocking file IO fitness function 7(b) fails a
      run for.
    - **page selection.** `PdfPages.starts` is indexed positionally, so a
      subset would make `page_at` answer *page 3* for what the reader will
      find on page 41. Reaching for it needs the page number carried
      explicitly, which is ledger 2.9's, and a knob that silently corrupts a
      citation is worse than one that is missing.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: ExtractionMode = ExtractionMode.PLAIN
    page_separator: str = "\n\n"
    #: An encrypted corpus has no other route: without this the document is only ever
    #: `Failed`, with no configuration that could have made it succeed.
    password: str | None = None
    strict: bool = False
    #: Which rotations to extract at all — a paper with sideways tables loses them entirely
    #: if its orientation is not in this set.
    orientations: tuple[PageOrientation, ...] = _ALL_ORIENTATIONS
    space_width: float = Field(default=200.0, gt=0.0)
    #: The four knobs that tune `ExtractionMode.LAYOUT`. `pypdf` ignores them in `plain`
    #: mode, so they are passed unconditionally rather than behind a branch here.
    layout_mode_space_vertically: bool = True
    layout_mode_scale_weight: float = Field(default=1.25, gt=0.0)
    layout_mode_strip_rotated: bool = True
    layout_mode_font_height_weight: float = Field(default=1.0, gt=0.0)


class PdfTextExtractor:
    """Reads each page's text layer with `pypdf` and builds one root `Node` per document."""

    extensions: tuple[str, ...] = EXTENSIONS
    config_model: type[PdfTextExtractorConfig] = PdfTextExtractorConfig

    def __init__(self, config: PdfTextExtractorConfig | None = None) -> None:
        self._config = config if config is not None else PdfTextExtractorConfig()

    async def run(self, payload: Sequence[SourceDoc], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx  # no service or locale this stage needs
        # `to_thread` rather than a direct call — see the module docstring, both for the
        # rule (`01` → *Colour*) and for what it weakens about cancellation.
        return await asyncio.to_thread(
            extract_documents,
            payload,
            backend=NAME,
            read_pages=self._read_pages,
            unreadable=(PyPdfError,),
            separator=self._config.page_separator,
        )

    def _read_pages(self, content: bytes) -> Sequence[PageText]:
        """Every page of `content`, in order, as `pypdf` reads it.

        `BytesIO` rather than a path: an `Extractor` is handed bytes and never
        touches the filesystem, which is what keeps this call free of the file
        IO the registration seam's blocking-call detector fails a run for.

        `ExtractionMode.value` satisfies `pypdf`'s own
        `Literal["plain", "layout"]` parameter without a cast, and that is worth
        knowing rather than rediscovering: the enum is where this pack declares
        the two values, per the project's enum-over-literal rule, and a member
        added here that `pypdf` does not accept fails the type check at this
        line rather than at run time on someone's corpus.
        """
        config = self._config
        reader = PdfReader(BytesIO(content), strict=config.strict, password=config.password)
        return tuple(
            PageText(
                number=number,
                text=page.extract_text(
                    extraction_mode=config.mode.value,
                    orientations=tuple(int(each) for each in config.orientations),
                    space_width=config.space_width,
                    layout_mode_space_vertically=config.layout_mode_space_vertically,
                    layout_mode_scale_weight=config.layout_mode_scale_weight,
                    layout_mode_strip_rotated=config.layout_mode_strip_rotated,
                    layout_mode_font_height_weight=config.layout_mode_font_height_weight,
                ),
                images=_declared_image_count(page),
            )
            for number, page in enumerate(reader.pages, start=1)
        )


def _declared_image_count(page: PageObject) -> int:
    """How much image evidence a page carries: nested XObjects included, inline images too.

    Counted from the declaration rather than by decoding — `pypdf`'s own
    `page.images` reads the pixels, which needs an image library this pack does
    not depend on and does work nothing here uses. The only question this pack
    asks of an image is whether *something* was on a page it found no text on,
    and a declaration answers that as well as a decode would.

    **Both halves are repairs for a reviewer finding, and each was measured
    against `pdfplumber` disagreeing.** The original scan read only the page's
    own `/Resources /XObject` and only `/Subtype /Image`, so a scan drawn
    through a Form XObject — an ordinary structure, the way a producer reuses
    a piece of drawing — counted zero while `pdf-layout` counted one. Two
    backends of one contract disagreeing about *this* is not cosmetic: task
    2.28's chain stops on `NothingToProduce`, so the document would have been
    dropped from the corpus as genuinely empty and never reached OCR. An inline
    image (`BI … ID … EI`) is the same defect by a second route: it is declared
    in no dictionary at all, so no resource walk can find it.

    This is evidence, not an inventory. A form reached twice is walked once
    (the recursion guard), so a page drawing one image through two forms
    answers 1 rather than 2 — the count is only ever compared against zero.

    A page whose resources are missing, indirect or shaped unexpectedly answers
    zero rather than raising: a page with no readable resource dictionary is a
    page with no evidence of an image. Bytes `pypdf` cannot decode at all raise
    its own `PyPdfError` from here, which `extract_documents` turns into
    `Failed` — the loud direction, not a silent zero.
    """
    return _images_in_resources(page.get("/Resources"), seen=set()) + _inline_image_count(page)


def _images_in_resources(resources: object, *, seen: set[object]) -> int:
    """Image XObjects reachable from `resources`, following Form XObjects into their own.

    `seen` holds the forms already walked, keyed by indirect-reference number
    where there is one, so a form that references itself — legal to write,
    however unusual — terminates instead of recursing forever.
    """
    resolved = _resolved(resources)
    if not isinstance(resolved, DictionaryObject):
        return 0
    xobjects = _resolved(resolved.get("/XObject"))
    if not isinstance(xobjects, DictionaryObject):
        return 0

    total = 0
    for value in xobjects.values():
        xobject = _resolved(value)
        if not isinstance(xobject, DictionaryObject):
            continue
        subtype = xobject.get("/Subtype")
        if subtype == "/Image":
            total += 1
        elif subtype == "/Form":
            key = value.idnum if isinstance(value, IndirectObject) else id(xobject)
            if key in seen:
                continue
            seen.add(key)
            total += _images_in_resources(xobject.get("/Resources"), seen=seen)
    return total


def _inline_image_count(page: PageObject) -> int:
    """Inline image operators in the page's content stream.

    The raw stream bytes rather than `page.get_contents()`: that builds a
    `ContentStream`, which tokenises every operator on the page to answer a
    question a scan for one token answers. `BI` is matched as an operator —
    preceded by whitespace or the start of the stream, followed by whitespace
    or the `/` of its first key — so the two letters inside a name or a string
    are not miscounted as one.

    A false positive here is the safe direction and the module's own rule: it
    makes a textless page `Failed`, which sends the document to the next
    backend, rather than declaring empty a page this backend could not see.
    """
    return sum(1 for _ in _INLINE_IMAGE.finditer(_content_bytes(page)))


def _content_bytes(page: PageObject) -> bytes:
    """A page's content stream as bytes, with `/Contents` as an array of streams handled.

    Empty for a page with no `/Contents` at all, which is legal and means the
    page draws nothing — the one case where "no evidence" really is the fact.
    """
    contents = _resolved(page.get("/Contents"))
    if isinstance(contents, ArrayObject):
        return b"\n".join(_stream_data(item) for item in contents)
    return _stream_data(contents)


def _stream_data(value: object) -> bytes:
    """`value`'s decoded stream bytes, or empty if it is not a stream at all."""
    stream = _resolved(value)
    if not isinstance(stream, StreamObject):
        return b""
    return stream.get_data()


def _resolved(value: object) -> object:
    """`value` with a `pypdf` indirect reference followed, if it is one.

    `DictionaryObject.get` is `dict.get`, which — unlike `__getitem__` — hands
    back the reference itself rather than what it points at. Every read of a
    PDF dictionary in this module goes through here, so a document that happens
    to store its resources indirectly is not silently read as having none.
    """
    return value.get_object() if isinstance(value, PdfObject) else value
