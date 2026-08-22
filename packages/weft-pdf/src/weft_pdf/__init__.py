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

**`PdfPages` reaches rehydration through `register()` itself, with no `weft-store`
dependency here at all — task 5.2g.** A pack that reads bytes off disk still has no
structural reason to also carry a database driver, and it no longer needs one:
`register()` calls `registrar.add_ext_model(PdfPages)`, exactly the shape
`weft_chunk.__init__` uses for `ChunkOffset` — `PackRegistrar` lives in `weft-kernel`,
and `ExtModel` is a kernel-owned payload primitive, not a capability, so buffering a
bare class reference here costs nothing. What actually walks `PackReport.ext_models`
into `weft_store.rehydrate.ext_models` is `weft_store.rehydrate.register_from_reports`,
called once, generically, by whatever already calls `discover()` —
`weft_cli.registry_bootstrap.build_dependencies` today — which is where the two ends of
a real pipeline, the pack that derives the data and the store that must read it back,
already meet, with no per-pack edit owed to `weft-cli` and no dependency on `weft-pdf`
gained by it either: `weft-cli` never imports this module, and does not need to.
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
    """Register both backends for `Extractor`, under the names a pipeline selects them by,
    and `PdfPages` as this pack's own `ExtModel` — task 5.2g, see the module docstring.
    """
    del settings
    registrar.add(Extractor, "pdf-text", PdfTextExtractor)
    registrar.add(Extractor, "pdf-layout", PdfLayoutExtractor)
    registrar.add_ext_model(PdfPages)


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
