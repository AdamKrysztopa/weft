"""First-party PDF extraction pack — two backends, one contract, no new contract.

`weft-extract` publishes `Extractor` and this pack registers under it; nothing
here publishes a contract of its own, because nothing about a PDF needs one. It
is a separate distribution for a dependency reason rather than a taxonomic one:
`weft-extract` has no third-party dependency at all, and putting `pypdf` and
`pdfplumber` there would make every install of the `Extractor` contract pay for
a parser it may never call.

**Two registrations, not one class with a switch.** `pdf-text` and `pdf-layout`
are separate plugins under one contract, selected by a pipeline document's
`use:` field, each carrying its own typed configuration model. That is what
makes changing which library parses a PDF an edit to a pipeline document and
nothing else — no edit to a package, no edit to core, no reinstall — and it is
what leaves room for a third parser nobody here wrote to register through this
same public entry point and be selectable immediately. A backend chosen by a
branch inside one class would satisfy none of that.

**`PdfPages` is not registered for rehydration here.** `document.py`'s own class
docstring records why: `weft_store.rehydrate` needs a namespace registered before it
can read one back, and this distribution deliberately does not depend on `weft-store`
to make that call itself — a pack that reads bytes off disk has no structural reason to
also carry a database driver, and `weft_kernel.registry`'s own `distribution=` argument
on that call would be `weft-pdf` regardless of who makes it. Whoever assembles a real
pipeline with a real store is where the two ends meet; today that is `weft-cli`, for
`weft_chunk.payload.ChunkOffset` — see that module's docstring — and `PdfPages` is not
yet wired the same way, because `weft-cli` does not depend on `weft-pdf` at all (an
`ask`-only deployment need not install a PDF backend it never runs), so there is no
existing import site to add the call to without giving the CLI a dependency the plugin
architecture is built to avoid. Recorded rather than silently left: a PDF-sourced
citation's `page` resolves correctly within one process (`weft_generate.page.page_for`
is proven against the real types in its own tests) but a node carrying `PdfPages` that
is *stored and then read back* — `weft index` followed by a separate `weft ask`
process against a PDF corpus — will fail to rehydrate until this is closed.
"""

from pydantic import BaseModel, ConfigDict

from weft_extract.contract import Extractor
from weft_kernel.discovery import PackRegistrar
from weft_pdf.document import EXTENSIONS, PageReader, PageText, PdfPages, extract_documents
from weft_pdf.pdf_layout import PdfLayoutExtractor, PdfLayoutExtractorConfig, TextDirection
from weft_pdf.pdf_text import (
    ExtractionMode,
    PageOrientation,
    PdfTextExtractor,
    PdfTextExtractorConfig,
)


class Settings(BaseModel):
    """`weft-pdf` takes no pack settings — an empty model is still the required shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register both backends for `Extractor`, under the names a pipeline selects them by."""
    del settings
    registrar.add(Extractor, "pdf-text", PdfTextExtractor)
    registrar.add(Extractor, "pdf-layout", PdfLayoutExtractor)


__all__ = [
    "EXTENSIONS",
    "ExtractionMode",
    "PageOrientation",
    "PageReader",
    "PageText",
    "PdfLayoutExtractor",
    "PdfLayoutExtractorConfig",
    "PdfPages",
    "PdfTextExtractor",
    "PdfTextExtractorConfig",
    "Settings",
    "TextDirection",
    "extract_documents",
    "register",
]
