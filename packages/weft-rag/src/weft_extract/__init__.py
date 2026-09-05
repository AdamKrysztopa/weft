"""First-party extraction pack.

Publishes the `Extractor` contract, in `contract.py` — the Protocol, its
version and the `SourceDoc` boundary type it needs, per the canonical-file
convention `docs/07-extension-cost.md` §1 sets for a brand new contract. The
kernel defines no capability contract at all (G1), so this contract is owned
here and this pack registers through the same public entry point a third
party would use — fitness function 2. `register()` and the built-in text
extractor (`text.py`) arrive at `docs/06-phase-0-build.md` step 8.

**A second contract lives here from task 2.27: `Renderer`**, with `Rendition`
in `payload.py` and the `markdown`/`plain` registrations in `render.py`.
`.phase2-design.md` A.2 places it in this distribution rather than a new one
for a dependency reason — rendering nodes to text needs nothing beyond what
this pack already has, and a fourth distribution to hold two format writers
would be taxonomy rather than a forcing constraint.
"""

from pydantic import BaseModel, ConfigDict

from weft_extract.accept import claimed_extensions, present_suffixes
from weft_extract.contract import (
    EXTRACTOR_CONTRACT_VERSION,
    RENDERER_CONTRACT_VERSION,
    Extractor,
    Renderer,
    SourceDoc,
)
from weft_extract.payload import DroppedContent, DroppedKind, Rendition
from weft_extract.render import (
    MARKDOWN_NAME,
    PLAIN_NAME,
    MarkdownRenderer,
    MarkdownRendererConfig,
    PlainRenderer,
    PlainRendererConfig,
)
from weft_extract.text import EXTENSIONS, TextExtractor, TextExtractorConfig, discover_source_docs
from weft_kernel.discovery import PackRegistrar


class Settings(BaseModel):
    """`weft-extract` takes no pack settings — an empty model is still the required shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register the text extractor, and the two renderers `.phase2-design.md` A.2 assigns here.

    Three plugins under two contracts, all through the one public seam a third
    party uses — a `docx` renderer registers exactly like `markdown` does, from
    its own distribution, and nothing here changes.
    """
    del settings
    registrar.add(Extractor, "text", TextExtractor)
    registrar.add(Renderer, PLAIN_NAME, PlainRenderer)
    registrar.add(Renderer, MARKDOWN_NAME, MarkdownRenderer)


__all__ = [
    "EXTENSIONS",
    "EXTRACTOR_CONTRACT_VERSION",
    "MARKDOWN_NAME",
    "PLAIN_NAME",
    "RENDERER_CONTRACT_VERSION",
    "DroppedContent",
    "DroppedKind",
    "Extractor",
    "MarkdownRenderer",
    "MarkdownRendererConfig",
    "PlainRenderer",
    "PlainRendererConfig",
    "Renderer",
    "Rendition",
    "Settings",
    "SourceDoc",
    "TextExtractor",
    "TextExtractorConfig",
    "claimed_extensions",
    "discover_source_docs",
    "present_suffixes",
    "register",
]
